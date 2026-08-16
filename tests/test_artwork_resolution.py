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
    ShowArtworkState,
)
from artwork.policy import SetAction
from artwork.reevaluation import (
    reevaluate_artwork_selection,
)
from artwork.resolution import (
    materialize_reevaluation_state,
)


EXPECTED = {
    1: frozenset({1, 2, 3, 4}),
}


def _asset(
    kind: ArtworkKind,
    asset_id: str,
) -> ArtworkAsset:
    return ArtworkAsset(
        kind=kind,
        source=ArtworkSource.MEDIUX,
        provider_asset_id=asset_id,
        url=(
            "https://api.mediux.pro/assets/"
            f"{asset_id}"
        ),
    )


def _set(
    set_id: str,
    cards: int,
    *,
    poster: bool = True,
    season_poster: bool = True,
) -> ArtworkSet:
    return ArtworkSet(
        provider=ArtworkSource.MEDIUX,
        set_id=set_id,
        creator=f"creator-{set_id}",
        poster=(
            _asset(
                ArtworkKind.SHOW_POSTER,
                f"{set_id}-poster",
            )
            if poster
            else None
        ),
        seasons={
            1: SeasonArtwork(
                season_number=1,
                poster=(
                    _asset(
                        ArtworkKind.SEASON_POSTER,
                        f"{set_id}-season",
                    )
                    if season_poster
                    else None
                ),
                episodes={
                    number: EpisodeArtwork(
                        episode_number=number,
                        card=_asset(
                            ArtworkKind.EPISODE_CARD,
                            f"{set_id}-e{number}",
                        ),
                    )
                    for number in range(
                        1,
                        cards + 1,
                    )
                },
            ),
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


def _state(
    assessment,
    *,
    mode=SelectionMode.AUTO,
):
    artwork_set = assessment.artwork_set

    return ShowArtworkState(
        title="Example Show",
        tvdb_id=12345,
        tmdb_id=67890,
        imdb_id="tt1234567",
        poster=artwork_set.poster,
        background=artwork_set.background,
        seasons=artwork_set.seasons,
        selected_set_id=artwork_set.set_id,
        selected_set_source=artwork_set.provider,
        selected_creator=artwork_set.creator,
        selection_mode=mode,
    )


def test_materializes_set_migration():
    current = _assessment(
        "A",
        2,
    )

    challenger = _assessment(
        "B",
        4,
    )

    result = reevaluate_artwork_selection(
        current=current,
        candidates=[
            challenger,
        ],
    )

    resolved = materialize_reevaluation_state(
        current_state=_state(current),
        current_assessment=current,
        result=result,
    )

    assert (
        resolved.action
        is SetAction.SET_MIGRATION
    )

    assert (
        resolved.state.selected_set_id
        == "B"
    )

    assert (
        resolved.state.selected_creator
        == "creator-B"
    )

    assert (
        resolved.state
        .seasons[1]
        .episodes[4]
        .card
        .url
        ==
        "https://api.mediux.pro/assets/B-e4"
    )


def test_materializes_same_set_refresh():
    current = _assessment(
        "A",
        2,
    )

    live = _assessment(
        "A",
        4,
    )

    result = reevaluate_artwork_selection(
        current=current,
        candidates=[
            live,
        ],
    )

    resolved = materialize_reevaluation_state(
        current_state=_state(current),
        current_assessment=current,
        result=result,
    )

    assert (
        resolved.action
        is SetAction.SET_REFRESH
    )

    assert (
        resolved.state.selected_set_id
        == "A"
    )

    assert (
        len(
            resolved.state
            .seasons[1]
            .episodes
        )
        == 4
    )


def test_materializes_keep_current():
    current = _assessment(
        "A",
        4,
    )

    live = _assessment(
        "A",
        4,
    )

    result = reevaluate_artwork_selection(
        current=current,
        candidates=[
            live,
        ],
    )

    resolved = materialize_reevaluation_state(
        current_state=_state(current),
        current_assessment=current,
        result=result,
    )

    assert (
        resolved.action
        is SetAction.KEEP_CURRENT
    )

    assert (
        resolved.state.selected_set_id
        == "A"
    )


def test_preserves_identity_and_selection_mode():
    current = _assessment(
        "A",
        2,
    )

    challenger = _assessment(
        "B",
        4,
    )

    state = _state(
        current,
        mode=SelectionMode.PREFERRED,
    )

    result = reevaluate_artwork_selection(
        current=current,
        candidates=[
            challenger,
        ],
        selection_mode=SelectionMode.PREFERRED,
    )

    resolved = materialize_reevaluation_state(
        current_state=state,
        current_assessment=current,
        result=result,
    )

    assert resolved.state.title == "Example Show"
    assert resolved.state.tvdb_id == 12345
    assert resolved.state.tmdb_id == 67890
    assert resolved.state.imdb_id == "tt1234567"

    assert (
        resolved.state.selection_mode
        is SelectionMode.PREFERRED
    )


def test_rejects_mismatched_current_state():
    current = _assessment(
        "A",
        2,
    )

    live = _assessment(
        "A",
        4,
    )

    bad_state = ShowArtworkState(
        title="Example Show",
        tvdb_id=12345,
        selected_set_id="WRONG",
        selected_set_source=ArtworkSource.MEDIUX,
    )

    result = reevaluate_artwork_selection(
        current=current,
        candidates=[
            live,
        ],
    )

    with pytest.raises(
        ValueError,
        match="does not match",
    ):
        materialize_reevaluation_state(
            current_state=bad_state,
            current_assessment=current,
            result=result,
        )
