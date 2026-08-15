from pathlib import Path

import pytest

from artwork.targets import (
    ArtworkTarget,
    MediaType,
)


def test_target_represents_one_plex_library():
    target = ArtworkTarget(
        name="TV",
        library="TV",
        media_type=MediaType.SHOW,
        output_path="metadata/artwork-tv.yaml",
    )

    assert target.name == "TV"
    assert target.library == "TV"
    assert target.media_type is MediaType.SHOW
    assert target.output_path == Path(
        "metadata/artwork-tv.yaml"
    )


def test_target_normalizes_string_values():
    target = ArtworkTarget(
        name="  Anime  ",
        library="  Anime  ",
        media_type=MediaType.SHOW,
        output_path="artwork-anime.yml",
    )

    assert target.name == "Anime"
    assert target.library == "Anime"


def test_target_requires_yaml_output():
    with pytest.raises(
        ValueError,
        match="must be a YAML file",
    ):
        ArtworkTarget(
            name="TV",
            library="TV",
            media_type=MediaType.SHOW,
            output_path="artwork-tv.txt",
        )
