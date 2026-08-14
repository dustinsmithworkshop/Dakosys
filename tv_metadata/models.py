"""Normalized TV metadata models used by Dakosys providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum


class ShowLifecycle(str, Enum):
    """Provider-independent lifecycle state for a TV series."""

    RETURNING = "returning"
    ENDED = "ended"
    UNKNOWN = "unknown"


class EpisodeState(str, Enum):
    """Provider-independent state for an upcoming episode."""

    AIRING = "airing"
    SEASON_PREMIERE = "season_premiere"
    SEASON_FINALE = "season_finale"
    MID_SEASON_FINALE = "mid_season_finale"
    SERIES_FINALE = "series_finale"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ShowIdentity:
    """Stable identity for a Plex show.

    Plex is the source of truth for the show being processed. External IDs
    allow metadata providers to resolve that show without fuzzy title
    matching.
    """

    title: str
    year: int | None
    library: str
    plex_rating_key: str

    tmdb_id: int | None = None
    tvdb_id: int | None = None
    imdb_id: str | None = None

    library_roles: tuple[str, ...] = ()


@dataclass(frozen=True)
class NextEpisode:
    """Normalized upcoming-episode metadata from a provider."""

    source: str

    season: int | None = None
    episode: int | None = None

    air_date: date | None = None
    air_datetime: datetime | None = None

    title: str | None = None
    state: EpisodeState = EpisodeState.UNKNOWN

    provider_episode_id: str | None = None
    raw_episode_type: str | None = None


@dataclass(frozen=True)
class ProviderResult:
    """Normalized metadata returned by one provider.

    A provider may successfully identify a show without supplying every
    metadata field. The resolver is responsible for combining provider
    results into the final ShowStatus.
    """

    source: str
    matched: bool

    lifecycle: ShowLifecycle = ShowLifecycle.UNKNOWN
    next_episode: NextEpisode | None = None

    provider_show_id: str | None = None
    reason: str | None = None

    warnings: tuple[str, ...] = field(
        default_factory=tuple
    )


@dataclass(frozen=True)
class ShowStatus:
    """Resolved TV status used by the Dakosys TV Status engine."""

    lifecycle: ShowLifecycle
    lifecycle_source: str | None

    next_episode: NextEpisode | None = None

    warnings: tuple[str, ...] = field(
        default_factory=tuple
    )


@dataclass(frozen=True)
class NextAiringEntry:
    """One Plex show with a provider-derived upcoming episode."""

    title: str
    year: int | None
    library: str
    plex_rating_key: str
    next_episode: NextEpisode
    tmdb_id: int | None = None
    tvdb_id: int | None = None
    imdb_id: str | None = None
