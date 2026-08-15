from pathlib import Path

import yaml

from artwork.kometa import (
    build_kometa_metadata,
    write_kometa_metadata,
)
from artwork.migration import import_mediux_metadata


FIXTURE = Path("tests/fixtures/mediux_sample.yml")


def test_builds_kometa_metadata():
    shows = import_mediux_metadata(FIXTURE)

    generated = build_kometa_metadata(shows)

    assert "metadata" in generated
    assert set(generated["metadata"]) == {
        301824,
        999999,
    }


def test_generates_show_level_artwork():
    shows = import_mediux_metadata(FIXTURE)

    generated = build_kometa_metadata(shows)

    show = generated["metadata"][301824]

    assert (
        show["url_poster"]
        == "https://api.mediux.pro/assets/example-show-poster"
    )
    assert (
        show["url_background"]
        == "https://api.mediux.pro/assets/example-show-background"
    )


def test_generates_season_and_episode_artwork():
    shows = import_mediux_metadata(FIXTURE)

    generated = build_kometa_metadata(shows)

    season = (
        generated["metadata"][301824]
        ["seasons"][1]
    )

    assert (
        season["url_poster"]
        == "https://api.mediux.pro/assets/example-season-poster"
    )

    assert set(season["episodes"]) == {1, 2}

    assert (
        season["episodes"][1]["url_poster"]
        == "https://api.mediux.pro/assets/example-s01e01"
    )


def test_preserves_specials_and_partial_coverage():
    shows = import_mediux_metadata(FIXTURE)

    generated = build_kometa_metadata(shows)

    seasons = generated["metadata"][999999]["seasons"]

    assert 0 in seasons
    assert 1 in seasons

    assert set(seasons[0]["episodes"]) == {1}
    assert set(seasons[1]["episodes"]) == {1, 3}


def test_round_trip_is_semantically_equivalent():
    original = yaml.safe_load(
        FIXTURE.read_text(encoding="utf-8")
    )

    shows = import_mediux_metadata(FIXTURE)
    generated = build_kometa_metadata(shows)

    assert generated == original


def test_writes_valid_yaml(tmp_path):
    shows = import_mediux_metadata(FIXTURE)

    output = tmp_path / "generated.yml"

    write_kometa_metadata(
        shows,
        output,
    )

    parsed = yaml.safe_load(
        output.read_text(encoding="utf-8")
    )

    assert (
        parsed
        == build_kometa_metadata(shows)
    )


def test_generates_canonical_season_for_legacy_input():
    legacy = Path(
        "tests/fixtures/mediux_legacy_implicit_season.yml"
    )

    shows = import_mediux_metadata(legacy)
    generated = build_kometa_metadata(shows)

    show = generated["metadata"][888888]

    assert set(show["seasons"]) == {1}
    assert "episodes" in show["seasons"][1]
    assert set(show["seasons"][1]["episodes"]) == {1, 2}
