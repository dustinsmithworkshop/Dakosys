from artwork.assessment import assess_artwork_set
from artwork.models import (
    ArtworkAsset,
    ArtworkKind,
    ArtworkSet,
    ArtworkSource,
    EpisodeArtwork,
    SeasonArtwork,
)


def _asset(
    kind: ArtworkKind,
    asset_id: str,
) -> ArtworkAsset:
    return ArtworkAsset(
        kind=kind,
        source=ArtworkSource.MEDIUX,
        provider_asset_id=asset_id,
    )


def _card(
    number: int,
) -> EpisodeArtwork:
    return EpisodeArtwork(
        episode_number=number,
        card=_asset(
            ArtworkKind.EPISODE_CARD,
            f"card-{number}",
        ),
    )


def test_assessment_tracks_independent_dimensions():
    artwork_set = ArtworkSet(
        provider=ArtworkSource.MEDIUX,
        set_id="A",
        creator="Artist",
        poster=_asset(
            ArtworkKind.SHOW_POSTER,
            "show-poster",
        ),
        background=_asset(
            ArtworkKind.SHOW_BACKGROUND,
            "show-background",
        ),
        seasons={
            0: SeasonArtwork(
                season_number=0,
                episodes={
                    1: _card(1),
                },
            ),
            1: SeasonArtwork(
                season_number=1,
                poster=_asset(
                    ArtworkKind.SEASON_POSTER,
                    "season-1-poster",
                ),
                episodes={
                    1: _card(1),
                    2: _card(2),
                },
            ),
        },
    )

    assessment = assess_artwork_set(
        artwork_set,
        {
            0: frozenset({1}),
            1: frozenset({1, 2}),
        },
    )

    assert assessment.set_id == "A"
    assert assessment.creator == "Artist"

    assert (
        assessment.episode_coverage.complete
        is True
    )

    assert (
        assessment.show_poster_available
        is True
    )

    assert (
        assessment.show_background_available
        is True
    )

    assert (
        assessment.expected_season_numbers
        == (0, 1)
    )

    assert (
        assessment.season_poster_numbers
        == (1,)
    )

    assert (
        assessment.missing_season_poster_numbers
        == (0,)
    )

    assert assessment.season_poster_ratio == 0.5


def test_provider_asset_id_counts_as_show_art():
    artwork_set = ArtworkSet(
        provider=ArtworkSource.MEDIUX,
        set_id="A",
        poster=_asset(
            ArtworkKind.SHOW_POSTER,
            "poster-id",
        ),
        background=_asset(
            ArtworkKind.SHOW_BACKGROUND,
            "background-id",
        ),
    )

    assessment = assess_artwork_set(
        artwork_set,
        {},
    )

    assert assessment.show_poster_available
    assert assessment.show_background_available


def test_extra_season_poster_does_not_inflate_ratio():
    artwork_set = ArtworkSet(
        provider=ArtworkSource.MEDIUX,
        set_id="A",
        seasons={
            1: SeasonArtwork(
                season_number=1,
                poster=_asset(
                    ArtworkKind.SEASON_POSTER,
                    "season-1",
                ),
                episodes={
                    1: _card(1),
                },
            ),
            2: SeasonArtwork(
                season_number=2,
                poster=_asset(
                    ArtworkKind.SEASON_POSTER,
                    "season-2",
                ),
            ),
        },
    )

    assessment = assess_artwork_set(
        artwork_set,
        {
            1: frozenset({1}),
        },
    )

    assert assessment.season_poster_ratio == 1.0

    assert (
        assessment.available_expected_season_poster_numbers
        == (1,)
    )

    assert (
        assessment.extra_season_poster_numbers
        == (2,)
    )


def test_complete_episode_cards_can_exist_without_show_art():
    artwork_set = ArtworkSet(
        provider=ArtworkSource.MEDIUX,
        set_id="cards-only",
        seasons={
            1: SeasonArtwork(
                season_number=1,
                episodes={
                    1: _card(1),
                    2: _card(2),
                },
            ),
        },
    )

    assessment = assess_artwork_set(
        artwork_set,
        {
            1: frozenset({1, 2}),
        },
    )

    assert (
        assessment.episode_coverage.complete
        is True
    )

    assert (
        assessment.show_poster_available
        is False
    )

    assert (
        assessment.show_background_available
        is False
    )

    assert assessment.season_poster_ratio == 0.0


def test_show_art_can_exist_without_episode_cards():
    artwork_set = ArtworkSet(
        provider=ArtworkSource.MEDIUX,
        set_id="poster-only",
        poster=_asset(
            ArtworkKind.SHOW_POSTER,
            "poster",
        ),
        background=_asset(
            ArtworkKind.SHOW_BACKGROUND,
            "background",
        ),
        seasons={
            1: SeasonArtwork(
                season_number=1,
                poster=_asset(
                    ArtworkKind.SEASON_POSTER,
                    "season-1",
                ),
            ),
        },
    )

    assessment = assess_artwork_set(
        artwork_set,
        {
            1: frozenset(
                {
                    1,
                    2,
                    3,
                }
            ),
        },
    )

    assert (
        assessment.episode_coverage.available_episode_count
        == 0
    )

    assert (
        assessment.episode_coverage.complete
        is False
    )

    assert assessment.show_poster_available
    assert assessment.show_background_available
    assert assessment.season_poster_ratio == 1.0


def test_no_expected_seasons_has_no_season_ratio():
    artwork_set = ArtworkSet(
        provider=ArtworkSource.MEDIUX,
        set_id="empty",
    )

    assessment = assess_artwork_set(
        artwork_set,
        {},
    )

    assert (
        assessment.expected_season_poster_count
        == 0
    )

    assert assessment.season_poster_ratio is None
    assert (
        assessment.missing_season_poster_numbers
        == ()
    )
