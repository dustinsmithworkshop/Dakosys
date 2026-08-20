"""Read-only Artwork Manager execution for movie libraries."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from artwork.models import (
    ArtworkSet,
    ArtworkSource,
    MovieArtworkState,
    SelectionMode,
)
from artwork.movie_inventory import (
    MovieInventory,
)
from artwork.movie_tmdb_fallback import (
    MovieTMDBFallbackResult,
    resolve_movie_tmdb_coverage,
    skip_movie_tmdb_missing_set_context,
)
from artwork.movie_reconciliation import (
    MovieTargetReconciliation,
    reconcile_movie_target,
)
from artwork.movie_state_store import (
    StoredMovieArtworkState,
)
from artwork.policy import (
    SetAction,
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
from artwork.providers.tmdb import (
    TMDBArtworkClient,
)
from artwork.search import (
    ArtworkSearchKind,
    ArtworkSearchRequest,
)
from artwork.source_policy import (
    UPGRADEABLE_FALLBACK_SOURCES,
    prefer_stored_or_primary_asset,
)
from artwork.targets import (
    ArtworkTarget,
    MediaType,
)


class MovieExecutionPath(
    str,
    Enum,
):
    DISCOVERED = "discovered"
    REFRESHED = "refreshed"
    MIGRATED = "migrated"
    KEEP_CURRENT = "keep_current"

    NO_CANDIDATES = "no_candidates"
    NO_USABLE_CANDIDATE = (
        "no_usable_candidate"
    )

    PROVIDER_UNAVAILABLE = (
        "provider_unavailable"
    )

    PROVIDER_ERROR = (
        "provider_error"
    )

    MISSING_SET_CONTEXT = (
        "missing_set_context"
    )


@dataclass(frozen=True)
class MovieExecutionResult:
    """One movie's read-only provider execution result."""

    inventory: MovieInventory

    current_state: MovieArtworkState | None

    state: MovieArtworkState | None

    path: MovieExecutionPath

    action: SetAction | None = None

    reason: str = ""

    provider_requested: bool = False
    provider_candidate_count: int = 0

    error_type: str | None = None
    error_message: str | None = None

    @property
    def resolved(
        self,
    ) -> bool:
        return self.state is not None


