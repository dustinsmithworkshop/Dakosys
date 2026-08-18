from types import SimpleNamespace

import pytest

from artwork.runtime import (
    build_artwork_runtime,
    build_configured_artwork_manager_workflow,
)
from artwork.workflow import (
    ArtworkManagerWorkflow,
)


def _config(
    *,
    enabled=True,
    mediux_token="config-mediux-token",
    tmdb_api_key="config-tmdb-key",
):
    artwork_manager = {
        "enabled": enabled,
        "output_dir": "/metadata",
    }

    if mediux_token is not None:
        artwork_manager[
            "providers"
        ] = {
            "mediux": {
                "api_token": (
                    mediux_token
                ),
            },
        }

    config = {
        "services": {
            "artwork_manager": (
                artwork_manager
            ),
        },
    }

    if tmdb_api_key is not None:
        config[
            "tmdb_api_key"
        ] = tmdb_api_key

    return config


def test_disabled_manager_needs_no_provider_credentials():
    runtime = build_artwork_runtime(
        {
            "services": {
                "artwork_manager": {
                    "enabled": False,
                },
            },
        },
        environ={},
    )

    assert runtime is None


def test_runtime_builds_configured_mediux_provider():
    runtime = build_artwork_runtime(
        _config(),
        environ={},
    )

    assert runtime is not None
    assert (
        runtime.primary_provider_name
        == "mediux"
    )

    assert (
        runtime.provider
        .client
        .api_token
        == "config-mediux-token"
    )


def test_mediux_environment_token_overrides_config():
    runtime = build_artwork_runtime(
        _config(),
        environ={
            "MEDIUX_API_TOKEN":
                "environment-mediux-token",
        },
    )

    assert runtime is not None

    assert (
        runtime.provider
        .client
        .api_token
        == "environment-mediux-token"
    )


def test_enabled_manager_requires_mediux_token():
    with pytest.raises(
        ValueError,
        match="requires a MediUX API token",
    ):
        build_artwork_runtime(
            _config(
                mediux_token=None,
            ),
            environ={},
        )


def test_runtime_uses_existing_tmdb_api_key():
    runtime = build_artwork_runtime(
        _config(),
        environ={},
    )

    assert runtime is not None
    assert runtime.tmdb_enabled

    assert (
        runtime.tmdb_client
        is not None
    )

    assert (
        runtime.tmdb_client.api_key
        == "config-tmdb-key"
    )

    assert (
        "Authorization"
        not in
        runtime.tmdb_client
        .session.headers
    )


def test_tmdb_bearer_environment_token_takes_precedence():
    runtime = build_artwork_runtime(
        _config(),
        environ={
            "TMDB_TOKEN":
                "environment-tmdb-token",
        },
    )

    assert runtime is not None
    assert (
        runtime.tmdb_client
        is not None
    )

    assert (
        runtime.tmdb_client.api_key
        is None
    )

    assert (
        runtime.tmdb_client
        .session
        .headers[
            "Authorization"
        ]
        == (
            "Bearer "
            "environment-tmdb-token"
        )
    )


def test_tmdb_is_optional():
    runtime = build_artwork_runtime(
        _config(
            tmdb_api_key=None,
        ),
        environ={},
    )

    assert runtime is not None
    assert not runtime.tmdb_enabled
    assert runtime.tmdb_client is None


def test_configured_workflow_passes_runtime_to_domain(
    monkeypatch,
):
    provider = object()
    tmdb_client = object()

    runtime = SimpleNamespace(
        provider=provider,
        tmdb_client=tmdb_client,
    )

    monkeypatch.setattr(
        "artwork.runtime."
        "build_artwork_runtime",
        lambda config, environ=None:
            runtime,
    )

    expected = object()
    seen = {}

    def fake_build_workflow(
        **kwargs,
    ):
        seen.update(kwargs)
        return expected

    monkeypatch.setattr(
        "artwork.runtime."
        "build_artwork_manager_workflow",
        fake_build_workflow,
    )

    plex = object()
    config = _config()

    result = (
        build_configured_artwork_manager_workflow(
            plex=plex,
            config=config,
            environ={},
            selected_libraries=(
                "Whatever Shows"
            ),
            legacy_metadata_by_library={
                "Whatever Shows":
                    "/import/legacy.yml",
            },
        )
    )

    assert result is expected
    assert seen["plex"] is plex
    assert seen["config"] is config
    assert seen["provider"] is provider

    assert (
        seen["tmdb_client"]
        is tmdb_client
    )

    assert (
        seen["selected_libraries"]
        == "Whatever Shows"
    )

    assert (
        seen[
            "legacy_metadata_by_library"
        ]
        == {
            "Whatever Shows":
                "/import/legacy.yml",
        }
    )


