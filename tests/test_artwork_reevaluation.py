import pytest

from artwork.assessment import assess_artwork_set
from artwork.models import (
    ArtworkAsset,
    ArtworkKind,
    ArtworkSet,
    ArtworkSource,
    EpisodeArtwork,
    SeasonArtwork,
    SelectionMode,
)
from artwork.policy import SetAction
from artwork.reevaluation import (
    ReevaluationPath,
    reevaluate_artwork_selection,
)


EXPECTED = {
    1: frozenset(
        range(1, 9)
    ),
}


def _card(
    set_id: str,
    number: int,
) -> EpisodeArtwork:
    return EpisodeArtwork(
        episode_number=number,
        card=ArtworkAsset(
            kind=ArtworkKind.EPISODE_CARD,
            source=ArtworkSource.MEDIUX,
            provider_asset_id=(
                f"{set_id}-card-{number}"
            ),
        ),
    )


def _set(
    set_id: str,
    cards: int,
    *,
    poster: bool = True,
    season_poster: bool = True,
    background: bool = True,
) -> ArtworkSet:
    season = SeasonArtwork(
        season_number=1,
        episodes={
            number: _card(
                set_id,
                number,
            )
            for number in range(
                1,
                cards + 1,
            )
        },
    )

    if season_poster:
        season.poster = ArtworkAsset(
            kind=ArtworkKind.SEASON_POSTER,
            source=ArtworkSource.MEDIUX,
            provider_asset_id=(
                f"{set_id}-season"
            ),
        )

    return ArtworkSet(
        provider=ArtworkSource.MEDIUX,
        set_id=set_id,
        poster=(
            ArtworkAsset(
                kind=ArtworkKind.SHOW_POSTER,
                source=ArtworkSource.MEDIUX,
                provider_asset_id=(
                    f"{set_id}-poster"
                ),
            )
            if poster
            else None
        ),
        background=(
            ArtworkAsset(
                kind=ArtworkKind.SHOW_BACKGROUND,
                source=ArtworkSource.MEDIUX,
                provider_asset_id=(
                    f"{set_id}-background"
                ),
            )
            if background
            else None
        ),
        seasons={
            1: season,
        },
    )


def _assessment(
    set_id: str,
    cards: int,
    **kwargs,
):
    return assess_artwork_set(
        _set(
            set_id,
            cards,
            **kwargs,
        ),
        EXPECTED,
    )


def test_same_set_gain_to_complete_refreshes_before_challengers():
    current = _assessment(
        "32310",
        7,
    )

    live_current = _assessment(
        "32310",
        8,
    )

    challenger = _assessment(
        "32089",
        8,
    )

    result = reevaluate_artwork_selection(
        current=current,
        candidates=[
            challenger,
            live_current,
        ],
    )

    assert (
        result.path
        is ReevaluationPath.CURRENT_SET
    )

    assert (
        result.action
        is SetAction.SET_REFRESH
    )

    assert (
        result.effective_current
        .episode_coverage
        .available_episode_count
        == 8
    )

    assert result.ranked_challengers == ()


def test_partial_same_set_gain_still_checks_complete_challenger():
    current = _assessment(
        "A",
        4,
    )

    live_current = _assessment(
        "A",
        5,
    )

    complete = _assessment(
        "B",
        8,
    )

    result = reevaluate_artwork_selection(
        current=current,
        candidates=[
            live_current,
            complete,
        ],
    )

    assert (
        result.path
        is ReevaluationPath.CHALLENGER
    )

    assert (
        result.action
        is SetAction.SET_MIGRATION
    )

    assert (
        result.evaluated_candidate
        is complete
    )


def test_partial_gain_uses_effective_current_as_migration_baseline():
    current = _assessment(
        "A",
        4,
    )

    live_current = _assessment(
        "A",
        5,
    )

    challenger = _assessment(
        "B",
        6,
    )

    result = reevaluate_artwork_selection(
        current=current,
        candidates=[
            live_current,
            challenger,
        ],
    )

    assert (
        result.path
        is ReevaluationPath.CURRENT_SET
    )

    assert (
        result.action
        is SetAction.SET_REFRESH
    )

    assert (
        result.effective_current
        .episode_coverage
        .available_episode_count
        == 5
    )


def test_provider_regression_preserves_stored_cards():
    current = _assessment(
        "A",
        6,
    )

    regressed_live = _assessment(
        "A",
        2,
    )

    result = reevaluate_artwork_selection(
        current=current,
        candidates=[
            regressed_live,
        ],
    )

    assert (
        result.effective_current
        .episode_coverage
        .available_episode_count
        == 6
    )

    assert (
        result.action
        is SetAction.KEEP_CURRENT
    )


def test_same_set_non_episode_gain_is_refresh():
    current = _assessment(
        "A",
        4,
        season_poster=False,
    )

    live_current = _assessment(
        "A",
        0,
        season_poster=True,
    )

    result = reevaluate_artwork_selection(
        current=current,
        candidates=[
            live_current,
        ],
    )

    assert (
        result.action
        is SetAction.SET_REFRESH
    )

    assert (
        result.effective_current
        .episode_coverage
        .available_episode_count
        == 4
    )

    assert (
        result.effective_current
        .available_expected_season_poster_count
        == 1
    )


