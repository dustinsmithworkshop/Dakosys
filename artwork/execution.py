"""Execute managed artwork reevaluation without writing output files."""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum

from artwork.assessment import (
    ArtworkSetAssessment,
    assess_artwork_set,
)
from artwork.discovery import (
    DiscoveryPath,
    discover_unmanaged_show,
)
from artwork.inventory import ShowInventory
from artwork.models import (
    ArtworkSet,
    ArtworkSource,
    SelectionMode,
    ShowArtworkState,
)
from artwork.policy import SetAction
from artwork.providers.base import ArtworkProvider
from artwork.reevaluation import (
    ReevaluationResult,
    reevaluate_artwork_selection,
)
from artwork.resolution import (
    materialize_reevaluation_state,
)
from artwork.search import (
    ArtworkSearchKind,
    ArtworkSearchRequest,
)


class ManagedExecutionPath(str, Enum):
    """High-level outcome for one managed Plex show."""

    COMPLETE_NO_PROVIDER = (
        "complete_no_provider"
    )

    REEVALUATED = "reevaluated"

    PROVIDER_ERROR = "provider_error"

    MISSING_SET_CONTEXT = (
        "missing_set_context"
    )


@dataclass(frozen=True)
class ManagedShowExecution:
    """Result of executing Artwork Manager for one managed show."""

    inventory: ShowInventory
    current_state: ShowArtworkState
    state: ShowArtworkState | None

    path: ManagedExecutionPath

    action: SetAction | None = None
    reason: str = ""

    current_assessment: (
        ArtworkSetAssessment | None
    ) = None

    reevaluation: (
        ReevaluationResult | None
    ) = None

    provider_requested: bool = False
    provider_candidate_count: int = 0

    error_type: str | None = None
    error_message: str | None = None

    @property
    def resolved(self) -> bool:
        """Whether this execution produced durable output state."""

        return self.state is not None

    @property
    def blocked_challenger_count(
        self,
    ) -> int:
        if self.reevaluation is None:
            return 0

        return len(
            self
            .reevaluation
            .blocked_challengers
        )


@dataclass(frozen=True)
class ManagedLibraryExecution:
    """Aggregate results for already-reconciled managed shows."""

    results: tuple[
        ManagedShowExecution,
        ...,
    ]

    @property
    def managed_count(self) -> int:
        return len(
            self.results
        )

    @property
    def resolved_states(
        self,
    ) -> tuple[ShowArtworkState, ...]:
        return tuple(
            result.state
            for result in self.results
            if result.state is not None
        )

    @property
    def resolved_count(self) -> int:
        return len(
            self.resolved_states
        )

    @property
    def provider_request_count(
        self,
    ) -> int:
        return sum(
            1
            for result in self.results
            if result.provider_requested
        )

    @property
    def provider_error_count(
        self,
    ) -> int:
        return sum(
            1
            for result in self.results
            if (
                result.path
                is ManagedExecutionPath.PROVIDER_ERROR
            )
        )

    @property
    def missing_set_context_count(
        self,
    ) -> int:
        return sum(
            1
            for result in self.results
            if (
                result.path
                is
                ManagedExecutionPath
                .MISSING_SET_CONTEXT
            )
        )

    @property
    def complete_no_provider_count(
        self,
    ) -> int:
        return sum(
            1
            for result in self.results
            if (
                result.path
                is
                ManagedExecutionPath
                .COMPLETE_NO_PROVIDER
            )
        )

    @property
    def set_refresh_count(
        self,
    ) -> int:
        return sum(
            1
            for result in self.results
            if (
                result.action
                is SetAction.SET_REFRESH
            )
        )

    @property
    def set_migration_count(
        self,
    ) -> int:
        return sum(
            1
            for result in self.results
            if (
                result.action
                is SetAction.SET_MIGRATION
            )
        )

    @property
    def keep_current_after_check_count(
        self,
    ) -> int:
        return sum(
            1
            for result in self.results
            if (
                result.path
                is ManagedExecutionPath.REEVALUATED
                and result.action
                is SetAction.KEEP_CURRENT
            )
        )

    @property
    def cohesion_blocked_count(
        self,
    ) -> int:
        return sum(
            result.blocked_challenger_count
            for result in self.results
        )


def _state_as_set(
    state: ShowArtworkState,
) -> ArtworkSet:
    if state.selected_set_id is None:
        raise ValueError(
            "managed artwork state has no "
            "selected set ID"
        )

    if (
        state.selected_set_source
        is None
    ):
        raise ValueError(
            "managed artwork state has no "
            "selected set source"
        )

    return ArtworkSet(
        provider=(
            state.selected_set_source
        ),
        set_id=(
            state.selected_set_id
        ),
        creator=(
            state.selected_creator
        ),
        title=state.title,
        poster=state.poster,
        background=state.background,
        seasons=state.seasons,
    )


