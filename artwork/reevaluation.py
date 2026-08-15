"""Reevaluation workflow for an existing cohesive artwork selection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from artwork.assessment import (
    ArtworkSetAssessment,
    assess_artwork_set,
)
from artwork.cohesion import (
    MigrationCompatibility,
    assess_migration_compatibility,
    merge_same_artwork_set,
)
from artwork.models import SelectionMode
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
class BlockedChallenger:
    """A ranked challenger rejected by the cohesion gate."""

    candidate: ArtworkSetAssessment
    compatibility: MigrationCompatibility


@dataclass(frozen=True)
class ReevaluationResult:
    """Explainable result from reevaluating one managed selection."""

    path: ReevaluationPath

    decision: SetDecision | None

    live_current: ArtworkSetAssessment | None
    effective_current: ArtworkSetAssessment

    evaluated_candidate: ArtworkSetAssessment | None

    ranked_challengers: tuple[
        ArtworkSetAssessment,
        ...,
    ] = ()

    blocked_challengers: tuple[
        BlockedChallenger,
        ...,
    ] = ()

    reason: str = ""

    @property
    def action(self) -> SetAction | None:
        if self.decision is None:
            return None

        return self.decision.action


def _expected_episodes(
    assessment: ArtworkSetAssessment,
) -> dict[int, frozenset[int]]:
    """Recover the Plex inventory used for an assessment."""

    return {
        season.season_number: frozenset(
            season.expected_episodes
        )
        for season
        in assessment.episode_coverage.seasons
    }


def _same_set_gained_artwork(
    stored: ArtworkSetAssessment,
    effective: ArtworkSetAssessment,
) -> bool:
    """Return whether additive same-set reconciliation gained artwork."""

    if (
        stored.artwork_set.provider
        is not effective.artwork_set.provider
        or stored.set_id != effective.set_id
    ):
        raise ValueError(
            "same-set gain comparison requires "
            "the same provider/set ID"
        )

    if (
        effective
        .episode_coverage
        .available_episode_count
        >
        stored
        .episode_coverage
        .available_episode_count
    ):
        return True

    if (
        effective.show_poster_available
        and not stored.show_poster_available
    ):
        return True

    if (
        effective.show_background_available
        and not stored.show_background_available
    ):
        return True

    stored_seasons = set(
        stored
        .available_expected_season_poster_numbers
    )

    effective_seasons = set(
        effective
        .available_expected_season_poster_numbers
    )

    return bool(
        effective_seasons
        - stored_seasons
    )


def _refresh_decision(
    stored: ArtworkSetAssessment,
    effective: ArtworkSetAssessment,
) -> SetDecision:
    """Build an explainable same-set refresh decision."""

    return SetDecision(
        action=SetAction.SET_REFRESH,
        reason="selected_set_gained_artwork",
        current_set_id=stored.set_id,
        candidate_set_id=effective.set_id,
        current_coverage=(
            stored
            .episode_coverage
            .coverage_ratio
        ),
        candidate_coverage=(
            effective
            .episode_coverage
            .coverage_ratio
        ),
    )


def reevaluate_artwork_selection(
    *,
    current: ArtworkSetAssessment,
    candidates: Iterable[
        ArtworkSetAssessment
    ],
    selection_mode: SelectionMode = SelectionMode.AUTO,
    incomplete_migration_threshold: float = 0.25,
) -> ReevaluationResult:
    """Reevaluate one currently managed cohesive artwork set.

    Provider state is refresh input rather than destructive truth.

    Workflow:

    1. Find the live representation of the currently selected set.
    2. Add live same-set artwork to durable stored artwork.
    3. Preserve stored assets when the provider regresses.
    4. Stop when the effective current set becomes episode-complete.
    5. Otherwise rank challengers.
    6. Reject challengers that remove currently managed cohesive art.
    7. Apply episode migration policy to remaining challengers.
    8. If no migration wins, retain any same-set refresh discovered.
    """

    candidate_tuple = tuple(
        candidates
    )

    current_provider = (
        current.artwork_set.provider
    )

    current_set_id = current.set_id

    live_current = find_selected_candidate(
        candidate_tuple,
        provider=current_provider,
        set_id=current_set_id,
    )

    effective_current = current

    if live_current is not None:
        merged_set = merge_same_artwork_set(
            current.artwork_set,
            live_current.artwork_set,
        )

        effective_current = assess_artwork_set(
            merged_set,
            _expected_episodes(current),
        )

    gained_artwork = _same_set_gained_artwork(
        current,
        effective_current,
    )

    refresh_decision = (
        _refresh_decision(
            current,
            effective_current,
        )
        if gained_artwork
        else None
    )

    # Locked selections may receive additive updates to the same set,
    # but must never migrate automatically.
    if selection_mode is SelectionMode.LOCKED:
        if refresh_decision is not None:
            return ReevaluationResult(
                path=ReevaluationPath.CURRENT_SET,
                decision=refresh_decision,
                live_current=live_current,
                effective_current=effective_current,
                evaluated_candidate=effective_current,
                reason=refresh_decision.reason,
            )

        keep = decide_set_action(
            current=current.episode_coverage,
            candidate=(
                effective_current
                .episode_coverage
            ),
            selection_mode=selection_mode,
            incomplete_migration_threshold=(
                incomplete_migration_threshold
            ),
        )

        return ReevaluationResult(
            path=ReevaluationPath.CURRENT_SET,
            decision=keep,
            live_current=live_current,
            effective_current=effective_current,
            evaluated_candidate=effective_current,
            reason=keep.reason,
        )

    # Once the effective selected set covers every actual Plex episode,
    # challenger migration would only create unnecessary churn.
    if (
        effective_current
        .episode_coverage
        .complete
    ):
        if refresh_decision is not None:
            return ReevaluationResult(
                path=ReevaluationPath.CURRENT_SET,
                decision=refresh_decision,
                live_current=live_current,
                effective_current=effective_current,
                evaluated_candidate=effective_current,
                reason=refresh_decision.reason,
            )

        keep = decide_set_action(
            current=current.episode_coverage,
            candidate=(
                effective_current
                .episode_coverage
            ),
            selection_mode=selection_mode,
            incomplete_migration_threshold=(
                incomplete_migration_threshold
            ),
        )

        return ReevaluationResult(
            path=ReevaluationPath.CURRENT_SET,
            decision=keep,
            live_current=live_current,
            effective_current=effective_current,
            evaluated_candidate=effective_current,
            reason=keep.reason,
        )

    if live_current is not None:
        challengers = rank_challengers(
            candidate_tuple,
            current_provider=current_provider,
            current_set_id=current_set_id,
        )
    else:
        challengers = rank_artwork_candidates(
            candidate_tuple
        )

    blocked: list[
        BlockedChallenger
    ] = []

    first_eligible: ArtworkSetAssessment | None = None
    first_eligible_decision: SetDecision | None = None

    for challenger in challengers:
        compatibility = (
            assess_migration_compatibility(
                effective_current,
                challenger,
            )
        )

        if not compatibility.eligible:
            blocked.append(
                BlockedChallenger(
                    candidate=challenger,
                    compatibility=compatibility,
                )
            )
            continue

        decision = decide_set_action(
            current=(
                effective_current
                .episode_coverage
            ),
            candidate=(
                challenger
                .episode_coverage
            ),
            selection_mode=selection_mode,
            incomplete_migration_threshold=(
                incomplete_migration_threshold
            ),
        )

        if first_eligible is None:
            first_eligible = challenger
            first_eligible_decision = decision

        if (
            decision.action
            is SetAction.SET_MIGRATION
        ):
            return ReevaluationResult(
                path=ReevaluationPath.CHALLENGER,
                decision=decision,
                live_current=live_current,
                effective_current=effective_current,
                evaluated_candidate=challenger,
                ranked_challengers=challengers,
                blocked_challengers=tuple(
                    blocked
                ),
                reason=decision.reason,
            )

    # No challenger justified a migration. Preserve any additive
    # same-set improvement discovered during reconciliation.
    if refresh_decision is not None:
        return ReevaluationResult(
            path=ReevaluationPath.CURRENT_SET,
            decision=refresh_decision,
            live_current=live_current,
            effective_current=effective_current,
            evaluated_candidate=effective_current,
            ranked_challengers=challengers,
            blocked_challengers=tuple(
                blocked
            ),
            reason=refresh_decision.reason,
        )

    if (
        first_eligible is not None
        and first_eligible_decision is not None
    ):
        return ReevaluationResult(
            path=ReevaluationPath.CHALLENGER,
            decision=first_eligible_decision,
            live_current=live_current,
            effective_current=effective_current,
            evaluated_candidate=first_eligible,
            ranked_challengers=challengers,
            blocked_challengers=tuple(
                blocked
            ),
            reason=first_eligible_decision.reason,
        )

    # Every challenger was blocked by cohesion, or no candidate exists.
    keep = SetDecision(
        action=SetAction.KEEP_CURRENT,
        reason=(
            "challengers_regress_cohesive_artwork"
            if blocked
            else "no_live_candidates"
        ),
        current_set_id=current_set_id,
        candidate_set_id=current_set_id,
        current_coverage=(
            current
            .episode_coverage
            .coverage_ratio
        ),
        candidate_coverage=(
            effective_current
            .episode_coverage
            .coverage_ratio
        ),
    )

    return ReevaluationResult(
        path=ReevaluationPath.CURRENT_SET,
        decision=keep,
        live_current=live_current,
        effective_current=effective_current,
        evaluated_candidate=effective_current,
        ranked_challengers=challengers,
        blocked_challengers=tuple(
            blocked
        ),
        reason=keep.reason,
    )
