from pathlib import Path

import pytest

from artwork.targets import (
    ArtworkTarget,
    MediaType,
    targets_from_config,
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


def test_disabled_service_has_no_targets():
    config = {
        "services": {
            "artwork_manager": {
                "enabled": False,
            },
        },
    }

    assert targets_from_config(config) == ()


def test_builds_one_target_per_configured_library():
    config = {
        "services": {
            "artwork_manager": {
                "enabled": True,
                "output_dir": "/kometa/metadata",
                "libraries": {
                    "TV": {
                        "media_type": "show",
                    },
                    "Anime": {
                        "media_type": "show",
                    },
                    "Cartoons": {
                        "media_type": "show",
                    },
                    "Movies": {
                        "media_type": "movie",
                    },
                },
            },
        },
    }

    targets = targets_from_config(
        config
    )

    assert [
        target.library
        for target in targets
    ] == [
        "TV",
        "Anime",
        "Cartoons",
        "Movies",
    ]

    assert [
        target.media_type
        for target in targets
    ] == [
        MediaType.SHOW,
        MediaType.SHOW,
        MediaType.SHOW,
        MediaType.MOVIE,
    ]


def test_default_output_is_derived_from_library_name():
    config = {
        "services": {
            "artwork_manager": {
                "enabled": True,
                "output_dir": "/kometa/metadata",
                "libraries": {
                    "Kids TV": {
                        "media_type": "show",
                    },
                },
            },
        },
    }

    target = targets_from_config(
        config
    )[0]

    assert target.output_path == Path(
        "/kometa/metadata/artwork-kids-tv.yaml"
    )


def test_library_can_override_output_path():
    config = {
        "services": {
            "artwork_manager": {
                "enabled": True,
                "output_dir": "/kometa/metadata",
                "libraries": {
                    "TV": {
                        "media_type": "show",
                        "output": "/custom/tv.yml",
                    },
                },
            },
        },
    }

    target = targets_from_config(
        config
    )[0]

    assert target.output_path == Path(
        "/custom/tv.yml"
    )


def test_enabled_service_requires_output_dir():
    config = {
        "services": {
            "artwork_manager": {
                "enabled": True,
                "libraries": {
                    "TV": {
                        "media_type": "show",
                    },
                },
            },
        },
    }

    with pytest.raises(
        ValueError,
        match="output_dir",
    ):
        targets_from_config(config)


def test_enabled_service_requires_libraries():
    config = {
        "services": {
            "artwork_manager": {
                "enabled": True,
                "output_dir": "/kometa/metadata",
            },
        },
    }

    with pytest.raises(
        ValueError,
        match="at least one Plex library",
    ):
        targets_from_config(config)


def test_invalid_media_type_is_rejected():
    config = {
        "services": {
            "artwork_manager": {
                "enabled": True,
                "output_dir": "/kometa/metadata",
                "libraries": {
                    "TV": {
                        "media_type": "banana",
                    },
                },
            },
        },
    }

    with pytest.raises(
        ValueError,
        match="invalid media_type",
    ):
        targets_from_config(config)


def test_targets_cannot_share_output_file():
    config = {
        "services": {
            "artwork_manager": {
                "enabled": True,
                "output_dir": "/kometa/metadata",
                "libraries": {
                    "TV": {
                        "media_type": "show",
                        "output": "/same/artwork.yaml",
                    },
                    "Anime": {
                        "media_type": "show",
                        "output": "/same/artwork.yaml",
                    },
                },
            },
        },
    }

    with pytest.raises(
        ValueError,
        match="cannot share output path",
    ):
        targets_from_config(config)