def _is_tmdb_fallback_only_state(
    state: ShowArtworkState,
) -> bool:
    """Whether missing set context is valid TMDB fallback state."""

    if (
        state.selected_set_id is not None
        or state.selected_set_source is not None
        or state.episode_selection is not None
        or state.presentation_selection is not None
    ):
        return False

    if (
        state.selection_mode
        is not SelectionMode.AUTO
    ):
        return False

    sources = []

    def collect(asset):
        if (
            asset is not None
            and asset.available
        ):
            sources.append(
                asset.source
            )

    collect(
        state.poster
    )
    collect(
        state.background
    )

    for season in (
        state.seasons.values()
    ):
        collect(
            season.poster
        )

        for episode in (
            season.episodes.values()
        ):
            collect(
                episode.card
            )

    return (
        bool(sources)
        and all(
            source
            is ArtworkSource.TMDB
            for source in sources
        )
    )


def _merge_primary_over_fallback(
    *,
    fallback: ShowArtworkState,
    primary: ShowArtworkState,
) -> ShowArtworkState:
    """Prefer selected primary artwork while retaining fallback gaps."""

    merged = deepcopy(
        primary
    )

    if merged.title is None:
        merged.title = (
            fallback.title
        )

    if merged.tvdb_id is None:
        merged.tvdb_id = (
            fallback.tvdb_id
        )

    if merged.tmdb_id is None:
        merged.tmdb_id = (
            fallback.tmdb_id
        )

    if merged.imdb_id is None:
        merged.imdb_id = (
            fallback.imdb_id
        )

    if (
        merged.poster is None
        or not merged.poster.available
    ):
        merged.poster = deepcopy(
            fallback.poster
        )

    if (
        merged.background is None
        or not merged.background.available
    ):
        merged.background = deepcopy(
            fallback.background
        )

    for (
        season_number,
        fallback_season,
    ) in fallback.seasons.items():
        primary_season = (
            merged.seasons.get(
                season_number
            )
        )

        if primary_season is None:
            merged.seasons[
                season_number
            ] = deepcopy(
                fallback_season
            )

            continue

        if (
            primary_season.poster is None
            or not primary_season.poster.available
        ):
            primary_season.poster = deepcopy(
                fallback_season.poster
            )

        for (
            episode_number,
            fallback_episode,
        ) in fallback_season.episodes.items():
            primary_episode = (
                primary_season
                .episodes
                .get(
                    episode_number
                )
            )

            if (
                primary_episode is None
                or primary_episode.card is None
                or not primary_episode.card.available
            ):
                primary_season.episodes[
                    episode_number
                ] = deepcopy(
                    fallback_episode
                )

    # The fallback state may carry an intentional mode even though it
    # has no provider-set selection.
    merged.selection_mode = (
        fallback.selection_mode
    )

    return merged


def _execute_tmdb_fallback_state(
    *,
    inventory: ShowInventory,
    current_state: ShowArtworkState,
    provider: ArtworkProvider,
) -> ManagedShowExecution:
    """Give a persisted TMDB-only state a primary-provider opportunity."""

    discovery = (
        discover_unmanaged_show(
            inventory=inventory,
            provider=provider,
        )
    )

    if (
        discovery.path
        is DiscoveryPath.PROVIDER_ERROR
    ):
        return ManagedShowExecution(
            inventory=inventory,
            current_state=current_state,
            state=current_state,
            path=(
                ManagedExecutionPath
                .PROVIDER_ERROR
            ),
            action=SetAction.KEEP_CURRENT,
            reason=(
                "fallback_primary_provider_error"
            ),
            provider_requested=True,
            provider_candidate_count=(
                discovery
                .provider_candidate_count
            ),
            error_type=(
                discovery.error_type
            ),
            error_message=(
                discovery.error_message
            ),
        )

    if discovery.state is None:
        return ManagedShowExecution(
            inventory=inventory,
            current_state=current_state,
            state=current_state,
            path=(
                ManagedExecutionPath
                .REEVALUATED
            ),
            action=SetAction.KEEP_CURRENT,
            reason=(
                "fallback_primary_not_available"
            ),
            provider_requested=(
                discovery.provider_requested
            ),
            provider_candidate_count=(
                discovery
                .provider_candidate_count
            ),
        )

    resolved = (
        _merge_primary_over_fallback(
            fallback=current_state,
            primary=discovery.state,
        )
    )

    return ManagedShowExecution(
        inventory=inventory,
        current_state=current_state,
        state=resolved,
        path=(
            ManagedExecutionPath
            .REEVALUATED
        ),
        action=SetAction.SET_MIGRATION,
        reason=(
            "fallback_promoted_to_primary_set"
        ),
        provider_requested=(
            discovery.provider_requested
        ),
        provider_candidate_count=(
            discovery
            .provider_candidate_count
        ),
    )


