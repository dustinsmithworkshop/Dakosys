"""Reevaluation workflow for an existing cohesive artwork selection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from artwork.assessment import ArtworkSetAssessment
from artwork.coverage import ArtworkSetCoverage
from artwork.models import (
    ArtworkSource,
    SelectionMode,
)
from artwork.policy import (
    SetAction,
    SetDecision,
    decide_set_action,
)
from artwork.selection import (
    find_selected_candidate,
    rank_artwork_candidates,
    rank_challengers,
)


class ReevaluationPath(str, Enum):
    """Which path produced the reevaluation result."""

    CURRENT_SET = "current_set"
    CHALLENGER = "challenger"
    NO_ACTION = "no_action"


@dataclass(frozen=True)
class ReevaluationResult:
    """Explainable result from reevaluating one managed selection."""

    path: ReevaluationPath

    decision: SetDecision | None

    live_current: ArtworkSetAssessment | None
    evaluated_candidate: ArtworkSetAssessment | None

    ranked_challengers: tuple[
        ArtworkSetAssessment,
        ...,
    ] = ()

    reason: str = ""

    @property
    def action(self) -> SetAction | None:
        if self.decision is None:
            return None

        return self.decision.action


def reevaluate_artwork_selection(
    *,
    current: ArtworkSetCoverage,
    current_provider: ArtworkSource,
    current_set_id: str,
    candidates: Iterable[
        ArtworkSetAssessment
    ],
    selection_mode: SelectionMode = SelectionMode.AUTO,
    incomplete_migration_threshold: float = 0.25,
) -> ReevaluationResult:
    """Reevaluate one currently managed cohesive artwork set.

    Workflow:

    1. Locate the currently selected set in the live provider result.
    2. Evaluate that same set first.
    3. Immediately refresh when the selected set gained artwork.
    4. Avoid challenger work for locked or already-complete selections.
    5. Otherwise rank challengers and let migration policy decide.

    The stored current coverage remains the migration baseline. A live
    provider regression must not make already-managed artwork appear
    worse than the artwork Dakosys currently has.
    """

    if (
        current.provider is not current_provider
        or current.set_id != current_set_id
    ):
        raise ValueError(
            "current coverage does not match "
            "the selected provider/set ID"
        )

    candidate_tuple = tuple(
        candidates
    )

    live_current = find_selected_candidate(
        candidate_tuple,
        provider=current_provider,
        set_id=current_set_id,
    )

    current_decision: SetDecision | None = None
    refresh_decision: SetDecision | None = None

    # Challenger policy should compare against the strongest state of
    # the currently selected set that Dakosys can actually preserve.
    #
    # If the live same set gained cards, use that improved coverage.
    # If the provider regressed, retain the stored managed baseline.
    comparison_current = current

    if live_current is not None:
        current_decision = decide_set_action(
            current=current,
            candidate=(
                live_current.episode_coverage
            ),
            selection_mode=selection_mode,
            incomplete_migration_threshold=(
                incomplete_migration_threshold
            ),
        )

        if (
            current_decision.action
            is SetAction.SET_REFRESH
        ):
            refresh_decision = current_decision
            comparison_current = (
                live_current.episode_coverage
            )

            # Once the selected cohesive set becomes complete there is
            # no reason to churn to an equally complete challenger.
            if (
                live_current
                .episode_coverage
                .complete
            ):
                return ReevaluationResult(
                    path=ReevaluationPath.CURRENT_SET,
                    decision=current_decision,
                    live_current=live_current,
                    evaluated_candidate=live_current,
                    reason=current_decision.reason,
                )

        # Locked selections may refresh the same set, but never migrate.
        if selection_mode is SelectionMode.LOCKED:
            return ReevaluationResult(
                path=ReevaluationPath.CURRENT_SET,
                decision=(
                    refresh_decision
                    or current_decision
                ),
                live_current=live_current,
                evaluated_candidate=live_current,
                reason=(
                    refresh_decision.reason
                    if refresh_decision
                    else current_decision.reason
                ),
            )

        # A complete stored current set is stable.
        if current.complete:
            return ReevaluationResult(
                path=ReevaluationPath.CURRENT_SET,
                decision=current_decision,
                live_current=live_current,
                evaluated_candidate=live_current,
                reason=current_decision.reason,
            )

        challengers = rank_challengers(
            candidate_tuple,
            current_provider=current_provider,
            current_set_id=current_set_id,
        )

    else:
        # A locked selection remains managed even if the provider no
        # longer returns the selected set.
        if selection_mode is SelectionMode.LOCKED:
            return ReevaluationResult(
                path=ReevaluationPath.NO_ACTION,
                decision=None,
                live_current=None,
                evaluated_candidate=None,
                reason="selection_locked",
            )

        challengers = rank_artwork_candidates(
            candidate_tuple
        )

    if not challengers:
        if refresh_decision is not None:
            return ReevaluationResult(
                path=ReevaluationPath.CURRENT_SET,
                decision=refresh_decision,
                live_current=live_current,
                evaluated_candidate=live_current,
                reason=refresh_decision.reason,
            )

        if current_decision is not None:
            return ReevaluationResult(
                path=ReevaluationPath.CURRENT_SET,
                decision=current_decision,
                live_current=live_current,
                evaluated_candidate=live_current,
                reason=current_decision.reason,
            )

        return ReevaluationResult(
            path=ReevaluationPath.NO_ACTION,
            decision=None,
            live_current=None,
            evaluated_candidate=None,
            reason="no_live_candidates",
        )

    best_challenger = challengers[0]

    challenger_decision = decide_set_action(
        current=comparison_current,
        candidate=(
            best_challenger.episode_coverage
        ),
        selection_mode=selection_mode,
        incomplete_migration_threshold=(
            incomplete_migration_threshold
        ),
    )

    if (
        challenger_decision.action
        is SetAction.SET_MIGRATION
    ):
        return ReevaluationResult(
            path=ReevaluationPath.CHALLENGER,
            decision=challenger_decision,
            live_current=live_current,
            evaluated_candidate=best_challenger,
            ranked_challengers=challengers,
            reason=challenger_decision.reason,
        )

    # The current set may have improved without becoming complete. If
    # no challenger justifies migration, preserve that same-set gain.
    if refresh_decision is not None:
        return ReevaluationResult(
            path=ReevaluationPath.CURRENT_SET,
            decision=refresh_decision,
            live_current=live_current,
            evaluated_candidate=live_current,
            ranked_challengers=challengers,
            reason=refresh_decision.reason,
        )

    return ReevaluationResult(
        path=ReevaluationPath.CHALLENGER,
        decision=challenger_decision,
        live_current=live_current,
        evaluated_candidate=best_challenger,
        ranked_challengers=challengers,
        reason=challenger_decision.reason,
    )
