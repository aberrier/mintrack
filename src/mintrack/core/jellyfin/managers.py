import collections.abc
import contextlib
import datetime as dt
import itertools
import typing
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.catalog.managers import CatalogManager
from mintrack.core.tracking.managers import TrackingManager
from mintrack.db.models import Episode, JellyfinAccount, JellyfinSyncStatus, Media, MediaType, User
from mintrack.integrations.jellyfin.client import (
    Authentication,
    Item,
    JellyfinClient,
    JellyfinError,
    JellyfinUnauthorizedError,
    JellyfinUnreachableError,
    QuickConnect,
    QuickConnectDisabledError,
)
from mintrack.integrations.tmdb.client import ExternalSource, TMDBClient, TMDBNotFoundError
from mintrack.observability.logging import logger
from mintrack.worker.defer import defer_jellyfin_sync

from .matching import FindTmdbId, WatchEvent, match

# Watches committed together with the cursor, so a failure keeps the batches before it.
BATCH_SIZE = 100
# Played items read in one sync, far above a real library's history.
MAX_PLAYED_ITEMS = 200_000


class QuickConnectPendingError(Exception):
    """The Quick Connect request is not approved yet."""


def device_id(user_id: uuid.UUID, server_url: str) -> uuid.UUID:
    """Jellyfin keeps one session per device and user: linking again from the same place replaces the old token."""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"mintrack:{user_id}:{server_url}")


def failure_status(error: Exception) -> JellyfinSyncStatus:
    match error:
        case JellyfinUnreachableError():
            return JellyfinSyncStatus.UNREACHABLE
        case JellyfinUnauthorizedError():
            return JellyfinSyncStatus.UNAUTHORIZED
        case _:
            return JellyfinSyncStatus.FAILED


def tmdb_finder(tmdb: TMDBClient) -> FindTmdbId:
    """TMDB's /find, remembered for one sync: the episodes of a series share its ids."""
    found: dict[tuple[ExternalSource, str, MediaType], int | None] = {}

    async def find(source: ExternalSource, external_id: str, media_type: MediaType) -> int | None:
        key = (source, external_id, media_type)
        if key not in found:
            results = await tmdb.find(external_id, source)
            matches = results["movie_results" if media_type is MediaType.MOVIE else "tv_results"]
            found[key] = matches[0]["id"] if matches else None
        return found[key]

    return find


def _played_at(item: Item) -> dt.datetime:
    return item.user_data.last_played_date or dt.datetime.min.replace(tzinfo=dt.UTC)


