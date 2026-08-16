from pathlib import Path

import pytest

from artwork.targets import (
    ArtworkTarget,
    MediaType,
    discover_artwork_targets,
)


class FakeSection:
    def __init__(
        self,
        title,
        section_type,
    ):
        self.title = title
        self.type = section_type


class FakeLibrary:
    def __init__(
        self,
        sections,
    ):
        self._sections = list(
            sections
        )

    def sections(self):
        return list(
            self._sections
        )


class FakePlex:
    def __init__(
        self,
        *sections,
    ):
        self.library = FakeLibrary(
            sections
        )


def _config(
    *,
    libraries=None,
):
    artwork_manager = {
        "enabled": True,
        "output_dir": "/kometa/metadata",
    }

    if libraries is not None:
        artwork_manager[
            "libraries"
        ] = libraries

    return {
        "services": {
            "artwork_manager": artwork_manager,
        },
    }


def test_target_represents_one_plex_library():
    target = ArtworkTarget(
        name="Television",
        library="Television",
        media_type=MediaType.SHOW,
        output_path="metadata/artwork-television",
    )

    assert target.name == "Television"
    assert target.library == "Television"
    assert target.media_type is MediaType.SHOW
    assert target.output_path == Path(
        "metadata/artwork-television"
    )


def test_target_normalizes_string_values():
    target = ArtworkTarget(
        name="  Series  ",
        library="  Series  ",
        media_type=MediaType.SHOW,
        output_path="artwork-series",
    )

    assert target.name == "Series"
    assert target.library == "Series"


def test_target_rejects_yaml_file_output():
    with pytest.raises(
        ValueError,
        match="item-store directory",
    ):
        ArtworkTarget(
            name="Series",
            library="Series",
            media_type=MediaType.SHOW,
            output_path="artwork-series.yaml",
        )


def test_disabled_service_has_no_targets():
    plex = FakePlex(
        FakeSection(
            "Anything",
            "show",
        )
    )

    config = {
        "services": {
            "artwork_manager": {
                "enabled": False,
            },
        },
    }

    assert (
        discover_artwork_targets(
            plex,
            config,
        )
        == ()
    )


def test_discovers_arbitrary_supported_plex_libraries():
    plex = FakePlex(
        FakeSection(
            "Films",
            "movie",
        ),
        FakeSection(
            "Television",
            "show",
        ),
        FakeSection(
            "Kids & Family",
            "show",
        ),
        FakeSection(
            "Music",
            "artist",
        ),
        FakeSection(
            "Photography",
            "photo",
        ),
    )

    targets = discover_artwork_targets(
        plex,
        _config(),
    )

    assert [
        target.library
        for target in targets
    ] == [
        "Films",
        "Television",
        "Kids & Family",
    ]

    assert [
        target.media_type
        for target in targets
    ] == [
        MediaType.MOVIE,
        MediaType.SHOW,
        MediaType.SHOW,
    ]

    assert [
        target.output_path
        for target in targets
    ] == [
        Path(
            "/kometa/metadata/artwork-films"
        ),
        Path(
            "/kometa/metadata/artwork-television"
        ),
        Path(
            "/kometa/metadata/artwork-kids-family"
        ),
    ]


def test_discovery_does_not_depend_on_dakosys_library_roles():
    plex = FakePlex(
        FakeSection(
            "My Series",
            "show",
        ),
    )

    config = _config()

    config["plex"] = {
        "libraries": {
            "tv": [
                "Completely Different Name"
            ],
        },
    }

    targets = discover_artwork_targets(
        plex,
        config,
    )

    assert len(targets) == 1
    assert targets[0].library == "My Series"


def test_include_restricts_discovered_libraries():
    plex = FakePlex(
        FakeSection(
            "Films",
            "movie",
        ),
        FakeSection(
            "Series",
            "show",
        ),
        FakeSection(
            "Documentaries",
            "show",
        ),
    )

    targets = discover_artwork_targets(
        plex,
        _config(
            libraries={
                "include": [
                    "Series",
                    "Documentaries",
                ],
            },
        ),
    )

    assert [
        target.library
        for target in targets
    ] == [
        "Series",
        "Documentaries",
    ]


def test_exclude_removes_discovered_library():
    plex = FakePlex(
        FakeSection(
            "Films",
            "movie",
        ),
        FakeSection(
            "Series",
            "show",
        ),
        FakeSection(
            "Home Videos",
            "movie",
        ),
    )

    targets = discover_artwork_targets(
        plex,
        _config(
            libraries={
                "exclude": [
                    "Home Videos",
                ],
            },
        ),
    )

    assert [
        target.library
        for target in targets
    ] == [
        "Films",
        "Series",
    ]


def test_library_can_override_output_path():
    plex = FakePlex(
        FakeSection(
            "My Series",
            "show",
        ),
    )

    targets = discover_artwork_targets(
        plex,
        _config(
            libraries={
                "overrides": {
                    "My Series": {
                        "output": (
                            "/custom/"
                            "series-artwork"
                        ),
                    },
                },
            },
        ),
    )

    assert targets[
        0
    ].output_path == Path(
        "/custom/series-artwork"
    )


