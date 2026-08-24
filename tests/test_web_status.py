import web_server


def test_status_includes_canonical_artwork_status(
    monkeypatch,
):
    config = {
        "services": {
            "artwork_manager": {
                "enabled": True,
            },
        },
    }

    artwork = {
        "enabled": True,
        "apply_mode": "auto",
        "schedule": None,
        "primary_provider": "mediux",
        "tmdb_enabled": True,
        "generator": {
            "enabled": True,
            "config_file":
                "config/artwork-generator.yaml",
            "local_asset_root":
                "/kometa/assets/generated-artwork",
            "kometa_asset_root":
                "/config/assets/generated-artwork",
            "default_font":
                "marcellus",
        },
        "libraries": [],
    }

    calls = []

    monkeypatch.setattr(
        web_server,
        "load_config",
        lambda: config,
    )

    def fake_build_artwork_status(
        *,
        config,
        plex,
    ):
        calls.append(
            {
                "config": config,
                "plex": plex,
            }
        )

        return artwork

    monkeypatch.setattr(
        web_server,
        "build_artwork_status",
        fake_build_artwork_status,
    )

    monkeypatch.setattr(
        web_server,
        "_get_local_trakt_summary",
        lambda value: {
            "required": False,
            "configured": False,
            "features": {
                "auto_schedule": False,
                "legacy_episode_publishing":
                    False,
            },
        },
    )

    monkeypatch.setattr(
        web_server.os.path,
        "exists",
        lambda value: False,
    )

    result = (
        web_server.get_status()
    )

    assert (
        result["artwork"]
        == artwork
    )

    assert calls == [
        {
            "config": config,
            "plex": None,
        },
    ]

    assert set(
        result["services"]
    ) == {
        "anime_episode_type",
        "tv_status_tracker",
        "size_overlay",
    }

    assert result[
        "stats"
    ] == {
        "total_shows": 0,
        "total_libraries": 0,
        "total_size_gb": 0.0,
    }


def test_status_passes_empty_config_to_artwork_status(
    monkeypatch,
):
    monkeypatch.setattr(
        web_server,
        "load_config",
        lambda: None,
    )

    seen = []

    def fake_build_artwork_status(
        *,
        config,
        plex,
    ):
        seen.append(
            (
                config,
                plex,
            )
        )

        return {
            "enabled": False,
        }

    monkeypatch.setattr(
        web_server,
        "build_artwork_status",
        fake_build_artwork_status,
    )

    monkeypatch.setattr(
        web_server,
        "_get_local_trakt_summary",
        lambda value: {
            "required": False,
            "configured": False,
            "features": {
                "auto_schedule": False,
                "legacy_episode_publishing":
                    False,
            },
        },
    )

    monkeypatch.setattr(
        web_server.os.path,
        "exists",
        lambda value: False,
    )

    result = (
        web_server.get_status()
    )

    assert result[
        "artwork"
    ] == {
        "enabled": False,
    }

    assert seen == [
        (
            {},
            None,
        ),
    ]
