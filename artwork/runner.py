"""Apply-mode-aware execution of reviewed Artwork Manager workflows."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from artwork.apply_policy import (
    ArtworkApplyMode,
)
from artwork.item_store_apply import (
    ItemStoreApplyResult,
)
from artwork.review import (
    build_artwork_review_fingerprint,
)
from artwork.targets import (
    ArtworkTarget,
)
from artwork.workflow import (
    ArtworkLibraryWorkflow,
    ArtworkManagerWorkflow,
    SkippedArtworkWorkflowTarget,
    apply_artwork_library_workflow,
)


class ArtworkRunOutcome(str, Enum):
    """Operational result for one Artwork Manager library."""

    APPLIED = "applied"
    NO_CHANGES = "no_changes"
    PENDING_REVIEW = "pending_review"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True)
class ArtworkLibraryRunResult:
    """Outcome for one discovered executable library."""

    workflow: ArtworkLibraryWorkflow
    apply_mode: ArtworkApplyMode
    outcome: ArtworkRunOutcome

    apply_result: (
        ItemStoreApplyResult | None
    ) = None

    error_type: str | None = None
    error_message: str | None = None

    review_fingerprint: str | None = None

    # Snapshot taken before any automatic apply mutates the live
    # filesystem. History must describe why this run acted, not only
    # what the filesystem looks like afterward.
    planned_needs_apply: bool = False

    @property
    def library(self) -> str:
        return self.workflow.library

    @property
    def safe_to_apply(self) -> bool:
        return (
            self.workflow.safe_to_apply
        )

    @property
    def needs_apply(self) -> bool:
        return (
            self.planned_needs_apply
        )


@dataclass(frozen=True)
class ArtworkLibraryRunFailure:
    """Outcome for a discovered library that could not build a workflow."""

    target: ArtworkTarget
    apply_mode: ArtworkApplyMode
    outcome: ArtworkRunOutcome
    error_type: str
    error_message: str

    def __post_init__(
        self,
    ) -> None:
        if self.outcome not in {
            ArtworkRunOutcome.BLOCKED,
            ArtworkRunOutcome.FAILED,
        }:
            raise ValueError(
                "pre-workflow library results "
                "must be BLOCKED or FAILED"
            )

    @property
    def library(self) -> str:
        return self.target.library

    @property
    def safe_to_apply(self) -> bool:
        return False

    @property
    def needs_apply(self) -> bool:
        return False

    @property
    def apply_result(self):
        return None

    @property
    def review_fingerprint(self):
        return None


@dataclass(frozen=True)
class ArtworkManagerRunResult:
    """Aggregate policy result across Artwork Manager libraries."""

    apply_mode: ArtworkApplyMode

    libraries: tuple[
        ArtworkLibraryRunResult
        | ArtworkLibraryRunFailure,
        ...,
    ]

    skipped: tuple[
        SkippedArtworkWorkflowTarget,
        ...,
    ]

    def count(
        self,
        outcome: ArtworkRunOutcome,
    ) -> int:
        return sum(
            1
            for result
            in self.libraries
            if result.outcome is outcome
        )

    @property
    def applied_count(self) -> int:
        return self.count(
            ArtworkRunOutcome.APPLIED
        )

    @property
    def no_changes_count(self) -> int:
        return self.count(
            ArtworkRunOutcome.NO_CHANGES
        )

    @property
    def pending_review_count(self) -> int:
        return self.count(
            ArtworkRunOutcome
            .PENDING_REVIEW
        )

    @property
    def blocked_count(self) -> int:
        return self.count(
            ArtworkRunOutcome.BLOCKED
        )

    @property
    def failed_count(self) -> int:
        return self.count(
            ArtworkRunOutcome.FAILED
        )


def execute_artwork_library_workflow(
    run: ArtworkLibraryWorkflow,
    *,
    apply_mode: ArtworkApplyMode,
) -> ArtworkLibraryRunResult:
    """Execute one already-built library according to apply policy."""

    if not isinstance(
        apply_mode,
        ArtworkApplyMode,
    ):
        raise ValueError(
            "apply_mode must be an "
            "ArtworkApplyMode"
        )

    if not run.safe_to_apply:
        return ArtworkLibraryRunResult(
            workflow=run,
            apply_mode=apply_mode,
            planned_needs_apply=False,
            outcome=(
                ArtworkRunOutcome.BLOCKED
            ),
        )

    planned_needs_apply = (
        run.needs_apply
    )

    if not planned_needs_apply:
        return ArtworkLibraryRunResult(
            workflow=run,
            apply_mode=apply_mode,
            planned_needs_apply=(
                planned_needs_apply
            ),
            outcome=(
                ArtworkRunOutcome.NO_CHANGES
            ),
        )

    if (
        apply_mode
        is ArtworkApplyMode.MANUAL
    ):
        return ArtworkLibraryRunResult(
            workflow=run,
            apply_mode=apply_mode,
            planned_needs_apply=(
                planned_needs_apply
            ),
            outcome=(
                ArtworkRunOutcome
                .PENDING_REVIEW
            ),
            review_fingerprint=(
                build_artwork_review_fingerprint(
                    run
                )
            ),
        )

    try:
        apply_result = (
            apply_artwork_library_workflow(
                run
            )
        )

    except Exception as exc:
        return ArtworkLibraryRunResult(
            workflow=run,
            apply_mode=apply_mode,
            planned_needs_apply=(
                planned_needs_apply
            ),
            outcome=(
                ArtworkRunOutcome.FAILED
            ),
            error_type=(
                type(exc).__name__
            ),
            error_message=str(
                exc
            ),
        )

    outcome = (
        ArtworkRunOutcome.APPLIED
        if apply_result.changed
        else ArtworkRunOutcome.NO_CHANGES
    )

    return ArtworkLibraryRunResult(
        workflow=run,
        apply_mode=apply_mode,
        planned_needs_apply=(
            planned_needs_apply
        ),
        outcome=outcome,
        apply_result=apply_result,
    )


def execute_artwork_manager_workflow(
    workflow: ArtworkManagerWorkflow,
    *,
    apply_mode: ArtworkApplyMode,
) -> ArtworkManagerRunResult:
    """Execute one already-built workflow according to apply policy.

    Each library is evaluated independently. An apply failure in one
    library does not prevent later libraries from executing.
    """

    if not isinstance(
        apply_mode,
        ArtworkApplyMode,
    ):
        raise ValueError(
            "apply_mode must be an "
            "ArtworkApplyMode"
        )

    results = tuple(
        execute_artwork_library_workflow(
            run,
            apply_mode=apply_mode,
        )
        for run in workflow.libraries
    )

    return ArtworkManagerRunResult(
        apply_mode=apply_mode,
        libraries=results,
        skipped=workflow.skipped,
    )