def test_unicode_library_name_gets_valid_default_output():
    plex = FakePlex(
        FakeSection(
            "日本のアニメ",
            "show",
        ),
    )

    targets = discover_artwork_targets(
        plex,
        _config(),
    )

    assert targets[
        0
    ].output_path == Path(
        "/kometa/metadata/"
        "artwork-日本のアニメ"
    )


def test_unknown_include_library_is_rejected():
    plex = FakePlex(
        FakeSection(
            "Series",
            "show",
        ),
    )

    with pytest.raises(
        ValueError,
        match="do not exist",
    ):
        discover_artwork_targets(
            plex,
            _config(
                libraries={
                    "include": [
                        "Not A Real Library",
                    ],
                },
            ),
        )


def test_unknown_exclude_library_is_rejected():
    plex = FakePlex(
        FakeSection(
            "Series",
            "show",
        ),
    )

    with pytest.raises(
        ValueError,
        match="do not exist",
    ):
        discover_artwork_targets(
            plex,
            _config(
                libraries={
                    "exclude": [
                        "Typo Library",
                    ],
                },
            ),
        )


def test_unknown_override_library_is_rejected():
    plex = FakePlex(
        FakeSection(
            "Series",
            "show",
        ),
    )

    with pytest.raises(
        ValueError,
        match="do not exist",
    ):
        discover_artwork_targets(
            plex,
            _config(
                libraries={
                    "overrides": {
                        "Missing": {
                            "output": (
                                "/tmp/missing.yaml"
                            ),
                        },
                    },
                },
            ),
        )


def test_explicitly_included_unsupported_library_is_rejected():
    plex = FakePlex(
        FakeSection(
            "Music Collection",
            "artist",
        ),
    )

    with pytest.raises(
        ValueError,
        match="unsupported type",
    ):
        discover_artwork_targets(
            plex,
            _config(
                libraries={
                    "include": [
                        "Music Collection",
                    ],
                },
            ),
        )


def test_slug_collision_is_rejected():
    plex = FakePlex(
        FakeSection(
            "Kids TV",
            "show",
        ),
        FakeSection(
            "Kids-TV",
            "show",
        ),
    )

    with pytest.raises(
        ValueError,
        match="output collision",
    ):
        discover_artwork_targets(
            plex,
            _config(),
        )


def test_output_override_collision_is_rejected():
    plex = FakePlex(
        FakeSection(
            "Films",
            "movie",
        ),
        FakeSection(
            "Series",
            "show",
        ),
    )

    with pytest.raises(
        ValueError,
        match="output collision",
    ):
        discover_artwork_targets(
            plex,
            _config(
                libraries={
                    "overrides": {
                        "Films": {
                            "output": (
                                "/shared/artwork"
                            ),
                        },
                        "Series": {
                            "output": (
                                "/shared/artwork"
                            ),
                        },
                    },
                },
            ),
        )


def test_libraries_configuration_must_be_mapping():
    plex = FakePlex(
        FakeSection(
            "Series",
            "show",
        ),
    )

    config = _config()

    config[
        "services"
    ][
        "artwork_manager"
    ][
        "libraries"
    ] = [
        "Series"
    ]

    with pytest.raises(
        ValueError,
        match="must be a mapping",
    ):
        discover_artwork_targets(
            plex,
            config,
        )



def test_enabled_manager_requires_artwork_output_dir():
    plex = FakePlex(
        FakeSection(
            "Series Collection",
            "show",
        ),
    )

    config = {
        "kometa_config": {
            "yaml_output_dir": "/kometa/overlays",
        },
        "services": {
            "artwork_manager": {
                "enabled": True,
            },
        },
    }

    with pytest.raises(
        ValueError,
        match="artwork_manager.output_dir",
    ):
        discover_artwork_targets(
            plex,
            config,
        )


def test_artwork_output_dir_is_independent_of_overlay_output():
    plex = FakePlex(
        FakeSection(
            "Feature Films",
            "movie",
        ),
    )

    config = {
        "kometa_config": {
            "yaml_output_dir": "/kometa/overlays",
        },
        "services": {
            "artwork_manager": {
                "enabled": True,
                "output_dir": "/kometa/metadata",
            },
        },
    }

    targets = discover_artwork_targets(
        plex,
        config,
    )

    assert targets[0].output_path == Path(
        "/kometa/metadata/"
        "artwork-feature-films"
    )


def test_default_target_is_canonical_item_store_directory():
    plex = FakePlex(
        FakeSection(
            "My Television",
            "show",
        ),
    )

    targets = discover_artwork_targets(
        plex,
        _config(),
    )

    assert len(targets) == 1

    target = targets[0]

    assert target.output_path == Path(
        "/kometa/metadata/"
        "artwork-my-television"
    )

    assert target.output_path.suffix == ""
