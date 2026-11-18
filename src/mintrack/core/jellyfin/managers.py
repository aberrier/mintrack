import collections.abc
import datetime as dt
import itertools
import typing
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.catalog.managers import CatalogManager
from mintrack.core.tracking.managers import TrackingManager
from mintrack.db.models import Episode, JellyfinAccount, JellyfinSyncStatus, MediaType, User
from mintrack.integrations.jellyfin.client import (
    Item,
    JellyfinClient,
    JellyfinError,
    JellyfinUnauthorizedError,
    JellyfinUnreachableError,
)
from mintrack.integrations.tmdb.client import ExternalSource, TMDBClient, TMDBNotFoundError
from mintrack.observability.logging import logger

from .matching import FindTmdbId, WatchEvent, match

# Watches committed together with the cursor, so a failure keeps the batches before it.
BATCH_SIZE = 100


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
        # No database connection stays checked out while Jellyfin answers.
        await self.session.commit()
        async with JellyfinClient(server_url, device_id=device_id(user.id, server_url)) as client:
            authentication = await client.authenticate(username, password)
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
        await self.session.commit()
        return account

    async def unlink(self, account: JellyfinAccount) -> None:
        await self._logout(account)
        await self.session.delete(account)
        await self.session.commit()

    async def sync(self, account: JellyfinAccount, tmdb: TMDBClient, now: dt.datetime, *, full: bool = False) -> None:
        """Mark watched what was played on Jellyfin since the last sync, or everything the first time and when `full`.

        A full pass picks up items skipped before, once their metadata or TMDB knows them.
        """
        account_id = account.id
        since = None if full else account.synced_until
        try:
            imported, skipped = await self._import(account, since, tmdb, now)
        except Exception as error:
            await self.session.rollback()
            logger.warning("jellyfin sync failed", account_id=str(account_id), error=type(error).__name__)
            account.last_sync_at = now
            account.last_sync_status = failure_status(error)
            await self.session.commit()
            if not isinstance(error, JellyfinError):
                raise
            return
        account.last_sync_at = account.last_success_at = now
        account.last_sync_status = JellyfinSyncStatus.OK
        account.last_sync_imported = imported
        # Only a pass over the whole history knows every item still not recognised.
        if since is None:
            account.last_sync_skipped = skipped
        await self.session.commit()

    async def _import(
        self, account: JellyfinAccount, since: dt.datetime | None, tmdb: TMDBClient, now: dt.datetime
    ) -> tuple[int, int]:
        user = await self.session.get_one(User, account.user_id)
        # No database connection stays checked out while Jellyfin answers.
        await self.session.commit()
        async with self._client(account) as client:
            played = await self._played_since(client, account.jellyfin_user_id, since)
            series_ids = {item.series_id for item in played if item.type == "Episode" and item.series_id}
            series = {item.id: item for item in await client.items(account.jellyfin_user_id, series_ids)}
        find = tmdb_finder(tmdb)
        previous_sync = account.synced_until
        imported = skipped = 0
        for batch in itertools.batched(played, BATCH_SIZE, strict=False):
            for item in batch:
                event = await match(item, series, find)
                if event is None or not await self._mark(user, event, tmdb, now):
                    skipped += 1
                    logger.info(
                        "jellyfin item not matched", account_id=str(account.id), item_id=item.id, type=item.type
                    )
                else:
                    imported += previous_sync is None or event.watched_at > previous_sync
            batch_end = typing.cast("dt.datetime", batch[-1].user_data.last_played_date)
            account.synced_until = max(account.synced_until or batch_end, batch_end)
            await self.session.commit()
        return imported, skipped

    @staticmethod
    async def _played_since(client: JellyfinClient, user_id: str, since: dt.datetime | None) -> list[Item]:
        """Items played at or after `since`, oldest first; items without a play date are left out."""
        played: list[Item] = []
        start_index = 0
        while True:
            page = await client.played_items(user_id, start_index)
            start_index += len(page.items)
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

    async def _mark(self, user: User, event: WatchEvent, tmdb: TMDBClient, now: dt.datetime) -> bool:
        """Mark the movie or episode watched; False when TMDB does not list it."""
        try:
            media = await CatalogManager(self.session, tmdb).get_or_fetch(event.media_type, event.tmdb_id, now)
        except TMDBNotFoundError:
            return False
        tracking = TrackingManager(self.session)
        if media.media_type is MediaType.MOVIE:
            await tracking.set_movie_watched(user, media, watched=True, now=event.watched_at)
            return True
        episode = await self.session.scalar(
            sa.select(Episode).where(
                Episode.media_id == media.id,
                Episode.season_number == event.season_number,
                Episode.episode_number == event.episode_number,
            )
        )
        if episode is None:
            return False
        await tracking.mark_watched(user, episode, event.watched_at)
        return True
