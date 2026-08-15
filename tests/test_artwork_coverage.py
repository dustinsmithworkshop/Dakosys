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


def _set(
    *,
    set_id: str = "100",
    seasons: dict[int, list[int]],
) -> ArtworkSet:
    return ArtworkSet(
        provider=ArtworkSource.MEDIUX,
        set_id=set_id,
        creator="ExampleArtist",
        seasons={
            season_number: SeasonArtwork(
                season_number=season_number,
                episodes={
                    episode_number: _card(
                        episode_number
                    )
                    for episode_number
                    in episode_numbers
                },
            )
            for season_number, episode_numbers
            in seasons.items()
        },
    )


def test_complete_set_has_full_coverage():
    artwork_set = _set(
        seasons={
            1: list(range(1, 9)),
        },
    )

    coverage = analyze_set_coverage(
        artwork_set,
        {
            1: range(1, 9),
        },
    )

    assert coverage.expected_episode_count == 8
    assert coverage.available_episode_count == 8
    assert coverage.missing_episode_count == 0
    assert coverage.coverage_ratio == 1.0
    assert coverage.complete is True


def test_partial_set_reports_missing_episodes():
    artwork_set = _set(
        seasons={
            1: list(range(1, 7)),
        },
    )

    coverage = analyze_set_coverage(
        artwork_set,
        {
            1: range(1, 9),
        },
    )

    season = coverage.season(1)

    assert season is not None
    assert season.expected_count == 8
    assert season.available_count == 6
    assert season.missing_episodes == frozenset(
        {7, 8}
    )
    assert season.coverage_ratio == pytest.approx(
        0.75
    )
    assert season.complete is False
    assert coverage.complete is False


def test_coverage_is_aggregated_across_seasons():
    artwork_set = _set(
        seasons={
            1: [1, 2, 3],
            2: [1, 2],
        },
    )

    coverage = analyze_set_coverage(
        artwork_set,
        {
            1: [1, 2, 3],
            2: [1, 2, 3],
        },
    )

    assert coverage.expected_episode_count == 6
    assert coverage.available_episode_count == 5
    assert coverage.missing_episode_count == 1
    assert coverage.coverage_ratio == pytest.approx(
        5 / 6
    )
    assert coverage.complete is False


def test_extra_provider_episodes_do_not_hurt_completeness():
    artwork_set = _set(
        seasons={
            1: [1, 2, 3, 4],
        },
    )

    coverage = analyze_set_coverage(
        artwork_set,
        {
            1: [1, 2, 3],
        },
    )

    season = coverage.season(1)

    assert season is not None
    assert season.complete is True
    assert season.extra_episodes == frozenset(
        {4}
    )
    assert coverage.complete is True


def test_missing_season_is_reported_as_missing():
    artwork_set = _set(
        seasons={
            1: [1, 2],
        },
    )

    coverage = analyze_set_coverage(
        artwork_set,
        {
            1: [1, 2],
            2: [1, 2, 3],
        },
    )

    season_two = coverage.season(2)

    assert season_two is not None
    assert season_two.available_count == 0
    assert season_two.missing_episodes == frozenset(
        {1, 2, 3}
    )
    assert coverage.complete is False


def test_specials_are_treated_as_normal_inventory():
    artwork_set = _set(
        seasons={
            0: [1, 2],
            1: [1, 2],
        },
    )

    coverage = analyze_set_coverage(
        artwork_set,
        {
            0: [1, 2],
            1: [1, 2],
        },
    )

    specials = coverage.season(0)

    assert specials is not None
    assert specials.complete is True
    assert coverage.complete is True


def test_episode_without_card_does_not_count_as_available():
    artwork_set = _set(
        seasons={
            1: [1],
        },
    )

    artwork_set.seasons[1].episodes[2] = (
        EpisodeArtwork(
            episode_number=2,
            card=None,
        )
    )

    coverage = analyze_set_coverage(
        artwork_set,
        {
            1: [1, 2],
        },
    )

    assert coverage.available_episode_count == 1
    assert coverage.missing_episode_count == 1
    assert coverage.season(1).missing_episodes == (
        frozenset({2})
    )


def test_empty_expected_inventory_is_not_complete():
    artwork_set = _set(
        seasons={
            1: [1, 2],
        },
    )

    coverage = analyze_set_coverage(
        artwork_set,
        {},
    )

    assert coverage.expected_episode_count == 0
    assert coverage.coverage_ratio == 0.0
    assert coverage.complete is False


def test_provider_asset_id_counts_as_available_without_url():
    artwork_set = ArtworkSet(
        provider=ArtworkSource.MEDIUX,
        set_id="provider-set",
        seasons={
            1: SeasonArtwork(
                season_number=1,
                episodes={
                    1: EpisodeArtwork(
                        episode_number=1,
                        card=ArtworkAsset(
                            kind=ArtworkKind.EPISODE_CARD,
                            source=ArtworkSource.MEDIUX,
                            provider_asset_id="card-1",
                        ),
                    ),
                },
            ),
        },
    )

    coverage = analyze_set_coverage(
        artwork_set,
        {
            1: frozenset({1}),
        },
    )

    assert coverage.available_episode_count == 1
    assert coverage.missing_episode_count == 0
    assert coverage.complete is True