def test_disabled_configured_workflow_is_empty():
    workflow = (
        build_configured_artwork_manager_workflow(
            plex=object(),
            config=_config(
                enabled=False,
            ),
            environ={},
        )
    )

    assert workflow == (
        ArtworkManagerWorkflow(
            libraries=(),
            skipped=(),
        )
    )


def test_runtime_defaults_to_auto_apply_mode():
    from artwork.apply_policy import (
        ArtworkApplyMode,
    )

    runtime = build_artwork_runtime(
        _config(),
        environ={},
    )

    assert runtime is not None
    assert (
        runtime.apply_mode
        is ArtworkApplyMode.AUTO
    )


def test_runtime_supports_manual_apply_mode():
    from artwork.apply_policy import (
        ArtworkApplyMode,
    )

    config = _config()

    config[
        "services"
    ][
        "artwork_manager"
    ][
        "apply_mode"
    ] = "manual"

    runtime = build_artwork_runtime(
        config,
        environ={},
    )

    assert runtime is not None
    assert (
        runtime.apply_mode
        is ArtworkApplyMode.MANUAL
    )


@pytest.mark.parametrize(
    "value",
    (
        "ask",
        "review",
        "",
        123,
    ),
)
def test_runtime_rejects_invalid_apply_mode(
    value,
):
    config = _config()

    config[
        "services"
    ][
        "artwork_manager"
    ][
        "apply_mode"
    ] = value

    with pytest.raises(
        ValueError,
        match="apply_mode",
    ):
        build_artwork_runtime(
            config,
            environ={},
        )


def test_configured_runner_uses_runtime_apply_mode(
    monkeypatch,
):
    from artwork.apply_policy import (
        ArtworkApplyMode,
    )
    from artwork.runtime import (
        run_configured_artwork_manager,
    )

    provider = object()
    tmdb_client = object()

    runtime = SimpleNamespace(
        provider=provider,
        tmdb_client=tmdb_client,
        apply_mode=(
            ArtworkApplyMode.MANUAL
        ),
    )

    monkeypatch.setattr(
        "artwork.runtime."
        "build_artwork_runtime",
        lambda config, environ=None:
            runtime,
    )

    workflow = object()

    seen_build = {}

    def fake_build(
        **kwargs,
    ):
        seen_build.update(
            kwargs
        )

        return workflow

    monkeypatch.setattr(
        "artwork.runtime."
        "build_artwork_manager_workflow",
        fake_build,
    )

    expected = object()
    seen_execute = {}

    def fake_execute(
        value,
        *,
        apply_mode,
    ):
        seen_execute[
            "workflow"
        ] = value

        seen_execute[
            "apply_mode"
        ] = apply_mode

        return expected

    monkeypatch.setattr(
        "artwork.runtime."
        "execute_artwork_manager_workflow",
        fake_execute,
    )

    plex = object()
    config = _config()

    result = (
        run_configured_artwork_manager(
            plex=plex,
            config=config,
            environ={},
            selected_libraries=(
                "Series"
            ),
        )
    )

    assert result is expected

    assert (
        seen_build["plex"]
        is plex
    )

    assert (
        seen_build["provider"]
        is provider
    )

    assert (
        seen_build["tmdb_client"]
        is tmdb_client
    )

    assert (
        seen_build[
            "selected_libraries"
        ]
        == "Series"
    )

    assert seen_execute == {
        "workflow":
            workflow,

        "apply_mode":
            ArtworkApplyMode.MANUAL,
    }


def test_disabled_configured_runner_returns_none(
    monkeypatch,
):
    from artwork.runtime import (
        run_configured_artwork_manager,
    )

    monkeypatch.setattr(
        "artwork.runtime."
        "build_artwork_runtime",
        lambda config, environ=None:
            None,
    )

    monkeypatch.setattr(
        "artwork.runtime."
        "build_artwork_manager_workflow",
        lambda **kwargs:
            (_ for _ in ())
            .throw(
                AssertionError(
                    "disabled manager "
                    "must not build workflow"
                )
            ),
    )

    result = (
        run_configured_artwork_manager(
            plex=object(),
            config=_config(
                enabled=False,
            ),
            environ={},
        )
    )

    assert result is None
