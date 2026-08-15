"""Selection and migration policy for cohesive artwork sets."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from artwork.coverage import ArtworkSetCoverage
from artwork.models import SelectionMode


class SetAction(str, Enum):
    """Action Dakosys should take for an artwork-set candidate."""

    KEEP_CURRENT = "keep_current"
    SELECT_SET = "select_set"
    SET_REFRESH = "set_refresh"
    SET_MIGRATION = "set_migration"


@dataclass(frozen=True)
class SetDecision:
    """Explainable result from artwork set policy evaluation."""

    action: SetAction
    reason: str

    current_set_id: str | None
    candidate_set_id: str

    current_coverage: float | None
    candidate_coverage: float


def _expected_inventory_signature(
    coverage: ArtworkSetCoverage,
) -> tuple[tuple[int, tuple[int, ...]], ...]:
    """Return the expected inventory used for coverage analysis."""

    return tuple(
        (
            season.season_number,
            tuple(sorted(season.expected_episodes)),
        )
        for season in coverage.seasons
    )


def decide_set_action(
    *,
    current: ArtworkSetCoverage | None,
    candidate: ArtworkSetCoverage,
    selection_mode: SelectionMode = SelectionMode.AUTO,
    incomplete_migration_threshold: float = 0.25,
) -> SetDecision:
    """Decide whether to keep, select, refresh, or migrate artwork.

    Policy principles:

    - A locked selection is never migrated automatically.
    - The same selected set may refresh as new artwork is added.
    - A complete current set is stable and is not replaced by an
      equivalent competing set.
    - A complete challenger beats an incomplete current set.
    - Two incomplete sets only migrate when the challenger provides a
      material coverage improvement.
    """

    if not 0.0 <= incomplete_migration_threshold <= 1.0:
        raise ValueError(
            "incomplete_migration_threshold must be between 0 and 1"
        )

    if current is None:
        return SetDecision(
            action=SetAction.SELECT_SET,
            reason="no_current_set",
            current_set_id=None,
            candidate_set_id=candidate.set_id,
            current_coverage=None,
            candidate_coverage=candidate.coverage_ratio,
        )

    if (
        _expected_inventory_signature(current)
        != _expected_inventory_signature(candidate)
    ):
        raise ValueError(
            "current and candidate coverage must use the same "
            "expected episode inventory"
        )

    same_set = (
        current.provider == candidate.provider
        and current.set_id == candidate.set_id
    )

    if same_set:
        if (
            candidate.available_episode_count
            > current.available_episode_count
        ):
            return SetDecision(
                action=SetAction.SET_REFRESH,
                reason="selected_set_gained_artwork",
                current_set_id=current.set_id,
                candidate_set_id=candidate.set_id,
                current_coverage=current.coverage_ratio,
                candidate_coverage=candidate.coverage_ratio,
            )

        return SetDecision(
            action=SetAction.KEEP_CURRENT,
            reason="selected_set_unchanged",
            current_set_id=current.set_id,
            candidate_set_id=candidate.set_id,
            current_coverage=current.coverage_ratio,
            candidate_coverage=candidate.coverage_ratio,
        )

    if selection_mode is SelectionMode.LOCKED:
        return SetDecision(
            action=SetAction.KEEP_CURRENT,
            reason="selection_locked",
            current_set_id=current.set_id,
            candidate_set_id=candidate.set_id,
            current_coverage=current.coverage_ratio,
            candidate_coverage=candidate.coverage_ratio,
        )

    if current.complete:
        return SetDecision(
            action=SetAction.KEEP_CURRENT,
            reason="current_set_complete",
            current_set_id=current.set_id,
            candidate_set_id=candidate.set_id,
            current_coverage=current.coverage_ratio,
            candidate_coverage=candidate.coverage_ratio,
        )

    if candidate.complete:
        return SetDecision(
            action=SetAction.SET_MIGRATION,
            reason="complete_challenger_replaces_incomplete_current",
            current_set_id=current.set_id,
            candidate_set_id=candidate.set_id,
            current_coverage=current.coverage_ratio,
            candidate_coverage=candidate.coverage_ratio,
        )

    improvement = (
        candidate.coverage_ratio
        - current.coverage_ratio
    )

    if improvement >= incomplete_migration_threshold:
        return SetDecision(
            action=SetAction.SET_MIGRATION,
            reason="material_incomplete_coverage_improvement",
            current_set_id=current.set_id,
            candidate_set_id=candidate.set_id,
            current_coverage=current.coverage_ratio,
            candidate_coverage=candidate.coverage_ratio,
        )

    return SetDecision(
        action=SetAction.KEEP_CURRENT,
        reason="challenger_not_materially_better",
        current_set_id=current.set_id,
        candidate_set_id=candidate.set_id,
        current_coverage=current.coverage_ratio,
        candidate_coverage=candidate.coverage_ratio,
    )
