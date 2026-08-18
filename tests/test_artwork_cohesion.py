import pytest

from artwork.assessment import assess_artwork_set
from artwork.cohesion import (
    assess_migration_compatibility,
    merge_same_artwork_set,
)
from artwork.models import (
    ArtworkAsset,
    ArtworkKind,
    ArtworkSet,
    ArtworkSource,
    EpisodeArtwork,
    SeasonArtwork,
)


EXPECTED = {
    1: frozenset(range(1, 11)),
    2: frozenset(range(1, 7)),
}


def _asset(
    kind: ArtworkKind,
    asset_id: str,
    source: ArtworkSource = ArtworkSource.MEDIUX,
) -> ArtworkAsset:
    return ArtworkAsset(
        kind=kind,
        source=source,
        provider_asset_id=asset_id,
    )


def _episodes(
    *,
    prefix: str,
    count: int,
) -> dict[int, EpisodeArtwork]:
    return {
        number: EpisodeArtwork(
            episode_number=number,
            card=_asset(
                ArtworkKind.EPISODE_CARD,
                f"{prefix}-{number}",
            ),
        )
        for number in range(
            1,
            count + 1,
        )
    }


def _assess(
    artwork_set: ArtworkSet,
    expected=EXPECTED,
):
    return assess_artwork_set(
        artwork_set,
        expected,
    )


def test_same_set_merge_preserves_stored_cards_and_adds_live_poster():
    stored = ArtworkSet(
        provider=ArtworkSource.MEDIUX,
        set_id="30879",
        poster=_asset(
            ArtworkKind.SHOW_POSTER,
            "stored-show",
        ),
        seasons={
            1: SeasonArtwork(
                season_number=1,
                poster=_asset(
                    ArtworkKind.SEASON_POSTER,
                    "stored-s1",
                ),
                episodes=_episodes(
                    prefix="stored",
                    count=10,
                ),
            ),
        },
    )

    live = ArtworkSet(
        provider=ArtworkSource.MEDIUX,
        set_id="30879",
        poster=_asset(
            ArtworkKind.SHOW_POSTER,
            "live-show",
        ),
        seasons={
            1: SeasonArtwork(
                season_number=1,
                poster=_asset(
                    ArtworkKind.SEASON_POSTER,
                    "live-s1",
                ),
            ),
            2: SeasonArtwork(
                season_number=2,
                poster=_asset(
                    ArtworkKind.SEASON_POSTER,
                    "live-s2",
                ),
            ),
        },
    )

    merged = merge_same_artwork_set(
        stored,
        live,
    )

    assessment = _assess(
        merged
    )

    assert (
        assessment
        .episode_coverage
        .available_episode_count
        == 10
    )

    assert (
        assessment
        .available_expected_season_poster_numbers
        == (1, 2)
    )

    # Existing usable artwork remains durable.
    assert (
        merged.poster.provider_asset_id
        == "stored-show"
    )

    assert (
        merged
        .seasons[1]
        .poster
        .provider_asset_id
        == "stored-s1"
    )

    # Newly available same-set artwork is added.
    assert (
        merged
        .seasons[2]
        .poster
        .provider_asset_id
        == "live-s2"
    )


def test_same_set_merge_adds_missing_live_episode_cards():
    stored = ArtworkSet(
        provider=ArtworkSource.MEDIUX,
        set_id="A",
        seasons={
            1: SeasonArtwork(
                season_number=1,
                episodes=_episodes(
                    prefix="stored",
                    count=2,
                ),
            ),
        },
    )

    live = ArtworkSet(
        provider=ArtworkSource.MEDIUX,
        set_id="A",
        seasons={
            1: SeasonArtwork(
                season_number=1,
                episodes=_episodes(
                    prefix="live",
                    count=4,
                ),
            ),
        },
    )

    merged = merge_same_artwork_set(
        stored,
        live,
    )

    assessment = assess_artwork_set(
        merged,
        {
            1: frozenset(
                {
                    1,
                    2,
                    3,
                    4,
                }
            ),
        },
    )

    assert (
        assessment
        .episode_coverage
        .available_episode_count
        == 4
    )

    assert (
        merged
        .seasons[1]
        .episodes[1]
        .card
        .provider_asset_id
        == "stored-1"
    )

    assert (
        merged
        .seasons[1]
        .episodes[4]
        .card
        .provider_asset_id
        == "live-4"
    )


