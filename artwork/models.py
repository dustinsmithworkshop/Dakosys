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
    MOVIE_POSTER = "movie_poster"
    MOVIE_BACKGROUND = "movie_background"


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

    @property
    def available(self) -> bool:
        """Whether the asset has a usable source reference.

        Provider candidates may have a stable provider asset ID before
        Dakosys has materialized a final image delivery URL.
        """

        return bool(
            (self.url or "").strip()
            or (
                self.provider_asset_id
                or ""
            ).strip()
        )


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


@dataclass(frozen=True)
class ArtworkSetSelection:
    """Provenance for one cohesive provider artwork family."""

    provider: ArtworkSource
    set_id: str
    creator: Optional[str] = None
    mode: SelectionMode = SelectionMode.AUTO

    def __post_init__(self) -> None:
        set_id = self.set_id.strip()

        if not set_id:
            raise ValueError(
                "artwork selection set ID cannot be empty"
            )

        object.__setattr__(
            self,
            "set_id",
            set_id,
        )


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

    # New v3 provenance model. These may independently identify the
    # cohesive set used for episode cards and the cohesive set used for
    # show/season presentation artwork.
    #
    # Legacy single-set state remains supported through the effective
    # selection properties below.
    episode_selection: Optional[ArtworkSetSelection] = None
    presentation_selection: Optional[ArtworkSetSelection] = None

    @property
    def legacy_selection(
        self,
    ) -> Optional[ArtworkSetSelection]:
        """Translate legacy single-set provenance when complete."""

        if (
            self.selected_set_id is None
            or self.selected_set_source is None
        ):
            return None

        return ArtworkSetSelection(
            provider=self.selected_set_source,
            set_id=self.selected_set_id,
            creator=self.selected_creator,
            mode=self.selection_mode,
        )

    @property
    def effective_episode_selection(
        self,
    ) -> Optional[ArtworkSetSelection]:
        """Episode-card selection with legacy fallback."""

        return (
            self.episode_selection
            or self.legacy_selection
        )

    @property
    def effective_presentation_selection(
        self,
    ) -> Optional[ArtworkSetSelection]:
        """Show/season selection with legacy fallback."""

        return (
            self.presentation_selection
            or self.legacy_selection
        )