def test_complete_effective_current_short_circuits_challengers():
    current = _assessment(
        "A",
        8,
    )

    live_current = _assessment(
        "A",
        8,
    )

    equivalent = _assessment(
        "B",
        8,
    )

    result = reevaluate_artwork_selection(
        current=current,
        candidates=[
            equivalent,
            live_current,
        ],
    )

    assert (
        result.path
        is ReevaluationPath.CURRENT_SET
    )

    assert (
        result.action
        is SetAction.KEEP_CURRENT
    )

    assert result.ranked_challengers == ()


def test_locked_selection_can_refresh_same_set():
    current = _assessment(
        "A",
        7,
    )

    refreshed = _assessment(
        "A",
        8,
    )

    result = reevaluate_artwork_selection(
        current=current,
        candidates=[
            refreshed,
        ],
        selection_mode=SelectionMode.LOCKED,
    )

    assert (
        result.action
        is SetAction.SET_REFRESH
    )


def test_locked_selection_never_migrates():
    current = _assessment(
        "A",
        4,
    )

    live_current = _assessment(
        "A",
        4,
    )

    challenger = _assessment(
        "B",
        8,
    )

    result = reevaluate_artwork_selection(
        current=current,
        candidates=[
            live_current,
            challenger,
        ],
        selection_mode=SelectionMode.LOCKED,
    )

    assert (
        result.path
        is ReevaluationPath.CURRENT_SET
    )

    assert (
        result.action
        is SetAction.KEEP_CURRENT
    )

    assert result.ranked_challengers == ()


def test_complete_eligible_challenger_can_migrate():
    current = _assessment(
        "A",
        6,
    )

    live_current = _assessment(
        "A",
        6,
    )

    challenger = _assessment(
        "B",
        8,
    )

    result = reevaluate_artwork_selection(
        current=current,
        candidates=[
            live_current,
            challenger,
        ],
    )

    assert (
        result.path
        is ReevaluationPath.CHALLENGER
    )

    assert (
        result.action
        is SetAction.SET_MIGRATION
    )

    assert result.blocked_challengers == ()


def test_cards_only_challenger_is_blocked_by_cohesion():
    current = _assessment(
        "A",
        4,
        poster=True,
        season_poster=True,
        background=False,
    )

    live_current = _assessment(
        "A",
        0,
        poster=True,
        season_poster=True,
        background=False,
    )

    cards_only = _assessment(
        "B",
        8,
        poster=False,
        season_poster=False,
        background=False,
    )

    result = reevaluate_artwork_selection(
        current=current,
        candidates=[
            live_current,
            cards_only,
        ],
    )

    assert (
        result.action
        is SetAction.KEEP_CURRENT
    )

    assert len(
        result.blocked_challengers
    ) == 1

    blocked = (
        result.blocked_challengers[0]
    )

    assert (
        blocked.candidate
        is cards_only
    )

    assert (
        blocked.compatibility.eligible
        is False
    )

    assert (
        blocked.compatibility.reasons
        == (
            "show_poster_regression",
            "season_poster_regression",
        )
    )


def test_blocked_top_candidate_does_not_hide_eligible_lower_candidate():
    current = _assessment(
        "A",
        4,
        poster=True,
        season_poster=True,
        background=False,
    )

    blocked_best = _assessment(
        "B",
        8,
        poster=False,
        season_poster=False,
        background=False,
    )

    eligible = _assessment(
        "C",
        7,
        poster=True,
        season_poster=True,
        background=False,
    )

    result = reevaluate_artwork_selection(
        current=current,
        candidates=[
            blocked_best,
            eligible,
        ],
    )

    assert (
        result.action
        is SetAction.SET_MIGRATION
    )

    assert (
        result.evaluated_candidate
        is eligible
    )

    assert len(
        result.blocked_challengers
    ) == 1


def test_missing_live_current_can_use_eligible_challenger():
    current = _assessment(
        "A",
        4,
    )

    challenger = _assessment(
        "B",
        8,
    )

    result = reevaluate_artwork_selection(
        current=current,
        candidates=[
            challenger,
        ],
    )

    assert result.live_current is None

    assert (
        result.action
        is SetAction.SET_MIGRATION
    )


def test_no_live_candidates_keeps_current():
    current = _assessment(
        "A",
        4,
    )

    result = reevaluate_artwork_selection(
        current=current,
        candidates=[],
    )

    assert (
        result.path
        is ReevaluationPath.CURRENT_SET
    )

    assert (
        result.action
        is SetAction.KEEP_CURRENT
    )

    assert (
        result.reason
        == "no_live_candidates"
    )


def test_duplicate_live_current_is_rejected():
    current = _assessment(
        "A",
        4,
    )

    first = _assessment(
        "A",
        4,
    )

    second = _assessment(
        "A",
        4,
    )

    with pytest.raises(
        ValueError,
        match="duplicate provider/set ID",
    ):
        reevaluate_artwork_selection(
            current=current,
            candidates=[
                first,
                second,
            ],
        )