@dataclass(frozen=True)
class MovieTargetExecution:
    """Reconciliation plus provider execution for one movie target."""

    reconciliation: MovieTargetReconciliation

    results: tuple[
        MovieExecutionResult,
        ...,
    ]

    tmdb_coverage: tuple[
        MovieTMDBFallbackResult,
        ...,
    ] = ()

    coverage_enabled: bool = False

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
    def provider_unavailable_count(
        self,
    ) -> int:
        return sum(
            1
            for result in self.results
            if (
                result.path
                is MovieExecutionPath
                .PROVIDER_UNAVAILABLE
            )
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
                is MovieExecutionPath
                .PROVIDER_ERROR
            )
        )

    @property
    def discovered_count(
        self,
    ) -> int:
        return sum(
            1
            for result in self.results
            if (
                result.path
                is MovieExecutionPath
                .DISCOVERED
            )
        )

    @property
    def migration_count(
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
    def refresh_count(
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
    def identity_enrichment_request_count(
        self,
    ) -> int:
        return 0

    @property
    def identity_enriched_count(
        self,
    ) -> int:
        return 0

    @property
    def identity_enrichment_error_count(
        self,
    ) -> int:
        return 0

    @property
    def tmdb_request_count(
        self,
    ) -> int:
        return sum(
            result.request_count
            for result
            in self.tmdb_coverage
        )

    @property
    def tmdb_provider_error_count(
        self,
    ) -> int:
        return sum(
            result.provider_error_count
            for result
            in self.tmdb_coverage
        )

    @property
    def tmdb_created_count(
        self,
    ) -> int:
        return sum(
            1
            for result
            in self.tmdb_coverage
            if result.created
        )

    @property
    def tmdb_changed_count(
        self,
    ) -> int:
        return sum(
            1
            for result
            in self.tmdb_coverage
            if result.changed
        )

    @property
    def tmdb_gap_fill_count(
        self,
    ) -> int:
        return sum(
            result.gaps_filled
            for result
            in self.tmdb_coverage
        )

    @property
    def tmdb_gap_remaining_count(
        self,
    ) -> int:
        return sum(
            result.gaps_remaining
            for result
            in self.tmdb_coverage
        )

    @property
    def resolved_items(
        self,
    ) -> tuple[
        tuple[
            MovieInventory,
            MovieArtworkState,
        ],
        ...,
    ]:
        if self.coverage_enabled:
            return tuple(
                (
                    result.inventory,
                    result.state,
                )
                for result
                in self.tmdb_coverage
                if result.state is not None
            )

        return tuple(
            (
                result.inventory,
                result.state,
            )
            for result in self.results
            if result.state is not None
        )

    @property
    def resolved_states(
        self,
    ) -> tuple[
        MovieArtworkState,
        ...,
    ]:
        return tuple(
            state
            for _, state
            in self.resolved_items
        )


def _asset_available(
    asset,
) -> bool:
    return bool(
        asset is not None
        and asset.available
    )


def _set_quality(
    artwork_set: ArtworkSet,
) -> tuple[
    int,
    bool,
    bool,
]:
    poster = _asset_available(
        artwork_set.poster
    )

    background = _asset_available(
        artwork_set.background
    )

    return (
        int(poster)
        + int(background),
        poster,
        background,
    )


def _state_quality(
    state: MovieArtworkState,
) -> tuple[
    int,
    bool,
    bool,
]:
    poster = _asset_available(
        state.poster
    )

    background = _asset_available(
        state.background
    )

    return (
        int(poster)
        + int(background),
        poster,
        background,
    )


def _usable_set(
    artwork_set: ArtworkSet,
) -> bool:
    return (
        _asset_available(
            artwork_set.poster
        )
        or _asset_available(
            artwork_set.background
        )
    )


def _set_key(
    artwork_set: ArtworkSet,
) -> tuple[str, str]:
    return (
        artwork_set.provider.value,
        artwork_set.set_id,
    )


def _choose_best(
    artwork_sets,
    *,
    preferred:
        tuple[
            ArtworkSource,
            str,
        ]
        | None = None,
) -> ArtworkSet | None:
    usable = tuple(
        artwork_set
        for artwork_set
        in artwork_sets
        if _usable_set(
            artwork_set
        )
    )

    if not usable:
        return None

    best_quality = max(
        _set_quality(
            artwork_set
        )
        for artwork_set
        in usable
    )

    tied = tuple(
        artwork_set
        for artwork_set
        in usable
        if (
            _set_quality(
                artwork_set
            )
            == best_quality
        )
    )

    if preferred is not None:
        for artwork_set in tied:
            if (
                artwork_set.provider
                is preferred[0]
                and artwork_set.set_id
                == preferred[1]
            ):
                return artwork_set

    return min(
        tied,
        key=_set_key,
    )


def _request(
    *,
    inventory: MovieInventory,
    kind: ArtworkSearchKind,
    current_state:
        MovieArtworkState | None = None,
) -> ArtworkSearchRequest:
    identity = (
        inventory.identity
    )

    return ArtworkSearchRequest(
        library=identity.library,
        plex_rating_key=(
            identity.plex_rating_key
        ),
        title=identity.title,
        year=identity.year,
        tvdb_id=None,
        tmdb_id=(
            identity.tmdb_id
            if identity.tmdb_id is not None
            else (
                current_state.tmdb_id
                if current_state is not None
                else None
            )
        ),
        imdb_id=(
            identity.imdb_id
            if identity.imdb_id is not None
            else (
                current_state.imdb_id
                if current_state is not None
                else None
            )
        ),
        seasons=(),
        kind=kind,
        media_type=MediaType.MOVIE,
        current_set_id=(
            current_state.selected_set_id
            if current_state is not None
            else None
        ),
        current_set_source=(
            current_state
            .selected_set_source
            if current_state is not None
            else None
        ),
        current_creator=(
            current_state
            .selected_creator
            if current_state is not None
            else None
        ),
        selection_mode=(
            current_state.selection_mode
            if current_state is not None
            else SelectionMode.AUTO
        ),
    )


def _state_from_set(
    *,
    inventory: MovieInventory,
    artwork_set: ArtworkSet,
    selection_mode:
        SelectionMode = SelectionMode.AUTO,
) -> MovieArtworkState:
    identity = inventory.identity

    return MovieArtworkState(
        title=identity.title,
        tmdb_id=identity.tmdb_id,
        imdb_id=identity.imdb_id,
        poster=(
            artwork_set.poster
            if _asset_available(
                artwork_set.poster
            )
            else None
        ),
        background=(
            artwork_set.background
            if _asset_available(
                artwork_set.background
            )
            else None
        ),
        selected_set_id=(
            artwork_set.set_id
        ),
        selected_set_source=(
            artwork_set.provider
        ),
        selected_creator=(
            artwork_set.creator
        ),
        selection_mode=(
            selection_mode
        ),
    )


def _same_selected_set(
    state: MovieArtworkState,
    artwork_set: ArtworkSet,
) -> bool:
    return (
        state.selected_set_source
        is artwork_set.provider
        and state.selected_set_id
        == artwork_set.set_id
    )


def _merge_live_selected_set(
    *,
    inventory: MovieInventory,
    current: MovieArtworkState,
    live: ArtworkSet,
) -> MovieArtworkState:
    """Refresh one selected set without destructive artwork churn."""

    identity = inventory.identity

    return MovieArtworkState(
        title=identity.title,
        tmdb_id=(
            identity.tmdb_id
            if identity.tmdb_id is not None
            else current.tmdb_id
        ),
        imdb_id=(
            identity.imdb_id
            if identity.imdb_id is not None
            else current.imdb_id
        ),
        poster=(
            prefer_stored_or_primary_asset(
                current.poster,
                live.poster,
                primary_provider=(
                    live.provider
                ),
            )
        ),
        background=(
            prefer_stored_or_primary_asset(
                current.background,
                live.background,
                primary_provider=(
                    live.provider
                ),
            )
        ),
        selected_set_id=(
            live.set_id
        ),
        selected_set_source=(
            live.provider
        ),
        selected_creator=(
            live.creator
        ),
        selection_mode=(
            current.selection_mode
        ),
    )


def _fallback_only_state(
    state: MovieArtworkState,
) -> bool:
    if (
        state.selected_set_id is not None
        or state.selected_set_source
        is not None
    ):
        return False

    assets = tuple(
        asset
        for asset in (
            state.poster,
            state.background,
        )
        if _asset_available(
            asset
        )
    )

    return (
        bool(assets)
        and all(
            asset.source
            in UPGRADEABLE_FALLBACK_SOURCES
            for asset in assets
        )
    )


def _provider_sets(
    *,
    provider: ArtworkProvider,
    request: ArtworkSearchRequest,
):
    return provider.find_sets(
        request
    )


def discover_movie(
    *,
    inventory: MovieInventory,
    provider: ArtworkProvider,
) -> MovieExecutionResult:
    """Discover a cohesive provider set for one unmanaged movie."""

    request = _request(
        inventory=inventory,
        kind=(
            ArtworkSearchKind
            .DISCOVERY
        ),
    )

    try:
        artwork_sets = (
            _provider_sets(
                provider=provider,
                request=request,
            )
        )

    except ArtworkProviderUnavailableError as exc:
        return MovieExecutionResult(
            inventory=inventory,
            current_state=None,
            state=None,
            path=(
                MovieExecutionPath
                .PROVIDER_UNAVAILABLE
            ),
            provider_requested=True,
            error_type=type(
                exc
            ).__name__,
            error_message=str(
                exc
            ),
        )

    except Exception as exc:
        return MovieExecutionResult(
            inventory=inventory,
            current_state=None,
            state=None,
            path=(
                MovieExecutionPath
                .PROVIDER_ERROR
            ),
            provider_requested=True,
            error_type=type(
                exc
            ).__name__,
            error_message=str(
                exc
            ),
        )

    if not artwork_sets:
        return MovieExecutionResult(
            inventory=inventory,
            current_state=None,
            state=None,
            path=(
                MovieExecutionPath
                .NO_CANDIDATES
            ),
            provider_requested=True,
            provider_candidate_count=0,
        )

    selected = _choose_best(
        artwork_sets
    )

    if selected is None:
        return MovieExecutionResult(
            inventory=inventory,
            current_state=None,
            state=None,
            path=(
                MovieExecutionPath
                .NO_USABLE_CANDIDATE
            ),
            provider_requested=True,
            provider_candidate_count=len(
                artwork_sets
            ),
        )

    state = _state_from_set(
        inventory=inventory,
        artwork_set=selected,
    )

    return MovieExecutionResult(
        inventory=inventory,
        current_state=None,
        state=state,
        path=(
            MovieExecutionPath
            .DISCOVERED
        ),
        action=(
            SetAction.SELECT_SET
        ),
        reason=(
            "initial_movie_set_selected"
        ),
        provider_requested=True,
        provider_candidate_count=len(
            artwork_sets
        ),
    )


def execute_managed_movie(
    *,
    inventory: MovieInventory,
    current_state: MovieArtworkState,
    provider: ArtworkProvider,
) -> MovieExecutionResult:
    """Reevaluate one already-managed movie."""

    has_set_context = (
        current_state.selected_set_id
        is not None
        and current_state
        .selected_set_source
        is not None
    )

    fallback_only = (
        _fallback_only_state(
            current_state
        )
    )

    if (
        not has_set_context
        and not fallback_only
    ):
        return MovieExecutionResult(
            inventory=inventory,
            current_state=current_state,
            state=current_state,
            path=(
                MovieExecutionPath
                .MISSING_SET_CONTEXT
            ),
            action=(
                SetAction.KEEP_CURRENT
            ),
            reason=(
                "managed_movie_missing_set_context"
            ),
            provider_requested=False,
        )

    request = _request(
        inventory=inventory,
        kind=(
            ArtworkSearchKind
            .REEVALUATION
        ),
        current_state=(
            current_state
        ),
    )

    try:
        artwork_sets = (
            _provider_sets(
                provider=provider,
                request=request,
            )
        )

    except ArtworkProviderUnavailableError as exc:
        return MovieExecutionResult(
            inventory=inventory,
            current_state=current_state,
            state=current_state,
            path=(
                MovieExecutionPath
                .PROVIDER_UNAVAILABLE
            ),
            action=(
                SetAction.KEEP_CURRENT
            ),
            reason=(
                "movie_provider_unavailable"
            ),
            provider_requested=True,
            error_type=type(
                exc
            ).__name__,
            error_message=str(
                exc
            ),
        )

    except Exception as exc:
        return MovieExecutionResult(
            inventory=inventory,
            current_state=current_state,
            state=current_state,
            path=(
                MovieExecutionPath
                .PROVIDER_ERROR
            ),
            action=(
                SetAction.KEEP_CURRENT
            ),
            reason=(
                "movie_provider_error"
            ),
            provider_requested=True,
            error_type=type(
                exc
            ).__name__,
            error_message=str(
                exc
            ),
        )

    if not artwork_sets:
        return MovieExecutionResult(
            inventory=inventory,
            current_state=current_state,
            state=current_state,
            path=(
                MovieExecutionPath
                .NO_CANDIDATES
            ),
            action=(
                SetAction.KEEP_CURRENT
            ),
            reason=(
                "movie_provider_has_no_sets"
            ),
            provider_requested=True,
            provider_candidate_count=0,
        )

    usable_sets = tuple(
        artwork_set
        for artwork_set
        in artwork_sets
        if _usable_set(
            artwork_set
        )
    )

    if not usable_sets:
        return MovieExecutionResult(
            inventory=inventory,
            current_state=current_state,
            state=current_state,
            path=(
                MovieExecutionPath
                .NO_USABLE_CANDIDATE
            ),
            action=(
                SetAction.KEEP_CURRENT
            ),
            reason=(
                "movie_provider_has_no_usable_sets"
            ),
            provider_requested=True,
            provider_candidate_count=len(
                artwork_sets
            ),
        )

    if fallback_only:
        if (
            current_state.selection_mode
            is SelectionMode.LOCKED
        ):
            return MovieExecutionResult(
                inventory=inventory,
                current_state=current_state,
                state=current_state,
                path=(
                    MovieExecutionPath
                    .KEEP_CURRENT
                ),
                action=(
                    SetAction.KEEP_CURRENT
                ),
                reason=(
                    "fallback_selection_locked"
                ),
                provider_requested=True,
                provider_candidate_count=len(
                    artwork_sets
                ),
            )

        selected = _choose_best(
            usable_sets
        )

        state = _state_from_set(
            inventory=inventory,
            artwork_set=selected,
            selection_mode=(
                current_state
                .selection_mode
            ),
        )

        return MovieExecutionResult(
            inventory=inventory,
            current_state=current_state,
            state=state,
            path=(
                MovieExecutionPath
                .MIGRATED
            ),
            action=(
                SetAction.SET_MIGRATION
            ),
            reason=(
                "fallback_upgraded_to_primary"
            ),
            provider_requested=True,
            provider_candidate_count=len(
                artwork_sets
            ),
        )

    current_live = next(
        (
            artwork_set
            for artwork_set
            in usable_sets
            if _same_selected_set(
                current_state,
                artwork_set,
            )
        ),
        None,
    )

    baseline = current_state
    baseline_action = (
        SetAction.KEEP_CURRENT
    )
    baseline_path = (
        MovieExecutionPath
        .KEEP_CURRENT
    )
    baseline_reason = (
        "selected_movie_set_unchanged"
    )

    if current_live is not None:
        refreshed = (
            _merge_live_selected_set(
                inventory=inventory,
                current=current_state,
                live=current_live,
            )
        )

        if (
            _state_quality(
                refreshed
            )
            >= _state_quality(
                current_state
            )
            and refreshed
            != current_state
        ):
            baseline = refreshed
            baseline_action = (
                SetAction.SET_REFRESH
            )
            baseline_path = (
                MovieExecutionPath
                .REFRESHED
            )
            baseline_reason = (
                "selected_movie_set_refreshed"
            )

    if (
        current_state.selection_mode
        is SelectionMode.LOCKED
    ):
        return MovieExecutionResult(
            inventory=inventory,
            current_state=current_state,
            state=baseline,
            path=baseline_path,
            action=baseline_action,
            reason=(
                "selection_locked"
                if (
                    baseline_action
                    is SetAction.KEEP_CURRENT
                )
                else baseline_reason
            ),
            provider_requested=True,
            provider_candidate_count=len(
                artwork_sets
            ),
        )

    preferred = (
        (
            current_state
            .selected_set_source,
            current_state
            .selected_set_id,
        )
        if (
            current_state
            .selected_set_source
            is not None
            and current_state
            .selected_set_id
            is not None
        )
        else None
    )

    challenger = _choose_best(
        usable_sets,
        preferred=preferred,
    )

    if challenger is None:
        return MovieExecutionResult(
            inventory=inventory,
            current_state=current_state,
            state=baseline,
            path=baseline_path,
            action=baseline_action,
            reason=baseline_reason,
            provider_requested=True,
            provider_candidate_count=len(
                artwork_sets
            ),
        )

    if _same_selected_set(
        current_state,
        challenger,
    ):
        return MovieExecutionResult(
            inventory=inventory,
            current_state=current_state,
            state=baseline,
            path=baseline_path,
            action=baseline_action,
            reason=baseline_reason,
            provider_requested=True,
            provider_candidate_count=len(
                artwork_sets
            ),
        )

    if (
        _set_quality(
            challenger
        )
        <= _state_quality(
            baseline
        )
    ):
        return MovieExecutionResult(
            inventory=inventory,
            current_state=current_state,
            state=baseline,
            path=baseline_path,
            action=baseline_action,
            reason=(
                baseline_reason
                if (
                    baseline_action
                    is SetAction.SET_REFRESH
                )
                else (
                    "challenger_not_better"
                )
            ),
            provider_requested=True,
            provider_candidate_count=len(
                artwork_sets
            ),
        )

    migrated = _state_from_set(
        inventory=inventory,
        artwork_set=challenger,
        selection_mode=(
            current_state
            .selection_mode
        ),
    )

    return MovieExecutionResult(
        inventory=inventory,
        current_state=current_state,
        state=migrated,
        path=(
            MovieExecutionPath
            .MIGRATED
        ),
        action=(
            SetAction.SET_MIGRATION
        ),
        reason=(
            "stronger_movie_set_selected"
        ),
        provider_requested=True,
        provider_candidate_count=len(
            artwork_sets
        ),
    )


def execute_movie_target(
    *,
    target: ArtworkTarget,
    inventories: Iterable[
        MovieInventory
    ],
    managed_items: Iterable[
        StoredMovieArtworkState
    ],
    provider: ArtworkProvider,
    tmdb_client: TMDBArtworkClient | None = None,
    progress_callback:
        ArtworkProgressCallback
        | None = None,
) -> MovieTargetExecution:
    """Reconcile and execute one movie library without writes."""

    reconciliation = (
        reconcile_movie_target(
            target=target,
            inventories=inventories,
            managed_items=managed_items,
        )
    )

    results = []

    managed_total = len(
        reconciliation.matched
    )

    for index, reconciled in enumerate(
        reconciliation.matched,
        start=1,
    ):
        result = (
            execute_managed_movie(
                inventory=(
                    reconciled.inventory
                ),
                current_state=(
                    reconciled.artwork
                ),
                provider=provider,
            )
        )

        results.append(
            result
        )

        emit_artwork_progress(
            progress_callback,
            library=target.library,
            phase=(
                ArtworkScanPhase
                .PRIMARY_MANAGED
            ),
            completed=index,
            total=managed_total,
            message=(
                "Reevaluating managed "
                "movie artwork"
            ),
            current_title=(
                reconciled
                .inventory
                .identity
                .title
            ),
        )

    discovery_total = len(
        reconciliation.unmanaged
    )

    for index, inventory in enumerate(
        reconciliation.unmanaged,
        start=1,
    ):
        result = discover_movie(
            inventory=inventory,
            provider=provider,
        )

        results.append(
            result
        )

        emit_artwork_progress(
            progress_callback,
            library=target.library,
            phase=(
                ArtworkScanPhase
                .PRIMARY_DISCOVERY
            ),
            completed=index,
            total=discovery_total,
            message=(
                "Discovering movie artwork "
                "with the primary provider"
            ),
            current_title=(
                inventory
                .identity
                .title
            ),
        )

    primary_results = tuple(
        results
    )

    if tmdb_client is None:
        return MovieTargetExecution(
            reconciliation=reconciliation,
            results=primary_results,
        )

    coverage_results = []

    managed_completed = 0
    discovery_completed = 0

    for result in primary_results:
        is_managed = (
            result.current_state
            is not None
        )

        if (
            result.path
            is MovieExecutionPath
            .MISSING_SET_CONTEXT
        ):
            coverage = (
                skip_movie_tmdb_missing_set_context(
                    inventory=(
                        result.inventory
                    ),
                    state=result.state,
                )
            )

        else:
            coverage = (
                resolve_movie_tmdb_coverage(
                    inventory=(
                        result.inventory
                    ),
                    state=result.state,
                    client=tmdb_client,
                )
            )

        coverage_results.append(
            coverage
        )

        if is_managed:
            managed_completed += 1

            emit_artwork_progress(
                progress_callback,
                library=target.library,
                phase=(
                    ArtworkScanPhase
                    .TMDB_MANAGED
                ),
                completed=(
                    managed_completed
                ),
                total=managed_total,
                message=(
                    "Checking managed movie "
                    "artwork gaps with TMDB"
                ),
                current_title=(
                    result.inventory
                    .identity.title
                ),
            )

        else:
            discovery_completed += 1

            emit_artwork_progress(
                progress_callback,
                library=target.library,
                phase=(
                    ArtworkScanPhase
                    .TMDB_DISCOVERY
                ),
                completed=(
                    discovery_completed
                ),
                total=discovery_total,
                message=(
                    "Checking unmanaged movie "
                    "artwork gaps with TMDB"
                ),
                current_title=(
                    result.inventory
                    .identity.title
                ),
            )

    return MovieTargetExecution(
        reconciliation=reconciliation,
        results=primary_results,
        tmdb_coverage=tuple(
            coverage_results
        ),
        coverage_enabled=True,
    )