class JellyfinManager:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_user(self, user: User) -> collections.abc.Sequence[JellyfinAccount]:
        query = (
            sa.select(JellyfinAccount).where(JellyfinAccount.user_id == user.id).order_by(JellyfinAccount.created_at)
        )
        return (await self.session.scalars(query)).all()

    async def get_for_user(self, user: User, account_id: uuid.UUID) -> JellyfinAccount | None:
        account = await self.session.get(JellyfinAccount, account_id)
        return account if account is not None and account.user_id == user.id else None

    async def link(self, user: User, server_url: str, username: str, password: str) -> JellyfinAccount:
        """Exchange the password for a token; linking the same Jellyfin user again only replaces the token."""
        async with self._new_client(user, server_url) as client:
            authentication = await client.authenticate(username, password)
        return await self._save(user, server_url, authentication)

    async def start_quick_connect(self, user: User, server_url: str) -> QuickConnect:
        """A Quick Connect request of this user's device; raises `QuickConnectDisabledError`."""
        async with self._new_client(user, server_url) as client:
            if not await client.quick_connect_enabled():
                raise QuickConnectDisabledError
            return await client.initiate_quick_connect()

    async def quick_connect_approved(self, user: User, server_url: str, secret: str) -> bool:
        async with self._new_client(user, server_url) as client:
            return (await client.quick_connect(secret)).authenticated

    async def link_quick_connect(self, user: User, server_url: str, secret: str) -> JellyfinAccount:
        """Link the account of the Jellyfin user who approved the request; raises `QuickConnectPendingError`
        until then."""
        async with self._new_client(user, server_url) as client:
            if not (await client.quick_connect(secret)).authenticated:
                raise QuickConnectPendingError
            authentication = await client.authenticate_with_quick_connect(secret)
        return await self._save(user, server_url, authentication)

    @contextlib.asynccontextmanager
    async def _new_client(self, user: User, server_url: str) -> collections.abc.AsyncGenerator[JellyfinClient]:
        """A client without a token, as this user's device on that server (Quick Connect requests belong to it),
        once the server answered as a Jellyfin server."""
        # No database connection stays checked out while Jellyfin answers.
        await self.session.commit()
        async with JellyfinClient(server_url, device_id=device_id(user.id, server_url)) as client:
            await client.check_server()
            yield client

    async def _save(self, user: User, server_url: str, authentication: Authentication) -> JellyfinAccount:
        account = await self.session.scalar(
            sa.select(JellyfinAccount).where(
                JellyfinAccount.user_id == user.id,
                JellyfinAccount.server_id == authentication.server_id,
                JellyfinAccount.jellyfin_user_id == authentication.user.id,
            )
        )
        if account is None:
            account = JellyfinAccount(
                user_id=user.id, server_id=authentication.server_id, jellyfin_user_id=authentication.user.id
            )
            self.session.add(account)
        elif account.server_url != server_url:
            await self._logout(account)
        account.server_url = server_url
        account.username = authentication.user.name
        account.token = authentication.access_token
        await self.session.flush()
        # The first sync, or the one that picks up after a revoked token.
        await self.request_sync(account)
        return account

    async def unlink(self, account: JellyfinAccount) -> None:
        await self._logout(account)
        await self.session.delete(account)
        await self.session.commit()

    async def request_sync(self, account: JellyfinAccount, *, full: bool = False) -> None:
        """Queue a sync of the account, committed with the session's transaction."""
        await defer_jellyfin_sync(self.session, account.id, account.user_id, full=full)
        await self.session.commit()

    async def sync(self, account: JellyfinAccount, tmdb: TMDBClient, now: dt.datetime, *, full: bool = False) -> None:
        """Mark watched what was played on Jellyfin since the last sync, or everything the first time and when `full`.

        A full pass picks up items skipped before, once their metadata or TMDB knows them. An account unlinked
        meanwhile ends the sync quietly.
        """
        account_id = account.id
        since = None if full else account.synced_until
        try:
            imported, skipped = await self._import(account, since, tmdb, now)
        except Exception as error:
            await self.session.rollback()
            logger.warning("jellyfin sync failed", account_id=str(account_id), error=type(error).__name__)
            still_linked = await self._record(
                account, account_id, last_sync_at=now, last_sync_status=failure_status(error)
            )
            if still_linked and not isinstance(error, JellyfinError):
                raise
            return
        values: dict[str, object] = {
            "last_sync_at": now,
            "last_success_at": now,
            "last_sync_status": JellyfinSyncStatus.OK,
            "last_sync_imported": imported,
        }
        # Only a pass over the whole history knows every item still not recognised.
        if since is None:
            values["last_sync_skipped"] = skipped
        await self._record(account, account_id, **values)

    async def _record(self, account: JellyfinAccount, account_id: uuid.UUID, **values: object) -> bool:
        """Write the account's columns, commit and reload it; False when it no longer exists (unlinked meanwhile)."""
        updated = await self.session.scalar(
            sa.update(JellyfinAccount)
            .where(JellyfinAccount.id == account_id)
            .values(values)
            .returning(JellyfinAccount.id)
            .execution_options(synchronize_session=False)
        )
        await self.session.commit()
        if updated is not None:
            await self.session.refresh(account)
        return updated is not None

    async def _import(
        self, account: JellyfinAccount, since: dt.datetime | None, tmdb: TMDBClient, now: dt.datetime
    ) -> tuple[int, int]:
        account_id, user = account.id, await self.session.get_one(User, account.user_id)
        # No database connection stays checked out while Jellyfin answers.
        await self.session.commit()
        async with self._client(account) as client:
            played = await self._played_since(client, account.jellyfin_user_id, since)
            series_ids = {item.series_id for item in played if item.type == "Episode" and item.series_id}
            series = {item.id: item for item in await client.items(account.jellyfin_user_id, series_ids)}
        find = tmdb_finder(tmdb)
        previous_sync, synced_until = account.synced_until, account.synced_until
        imported = skipped = 0
        library = _Library(self.session, tmdb, now)
        tracking = TrackingManager(self.session)
        for batch in itertools.batched(played, BATCH_SIZE, strict=False):
            shows: dict[Media, dict[uuid.UUID, dt.datetime]] = {}
            for item in batch:
                event = await match(item, series, find)
                found = None if event is None else await library.find(event)
                if event is None or found is None:
                    skipped += 1
                    logger.info(
                        "jellyfin item not matched", account_id=str(account_id), item_id=item.id, type=item.type
                    )
                    continue
                media, episode_id = found
                # A play date after now is a server clock ahead of ours.
                watched_at = min(event.watched_at, now)
                if episode_id is None:
                    await tracking.set_movie_watched(user, media, watched=True, at=watched_at, now=now)
                else:
                    shows.setdefault(media, {})[episode_id] = watched_at
                imported += previous_sync is None or event.watched_at > previous_sync
            await tracking.record_watches(user, shows, now=now)
            batch_end = typing.cast("dt.datetime", batch[-1].user_data.last_played_date)
            synced_until = max(synced_until or batch_end, batch_end)
            if not await self._record(account, account_id, synced_until=synced_until):
                raise _UnlinkedError
        return imported, skipped

    @staticmethod
    async def _played_since(client: JellyfinClient, user_id: str, since: dt.datetime | None) -> list[Item]:
        """Items played at or after `since`, oldest first; items without a play date are left out."""
        played: list[Item] = []
        start_index = 0
        while True:
            page = await client.played_items(user_id, start_index)
            start_index += len(page.items)
            if start_index > MAX_PLAYED_ITEMS:
                # A server answering pages without end would otherwise fill the memory.
                msg = f"more than {MAX_PLAYED_ITEMS} played items"
                raise JellyfinError(msg)
            for item in page.items:
                played_at = item.user_data.last_played_date
                if played_at is None:
                    continue
                if since is not None and played_at < since:
                    return sorted(played, key=_played_at)
                played.append(item)
            if not page.items or start_index >= page.total_record_count:
                return sorted(played, key=_played_at)

    def _client(self, account: JellyfinAccount) -> JellyfinClient:
        if account.token is None:
            raise JellyfinUnauthorizedError
        return JellyfinClient(
            account.server_url, device_id=device_id(account.user_id, account.server_url), token=account.token
        )

    async def _logout(self, account: JellyfinAccount) -> None:
        """Revoke the token on the server, when it still answers."""
        if account.token is None:
            return
        # No database connection stays checked out while Jellyfin answers.
        await self.session.commit()
        try:
            async with self._client(account) as client:
                await client.logout()
        except JellyfinError as error:
            logger.info("jellyfin logout failed", account_id=str(account.id), error=type(error).__name__)


