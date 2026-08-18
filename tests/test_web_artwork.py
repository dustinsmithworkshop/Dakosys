from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import web_server

from artwork.targets import (
    MediaType,
)


class FakeTarget:
    def __init__(
        self,
        library,
        media_type,
        output_path,
    ):
        self.library = library
        self.media_type = media_type
        self.output_path = Path(
            output_path
        )


def test_config_masks_mediux_api_token():
    config = {
        "services": {
            "artwork_manager": {
                "enabled": True,
                "providers": {
                    "mediux": {
                        "api_token":
                            "super-secret-token",
                    },
                },
            },
        },
    }

    masked = (
        web_server.mask_secrets(
            config
        )
    )

    assert (
        masked["services"]
        ["artwork_manager"]
        ["providers"]
        ["mediux"]
        ["api_token"]
        == web_server.MASKED
    )

    assert (
        config["services"]
        ["artwork_manager"]
        ["providers"]
        ["mediux"]
        ["api_token"]
        == "super-secret-token"
    )


def test_artwork_targets_are_dynamic(
    monkeypatch,
):
    config = {
        "services": {
            "artwork_manager": {
                "enabled": True,
                "output_dir":
                    "/metadata",
            },
        },
        "plex": {
            "url": "http://plex",
            "token": "token",
        },
    }

    plex = object()

    monkeypatch.setattr(
        web_server,
        "load_config",
        lambda: config,
    )

    monkeypatch.setattr(
        web_server,
        "_connect_plex",
        lambda value: plex,
    )

    def fake_discover(
        received_plex,
        received_config,
    ):
        assert (
            received_plex
            is plex
        )

        assert (
            received_config
            is config
        )

        return (
            FakeTarget(
                "Bob's Television",
                MediaType.SHOW,
                (
                    "/metadata/"
                    "artwork-bob-s-television"
                ),
            ),
            FakeTarget(
                "Cinema Vault",
                MediaType.MOVIE,
                (
                    "/metadata/"
                    "artwork-cinema-vault"
                ),
            ),
        )

    monkeypatch.setattr(
        web_server,
        "discover_artwork_targets",
        fake_discover,
    )

    result = (
        web_server.get_artwork_targets()
    )

    assert result == {
        "enabled": True,
        "targets": [
            {
                "library":
                    "Bob's Television",
                "media_type":
                    "show",
                "output_path":
                    (
                        "/metadata/"
                        "artwork-bob-s-television"
                    ),
                "supported": True,
                "status": "ready",
            },
            {
                "library":
                    "Cinema Vault",
                "media_type":
                    "movie",
                "output_path":
                    (
                        "/metadata/"
                        "artwork-cinema-vault"
                    ),
                "supported": False,
                "status":
                    "movie_support_pending",
            },
        ],
    }


def test_disabled_artwork_targets_do_not_connect_to_plex(
    monkeypatch,
):
    config = {
        "services": {
            "artwork_manager": {
                "enabled": False,
            },
        },
    }

    monkeypatch.setattr(
        web_server,
        "load_config",
        lambda: config,
    )

    def should_not_connect(
        config,
    ):
        raise AssertionError(
            "Plex should not be contacted"
        )

    monkeypatch.setattr(
        web_server,
        "_connect_plex",
        should_not_connect,
    )

    assert (
        web_server.get_artwork_targets()
        == {
            "enabled": False,
            "targets": [],
        }
    )


def test_artwork_preview_uses_exact_library(
    monkeypatch,
):
    config = {
        "services": {
            "artwork_manager": {
                "enabled": True,
            },
        },
    }

    plex = object()

    workflow = SimpleNamespace(
        libraries=(object(),),
        skipped=(),
    )

    serialized = {
        "summary": {
            "library_count": 1,
        },
    }

    seen = {}

    monkeypatch.setattr(
        web_server,
        "load_config",
        lambda: config,
    )

    monkeypatch.setattr(
        web_server,
        "_connect_plex",
        lambda value: plex,
    )

    def fake_build(
        **kwargs,
    ):
        seen.update(
            kwargs
        )

        return workflow

    monkeypatch.setattr(
        web_server,
        (
            "build_configured_"
            "artwork_manager_workflow"
        ),
        fake_build,
    )

    monkeypatch.setattr(
        web_server,
        "serialize_artwork_workflow",
        lambda value: serialized,
    )

    result = (
        web_server.get_artwork_preview(
            "Kids & Family"
        )
    )

    assert result is serialized

    assert (
        seen["plex"]
        is plex
    )

    assert (
        seen["config"]
        is config
    )

    assert (
        seen["selected_libraries"]
        == "Kids & Family"
    )


def test_artwork_preview_unknown_library_is_400(
    monkeypatch,
):
    config = {
        "services": {
            "artwork_manager": {
                "enabled": True,
            },
        },
    }

    monkeypatch.setattr(
        web_server,
        "load_config",
        lambda: config,
    )

    monkeypatch.setattr(
        web_server,
        "_connect_plex",
        lambda value: object(),
    )

    def fake_build(
        **kwargs,
    ):
        raise ValueError(
            "selected Artwork Manager "
            "libraries were not discovered "
            "in Plex: 'Missing'"
        )

    monkeypatch.setattr(
        web_server,
        (
            "build_configured_"
            "artwork_manager_workflow"
        ),
        fake_build,
    )

    with pytest.raises(
        HTTPException,
    ) as caught:
        (
            web_server
            .get_artwork_preview(
                "Missing"
            )
        )

    assert (
        caught.value.status_code
        == 400
    )


def test_artwork_preview_never_applies(
    monkeypatch,
):
    """The read-only Web endpoint must not expose persistence."""

    config = {
        "services": {
            "artwork_manager": {
                "enabled": True,
            },
        },
    }

    plex = object()

    workflow = SimpleNamespace(
        libraries=(object(),),
        skipped=(),
    )

    monkeypatch.setattr(
        web_server,
        "load_config",
        lambda: config,
    )

    monkeypatch.setattr(
        web_server,
        "_connect_plex",
        lambda value: plex,
    )

    monkeypatch.setattr(
        web_server,
        (
            "build_configured_"
            "artwork_manager_workflow"
        ),
        lambda **kwargs:
            workflow,
    )

    monkeypatch.setattr(
        web_server,
        "serialize_artwork_workflow",
        lambda value: {
            "safe": True,
        },
    )

    result = (
        web_server.get_artwork_preview(
            "Any Library"
        )
    )

    assert result == {
        "safe": True,
    }
