import pytest

from artwork.assessment import (
    ArtworkSetAssessment,
    assess_artwork_set,
)
from artwork.models import (
    ArtworkAsset,
    ArtworkKind,
    ArtworkSet,
    ArtworkSource,
    EpisodeArtwork,
    SeasonArtwork,
)
from artwork.selection import (
    candidate_quality_key,
    choose_discovery_candidate,
    find_selected_candidate,
    rank_artwork_candidates,
    rank_challengers,
)


EXPECTED = {
    1: frozenset(
        {
            1,
            2,
            3,
            4,
        }
    ),
}


def _asset(
    kind: ArtworkKind,
    asset_id: str,
    *,
    source: ArtworkSource = ArtworkSource.MEDIUX,
) -> ArtworkAsset:
    return ArtworkAsset(
        kind=kind,
        source=source,
        provider_asset_id=asset_id,
    )


def _candidate(
    set_id: str,
    *,
    cards: int,
    poster: bool = False,
    season_poster: bool = False,
    background: bool = False,
    provider: ArtworkSource = ArtworkSource.MEDIUX,
    expected=EXPECTED,
) -> ArtworkSetAssessment:
    season = SeasonArtwork(
        season_number=1,
        episodes={
            number: EpisodeArtwork(
                episode_number=number,
                card=_asset(
                    ArtworkKind.EPISODE_CARD,
                    f"{set_id}-card-{number}",
                    source=provider,
                ),
            )
            for number in range(
                1,
                cards + 1,
            )
        },
    )

    if season_poster:
        season.poster = _asset(
            ArtworkKind.SEASON_POSTER,
            f"{set_id}-season",
            source=provider,
        )

    artwork_set = ArtworkSet(
        provider=provider,
        set_id=set_id,
        poster=(
            _asset(
                ArtworkKind.SHOW_POSTER,
                f"{set_id}-poster",
                source=provider,
            )
            if poster
            else None
        ),
        background=(
            _asset(
                ArtworkKind.SHOW_BACKGROUND,
                f"{set_id}-background",
                source=provider,
            )
            if background
            else None
        ),
        seasons={
            1: season,
        },
    )

    return assess_artwork_set(
        artwork_set,
        expected,
    )


def test_episode_coverage_outranks_richer_poster_set():
    cards_only = _candidate(
        "cards",
        cards=4,
    )

    posters_only = _candidate(
        "posters",
        cards=0,
        poster=True,
        season_poster=True,
        background=True,
    )

    ranked = rank_artwork_candidates(
        [
            posters_only,
            cards_only,
        ]
    )

    assert ranked[0].set_id == "cards"


def test_show_poster_breaks_episode_coverage_tie():
    plain = _candidate(
        "plain",
        cards=4,
    )

    with_poster = _candidate(
        "poster",
        cards=4,
        poster=True,
    )

    ranked = rank_artwork_candidates(
        [
            plain,
            with_poster,
        ]
    )

    assert ranked[0].set_id == "poster"


def test_season_poster_breaks_show_poster_tie():
    show_only = _candidate(
        "show-only",
        cards=4,
        poster=True,
    )

    cohesive = _candidate(
        "cohesive",
        cards=4,
        poster=True,
        season_poster=True,
    )

    ranked = rank_artwork_candidates(
        [
            show_only,
            cohesive,
        ]
    )

    assert ranked[0].set_id == "cohesive"


def test_background_breaks_remaining_quality_tie():
    no_background = _candidate(
        "no-background",
        cards=4,
        poster=True,
        season_poster=True,
    )

    complete = _candidate(
        "complete",
        cards=4,
        poster=True,
        season_poster=True,
        background=True,
    )

    ranked = rank_artwork_candidates(
        [
            no_background,
            complete,
        ]
    )

    assert ranked[0].set_id == "complete"


def test_exact_quality_tie_has_stable_set_id_order():
    later = _candidate(
        "B",
        cards=4,
        poster=True,
        season_poster=True,
        background=True,
    )

    earlier = _candidate(
        "A",
        cards=4,
        poster=True,
        season_poster=True,
        background=True,
    )

    ranked = rank_artwork_candidates(
        [
            later,
            earlier,
        ]
    )

    assert [
        item.set_id
        for item in ranked
    ] == [
        "A",
        "B",
    ]


def test_discovery_returns_best_candidate():
    weak = _candidate(
        "weak",
        cards=2,
        poster=True,
        season_poster=True,
        background=True,
    )

    strong = _candidate(
        "strong",
        cards=4,
    )

    selected = choose_discovery_candidate(
        [
            weak,
            strong,
        ]
    )

    assert selected is strong


def test_empty_discovery_has_no_candidate():
    assert (
        choose_discovery_candidate([])
        is None
    )


def test_finds_exact_current_provider_and_set():
    current = _candidate(
        "32310",
        cards=4,
        provider=ArtworkSource.MEDIUX,
    )

    same_id_other_provider = _candidate(
        "32310",
        cards=4,
        provider=ArtworkSource.TMDB,
    )

    selected = find_selected_candidate(
        [
            same_id_other_provider,
            current,
        ],
        provider=ArtworkSource.MEDIUX,
        set_id="32310",
    )

    assert selected is current


def test_challenger_ranking_excludes_current_set():
    current = _candidate(
        "32310",
        cards=4,
        poster=True,
        season_poster=True,
        background=True,
    )

    challenger = _candidate(
        "32089",
        cards=4,
        poster=True,
        season_poster=True,
        background=True,
    )

    weaker = _candidate(
        "36723",
        cards=4,
    )

    ranked = rank_challengers(
        [
            current,
            weaker,
            challenger,
        ],
        current_provider=ArtworkSource.MEDIUX,
        current_set_id="32310",
    )

    assert [
        item.set_id
        for item in ranked
    ] == [
        "32089",
        "36723",
    ]


def test_ranking_rejects_different_plex_inventories():
    first = _candidate(
        "A",
        cards=1,
        expected={
            1: frozenset({1}),
        },
    )

    second = _candidate(
        "B",
        cards=1,
        expected={
            1: frozenset(
                {
                    1,
                    2,
                }
            ),
        },
    )

    with pytest.raises(
        ValueError,
        match="same expected episode inventory",
    ):
        rank_artwork_candidates(
            [
                first,
                second,
            ]
        )


def test_quality_key_is_explicit_not_weighted():
    candidate = _candidate(
        "A",
        cards=3,
        poster=True,
        season_poster=True,
        background=False,
    )

    assert candidate_quality_key(
        candidate
    ) == (
        3,
        True,
        1,
        False,
    )
