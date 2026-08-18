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

from artwork.inventory import build_show_inventory
from artwork.item_store import (
    ItemStorePlan,
    build_show_item_store_plan,
)
from artwork.item_store_apply import (
    ItemStoreApplyResult,
    apply_show_item_store,
    item_store_plan_needs_apply,
)
from artwork.managed_state import (
    ManagedStateBaseline,
    load_show_managed_state_baseline,
)
from artwork.preview import (
    ArtworkTargetPreview,
    build_show_target_preview,
)
from artwork.providers.base import ArtworkProvider
from artwork.providers.tmdb import TMDBArtworkClient
from artwork.target_execution import (
    ShowTargetExecution,
    execute_show_target,
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
    baseline: ManagedStateBaseline
    execution: ShowTargetExecution
    preview: ArtworkTargetPreview
    plan: ItemStorePlan

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
        return self.plan.desired_count

    @property
    def added_count(self) -> int:
        return self.plan.added_count

    @property
    def updated_count(self) -> int:
        return self.plan.updated_count

    @property
    def removed_count(self) -> int:
        return self.plan.removed_count

    @property
    def changed_file_count(self) -> int:
        return (
            self.added_count
            + self.updated_count
            + self.removed_count
        )

    @property
    def needs_apply(self) -> bool:
        """Whether transactional persistence would change durable state."""

        return (
            item_store_plan_needs_apply(
                self.plan
            )
        )


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


def build_artwork_manager_workflow(
    *,
    plex,
    config: dict,
    provider: ArtworkProvider,
    tmdb_client: TMDBArtworkClient | None = None,
    selected_libraries: str | Iterable[str] | None = None,
    legacy_metadata_by_library: Mapping[
        str,
        str | Path,
    ]
    | None = None,
    incomplete_migration_threshold: float = 0.25,
) -> ArtworkManagerWorkflow:
    """Build the complete read-only Artwork Manager workflow.

    Plex library discovery is authoritative. Library names are treated as
    opaque exact names and have no Dakosys-specific roles.

    ``selected_libraries`` may restrict execution to exact discovered Plex
    library names without changing configuration.

    ``legacy_metadata_by_library`` is an explicit one-time migration input.
    Legacy metadata is never inferred from the name of a Plex library.
    Durable state remains authoritative whenever it already exists.

    This function performs provider reads but does not write item stores.
    """

    targets = discover_artwork_targets(
        plex,
        config,
    )

    targets_by_library = {
        target.library: target
        for target in targets
    }

    selected = _normalize_selected_libraries(
        selected_libraries
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

        selected_names = set(selected)

        execution_targets = tuple(
            target
            for target in targets
            if target.library in selected_names
        )
    else:
        execution_targets = targets

    legacy = _normalize_legacy_metadata(
        legacy_metadata_by_library
    )

    show_target_names = {
        target.library
        for target in targets
        if target.media_type is MediaType.SHOW
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

    library_runs: list[
        ArtworkLibraryWorkflow
    ] = []

    skipped: list[
        SkippedArtworkWorkflowTarget
    ] = []

    for target in execution_targets:
        if target.media_type is MediaType.MOVIE:
            skipped.append(
                SkippedArtworkWorkflowTarget(
                    target=target,
                    reason=(
                        ArtworkWorkflowSkipReason
                        .MOVIE_SUPPORT_PENDING
                    ),
                )
            )
            continue

        if target.media_type is not MediaType.SHOW:
            raise ValueError(
                "unsupported Artwork Manager media type "
                f"{target.media_type!r}"
            )

        baseline = load_show_managed_state_baseline(
            directory=target.output_path,
            library=target.library,
            legacy_metadata=legacy.get(
                target.library
            ),
        )

        section = plex.library.section(
            target.library
        )

        inventories = tuple(
            build_show_inventory(
                show,
                target.library,
            )
            for show in section.all()
        )

        execution = execute_show_target(
            target=target,
            inventories=inventories,
            managed_shows=baseline.states,
            provider=provider,
            tmdb_client=tmdb_client,
            incomplete_migration_threshold=(
                incomplete_migration_threshold
            ),
        )

        preview = build_show_target_preview(
            execution
        )

        plan = build_show_item_store_plan(
            execution
        )

        library_runs.append(
            ArtworkLibraryWorkflow(
                target=target,
                baseline=baseline,
                execution=execution,
                preview=preview,
                plan=plan,
            )
        )

    return ArtworkManagerWorkflow(
        libraries=tuple(library_runs),
        skipped=tuple(skipped),
    )


def apply_artwork_library_workflow(
    run: ArtworkLibraryWorkflow,
) -> ItemStoreApplyResult:
    """Persist one previously reviewed library workflow transactionally.

    The underlying apply layer revalidates both the semantic preview and
    filesystem plan before making any changes.
    """

    return apply_show_item_store(
        execution=run.execution,
        preview=run.preview,
        plan=run.plan,
    )
