"""Discover artwork for previously unmanaged Plex shows."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from artwork.assessment import (
    ArtworkSetAssessment,
    assess_artwork_set,
)
from artwork.inventory import ShowInventory
from artwork.models import (
    ArtworkSetSelection,
    EpisodeArtwork,
    SeasonArtwork,
    SelectionMode,
    ShowArtworkState,
)
from artwork.progress import (
    ArtworkProgressCallback,
    ArtworkScanPhase,
    emit_artwork_progress,
)
from artwork.providers.base import (
    ArtworkProvider,
    ArtworkProviderUnavailableError,
)
from artwork.search import (
    ArtworkSearchKind,
    ArtworkSearchRequest,
)
from artwork.selection import (
    choose_episode_candidate,
    choose_presentation_candidate,
)


class DiscoveryPath(str, Enum):
    """Outcome of artwork discovery for one unmanaged show."""

    SELECTED = "selected"
    NO_CANDIDATES = "no_candidates"
    NO_USABLE_CANDIDATE = (
        "no_usable_candidate"
    )
    PROVIDER_UNAVAILABLE = (
        "provider_unavailable"
    )
    PROVIDER_ERROR = "provider_error"


@dataclass(frozen=True)
class ShowDiscoveryExecution:
    """Result of provider discovery for one unmanaged Plex show."""

    inventory: ShowInventory
    state: ShowArtworkState | None
    path: DiscoveryPath

    # Primary selection retained for callers that still expect one
    # selected assessment. Episode artwork wins when available.
    selected: ArtworkSetAssessment | None = None

    episode_selected: (
        ArtworkSetAssessment | None
    ) = None

    presentation_selected: (
        ArtworkSetAssessment | None
    ) = None

    provider_requested: bool = True
    provider_candidate_count: int = 0
    usable_candidate_count: int = 0

    error_type: str | None = None
    error_message: str | None = None

    @property
    def resolved(self) -> bool:
        return self.state is not None


@dataclass(frozen=True)
class LibraryDiscoveryExecution:
    """Aggregate discovery results for unmanaged Plex shows."""

    results: tuple[
        ShowDiscoveryExecution,
        ...,
    ]

    @property
    def unmanaged_count(self) -> int:
        return len(
            self.results
        )

    @property
    def selected_states(
        self,
    ) -> tuple[ShowArtworkState, ...]:
        return tuple(
            result.state
            for result in self.results
            if result.state is not None
        )

    @property
    def selected_count(self) -> int:
        return len(
            self.selected_states
        )

    @property
    def provider_request_count(self) -> int:
        return sum(
            1
            for result in self.results
            if result.provider_requested
        )

    @property
    def no_candidates_count(self) -> int:
        return sum(
            1
            for result in self.results
            if (
                result.path
                is DiscoveryPath.NO_CANDIDATES
            )
        )

    @property
    def no_usable_candidate_count(
        self,
    ) -> int:
        return sum(
            1
            for result in self.results
            if (
                result.path
                is DiscoveryPath.NO_USABLE_CANDIDATE
            )
        )

    @property
    def provider_unavailable_count(
        self,
    ) -> int:
        return sum(
            1
            for result in self.results
            if (
                result.path
                is
                DiscoveryPath
                .PROVIDER_UNAVAILABLE
            )
        )

    @property
    def provider_error_count(self) -> int:
        return sum(
            1
            for result in self.results
            if (
                result.path
                is DiscoveryPath.PROVIDER_ERROR
            )
        )


def _has_usable_artwork(
    assessment: ArtworkSetAssessment,
) -> bool:
    if (
        assessment
        .episode_coverage
        .available_episode_count
        > 0
    ):
        return True

    if assessment.show_poster_available:
        return True

    if assessment.show_background_available:
        return True

    expected_seasons = set(
        assessment.expected_season_numbers
    )

    provider_seasons = set(
        assessment.season_poster_numbers
    )

    return bool(
        expected_seasons
        & provider_seasons
    )


def _selection_from_assessment(
    assessment: ArtworkSetAssessment | None,
) -> ArtworkSetSelection | None:
    if assessment is None:
        return None

    artwork_set = assessment.artwork_set

    return ArtworkSetSelection(
        provider=artwork_set.provider,
        set_id=artwork_set.set_id,
        creator=artwork_set.creator,
        mode=SelectionMode.AUTO,
    )


def _resolved_seasons(
    *,
    inventory: ShowInventory,
    episode_selected: (
        ArtworkSetAssessment | None
    ),
    presentation_selected: (
        ArtworkSetAssessment | None
    ),
) -> dict[int, SeasonArtwork]:
    """Resolve Plex-backed seasons from the two cohesive families."""

    expected = inventory.expected_episodes()

    episode_set = (
        episode_selected.artwork_set
        if episode_selected is not None
        else None
    )

    presentation_set = (
        presentation_selected.artwork_set
        if presentation_selected is not None
        else None
    )

    resolved: dict[
        int,
        SeasonArtwork,
    ] = {}

    for season_number in sorted(
        expected
    ):
        expected_episodes = expected[
            season_number
        ]

        episode_season = (
            episode_set.seasons.get(
                season_number
            )
            if episode_set is not None
            else None
        )

        presentation_season = (
            presentation_set.seasons.get(
                season_number
            )
            if presentation_set is not None
            else None
        )

        poster = (
            presentation_season.poster
            if (
                presentation_season
                is not None
                and presentation_season.poster
                is not None
                and presentation_season
                .poster
                .available
            )
            else None
        )

        episodes: dict[
            int,
            EpisodeArtwork,
        ] = {}

        if episode_season is not None:
            for episode_number in sorted(
                expected_episodes
            ):
                episode = (
                    episode_season
                    .episodes
                    .get(
                        episode_number
                    )
                )

                if (
                    episode is None
                    or episode.card is None
                    or not episode.card.available
                ):
                    continue

                episodes[
                    episode_number
                ] = EpisodeArtwork(
                    episode_number=(
                        episode_number
                    ),
                    card=episode.card,
                )

        if (
            poster is not None
            or episodes
        ):
            resolved[
                season_number
            ] = SeasonArtwork(
                season_number=(
                    season_number
                ),
                poster=poster,
                episodes=episodes,
            )

    return resolved


def _state_from_discovery(
    *,
    inventory: ShowInventory,
    episode_selected: (
        ArtworkSetAssessment | None
    ),
    presentation_selected: (
        ArtworkSetAssessment | None
    ),
) -> ShowArtworkState:
    """Create initial resolved state from independent artwork families."""

    identity = inventory.identity

    episode_selection = (
        _selection_from_assessment(
            episode_selected
        )
    )

    presentation_selection = (
        _selection_from_assessment(
            presentation_selected
        )
    )

    # Keep legacy single-set fields populated while older managed
    # reevaluation code still consumes them. Episode-card provenance is
    # primary when it exists because gap filling is the central artwork
    # objective.
    legacy_selection = (
        episode_selection
        or presentation_selection
    )

    presentation_set = (
        presentation_selected.artwork_set
        if presentation_selected is not None
        else None
    )

    poster = (
        presentation_set.poster
        if (
            presentation_set is not None
            and presentation_set.poster is not None
            and presentation_set.poster.available
        )
        else None
    )

    background = (
        presentation_set.background
        if (
            presentation_set is not None
            and presentation_set.background is not None
            and presentation_set.background.available
        )
        else None
    )

    return ShowArtworkState(
        title=identity.title,
        tvdb_id=identity.tvdb_id,
        tmdb_id=identity.tmdb_id,
        imdb_id=identity.imdb_id,
        poster=poster,
        background=background,
        seasons=_resolved_seasons(
            inventory=inventory,
            episode_selected=(
                episode_selected
            ),
            presentation_selected=(
                presentation_selected
            ),
        ),
        selected_set_id=(
            legacy_selection.set_id
            if legacy_selection is not None
            else None
        ),
        selected_set_source=(
            legacy_selection.provider
            if legacy_selection is not None
            else None
        ),
        selected_creator=(
            legacy_selection.creator
            if legacy_selection is not None
            else None
        ),
        selection_mode=SelectionMode.AUTO,
        episode_selection=(
            episode_selection
        ),
        presentation_selection=(
            presentation_selection
        ),
    )


def discover_unmanaged_show(
    *,
    inventory: ShowInventory,
    provider: ArtworkProvider,
) -> ShowDiscoveryExecution:
    """Discover artwork for one previously unmanaged Plex show."""

    identity = inventory.identity

    request = ArtworkSearchRequest(
        library=identity.library,
        plex_rating_key=str(
            identity.plex_rating_key
        ),
        title=identity.title,
        year=identity.year,
        tvdb_id=identity.tvdb_id,
        tmdb_id=identity.tmdb_id,
        imdb_id=identity.imdb_id,
        seasons=inventory.seasons,
        kind=ArtworkSearchKind.DISCOVERY,
    )

    try:
        artwork_sets = provider.find_sets(
            request
        )

    except ArtworkProviderUnavailableError as exc:
        return ShowDiscoveryExecution(
            inventory=inventory,
            state=None,
            path=(
                DiscoveryPath
                .PROVIDER_UNAVAILABLE
            ),
            error_type=type(exc).__name__,
            error_message=str(exc),
        )

    except Exception as exc:
        return ShowDiscoveryExecution(
            inventory=inventory,
            state=None,
            path=DiscoveryPath.PROVIDER_ERROR,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )

    if not artwork_sets:
        return ShowDiscoveryExecution(
            inventory=inventory,
            state=None,
            path=DiscoveryPath.NO_CANDIDATES,
            provider_candidate_count=0,
            usable_candidate_count=0,
        )

    expected = inventory.expected_episodes()

    assessments = tuple(
        assess_artwork_set(
            artwork_set,
            expected,
        )
        for artwork_set in artwork_sets
    )

    usable = tuple(
        assessment
        for assessment in assessments
        if _has_usable_artwork(
            assessment
        )
    )

    if not usable:
        return ShowDiscoveryExecution(
            inventory=inventory,
            state=None,
            path=(
                DiscoveryPath
                .NO_USABLE_CANDIDATE
            ),
            provider_candidate_count=len(
                assessments
            ),
            usable_candidate_count=0,
        )

    episode_selected = (
        choose_episode_candidate(
            usable
        )
    )

    presentation_selected = (
        choose_presentation_candidate(
            usable,
            preferred=episode_selected,
        )
    )

    primary = (
        episode_selected
        or presentation_selected
    )

    if primary is None:
        raise RuntimeError(
            "usable discovery candidates produced "
            "no artwork-family selection"
        )

    state = _state_from_discovery(
        inventory=inventory,
        episode_selected=(
            episode_selected
        ),
        presentation_selected=(
            presentation_selected
        ),
    )

    return ShowDiscoveryExecution(
        inventory=inventory,
        state=state,
        path=DiscoveryPath.SELECTED,
        selected=primary,
        episode_selected=(
            episode_selected
        ),
        presentation_selected=(
            presentation_selected
        ),
        provider_candidate_count=len(
            assessments
        ),
        usable_candidate_count=len(
            usable
        ),
    )


def discover_unmanaged_library(
    *,
    inventories: Iterable[ShowInventory],
    provider: ArtworkProvider,
    progress_callback: ArtworkProgressCallback | None = None,
) -> LibraryDiscoveryExecution:
    """Discover artwork for already-reconciled unmanaged shows."""

    inventory_tuple = tuple(
        inventories
    )

    total = len(
        inventory_tuple
    )

    results: list[
        ShowDiscoveryExecution
    ] = []

    for index, inventory in enumerate(
        inventory_tuple,
        start=1,
    ):
        result = (
            discover_unmanaged_show(
                inventory=inventory,
                provider=provider,
            )
        )

        results.append(
            result
        )

        emit_artwork_progress(
            progress_callback,
            library=(
                inventory.identity.library
            ),
            phase=(
                ArtworkScanPhase
                .PRIMARY_DISCOVERY
            ),
            completed=index,
            total=total,
            message=(
                "Discovering artwork "
                "with the primary provider"
            ),
            current_title=(
                inventory.identity.title
            ),
        )

    return LibraryDiscoveryExecution(
        results=tuple(
            results
        )
    )
