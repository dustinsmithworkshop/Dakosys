"""High-level Artwork Manager workflow orchestration.

This module is the application-facing Artwork Manager boundary.

It composes dynamic Plex target discovery, durable managed-state loading,
provider execution, semantic preview, item-store planning, and reviewed
transactional apply.

Library names are opaque Plex identities. Dakosys does not assign special
meaning to names such as TV, Anime, Cartoons, Series, or Movies.

Building a workflow is read-only. Persistence is exposed separately and
operates on one reviewed library workflow at a time.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from artwork.episode_coverage import (
    EpisodeGeneratorOptions,
)
from artwork.inventory import build_show_inventory
from artwork.movie_inventory import (
    build_movie_inventory,
)
from artwork.item_store import (
    ItemStorePlan,
    build_show_item_store_plan,
)
from artwork.item_store_bootstrap import (
    load_show_item_store_bootstrap_seeds,
)
from artwork.item_store_bootstrap_resolver import (
    resolve_show_item_store_bootstrap,
)
from artwork.movie_item_store import (
    MovieItemStorePlan,
    build_movie_item_store_plan,
)
from artwork.item_store_apply import (
    ItemStoreApplyResult,
    apply_show_item_store,
    item_store_plan_needs_apply,
)
from artwork.movie_item_store_apply import (
    apply_movie_item_store,
)
from artwork.managed_state import (
    ManagedStateBaseline,
    ManagedStateBaselineSource,
    load_show_managed_state_baseline,
)
from artwork.migration import (
    import_mediux_metadata,
)
from artwork.movie_managed_state import (
    MovieManagedStateBaseline,
    load_movie_managed_state_baseline,
)
from artwork.preview import (
    ArtworkTargetPreview,
    PreviewIssueCode,
    build_show_target_preview,
)
from artwork.movie_preview import (
    MovieArtworkTargetPreview,
    build_movie_target_preview,
)
from artwork.progress import (
    ArtworkProgressCallback,
    ArtworkScanPhase,
    emit_artwork_progress,
)
from artwork.providers.base import ArtworkProvider
from artwork.providers.tmdb import TMDBArtworkClient
from artwork.target_execution import (
    ShowTargetExecution,
    execute_show_target,
)
from artwork.movie_execution import (
    MovieTargetExecution,
    execute_movie_target,
)
from artwork.targets import (
    ArtworkTarget,
    MediaType,
    discover_artwork_targets,
)


class ArtworkWorkflowSkipReason(str, Enum):
    """Why a discovered target cannot currently execute."""

    MOVIE_SUPPORT_PENDING = "movie_support_pending"


@dataclass(frozen=True)
class SkippedArtworkWorkflowTarget:
    """A dynamically discovered target not yet executable."""

    target: ArtworkTarget
    reason: ArtworkWorkflowSkipReason


@dataclass(frozen=True)
class ArtworkLibraryWorkflow:
    """Complete reviewed state for one show-library execution."""

    target: ArtworkTarget
    baseline: (
        ManagedStateBaseline
        | MovieManagedStateBaseline
    )
    execution: (
        ShowTargetExecution
        | MovieTargetExecution
    )
    preview: (
        ArtworkTargetPreview
        | MovieArtworkTargetPreview
    )
    plan: (
        ItemStorePlan
        | MovieItemStorePlan
        | None
    )

    @property
    def library(self) -> str:
        return self.target.library

    @property
    def output_path(self) -> Path:
        return self.target.output_path

    @property
    def safe_to_apply(self) -> bool:
        return self.preview.safe_to_apply

    @property
    def desired_count(self) -> int:
        return (
            self.plan.desired_count
            if self.plan is not None
            else 0
        )

    @property
    def added_count(self) -> int:
        return (
            self.plan.added_count
            if self.plan is not None
            else 0
        )

    @property
    def updated_count(self) -> int:
        return (
            self.plan.updated_count
            if self.plan is not None
            else 0
        )

    @property
    def removed_count(self) -> int:
        return (
            self.plan.removed_count
            if self.plan is not None
            else 0
        )

    @property
    def changed_file_count(self) -> int:
        return (
            self.added_count
            + self.updated_count
            + self.removed_count
        )

    @property
    def generator_materialization_needed_count(
        self,
    ) -> int:
        """Generated files that reviewed APPLY still needs to create."""

        if (
            self.target.media_type
            is not MediaType.SHOW
        ):
            return 0

        return int(
            getattr(
                self.execution,
                "generator_materialization_needed_count",
                0,
            )
            or 0
        )

    @property
    def needs_apply(self) -> bool:
        """Whether reviewed APPLY still has durable work to perform."""

        if self.plan is None:
            return False

        return (
            item_store_plan_needs_apply(
                self.plan
            )
            or (
                self.generator_materialization_needed_count
                > 0
            )
        )

    @property
    def plan_available(self) -> bool:
        return self.plan is not None


@dataclass(frozen=True)
class ArtworkManagerWorkflow:
    """Read-only Artwork Manager workflow across selected Plex targets."""

    libraries: tuple[ArtworkLibraryWorkflow, ...]
    skipped: tuple[SkippedArtworkWorkflowTarget, ...]

    @property
    def library_count(self) -> int:
        return len(self.libraries)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)

    @property
    def safe_to_apply(self) -> bool:
        return all(
            library.safe_to_apply
            for library in self.libraries
        )

    @property
    def changed_file_count(self) -> int:
        return sum(
            library.changed_file_count
            for library in self.libraries
        )

    def run_for_library(
        self,
        library: str,
    ) -> ArtworkLibraryWorkflow | None:
        """Return the reviewed workflow for one exact Plex library name."""

        for run in self.libraries:
            if run.library == library:
                return run

        return None


def _normalize_selected_libraries(
    libraries: str | Iterable[str] | None,
) -> tuple[str, ...] | None:
    if libraries is None:
        return None

    if isinstance(libraries, str):
        raw_values = (libraries,)
    else:
        raw_values = tuple(libraries)

    normalized: list[str] = []

    for raw_value in raw_values:
        if not isinstance(raw_value, str):
            raise ValueError(
                "selected Artwork Manager library names must be strings"
            )

        value = raw_value.strip()

        if not value:
            raise ValueError(
                "selected Artwork Manager library name cannot be empty"
            )

        if value not in normalized:
            normalized.append(value)

    return tuple(normalized)


def _normalize_legacy_metadata(
    legacy_metadata_by_library: Mapping[
        str,
        str | Path,
    ]
    | None,
) -> dict[str, Path]:
    if legacy_metadata_by_library is None:
        return {}

    result: dict[str, Path] = {}

    for raw_library, raw_path in legacy_metadata_by_library.items():
        if not isinstance(raw_library, str):
            raise ValueError(
                "legacy Artwork Manager library names must be strings"
            )

        library = raw_library.strip()

        if not library:
            raise ValueError(
                "legacy Artwork Manager library name cannot be empty"
            )

        if raw_path is None:
            raise ValueError(
                f"legacy metadata path for {library!r} cannot be empty"
            )

        path_text = str(raw_path).strip()

        if not path_text:
            raise ValueError(
                f"legacy metadata path for {library!r} cannot be empty"
            )

        if library in result:
            raise ValueError(
                f"duplicate legacy metadata source for {library!r}"
            )

        result[library] = Path(path_text)

    return result


def resolve_artwork_workflow_targets(
    targets: Iterable[ArtworkTarget],
    *,
    selected_libraries: (
        str
        | Iterable[str]
        | None
    ) = None,
    legacy_metadata_by_library: Mapping[
        str,
        str | Path,
    ]
    | None = None,
) -> tuple[
    tuple[ArtworkTarget, ...],
    dict[str, Path],
]:
    """Resolve exact execution targets from one discovery snapshot."""

    targets = tuple(
        targets
    )

    targets_by_library = {
        target.library: target
        for target in targets
    }

    selected = (
        _normalize_selected_libraries(
            selected_libraries
        )
    )

    if selected is not None:
        unknown_selected = sorted(
            set(selected)
            - set(targets_by_library),
            key=str.casefold,
        )

        if unknown_selected:
            formatted = ", ".join(
                repr(name)
                for name in unknown_selected
            )

            raise ValueError(
                "selected Artwork Manager libraries "
                "were not discovered in Plex: "
                f"{formatted}"
            )

        selected_names = set(
            selected
        )

        execution_targets = tuple(
            target
            for target in targets
            if (
                target.library
                in selected_names
            )
        )

    else:
        execution_targets = (
            targets
        )

    legacy = (
        _normalize_legacy_metadata(
            legacy_metadata_by_library
        )
    )

    show_target_names = {
        target.library
        for target in targets
        if (
            target.media_type
            is MediaType.SHOW
        )
    }

    unknown_legacy = sorted(
        set(legacy)
        - show_target_names,
        key=str.casefold,
    )

    if unknown_legacy:
        formatted = ", ".join(
            repr(name)
            for name in unknown_legacy
        )

        raise ValueError(
            "legacy Artwork Manager metadata was provided "
            "for libraries that are not discovered show targets: "
            f"{formatted}"
        )

    return (
        execution_targets,
        legacy,
    )


def build_movie_artwork_target_workflow(
    *,
    plex,
    target: ArtworkTarget,
    provider: ArtworkProvider,
    tmdb_client: TMDBArtworkClient | None = None,
    progress_callback: ArtworkProgressCallback | None = None,
) -> ArtworkLibraryWorkflow:
    """Build one already-discovered movie target read-only."""

    if (
        target.media_type
        is not MediaType.MOVIE
    ):
        raise ValueError(
            "movie Artwork Manager workflow "
            "requires a movie target"
        )

    baseline = (
        load_movie_managed_state_baseline(
            directory=target.output_path,
            library=target.library,
        )
    )

    section = plex.library.section(
        target.library
    )

    movies = tuple(
        section.all()
    )

    inventory_results = []

    total_movies = len(
        movies
    )

    for index, movie in enumerate(
        movies,
        start=1,
    ):
        inventory = (
            build_movie_inventory(
                movie,
                target.library,
            )
        )

        inventory_results.append(
            inventory
        )

        emit_artwork_progress(
            progress_callback,
            library=target.library,
            phase=(
                ArtworkScanPhase
                .INVENTORY
            ),
            completed=index,
            total=total_movies,
            message=(
                "Reading Plex movie inventory"
            ),
            current_title=(
                inventory.identity.title
            ),
        )

    execution = execute_movie_target(
        target=target,
        inventories=tuple(
            inventory_results
        ),
        managed_items=baseline.items,
        provider=provider,
        tmdb_client=tmdb_client,
        progress_callback=(
            progress_callback
        ),
    )

    preview = (
        build_movie_target_preview(
            execution
        )
    )

    emit_artwork_progress(
        progress_callback,
        library=target.library,
        phase=(
            ArtworkScanPhase.PLANNING
        ),
        completed=1,
        total=2,
        message=(
            "Evaluating movie safety "
            "and changes"
        ),
    )

    unplannable_codes = {
        PreviewIssueCode
        .OUTPUT_IDENTITY_MISSING,
        PreviewIssueCode
        .KOMETA_RENDER_ERROR,
    }

    unplannable = any(
        issue.code in unplannable_codes
        for issue in preview.issues
    )

    plan = (
        None
        if unplannable
        else build_movie_item_store_plan(
            library=target.library,
            directory=target.output_path,
            items=(
                execution
                .resolved_items
            ),
        )
    )

    emit_artwork_progress(
        progress_callback,
        library=target.library,
        phase=(
            ArtworkScanPhase.PLANNING
        ),
        completed=2,
        total=2,
        message=(
            "Planning Artwork Manager "
            "movie output"
        ),
    )

    run = ArtworkLibraryWorkflow(
        target=target,
        baseline=baseline,
        execution=execution,
        preview=preview,
        plan=plan,
    )

    emit_artwork_progress(
        progress_callback,
        library=target.library,
        phase=(
            ArtworkScanPhase.COMPLETE
        ),
        completed=1,
        total=1,
        message=(
            "Current-state movie scan complete"
        ),
    )

    return run


def build_artwork_target_workflow(
    *,
    plex,
    target: ArtworkTarget,
    provider: ArtworkProvider,
    tmdb_client: TMDBArtworkClient | None = None,
    generator_options: (
        EpisodeGeneratorOptions
        | None
    ) = None,
    legacy_metadata: str | Path | None = None,
    incomplete_migration_threshold: float = 0.25,
    progress_callback: ArtworkProgressCallback | None = None,
) -> ArtworkLibraryWorkflow:
    """Build one already-discovered Artwork Manager target."""

    if (
        target.media_type
        is MediaType.MOVIE
    ):
        if legacy_metadata is not None:
            raise ValueError(
                "legacy show metadata cannot "
                "bootstrap a movie target"
            )

        return (
            build_movie_artwork_target_workflow(
                plex=plex,
                target=target,
                provider=provider,
                tmdb_client=tmdb_client,
                progress_callback=(
                    progress_callback
                ),
            )
        )

    if (
        target.media_type
        is not MediaType.SHOW
    ):
        raise ValueError(
            "unsupported Artwork Manager "
            "target media type"
        )

    baseline = (
        load_show_managed_state_baseline(
            directory=target.output_path,
            library=target.library,
            legacy_metadata=(
                legacy_metadata
            ),
        )
    )

    section = plex.library.section(
        target.library
    )

    shows = tuple(
        section.all()
    )

    inventory_results = []

    total_shows = len(
        shows
    )

    for index, show in enumerate(
        shows,
        start=1,
    ):
        inventory = (
            build_show_inventory(
                show,
                target.library,
            )
        )

        inventory_results.append(
            inventory
        )

        emit_artwork_progress(
            progress_callback,
            library=target.library,
            phase=(
                ArtworkScanPhase
                .INVENTORY
            ),
            completed=index,
            total=total_shows,
            message=(
                "Reading Plex library inventory"
            ),
            current_title=(
                getattr(
                    getattr(
                        inventory,
                        "identity",
                        None,
                    ),
                    "title",
                    None,
                )
            ),
        )

    inventories = tuple(
        inventory_results
    )

    if (
        baseline.source
        is ManagedStateBaselineSource
        .ITEM_STORE_BOOTSTRAP
    ):
        if legacy_metadata is None:
            raise RuntimeError(
                "pre-state-store bootstrap "
                "requires explicit historical metadata"
            )

        seeds = (
            load_show_item_store_bootstrap_seeds(
                directory=target.output_path,
                expected_library=target.library,
            )
        )

        legacy_states = tuple(
            import_mediux_metadata(
                legacy_metadata
            )
        )

        bootstrap = (
            resolve_show_item_store_bootstrap(
                seeds=seeds,
                inventories=inventories,
                provider=provider,
                legacy_states=legacy_states,
            )
        )

        baseline = ManagedStateBaseline(
            library=baseline.library,
            states=bootstrap.states,
            source=baseline.source,
            manifest=baseline.manifest,
            state_store=baseline.state_store,
        )

    execution_options = {}

    if progress_callback is not None:
        execution_options[
            "progress_callback"
        ] = progress_callback

    execution = execute_show_target(
        target=target,
        inventories=inventories,
        managed_shows=baseline.states,
        provider=provider,
        tmdb_client=tmdb_client,
        generator_options=(
            generator_options
        ),
        incomplete_migration_threshold=(
            incomplete_migration_threshold
        ),
        **execution_options,
    )

    preview = (
        build_show_target_preview(
            execution
        )
    )

    emit_artwork_progress(
        progress_callback,
        library=target.library,
        phase=(
            ArtworkScanPhase.PLANNING
        ),
        completed=1,
        total=2,
        message=(
            "Evaluating safety and changes"
        ),
    )

    unplannable_codes = {
        PreviewIssueCode
        .OUTPUT_IDENTITY_MISSING,
        PreviewIssueCode
        .KOMETA_RENDER_ERROR,
    }

    unplannable = any(
        issue.code in unplannable_codes
        for issue in preview.issues
    )

    plan = (
        None
        if unplannable
        else build_show_item_store_plan(
            execution
        )
    )

    emit_artwork_progress(
        progress_callback,
        library=target.library,
        phase=(
            ArtworkScanPhase.PLANNING
        ),
        completed=2,
        total=2,
        message=(
            "Planning Artwork Manager output"
        ),
    )

    run = ArtworkLibraryWorkflow(
        target=target,
        baseline=baseline,
        execution=execution,
        preview=preview,
        plan=plan,
    )

    emit_artwork_progress(
        progress_callback,
        library=target.library,
        phase=(
            ArtworkScanPhase.COMPLETE
        ),
        completed=1,
        total=1,
        message=(
            "Current-state scan complete"
        ),
    )

    return run


def build_artwork_manager_workflow(
    *,
    plex,
    config: dict,
    provider: ArtworkProvider,
    tmdb_client: TMDBArtworkClient | None = None,
    generator_options: (
        EpisodeGeneratorOptions
        | None
    ) = None,
    selected_libraries: str | Iterable[str] | None = None,
    legacy_metadata_by_library: Mapping[
        str,
        str | Path,
    ]
    | None = None,
    incomplete_migration_threshold: float = 0.25,
    progress_callback: ArtworkProgressCallback | None = None,
) -> ArtworkManagerWorkflow:
    """Build the complete read-only Artwork Manager workflow."""

    targets = (
        discover_artwork_targets(
            plex,
            config,
        )
    )

    (
        execution_targets,
        legacy,
    ) = resolve_artwork_workflow_targets(
        targets,
        selected_libraries=(
            selected_libraries
        ),
        legacy_metadata_by_library=(
            legacy_metadata_by_library
        ),
    )

    library_runs: list[
        ArtworkLibraryWorkflow
    ] = []

    skipped: list[
        SkippedArtworkWorkflowTarget
    ] = []

    for target in execution_targets:
        library_runs.append(
            build_artwork_target_workflow(
                plex=plex,
                target=target,
                provider=provider,
                tmdb_client=tmdb_client,
                generator_options=(
                    generator_options
                ),
                legacy_metadata=(
                    legacy.get(
                        target.library
                    )
                ),
                incomplete_migration_threshold=(
                    incomplete_migration_threshold
                ),
                progress_callback=(
                    progress_callback
                ),
            )
        )

    return ArtworkManagerWorkflow(
        libraries=tuple(
            library_runs
        ),
        skipped=tuple(
            skipped
        ),
    )


def apply_artwork_library_workflow(
    run: ArtworkLibraryWorkflow,
) -> ItemStoreApplyResult:
    """Persist one previously reviewed library workflow transactionally.

    The underlying apply layer revalidates both the semantic preview and
    filesystem plan before making any changes.
    """

    if run.plan is None:
        raise RuntimeError(
            "Artwork Manager workflow has no "
            "safe filesystem plan"
        )

    if (
        run.target.media_type
        is MediaType.MOVIE
    ):
        return apply_movie_item_store(
            execution=run.execution,
            preview=run.preview,
            plan=run.plan,
        )

    return apply_show_item_store(
        execution=run.execution,
        preview=run.preview,
        plan=run.plan,
    )
