"""Materialize artwork decisions into managed artwork state."""

from __future__ import annotations

from dataclasses import dataclass

from artwork.assessment import ArtworkSetAssessment
from artwork.models import ShowArtworkState
from artwork.policy import SetAction
from artwork.reevaluation import ReevaluationResult


@dataclass(frozen=True)
class ResolvedArtworkState:
    """Managed state produced from a reevaluation decision."""

    state: ShowArtworkState
    action: SetAction
    reason: str
    selected: ArtworkSetAssessment


def materialize_reevaluation_state(
    *,
    current_state: ShowArtworkState,
    current_assessment: ArtworkSetAssessment,
    result: ReevaluationResult,
) -> ResolvedArtworkState:
    """Turn a reevaluation result into durable managed artwork state.

    - SET_REFRESH uses the additive effective current set.
    - KEEP_CURRENT preserves the effective current set.
    - SET_MIGRATION replaces the cohesive set atomically with the
      selected challenger.
    """

    if (
        current_state.selected_set_id
        != current_assessment.set_id
        or current_state.selected_set_source
        is not current_assessment.artwork_set.provider
    ):
        raise ValueError(
            "current state does not match "
            "the current artwork assessment"
        )

    if result.action is None:
        raise ValueError(
            "reevaluation result has no action"
        )

    if result.action is SetAction.SET_MIGRATION:
        selected = result.evaluated_candidate

        if selected is None:
            raise ValueError(
                "SET_MIGRATION requires "
                "an evaluated candidate"
            )

        if (
            selected.set_id
            == current_assessment.set_id
            and selected.artwork_set.provider
            is current_assessment.artwork_set.provider
        ):
            raise ValueError(
                "SET_MIGRATION cannot select "
                "the current provider/set ID"
            )

    elif result.action in (
        SetAction.SET_REFRESH,
        SetAction.KEEP_CURRENT,
    ):
        selected = result.effective_current

        if (
            selected.set_id
            != current_assessment.set_id
            or selected.artwork_set.provider
            is not current_assessment.artwork_set.provider
        ):
            raise ValueError(
                "refresh/keep decision changed "
                "the selected provider/set ID"
            )

    else:
        raise ValueError(
            "unsupported reevaluation action: "
            f"{result.action.value}"
        )

    artwork_set = selected.artwork_set

    state = ShowArtworkState(
        title=current_state.title,
        tvdb_id=current_state.tvdb_id,
        tmdb_id=current_state.tmdb_id,
        imdb_id=current_state.imdb_id,
        poster=artwork_set.poster,
        background=artwork_set.background,
        seasons=artwork_set.seasons,
        selected_set_id=artwork_set.set_id,
        selected_set_source=artwork_set.provider,
        selected_creator=artwork_set.creator,
        selection_mode=current_state.selection_mode,
    )

    return ResolvedArtworkState(
        state=state,
        action=result.action,
        reason=result.reason,
        selected=selected,
    )
