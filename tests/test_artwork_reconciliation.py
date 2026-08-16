import pytest

from artwork.inventory import (
    SeasonInventory,
    ShowInventory,
)
from artwork.models import (
    ArtworkAsset,
    ArtworkKind,
    ArtworkQuality,
    ArtworkSource,
    EpisodeArtwork,
    SeasonArtwork,
    ShowArtworkState,
)
from artwork.reconciliation import (
    reconcile_show_target,
)
from artwork.targets import (
    ArtworkTarget,
    MediaType,
)
from tv_metadata.models import ShowIdentity


def _target(
    library="TV",
    media_type=MediaType.SHOW,
):
    return ArtworkTarget(
        name=library,
        library=library,
        media_type=media_type,
        output_path=f"artwork-{library.lower()}",
    )


def _inventory(
    *,
    title="Example",
    tvdb_id=100,
    library="TV",
    episodes=(1, 2, 3),
):
    return ShowInventory(
        identity=ShowIdentity(
            title=title,
            year=2026,
            library=library,
            plex_rating_key=f"{library}-{title}",
            tvdb_id=tvdb_id,
        ),
        seasons=(
            SeasonInventory(
                season_number=1,
                episode_numbers=frozenset(
                    episodes
                ),
            ),
        ),
    )


def _managed(
    *,
    title="Example",
    tvdb_id=100,
    episodes=(1, 2, 3),
):
    season = SeasonArtwork(
        season_number=1,
    )

    for number in episodes:
        season.episodes[number] = (
            EpisodeArtwork(
                episode_number=number,
                card=ArtworkAsset(
                    kind=ArtworkKind.EPISODE_CARD,
                    source=ArtworkSource.MEDIUX,
                    url=(
                        "https://example.test/"
                        f"s01e{number:02d}.jpg"
                    ),
                    quality=ArtworkQuality.CURATED,
                ),
            )
        )

    return ShowArtworkState(
        title=title,
        tvdb_id=tvdb_id,
        seasons={
            1: season,
        },
        selected_set_id="12345",
        selected_set_source=ArtworkSource.MEDIUX,
        selected_creator="ExampleArtist",
    )


def test_matches_managed_show_and_measures_coverage():
    result = reconcile_show_target(
        target=_target(),
        inventories=[
            _inventory(),
        ],
        managed_shows=[
            _managed(),
        ],
    )

    assert result.plex_show_count == 1
    assert result.managed_show_count == 1
    assert result.complete_show_count == 1
    assert result.incomplete_show_count == 0
    assert result.expected_episode_count == 3
    assert result.available_episode_count == 3
    assert result.missing_episode_count == 0
    assert result.coverage_ratio == 1.0


def test_reports_incomplete_managed_show():
    result = reconcile_show_target(
        target=_target(),
        inventories=[
            _inventory(
                episodes=(1, 2, 3, 4),
            ),
        ],
        managed_shows=[
            _managed(
                episodes=(1, 2),
            ),
        ],
    )

    assert result.complete_show_count == 0
    assert result.incomplete_show_count == 1
    assert result.expected_episode_count == 4
    assert result.available_episode_count == 2
    assert result.missing_episode_count == 2


def test_reports_unmanaged_plex_show():
    result = reconcile_show_target(
        target=_target(),
        inventories=[
            _inventory(),
        ],
        managed_shows=[],
    )

    assert result.managed_show_count == 0
    assert result.unmanaged_show_count == 1
    assert result.orphaned_show_count == 0


def test_reports_plex_show_without_tvdb_identity():
    result = reconcile_show_target(
        target=_target(),
        inventories=[
            _inventory(
                tvdb_id=None,
            ),
        ],
        managed_shows=[],
    )

    assert result.plex_show_count == 1
    assert result.unmanaged_show_count == 0
    assert result.missing_identity_count == 1


def test_reports_orphaned_managed_show():
    result = reconcile_show_target(
        target=_target(),
        inventories=[],
        managed_shows=[
            _managed(),
        ],
    )

    assert result.plex_show_count == 0
    assert result.orphaned_show_count == 1