def execute_managed_show(
    *,
    inventory: ShowInventory,
    current_state: ShowArtworkState,
    provider: ArtworkProvider,
    incomplete_migration_threshold: float = 0.25,
) -> ManagedShowExecution:
    """Reevaluate one already-managed Plex show.

    Complete episode-card coverage does not query providers.

    Provider failure preserves durable current state.

    This function performs no file writes and makes no Plex changes.
    """

    identity = inventory.identity

    if (
        current_state.tvdb_id
        is not None
        and identity.tvdb_id
        is not None
        and current_state.tvdb_id
        != identity.tvdb_id
    ):
        raise ValueError(
            "managed state TVDB ID does not "
            "match Plex inventory"
        )

    if (
        current_state.selected_set_id
        is None
        or current_state.selected_set_source
        is None
    ):
        if _is_tmdb_fallback_only_state(
            current_state
        ):
            return (
                _execute_tmdb_fallback_state(
                    inventory=inventory,
                    current_state=current_state,
                    provider=provider,
                )
            )

        return ManagedShowExecution(
            inventory=inventory,
            current_state=current_state,
            state=None,
            path=(
                ManagedExecutionPath
                .MISSING_SET_CONTEXT
            ),
            reason=(
                "missing_selected_set_context"
            ),
        )

    expected = (
        inventory.expected_episodes()
    )

    current_assessment = (
        assess_artwork_set(
            _state_as_set(
                current_state
            ),
            expected,
        )
    )

    if (
        current_assessment
        .episode_coverage
        .complete
    ):
        return ManagedShowExecution(
            inventory=inventory,
            current_state=current_state,
            state=current_state,
            path=(
                ManagedExecutionPath
                .COMPLETE_NO_PROVIDER
            ),
            action=SetAction.KEEP_CURRENT,
            reason=(
                "current_episode_coverage_complete"
            ),
            current_assessment=(
                current_assessment
            ),
        )

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
        kind=(
            ArtworkSearchKind
            .REEVALUATION
        ),
        current_set_id=(
            current_state
            .selected_set_id
        ),
        current_set_source=(
            current_state
            .selected_set_source
        ),
        current_creator=(
            current_state
            .selected_creator
        ),
        selection_mode=(
            current_state
            .selection_mode
        ),
    )

    try:
        artwork_sets = (
            provider.find_sets(
                request
            )
        )

    except Exception as exc:
        # Durable managed state wins over transient
        # provider/API failure.
        return ManagedShowExecution(
            inventory=inventory,
            current_state=current_state,
            state=current_state,
            path=(
                ManagedExecutionPath
                .PROVIDER_ERROR
            ),
            action=SetAction.KEEP_CURRENT,
            reason="provider_error",
            current_assessment=(
                current_assessment
            ),
            provider_requested=True,
            error_type=(
                type(exc).__name__
            ),
            error_message=str(
                exc
            ),
        )

    candidates = tuple(
        assess_artwork_set(
            artwork_set,
            expected,
        )
        for artwork_set in artwork_sets
    )

    reevaluation = (
        reevaluate_artwork_selection(
            current=(
                current_assessment
            ),
            candidates=candidates,
            selection_mode=(
                current_state
                .selection_mode
            ),
            incomplete_migration_threshold=(
                incomplete_migration_threshold
            ),
        )
    )

    resolved = (
        materialize_reevaluation_state(
            current_state=(
                current_state
            ),
            current_assessment=(
                current_assessment
            ),
            result=reevaluation,
        )
    )

    return ManagedShowExecution(
        inventory=inventory,
        current_state=current_state,
        state=resolved.state,
        path=(
            ManagedExecutionPath
            .REEVALUATED
        ),
        action=resolved.action,
        reason=resolved.reason,
        current_assessment=(
            current_assessment
        ),
        reevaluation=reevaluation,
        provider_requested=True,
        provider_candidate_count=len(
            candidates
        ),
    )


def execute_managed_library(
    *,
    items: Iterable[
        tuple[
            ShowInventory,
            ShowArtworkState,
        ]
    ],
    provider: ArtworkProvider,
    incomplete_migration_threshold: float = 0.25,
) -> ManagedLibraryExecution:
    """Execute already-reconciled managed shows."""

    results = tuple(
        execute_managed_show(
            inventory=inventory,
            current_state=current_state,
            provider=provider,
            incomplete_migration_threshold=(
                incomplete_migration_threshold
            ),
        )
        for inventory, current_state
        in items
    )

    return ManagedLibraryExecution(
        results=results
    )
