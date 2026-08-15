import pytest

from artwork.coverage import analyze_set_coverage
from artwork.models import (
    ArtworkAsset,
    ArtworkKind,
    ArtworkQuality,
    ArtworkSet,
    ArtworkSource,
    EpisodeArtwork,
    SeasonArtwork,
    SelectionMode,
)
from artwork.policy import (
    SetAction,
    decide_set_action,
)


def _card(number: int) -> EpisodeArtwork:
    return EpisodeArtwork(
        episode_number=number,
        card=ArtworkAsset(
            kind=ArtworkKind.EPISODE_CARD,
            source=ArtworkSource.MEDIUX,
            url=f"https://example.test/e{number}.jpg",
            quality=ArtworkQuality.CURATED,
        ),
    )


def _coverage(
    *,
    set_id: str,
    available: list[int],
    expected: list[int],
):
    artwork_set = ArtworkSet(
        provider=ArtworkSource.MEDIUX,
        set_id=set_id,
        creator="ExampleArtist",
        seasons={
            1: SeasonArtwork(
                season_number=1,
                episodes={
                    number: _card(number)
                    for number in available
                },
            ),
        },
    )

    return analyze_set_coverage(
        artwork_set,
        {
            1: expected,
        },
    )


def test_selects_set_when_no_current_selection():
    candidate = _coverage(
        set_id="B",
        available=[1, 2, 3],
        expected=[1, 2, 3],
    )

    decision = decide_set_action(
        current=None,
        candidate=candidate,
    )

    assert decision.action is SetAction.SELECT_SET
    assert decision.reason == "no_current_set"


def test_same_set_gain_is_refresh():
    current = _coverage(
        set_id="A",
        available=[1, 2, 3, 4, 5, 6],
        expected=list(range(1, 9)),
    )

    refreshed = _coverage(
        set_id="A",
        available=list(range(1, 9)),
        expected=list(range(1, 9)),
    )

    decision = decide_set_action(
        current=current,
        candidate=refreshed,
    )

    assert decision.action is SetAction.SET_REFRESH
    assert decision.reason == "selected_set_gained_artwork"


def test_same_set_without_gain_is_kept():
    current = _coverage(
        set_id="A",
        available=[1, 2, 3],
        expected=[1, 2, 3, 4],
    )

    candidate = _coverage(
        set_id="A",
        available=[1, 2, 3],
        expected=[1, 2, 3, 4],
    )

    decision = decide_set_action(
        current=current,
        candidate=candidate,
    )

    assert decision.action is SetAction.KEEP_CURRENT


def test_complete_current_set_beats_equivalent_challenger():
    current = _coverage(
        set_id="A",
        available=list(range(1, 9)),
        expected=list(range(1, 9)),
    )

    challenger = _coverage(
        set_id="B",
        available=list(range(1, 9)),
        expected=list(range(1, 9)),
    )

    decision = decide_set_action(
        current=current,
        candidate=challenger,
    )

    assert decision.action is SetAction.KEEP_CURRENT
    assert decision.reason == "current_set_complete"


def test_complete_challenger_replaces_incomplete_current():
    current = _coverage(
        set_id="A",
        available=list(range(1, 7)),
        expected=list(range(1, 9)),
    )

    challenger = _coverage(
        set_id="B",
        available=list(range(1, 9)),
        expected=list(range(1, 9)),
    )

    decision = decide_set_action(
        current=current,
        candidate=challenger,
    )

    assert decision.action is SetAction.SET_MIGRATION
    assert (
        decision.reason
        == "complete_challenger_replaces_incomplete_current"
    )


def test_small_incomplete_gain_does_not_trigger_migration():
    current = _coverage(
        set_id="A",
        available=list(range(1, 7)),
        expected=list(range(1, 9)),
    )

    challenger = _coverage(
        set_id="B",
        available=list(range(1, 8)),
        expected=list(range(1, 9)),
    )

    decision = decide_set_action(
        current=current,
        candidate=challenger,
    )

    assert decision.action is SetAction.KEEP_CURRENT
    assert (
        decision.reason
        == "challenger_not_materially_better"
    )


def test_large_incomplete_gain_can_trigger_migration():
    current = _coverage(
        set_id="A",
        available=list(range(1, 6)),
        expected=list(range(1, 13)),
    )

    challenger = _coverage(
        set_id="B",
        available=list(range(1, 12)),
        expected=list(range(1, 13)),
    )

    decision = decide_set_action(
        current=current,
        candidate=challenger,
    )

    assert decision.action is SetAction.SET_MIGRATION
    assert (
        decision.reason
        == "material_incomplete_coverage_improvement"
    )


def test_locked_selection_never_migrates():
    current = _coverage(
        set_id="A",
        available=[1, 2],
        expected=[1, 2, 3, 4],
    )

    challenger = _coverage(
        set_id="B",
        available=[1, 2, 3, 4],
        expected=[1, 2, 3, 4],
    )

    decision = decide_set_action(
        current=current,
        candidate=challenger,
        selection_mode=SelectionMode.LOCKED,
    )

    assert decision.action is SetAction.KEEP_CURRENT
    assert decision.reason == "selection_locked"


def test_policy_rejects_different_expected_inventories():
    current = _coverage(
        set_id="A",
        available=[1, 2],
        expected=[1, 2, 3],
    )

    challenger = _coverage(
        set_id="B",
        available=[1, 2, 3, 4],
        expected=[1, 2, 3, 4],
    )

    with pytest.raises(
        ValueError,
        match="same expected episode inventory",
    ):
        decide_set_action(
            current=current,
            candidate=challenger,
        )


def test_threshold_must_be_valid():
    candidate = _coverage(
        set_id="B",
        available=[1],
        expected=[1],
    )

    with pytest.raises(
        ValueError,
        match="between 0 and 1",
    ):
        decide_set_action(
            current=None,
            candidate=candidate,
            incomplete_migration_threshold=1.5,
        )
