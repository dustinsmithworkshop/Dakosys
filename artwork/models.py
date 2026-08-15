"""Normalized artwork models for Dakosys Artwork Manager."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ArtworkKind(str, Enum):
    SHOW_POSTER = "show_poster"
    SHOW_BACKGROUND = "show_background"
    SEASON_POSTER = "season_poster"
    EPISODE_CARD = "episode_card"


class ArtworkSource(str, Enum):
    MEDIUX = "mediux"
    POSTERDB = "posterdb"
    TMDB = "tmdb"
    TVDB = "tvdb"
    PLEX = "plex"
    GENERATED = "generated"
    MANUAL = "manual"


class ArtworkQuality(str, Enum):
    CURATED = "curated"
    GENERATED = "generated"
    RAW_STILL = "raw_still"
    EXISTING = "existing"


class SelectionMode(str, Enum):
    AUTO = "auto"
    PREFERRED = "preferred"
    LOCKED = "locked"


@dataclass(frozen=True)
class ArtworkAsset:
    kind: ArtworkKind
    source: ArtworkSource
    url: Optional[str] = None
    provider_asset_id: Optional[str] = None
    quality: Optional[ArtworkQuality] = None


@dataclass
class EpisodeArtwork:
    episode_number: int
    card: Optional[ArtworkAsset] = None


@dataclass
class SeasonArtwork:
    season_number: int
    poster: Optional[ArtworkAsset] = None
    episodes: dict[int, EpisodeArtwork] = field(default_factory=dict)


@dataclass
class ArtworkSet:
    """One cohesive artwork set from a provider."""

    provider: ArtworkSource
    set_id: str
    creator: Optional[str] = None
    seasons: dict[int, SeasonArtwork] = field(
        default_factory=dict
    )

    # Provider metadata and show-level artwork.
    title: Optional[str] = None
    poster: Optional[ArtworkAsset] = None
    background: Optional[ArtworkAsset] = None


@dataclass
class ShowArtworkState:
    title: Optional[str]
    tvdb_id: Optional[int]
    tmdb_id: Optional[int] = None
    imdb_id: Optional[str] = None

    poster: Optional[ArtworkAsset] = None
    background: Optional[ArtworkAsset] = None

    seasons: dict[int, SeasonArtwork] = field(default_factory=dict)

    selected_set_id: Optional[str] = None
    selected_set_source: Optional[ArtworkSource] = None
    selected_creator: Optional[str] = None
    selection_mode: SelectionMode = SelectionMode.AUTO