def test_reconciliation_is_scoped_to_target_library():
    result = reconcile_show_target(
        target=_target("TV"),
        inventories=[
            _inventory(
                title="TV Copy",
                tvdb_id=100,
                library="TV",
            ),
            _inventory(
                title="Anime Copy",
                tvdb_id=100,
                library="Anime",
            ),
        ],
        managed_shows=[
            _managed(
                tvdb_id=100,
            ),
        ],
    )

    assert result.plex_show_count == 1
    assert result.managed_show_count == 1
    assert (
        result.matched[0]
        .inventory.identity.library
        == "TV"
    )


def test_duplicate_managed_tvdb_ids_are_rejected():
    with pytest.raises(
        ValueError,
        match="duplicate managed TVDB ID 100",
    ):
        reconcile_show_target(
            target=_target(),
            inventories=[
                _inventory(),
            ],
            managed_shows=[
                _managed(),
                _managed(),
            ],
        )


def test_movie_target_is_rejected_by_show_reconciliation():
    with pytest.raises(
        ValueError,
        match="requires a show target",
    ):
        reconcile_show_target(
            target=_target(
                "Movies",
                MediaType.MOVIE,
            ),
            inventories=[],
            managed_shows=[],
        )


def test_duplicate_unmanaged_tvdb_ids_are_independent_plex_items():
    first = _inventory(
        title="Duplicate Show",
        tvdb_id=100,
        library="Anime",
    )

    second = ShowInventory(
        identity=ShowIdentity(
            title="Duplicate Show",
            year=2026,
            library="Anime",
            plex_rating_key="Anime-Duplicate-2",
            tvdb_id=100,
        ),
        seasons=first.seasons,
    )

    result = reconcile_show_target(
        target=_target("Anime"),
        inventories=[
            first,
            second,
        ],
        managed_shows=[],
    )

    assert result.plex_show_count == 2
    assert result.unmanaged_show_count == 2
    assert result.ambiguous_match_count == 0


def test_managed_tvdb_with_multiple_plex_items_is_ambiguous():
    first = _inventory(
        title="Duplicate Show",
        tvdb_id=100,
        library="Anime",
    )

    second = ShowInventory(
        identity=ShowIdentity(
            title="Duplicate Show",
            year=2026,
            library="Anime",
            plex_rating_key="Anime-Duplicate-2",
            tvdb_id=100,
        ),
        seasons=first.seasons,
    )

    result = reconcile_show_target(
        target=_target("Anime"),
        inventories=[
            first,
            second,
        ],
        managed_shows=[
            _managed(
                title="Duplicate Show",
                tvdb_id=100,
            ),
        ],
    )

    assert result.plex_show_count == 2
    assert result.managed_show_count == 0
    assert result.unmanaged_show_count == 0
    assert result.orphaned_show_count == 0

    assert result.ambiguous_match_count == 1
    assert result.ambiguous_plex_show_count == 2

    ambiguity = result.ambiguous[0]

    assert ambiguity.tvdb_id == 100
    assert len(ambiguity.inventories) == 2


def test_ambiguous_match_does_not_affect_other_managed_shows():
    duplicate_one = _inventory(
        title="Duplicate",
        tvdb_id=100,
        library="Anime",
    )

    duplicate_two = ShowInventory(
        identity=ShowIdentity(
            title="Duplicate",
            year=2026,
            library="Anime",
            plex_rating_key="Anime-Duplicate-2",
            tvdb_id=100,
        ),
        seasons=duplicate_one.seasons,
    )

    normal = _inventory(
        title="Normal",
        tvdb_id=200,
        library="Anime",
    )

    result = reconcile_show_target(
        target=_target("Anime"),
        inventories=[
            duplicate_one,
            duplicate_two,
            normal,
        ],
        managed_shows=[
            _managed(
                title="Duplicate",
                tvdb_id=100,
            ),
            _managed(
                title="Normal",
                tvdb_id=200,
            ),
        ],
    )

    assert result.plex_show_count == 3
    assert result.managed_show_count == 1
    assert result.ambiguous_match_count == 1
    assert result.complete_show_count == 1