def test_different_sets_cannot_be_merged():
    stored = ArtworkSet(
        provider=ArtworkSource.MEDIUX,
        set_id="A",
    )

    live = ArtworkSet(
        provider=ArtworkSource.MEDIUX,
        set_id="B",
    )

    with pytest.raises(
        ValueError,
        match="same provider/set ID",
    ):
        merge_same_artwork_set(
            stored,
            live,
        )


def test_different_providers_cannot_be_merged():
    stored = ArtworkSet(
        provider=ArtworkSource.MEDIUX,
        set_id="A",
    )

    live = ArtworkSet(
        provider=ArtworkSource.TMDB,
        set_id="A",
    )

    with pytest.raises(
        ValueError,
        match="same provider/set ID",
    ):
        merge_same_artwork_set(
            stored,
            live,
        )


def test_cards_only_challenger_regresses_cohesive_art():
    current = _assess(
        ArtworkSet(
            provider=ArtworkSource.MEDIUX,
            set_id="30879",
            poster=_asset(
                ArtworkKind.SHOW_POSTER,
                "show",
            ),
            seasons={
                1: SeasonArtwork(
                    season_number=1,
                    poster=_asset(
                        ArtworkKind.SEASON_POSTER,
                        "s1",
                    ),
                    episodes=_episodes(
                        prefix="current",
                        count=10,
                    ),
                ),
                2: SeasonArtwork(
                    season_number=2,
                    poster=_asset(
                        ArtworkKind.SEASON_POSTER,
                        "s2",
                    ),
                ),
            },
        )
    )

    challenger = _assess(
        ArtworkSet(
            provider=ArtworkSource.MEDIUX,
            set_id="33058",
            seasons={
                1: SeasonArtwork(
                    season_number=1,
                    episodes=_episodes(
                        prefix="challenger-s1",
                        count=10,
                    ),
                ),
                2: SeasonArtwork(
                    season_number=2,
                    episodes=_episodes(
                        prefix="challenger-s2",
                        count=6,
                    ),
                ),
            },
        )
    )

    compatibility = (
        assess_migration_compatibility(
            current,
            challenger,
        )
    )

    assert compatibility.eligible is False

    assert (
        compatibility.show_poster_regression
        is True
    )

    assert (
        compatibility.season_poster_regressions
        == (1, 2)
    )

    assert compatibility.reasons == (
        "show_poster_regression",
        "season_poster_regression",
    )


def test_challenger_preserving_current_artwork_is_eligible():
    current = _assess(
        ArtworkSet(
            provider=ArtworkSource.MEDIUX,
            set_id="A",
            poster=_asset(
                ArtworkKind.SHOW_POSTER,
                "a-show",
            ),
            seasons={
                1: SeasonArtwork(
                    season_number=1,
                    poster=_asset(
                        ArtworkKind.SEASON_POSTER,
                        "a-s1",
                    ),
                ),
            },
        )
    )

    challenger = _assess(
        ArtworkSet(
            provider=ArtworkSource.MEDIUX,
            set_id="B",
            poster=_asset(
                ArtworkKind.SHOW_POSTER,
                "b-show",
            ),
            seasons={
                1: SeasonArtwork(
                    season_number=1,
                    poster=_asset(
                        ArtworkKind.SEASON_POSTER,
                        "b-s1",
                    ),
                ),
                2: SeasonArtwork(
                    season_number=2,
                    poster=_asset(
                        ArtworkKind.SEASON_POSTER,
                        "b-s2",
                    ),
                ),
            },
        )
    )

    compatibility = (
        assess_migration_compatibility(
            current,
            challenger,
        )
    )

    assert compatibility.eligible is True
    assert compatibility.reasons == ()


def test_background_regression_blocks_migration():
    current = _assess(
        ArtworkSet(
            provider=ArtworkSource.MEDIUX,
            set_id="A",
            background=_asset(
                ArtworkKind.SHOW_BACKGROUND,
                "a-background",
            ),
        )
    )

    challenger = _assess(
        ArtworkSet(
            provider=ArtworkSource.MEDIUX,
            set_id="B",
        )
    )

    compatibility = (
        assess_migration_compatibility(
            current,
            challenger,
        )
    )

    assert compatibility.eligible is False

    assert (
        compatibility.show_background_regression
        is True
    )


