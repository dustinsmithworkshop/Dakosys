from pathlib import Path

import pytest

from artwork.generator_config import (
    ARTWORK_GENERATOR_CONFIG_VERSION,
    ArtworkGeneratorConfigError,
    load_artwork_generator_config,
    parse_artwork_generator_config,
)


def test_missing_generator_config_uses_safe_defaults(
    tmp_path,
):
    config = load_artwork_generator_config(
        tmp_path / "artwork-generator.yaml"
    )

    assert (
        config.version
        == ARTWORK_GENERATOR_CONFIG_VERSION
    )

    assert (
        config.resolve_style().font
        == "marcellus"
    )


def test_resolves_global_library_and_show_font_inheritance():
    config = parse_artwork_generator_config(
        {
            "version": 1,
            "defaults": {
                "font": "marcellus",
            },
            "libraries": {
                "Anime": {
                    "font": (
                        "Cormorant Garamond"
                    ),
                },
            },
            "shows": {
                "tmdb:1398": {
                    "font": "prata",
                },
            },
        }
    )

    assert (
        config.resolve_style(
            library="TV",
        ).font
        == "marcellus"
    )

    assert (
        config.resolve_style(
            library="Anime",
        ).font
        == "cormorant_garamond"
    )

    assert (
        config.resolve_style(
            library="Anime",
            show_id="tmdb:1398",
        ).font
        == "prata"
    )


def test_show_override_inherits_global_when_library_not_used():
    config = parse_artwork_generator_config(
        {
            "defaults": {
                "font": "marcellus",
            },
            "shows": {
                "tmdb:100": {
                    "font": "cinzel",
                },
            },
        }
    )

    assert (
        config.resolve_style(
            library="TV",
            show_id="tmdb:100",
        ).font
        == "cinzel"
    )


def test_font_names_are_normalized():
    config = parse_artwork_generator_config(
        {
            "defaults": {
                "font": (
                    "Libre Baskerville"
                ),
            },
        }
    )

    assert (
        config.defaults.font
        == "libre_baskerville"
    )


def test_rejects_unknown_font():
    with pytest.raises(
        ArtworkGeneratorConfigError,
        match="unsupported",
    ):
        parse_artwork_generator_config(
            {
                "defaults": {
                    "font": (
                        "Comic Sans"
                    ),
                },
            }
        )


def test_rejects_unknown_config_version():
    with pytest.raises(
        ArtworkGeneratorConfigError,
        match="version",
    ):
        parse_artwork_generator_config(
            {
                "version": 2,
            }
        )


def test_rejects_unknown_setting():
    with pytest.raises(
        ArtworkGeneratorConfigError,
        match="unsupported",
    ):
        parse_artwork_generator_config(
            {
                "defaults": {
                    "font": "marcellus",
                    "show_title": True,
                },
            }
        )


def test_loads_yaml_from_disk(
    tmp_path: Path,
):
    path = (
        tmp_path
        / "artwork-generator.yaml"
    )

    path.write_text(
        """
version: 1

defaults:
  font: marcellus

libraries:
  Anime:
    font: cormorant_garamond

shows:
  tmdb:1398:
    font: prata
""".lstrip(),
        encoding="utf-8",
    )

    config = (
        load_artwork_generator_config(
            path
        )
    )

    assert (
        config.resolve_style(
            library="Anime",
        ).font
        == "cormorant_garamond"
    )

    assert (
        config.resolve_style(
            library="Anime",
            show_id="tmdb:1398",
        ).font
        == "prata"
    )
