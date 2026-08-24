from pathlib import Path

from artwork.status import (
    build_artwork_status,
)


def _enabled_config(
    tmp_path: Path,
) -> dict:
    creative = (
        tmp_path
        / "artwork-generator.yaml"
    )

    creative.write_text(
        """
version: 1

defaults:
  font: prata

libraries: {}
shows: {}
""".lstrip(),
        encoding="utf-8",
    )

    return {
        "plex": {
            "url":
                "http://plex:32400",
            "token":
                "plex-token",
        },
        "tmdb_api_key":
            "tmdb-key",
        "kometa_config": {
            "asset_directory":
                "/kometa/assets",
        },
        "services": {
            "artwork_manager": {
                "enabled":
                    True,
                "apply_mode":
                    "manual",
                "providers": {
                    "mediux": {
                        "api_token":
                            "mediux-token",
                    },
                },
                "generated_episode_cards": {
                    "enabled":
                        True,
                    "kometa_asset_directory":
                        "/config/assets",
                    "config_file":
                        str(
                            creative
                        ),
                },
            },
        },
        "scheduler": {
            "artwork_manager":
                "03:00",
        },
    }


def test_disabled_status_is_stable_without_runtime_credentials():
    status = build_artwork_status(
        config={
            "services": {
                "artwork_manager": {
                    "enabled":
                        False,
                },
            },
        },
        environ={},
    )

    assert status == {
        "enabled": False,
        "apply_mode": "auto",
        "schedule": None,
        "primary_provider": None,
        "tmdb_enabled": False,
        "generator": {
            "enabled": False,
            "config_file": None,
            "local_asset_root": None,
            "kometa_asset_root": None,
            "default_font": None,
        },
        "libraries": [],
    }


def test_enabled_status_uses_runtime_generator_configuration(
    tmp_path,
):
    status = build_artwork_status(
        config=_enabled_config(
            tmp_path
        ),
        environ={},
    )

    assert status[
        "enabled"
    ]

    assert (
        status["apply_mode"]
        == "manual"
    )

    assert (
        status["schedule"]
        == "03:00"
    )

    assert (
        status["primary_provider"]
        == "mediux"
    )

    assert status[
        "tmdb_enabled"
    ]

    generator = status[
        "generator"
    ]

    assert generator[
        "enabled"
    ]

    assert (
        generator[
            "local_asset_root"
        ]
        == (
            "/kometa/assets/"
            "generated-artwork"
        )
    )

    assert (
        generator[
            "kometa_asset_root"
        ]
        == (
            "/config/assets/"
            "generated-artwork"
        )
    )

    assert (
        generator[
            "default_font"
        ]
        == "prata"
    )

    assert (
        generator[
            "config_file"
        ]
        .endswith(
            "artwork-generator.yaml"
        )
    )