def test_compatibility_requires_same_plex_inventory():
    current = assess_artwork_set(
        ArtworkSet(
            provider=ArtworkSource.MEDIUX,
            set_id="A",
        ),
        {
            1: frozenset({1}),
        },
    )

    challenger = assess_artwork_set(
        ArtworkSet(
            provider=ArtworkSource.MEDIUX,
            set_id="B",
        ),
        {
            1: frozenset({1, 2}),
        },
    )

    with pytest.raises(
        ValueError,
        match="same expected episode inventory",
    ):
        assess_migration_compatibility(
            current,
            challenger,
        )


def test_migration_cannot_drop_existing_episode_cards():
    current = assess_artwork_set(
        ArtworkSet(
            provider=ArtworkSource.MEDIUX,
            set_id="A",
            seasons={
                1: SeasonArtwork(
                    season_number=1,
                    episodes={
                        number: EpisodeArtwork(
                            episode_number=number,
                            card=_asset(
                                ArtworkKind.EPISODE_CARD,
                                f"a-{number}",
                            ),
                        )
                        for number in range(1, 5)
                    },
                ),
            },
        ),
        {
            1: frozenset(range(1, 9)),
        },
    )

    challenger = assess_artwork_set(
        ArtworkSet(
            provider=ArtworkSource.MEDIUX,
            set_id="B",
            seasons={
                1: SeasonArtwork(
                    season_number=1,
                    episodes={
                        number: EpisodeArtwork(
                            episode_number=number,
                            card=_asset(
                                ArtworkKind.EPISODE_CARD,
                                f"b-{number}",
                            ),
                        )
                        for number in range(3, 9)
                    },
                ),
            },
        ),
        {
            1: frozenset(range(1, 9)),
        },
    )

    compatibility = (
        assess_migration_compatibility(
            current,
            challenger,
        )
    )

    assert compatibility.eligible is False

    assert (
        compatibility.episode_card_regressions
        == (
            (1, 1),
            (1, 2),
        )
    )

    assert (
        "episode_card_regression"
        in compatibility.reasons
    )


def test_migration_can_add_cards_without_losing_existing_cards():
    current = assess_artwork_set(
        ArtworkSet(
            provider=ArtworkSource.MEDIUX,
            set_id="A",
            seasons={
                1: SeasonArtwork(
                    season_number=1,
                    episodes={
                        number: EpisodeArtwork(
                            episode_number=number,
                            card=_asset(
                                ArtworkKind.EPISODE_CARD,
                                f"a-{number}",
                            ),
                        )
                        for number in range(1, 5)
                    },
                ),
            },
        ),
        {
            1: frozenset(range(1, 9)),
        },
    )

    challenger = assess_artwork_set(
        ArtworkSet(
            provider=ArtworkSource.MEDIUX,
            set_id="B",
            seasons={
                1: SeasonArtwork(
                    season_number=1,
                    episodes={
                        number: EpisodeArtwork(
                            episode_number=number,
                            card=_asset(
                                ArtworkKind.EPISODE_CARD,
                                f"b-{number}",
                            ),
                        )
                        for number in range(1, 7)
                    },
                ),
            },
        ),
        {
            1: frozenset(range(1, 9)),
        },
    )

    compatibility = (
        assess_migration_compatibility(
            current,
            challenger,
        )
    )

    assert compatibility.eligible is True

    assert (
        compatibility.episode_card_regressions
        == ()
    )


def test_complete_challenger_never_regresses_expected_episode_cards():
    current = assess_artwork_set(
        ArtworkSet(
            provider=ArtworkSource.MEDIUX,
            set_id="A",
            seasons={
                1: SeasonArtwork(
                    season_number=1,
                    episodes={
                        number: EpisodeArtwork(
                            episode_number=number,
                            card=_asset(
                                ArtworkKind.EPISODE_CARD,
                                f"a-{number}",
                            ),
                        )
                        for number in range(1, 5)
                    },
                ),
            },
        ),
        {
            1: frozenset(range(1, 9)),
        },
    )

    challenger = assess_artwork_set(
        ArtworkSet(
            provider=ArtworkSource.MEDIUX,
            set_id="B",
            seasons={
                1: SeasonArtwork(
                    season_number=1,
                    episodes={
                        number: EpisodeArtwork(
                            episode_number=number,
                            card=_asset(
                                ArtworkKind.EPISODE_CARD,
                                f"b-{number}",
                            ),
                        )
                        for number in range(1, 9)
                    },
                ),
            },
        ),
        {
            1: frozenset(range(1, 9)),
        },
    )

    compatibility = (
        assess_migration_compatibility(
            current,
            challenger,
        )
    )

    assert (
        compatibility.episode_card_regressions
        == ()
    )



