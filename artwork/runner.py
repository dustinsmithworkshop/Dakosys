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
            self.workflow.needs_apply
        )


@dataclass(frozen=True)
class ArtworkManagerRunResult:
    """Aggregate policy result across Artwork Manager libraries."""

    apply_mode: ArtworkApplyMode

    libraries: tuple[
        ArtworkLibraryRunResult,
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


def execute_artwork_manager_workflow(
    workflow: ArtworkManagerWorkflow,
    *,
    apply_mode: ArtworkApplyMode,
) -> ArtworkManagerRunResult:
    """Execute one already-built workflow according to apply policy.

    Safety always wins over apply mode:

    unsafe               -> BLOCKED
    safe + no changes    -> NO_CHANGES
    safe + manual        -> PENDING_REVIEW
    safe + auto          -> transactional apply

    A failure applying one library does not prevent later libraries from
    being processed.
    """

    if not isinstance(
        apply_mode,
        ArtworkApplyMode,
    ):
        raise ValueError(
            "apply_mode must be an "
            "ArtworkApplyMode"
        )

    results: list[
        ArtworkLibraryRunResult
    ] = []

    for run in workflow.libraries:
        if not run.safe_to_apply:
            results.append(
                ArtworkLibraryRunResult(
                    workflow=run,
                    apply_mode=apply_mode,
                    outcome=(
                        ArtworkRunOutcome
                        .BLOCKED
                    ),
                )
            )

            continue

        if not run.needs_apply:
            results.append(
                ArtworkLibraryRunResult(
                    workflow=run,
                    apply_mode=apply_mode,
                    outcome=(
                        ArtworkRunOutcome
                        .NO_CHANGES
                    ),
                )
            )

            continue

        if (
            apply_mode
            is ArtworkApplyMode.MANUAL
        ):
            results.append(
                ArtworkLibraryRunResult(
                    workflow=run,
                    apply_mode=apply_mode,
                    outcome=(
                        ArtworkRunOutcome
                        .PENDING_REVIEW
                    ),
                )
            )

            continue

        try:
            apply_result = (
                apply_artwork_library_workflow(
                    run
                )
            )

        except Exception as exc:
            results.append(
                ArtworkLibraryRunResult(
                    workflow=run,
                    apply_mode=apply_mode,
                    outcome=(
                        ArtworkRunOutcome
                        .FAILED
                    ),
                    error_type=(
                        type(exc).__name__
                    ),
                    error_message=str(
                        exc
                    ),
                )
            )

            continue

        outcome = (
            ArtworkRunOutcome.APPLIED
            if apply_result.changed
            else (
                ArtworkRunOutcome
                .NO_CHANGES
            )
        )

        results.append(
            ArtworkLibraryRunResult(
                workflow=run,
                apply_mode=apply_mode,
                outcome=outcome,
                apply_result=apply_result,
            )
        )

    return ArtworkManagerRunResult(
        apply_mode=apply_mode,
        libraries=tuple(results),
        skipped=workflow.skipped,
    )