class _UnlinkedError(Exception):
    """The account was unlinked during its sync."""


class _Library:
    """The media and episodes plays stand for, each looked up once per sync."""

    def __init__(self, session: AsyncSession, tmdb: TMDBClient, now: dt.datetime) -> None:
        self.session = session
        self.catalog = CatalogManager(session, tmdb)
        self.now = now
        self.media: dict[tuple[MediaType, int], Media | None] = {}
        self.episodes: dict[uuid.UUID, dict[tuple[int, int], uuid.UUID]] = {}

    async def find(self, event: WatchEvent) -> tuple[Media, uuid.UUID | None] | None:
        """The media and, for an episode, its id; None when TMDB or the show does not list it."""
        key = (event.media_type, event.tmdb_id)
        if key not in self.media:
            try:
                self.media[key] = await self.catalog.get_or_fetch(event.media_type, event.tmdb_id, self.now)
            except TMDBNotFoundError:
                self.media[key] = None
        media = self.media[key]
        if media is None or media.media_type is MediaType.MOVIE:
            return None if media is None else (media, None)
        if media.id not in self.episodes:
            rows = await self.session.execute(
                sa.select(Episode.season_number, Episode.episode_number, Episode.id).where(Episode.media_id == media.id)
            )
            self.episodes[media.id] = {(season, number): episode_id for season, number, episode_id in rows}
        episode_id = self.episodes[media.id].get((event.season_number or 0, event.episode_number or 0))
        return None if episode_id is None else (media, episode_id)