@pytest.mark.parametrize(
    "fallback_source",
    (
        ArtworkSource.TMDB,
        ArtworkSource.TVDB,
        ArtworkSource.PLEX,
        ArtworkSource.GENERATED,
    ),
)
def test_same_set_merge_replaces_upgradeable_fallback_asset(
    fallback_source,
):
    stored = ArtworkSet(
        provider=ArtworkSource.MEDIUX,
        set_id="A",
        seasons={
            1: SeasonArtwork(
                season_number=1,
                episodes={
                    1: EpisodeArtwork(
                        episode_number=1,
                        card=_asset(
                            ArtworkKind.EPISODE_CARD,
                            "fallback",
                            source=fallback_source,
                        ),
                    ),
                },
            ),
        },
    )

    live = ArtworkSet(
        provider=ArtworkSource.MEDIUX,
        set_id="A",
        seasons={
            1: SeasonArtwork(
                season_number=1,
                episodes={
                    1: EpisodeArtwork(
                        episode_number=1,
                        card=_asset(
                            ArtworkKind.EPISODE_CARD,
                            "primary",
                        ),
                    ),
                },
            ),
        },
    )

    merged = merge_same_artwork_set(
        stored,
        live,
    )

    card = (
        merged
        .seasons[1]
        .episodes[1]
        .card
    )

    assert (
        card.source
        is ArtworkSource.MEDIUX
    )

    assert (
        card.provider_asset_id
        == "primary"
    )


@pytest.mark.parametrize(
    "protected_source",
    (
        ArtworkSource.POSTERDB,
        ArtworkSource.MANUAL,
    ),
)
def test_same_set_merge_preserves_curated_or_manual_asset(
    protected_source,
):
    stored = ArtworkSet(
        provider=ArtworkSource.MEDIUX,
        set_id="A",
        seasons={
            1: SeasonArtwork(
                season_number=1,
                episodes={
                    1: EpisodeArtwork(
                        episode_number=1,
                        card=_asset(
                            ArtworkKind.EPISODE_CARD,
                            "protected",
                            source=protected_source,
                        ),
                    ),
                },
            ),
        },
    )

    live = ArtworkSet(
        provider=ArtworkSource.MEDIUX,
        set_id="A",
        seasons={
            1: SeasonArtwork(
                season_number=1,
                episodes={
                    1: EpisodeArtwork(
                        episode_number=1,
                        card=_asset(
                            ArtworkKind.EPISODE_CARD,
                            "primary",
                        ),
                    ),
                },
            ),
        },
    )

    merged = merge_same_artwork_set(
        stored,
        live,
    )

    card = (
        merged
        .seasons[1]
        .episodes[1]
        .card
    )

    assert (
        card.source
        is protected_source
    )

    assert (
        card.provider_asset_id
        == "protected"
    )


def test_same_set_merge_upgrades_fallback_presentation_assets():
    stored = ArtworkSet(
        provider=ArtworkSource.MEDIUX,
        set_id="A",
        poster=_asset(
            ArtworkKind.SHOW_POSTER,
            "tmdb-show",
            source=ArtworkSource.TMDB,
        ),
        seasons={
            1: SeasonArtwork(
                season_number=1,
                poster=_asset(
                    ArtworkKind.SEASON_POSTER,
                    "plex-season",
                    source=ArtworkSource.PLEX,
                ),
            ),
        },
    )

    live = ArtworkSet(
        provider=ArtworkSource.MEDIUX,
        set_id="A",
        poster=_asset(
            ArtworkKind.SHOW_POSTER,
            "mediux-show",
        ),
        seasons={
            1: SeasonArtwork(
                season_number=1,
                poster=_asset(
                    ArtworkKind.SEASON_POSTER,
                    "mediux-season",
                ),
            ),
        },
    )

    merged = merge_same_artwork_set(
        stored,
        live,
    )

    assert (
        merged.poster.provider_asset_id
        == "mediux-show"
    )

    assert (
        merged.seasons[1]
        .poster
        .provider_asset_id
        == "mediux-season"
    )
