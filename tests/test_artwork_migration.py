from pathlib import Path

from artwork.migration import import_mediux_metadata
from artwork.models import ArtworkSource


FIXTURE = Path("tests/fixtures/mediux_sample.yml")


def _show(tvdb_id: int):
    return next(
        show
        for show in import_mediux_metadata(FIXTURE)
        if show.tvdb_id == tvdb_id
    )


def test_imports_shows():
    shows = import_mediux_metadata(FIXTURE)

    assert len(shows) == 2


def test_imports_show_metadata():
    show = _show(301824)

    assert show.title == "11.22.63"
    assert show.selected_set_id == "10146"
    assert show.selected_creator == "MediuxKing79"
    assert show.selected_set_source is ArtworkSource.MEDIUX


def test_imports_show_level_artwork():
    show = _show(301824)

    assert show.poster is not None
    assert show.background is not None
    assert show.poster.source is ArtworkSource.MEDIUX
    assert show.background.source is ArtworkSource.MEDIUX


def test_imports_season_and_episode_artwork():
    show = _show(301824)

    season = show.seasons[1]

    assert season.poster is not None
    assert set(season.episodes) == {1, 2}
    assert season.episodes[1].card is not None
    assert season.episodes[2].card is not None
    assert season.episodes[1].card.source is ArtworkSource.MEDIUX


def test_imports_specials():
    show = _show(999999)

    assert 0 in show.seasons
    assert 1 in show.seasons[0].episodes


def test_preserves_partial_episode_coverage():
    show = _show(999999)

    assert set(show.seasons[1].episodes) == {1, 3}


LEGACY_FIXTURE = Path(
    "tests/fixtures/mediux_legacy_implicit_season.yml"
)


def test_normalizes_legacy_implicit_season_to_season_one():
    shows = import_mediux_metadata(LEGACY_FIXTURE)

    assert len(shows) == 1

    show = shows[0]

    assert show.tvdb_id == 888888
    assert show.title == "Legacy Example"
    assert set(show.seasons) == {1}
    assert set(show.seasons[1].episodes) == {1, 2}
