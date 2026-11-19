"""Lookups shared by several API modules, which never import one another for them."""

import typing
import uuid

import fastapi
from sqlalchemy.ext.asyncio import AsyncSession

from mintrack.core.catalog.managers import find_media
from mintrack.db.models import Episode, Media, MediaType

EpisodeId = typing.Annotated[uuid.UUID, fastapi.Path()]


async def cached(session: AsyncSession, media_type: MediaType, tmdb_id: int) -> Media:
    """Media are written only after their page loaded it into the cache."""
    media = await find_media(session, media_type, tmdb_id)
    if media is None:
        raise fastapi.HTTPException(fastapi.status.HTTP_404_NOT_FOUND, "Not in the catalog")
    return media


async def episode_and_show(session: AsyncSession, episode_id: uuid.UUID) -> tuple[Episode, Media]:
    """Episodes exist only once their show's page loaded them into the catalog."""
    episode = await session.get(Episode, episode_id)
    if episode is None:
        raise fastapi.HTTPException(fastapi.status.HTTP_404_NOT_FOUND, "No such episode")
    return episode, await session.get_one(Media, episode.media_id)
