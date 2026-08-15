import pytest

from artwork.assessment import assess_artwork_set
from artwork.coverage import analyze_set_coverage
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


def _coverage(
    set_id: str,
    cards: int,
):
    return analyze_set_coverage(
        _set(
            set_id,
            cards,
        ),
        EXPECTED,
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


def test_same_set_gain_refreshes_before_challengers():
    current = _coverage(
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
        current_provider=ArtworkSource.MEDIUX,
        current_set_id="32310",
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
        result.evaluated_candidate
        is live_current
    )

    assert result.ranked_challengers == ()


def test_unchanged_incomplete_current_can_migrate():
    current = _coverage(
        "A",
        6,
    )

    live_current = _assessment(
        "A",
        6,
    )

    complete = _assessment(
        "B",
        8,
    )

    result = reevaluate_artwork_selection(
        current=current,
        current_provider=ArtworkSource.MEDIUX,
        current_set_id="A",
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


def test_complete_current_short_circuits_challengers():
    current = _coverage(
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
        current_provider=ArtworkSource.MEDIUX,
        current_set_id="A",
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
    current = _coverage(
        "A",
        7,
    )

    refreshed = _assessment(
        "A",
        8,
    )

    result = reevaluate_artwork_selection(
        current=current,
        current_provider=ArtworkSource.MEDIUX,
        current_set_id="A",
        candidates=[
            refreshed,
        ],
        selection_mode=SelectionMode.LOCKED,
    )

    assert (
        result.action
        is SetAction.SET_REFRESH
    )


def test_locked_unchanged_selection_does_not_migrate():
    current = _coverage(
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
        current_provider=ArtworkSource.MEDIUX,
        current_set_id="A",
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


def test_missing_live_current_can_use_challenger():
    current = _coverage(
        "A",
        4,
    )

    challenger = _assessment(
        "B",
        8,
    )

    result = reevaluate_artwork_selection(
        current=current,
        current_provider=ArtworkSource.MEDIUX,
        current_set_id="A",
        candidates=[
            challenger,
        ],
    )

    assert result.live_current is None

    assert (
        result.path
        is ReevaluationPath.CHALLENGER
    )

    assert (
        result.action
        is SetAction.SET_MIGRATION
    )


def test_no_live_candidates_is_no_action():
    current = _coverage(
        "A",
        4,
    )

    result = reevaluate_artwork_selection(
        current=current,
        current_provider=ArtworkSource.MEDIUX,
        current_set_id="A",
        candidates=[],
    )

    assert (
        result.path
        is ReevaluationPath.NO_ACTION
    )

    assert result.decision is None
    assert result.action is None

    assert (
        result.reason
        == "no_live_candidates"
    )


def test_rejects_current_selection_mismatch():
    current = _coverage(
        "A",
        4,
    )

    with pytest.raises(
        ValueError,
        match="does not match",
    ):
        reevaluate_artwork_selection(
            current=current,
            current_provider=ArtworkSource.MEDIUX,
            current_set_id="B",
            candidates=[],
        )
