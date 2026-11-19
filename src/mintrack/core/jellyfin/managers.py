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
from mintrack.db.models import (
    Episode,
    JellyfinAccount,
    JellyfinSyncStatus,
    JellyfinUnmatchedItem,
    JellyfinUnmatchedReason,
    Media,
    MediaType,
    User,
)
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
from mintrack.integrations.tmdb.schemas import TMDBSearchResult
from mintrack.observability.logging import logger
from mintrack.worker.defer import defer_jellyfin_sync

from .matching import Found, WatchEvent, match, unmatched_item

# Watches committed together with the cursor, so a failure keeps the batches before it.
BATCH_SIZE = 100
# Items not matched described in the sync report; the count covers all of them.
MAX_REPORTED_UNMATCHED = 100
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
            imported, unmatched = await self._import(account, since, tmdb, now)
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
            values["last_sync_skipped"] = unmatched.count
            values["last_sync_unmatched"] = list(unmatched.items.values())
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
    ) -> tuple[int, _Unmatched]:
        account_id, user = account.id, await self.session.get_one(User, account.user_id)
        # No database connection stays checked out while Jellyfin answers.
        await self.session.commit()
        # The client stays open while matching, which asks Jellyfin for a series' seasons when it needs them.
        async with self._client(account) as client:
            played = await self._played_since(client, account.jellyfin_user_id, since)
            series_ids = {item.series_id for item in played if item.type == "Episode" and item.series_id}
            series = {item.id: item for item in await client.items(account.jellyfin_user_id, series_ids)}
            seasons = _RegularSeasons(self.session, client, account.jellyfin_user_id)
            previous_sync, synced_until = account.synced_until, account.synced_until
            imported = 0
            unmatched = _Unmatched()
            library = _Library(self.session, tmdb, now)
            tracking = TrackingManager(self.session)
            for batch in itertools.batched(played, BATCH_SIZE, strict=False):
                shows: dict[Media, dict[uuid.UUID, dt.datetime]] = {}
                for item in batch:
                    event = await match(item, _played_at(item), series, library, seasons)
                    if isinstance(event, JellyfinUnmatchedReason):
                        unmatched.add(unmatched_item(item, series, event), item)
                        logger.info(
                            "jellyfin item not matched",
                            account_id=str(account_id),
                            item_id=item.id,
                            type=item.type,
                            reason=event,
                        )
                        continue
                    media, episode_id = library.watched(event)
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
        return imported, unmatched

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


class _Unmatched:
    """The items no watch was found for: all counted, the first ones described, once per series not found."""

    def __init__(self) -> None:
        self.count = 0
        self.items: dict[str, JellyfinUnmatchedItem] = {}

    def add(self, unmatched: JellyfinUnmatchedItem, item: Item) -> None:
        self.count += 1
        if unmatched["reason"] is JellyfinUnmatchedReason.NOT_FOUND and item.type == "Episode":
            key = f"series:{item.series_id}"
        else:
            key = item.id
        if len(self.items) < MAX_REPORTED_UNMATCHED:
            self.items.setdefault(key, unmatched)


class _RegularSeasons:
    """The number of regular seasons (specials aside) Jellyfin has for each series, asked once per series in a sync;
    None when Jellyfin could not tell for that series (deleted meanwhile, an answer not understood)."""

    def __init__(self, session: AsyncSession, client: JellyfinClient, user_id: str) -> None:
        self.session = session
        self.client = client
        self.user_id = user_id
        self.counts: dict[str, int | None] = {}

    async def __call__(self, series_id: str) -> int | None:
        if series_id not in self.counts:
            # No database connection stays checked out while Jellyfin answers.
            await self.session.commit()
            try:
                numbers = await self.client.season_numbers(self.user_id, series_id)
            except JellyfinUnauthorizedError, JellyfinUnreachableError:
                raise
            except JellyfinError as error:
                logger.warning("jellyfin seasons not read", series_id=series_id, error=type(error).__name__)
                self.counts[series_id] = None
            else:
                self.counts[series_id] = len({number for number in numbers if number >= 1})
        return self.counts[series_id]


class _Library:
    """The TMDB lookups of one sync, each made once, and the media and episodes the matched plays stand for."""

    def __init__(self, session: AsyncSession, tmdb: TMDBClient, now: dt.datetime) -> None:
        self.session = session
        self.tmdb = tmdb
        self.catalog = CatalogManager(session, tmdb)
        self.now = now
        self.found: dict[tuple[ExternalSource, str], Found] = {}
        self.searched: dict[tuple[MediaType, str], list[TMDBSearchResult]] = {}
        self.media: dict[tuple[MediaType, int], Media | None] = {}
        self.episodes: dict[uuid.UUID, dict[tuple[int, int], uuid.UUID]] = {}
        self.listed: dict[int, frozenset[tuple[int, int]]] = {}

    async def find(self, source: ExternalSource, external_id: str) -> Found:
        key = (source, external_id)
        if key not in self.found:
            results = await self.tmdb.find(external_id, source)
            self.found[key] = Found(
                movies=tuple(result["id"] for result in results.get("movie_results") or []),
                shows=tuple(result["id"] for result in results.get("tv_results") or []),
                episodes=tuple(
                    (result["show_id"], result["season_number"], result["episode_number"])
                    for result in results.get("tv_episode_results") or []
                ),
            )
        return self.found[key]

    async def search(self, media_type: MediaType, title: str) -> list[TMDBSearchResult]:
        key = (media_type, title)
        if key not in self.searched:
            self.searched[key] = await self.tmdb.search(title, media_type)
        return self.searched[key]

    async def exists(self, media_type: MediaType, tmdb_id: int) -> bool:
        key = (media_type, tmdb_id)
        if key not in self.media:
            try:
                self.media[key] = await self.catalog.get_or_fetch(media_type, tmdb_id, self.now)
            except TMDBNotFoundError:
                self.media[key] = None
        return self.media[key] is not None

    async def episode_numbers(self, show_id: int) -> collections.abc.Set[tuple[int, int]]:
        return (await self._episodes(self._media(MediaType.TV, show_id))).keys()

    async def listed_episode_numbers(self, show_id: int) -> collections.abc.Set[tuple[int, int]]:
        if show_id not in self.listed:
            # As get_or_fetch does, no database connection stays checked out while TMDB answers.
            await self.session.commit()
            show = await self.tmdb.show(show_id)
            self.listed[show_id] = frozenset(
                (season.season_number, episode.episode_number) for season in show.seasons for episode in season.episodes
            )
        return self.listed[show_id]

    def watched(self, event: WatchEvent) -> tuple[Media, uuid.UUID | None]:
        """The media and, for an episode, its id, of a watch `match` found."""
        media = self._media(event.media_type, event.tmdb_id)
        if media.media_type is MediaType.MOVIE:
            return media, None
        return media, self.episodes[media.id][
            typing.cast("int", event.season_number), typing.cast("int", event.episode_number)
        ]

    def _media(self, media_type: MediaType, tmdb_id: int) -> Media:
        return typing.cast("Media", self.media[media_type, tmdb_id])

    async def _episodes(self, media: Media) -> dict[tuple[int, int], uuid.UUID]:
        if media.id not in self.episodes:
            rows = await self.session.execute(
                sa.select(Episode.season_number, Episode.episode_number, Episode.id).where(Episode.media_id == media.id)
            )
            self.episodes[media.id] = {(season, number): episode_id for season, number, episode_id in rows}
        return self.episodes[media.id]
