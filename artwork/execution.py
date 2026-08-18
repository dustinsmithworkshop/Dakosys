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
    SeasonArtwork,
    SelectionMode,
    ShowArtworkState,
)
from artwork.policy import SetAction
from artwork.progress import (
    ArtworkProgressCallback,
    ArtworkScanPhase,
    emit_artwork_progress,
)
from artwork.providers.base import ArtworkProvider
from artwork.reevaluation import (
    ReevaluationResult,
    reevaluate_artwork_selection,
)
from artwork.resolution import (
    materialize_reevaluation_state,
)
from artwork.source_policy import (
    UPGRADEABLE_FALLBACK_SOURCES,
    artwork_set_has_upgradeable_fallback,
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


def _selection_key(
    selection,
):
    if selection is None:
        return None

    return (
        selection.provider,
        selection.set_id,
    )


def _has_split_family_selection(
    state: ShowArtworkState,
) -> bool:
    """Whether episode and presentation artwork use different sets."""

    episode = (
        state.effective_episode_selection
    )

    presentation = (
        state.effective_presentation_selection
    )

    return (
        episode is not None
        and presentation is not None
        and _selection_key(
            episode
        )
        != _selection_key(
            presentation
        )
    )


def _episode_only_set(
    artwork_set: ArtworkSet,
) -> ArtworkSet:
    """Project one provider set to episode-card artwork only."""

    return ArtworkSet(
        provider=artwork_set.provider,
        set_id=artwork_set.set_id,
        creator=artwork_set.creator,
        title=artwork_set.title,
        seasons={
            season_number:
                SeasonArtwork(
                    season_number=(
                        season_number
                    ),
                    episodes=deepcopy(
                        season.episodes
                    ),
                )
            for (
                season_number,
                season,
            )
            in artwork_set.seasons.items()
        },
    )


def _state_as_episode_set(
    state: ShowArtworkState,
) -> ArtworkSet:
    """Project durable split state to its episode cohesive family."""

    selection = (
        state.effective_episode_selection
    )

    if selection is None:
        raise ValueError(
            "managed artwork state has no "
            "episode selection"
        )

    return ArtworkSet(
        provider=selection.provider,
        set_id=selection.set_id,
        creator=selection.creator,
        title=state.title,
        seasons={
            season_number:
                SeasonArtwork(
                    season_number=(
                        season_number
                    ),
                    episodes=deepcopy(
                        season.episodes
                    ),
                )
            for (
                season_number,
                season,
            )
            in state.seasons.items()
        },
    )


def _restore_split_presentation(
    *,
    current_state: ShowArtworkState,
    resolved_state: ShowArtworkState,
) -> ShowArtworkState:
    """Preserve presentation artwork across episode-family reevaluation."""

    restored = deepcopy(
        resolved_state
    )

    restored.poster = deepcopy(
        current_state.poster
    )

    restored.background = deepcopy(
        current_state.background
    )

    season_numbers = sorted(
        set(
            current_state.seasons
        )
        | set(
            restored.seasons
        )
    )

    seasons = {}

    for season_number in season_numbers:
        current_season = (
            current_state.seasons.get(
                season_number
            )
        )

        resolved_season = (
            restored.seasons.get(
                season_number
            )
        )

        poster = (
            deepcopy(
                current_season.poster
            )
            if current_season is not None
            else None
        )

        episodes = (
            deepcopy(
                resolved_season.episodes
            )
            if resolved_season is not None
            else {}
        )

        if (
            poster is not None
            or episodes
        ):
            seasons[
                season_number
            ] = SeasonArtwork(
                season_number=(
                    season_number
                ),
                poster=poster,
                episodes=episodes,
            )

    restored.seasons = seasons

    # Make the independent presentation provenance explicit even when
    # it originally came from legacy fallback. This prevents an episode
    # migration from silently changing presentation ownership.
    restored.presentation_selection = (
        current_state
        .effective_presentation_selection
    )

    return restored


def _is_upgradeable_fallback_only_state(
    state: ShowArtworkState,
) -> bool:
    """Whether missing set context is valid upgradeable fallback state."""

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
            in UPGRADEABLE_FALLBACK_SOURCES
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


def _execute_fallback_state(
    *,
    inventory: ShowInventory,
    current_state: ShowArtworkState,
    provider: ArtworkProvider,
) -> ManagedShowExecution:
    """Give persisted fallback state a primary-provider opportunity."""

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

    Complete primary artwork can skip provider queries.

    Complete coverage that still contains upgradeable fallback remains
    eligible for same-set primary-provider refresh.

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
        if _is_upgradeable_fallback_only_state(
            current_state
        ):
            return (
                _execute_fallback_state(
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

    split_families = (
        _has_split_family_selection(
            current_state
        )
    )

    current_selection = (
        current_state
        .effective_episode_selection
        if split_families
        else current_state.legacy_selection
    )

    if current_selection is None:
        raise RuntimeError(
            "managed artwork state has no "
            "current reevaluation selection"
        )

    current_set = (
        _state_as_episode_set(
            current_state
        )
        if split_families
        else _state_as_set(
            current_state
        )
    )

    current_assessment = (
        assess_artwork_set(
            current_set,
            expected,
        )
    )

    if (
        current_assessment
        .episode_coverage
        .complete
        and not (
            artwork_set_has_upgradeable_fallback(
                current_set
            )
        )
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
            current_selection.set_id
        ),
        current_set_source=(
            current_selection.provider
        ),
        current_creator=(
            current_selection.creator
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
            (
                _episode_only_set(
                    artwork_set
                )
                if split_families
                else artwork_set
            ),
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

    materialization_state = (
        current_state
    )

    if split_families:
        materialization_state = deepcopy(
            current_state
        )

        # The legacy fields remain episode-oriented while old managed
        # materialization still consumes them.
        materialization_state.selected_set_id = (
            current_selection.set_id
        )
        materialization_state.selected_set_source = (
            current_selection.provider
        )
        materialization_state.selected_creator = (
            current_selection.creator
        )

    resolved = (
        materialize_reevaluation_state(
            current_state=(
                materialization_state
            ),
            current_assessment=(
                current_assessment
            ),
            result=reevaluation,
        )
    )

    resolved_state = (
        resolved.state
    )

    if split_families:
        resolved_state = (
            _restore_split_presentation(
                current_state=(
                    current_state
                ),
                resolved_state=(
                    resolved_state
                ),
            )
        )

    return ManagedShowExecution(
        inventory=inventory,
        current_state=current_state,
        state=resolved_state,
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
    progress_callback: ArtworkProgressCallback | None = None,
) -> ManagedLibraryExecution:
    """Execute already-reconciled managed shows."""

    item_tuple = tuple(
        items
    )

    total = len(
        item_tuple
    )

    results: list[
        ManagedShowExecution
    ] = []

    for index, (
        inventory,
        current_state,
    ) in enumerate(
        item_tuple,
        start=1,
    ):
        result = execute_managed_show(
            inventory=inventory,
            current_state=current_state,
            provider=provider,
            incomplete_migration_threshold=(
                incomplete_migration_threshold
            ),
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
                .PRIMARY_MANAGED
            ),
            completed=index,
            total=total,
            message=(
                "Checking managed artwork "
                "with the primary provider"
            ),
            current_title=(
                inventory.identity.title
            ),
        )

    return ManagedLibraryExecution(
        results=tuple(
            results
        )
    )
