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

    generator_options = object()

    runtime = SimpleNamespace(
        provider=provider,
        tmdb_client=tmdb_client,
        generator_options=(
            generator_options
        ),
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
        seen["generator_options"]
        is generator_options
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


def test_configured_runner_processes_targets_independently(
    monkeypatch,
):
    from pathlib import Path

    from artwork.apply_policy import (
        ArtworkApplyMode,
    )
    from artwork.runner import (
        ArtworkRunOutcome,
    )
    from artwork.runtime import (
        run_configured_artwork_manager,
    )
    from artwork.targets import (
        ArtworkTarget,
        MediaType,
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

    targets = (
        ArtworkTarget(
            name="Series One",
            library="Series One",
            media_type=MediaType.SHOW,
            output_path=Path(
                "/metadata/artwork-series-one"
            ),
        ),
        ArtworkTarget(
            name="Cinema",
            library="Cinema",
            media_type=MediaType.MOVIE,
            output_path=Path(
                "/metadata/artwork-cinema"
            ),
        ),
        ArtworkTarget(
            name="Series Two",
            library="Series Two",
            media_type=MediaType.SHOW,
            output_path=Path(
                "/metadata/artwork-series-two"
            ),
        ),
    )

    discoveries = []

    def fake_discover(
        plex,
        config,
    ):
        discoveries.append(
            (
                plex,
                config,
            )
        )

        return targets

    monkeypatch.setattr(
        "artwork.runtime."
        "discover_artwork_targets",
        fake_discover,
    )

    built = []

    progress_callback = object()

    def fake_build(
        **kwargs,
    ):
        built.append(
            kwargs["target"].library
        )

        assert (
            kwargs["progress_callback"]
            is progress_callback
        )

        return SimpleNamespace(
            library=(
                kwargs["target"].library
            ),
        )

    monkeypatch.setattr(
        "artwork.runtime."
        "build_artwork_target_workflow",
        fake_build,
    )

    executed = []

    def fake_execute(
        run,
        *,
        apply_mode,
    ):
        executed.append(
            (
                run.library,
                apply_mode,
            )
        )

        return SimpleNamespace(
            library=run.library,
            outcome=(
                ArtworkRunOutcome
                .NO_CHANGES
            ),
        )

    monkeypatch.setattr(
        "artwork.runtime."
        "execute_artwork_library_workflow",
        fake_execute,
    )

    plex = object()
    config = _config()

    result = (
        run_configured_artwork_manager(
            plex=plex,
            config=config,
            environ={},
            progress_callback=(
                progress_callback
            ),
        )
    )

    assert result is not None

    assert len(
        discoveries
    ) == 1

    assert built == [
        "Series One",
        "Cinema",
        "Series Two",
    ]

    assert executed == [
        (
            "Series One",
            ArtworkApplyMode.MANUAL,
        ),
        (
            "Cinema",
            ArtworkApplyMode.MANUAL,
        ),
        (
            "Series Two",
            ArtworkApplyMode.MANUAL,
        ),
    ]

    assert result.skipped == ()



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


def test_configured_runner_persists_history_when_requested(
    monkeypatch,
    tmp_path,
):
    from pathlib import Path

    from artwork.apply_policy import (
        ArtworkApplyMode,
    )
    from artwork.runner import (
        ArtworkRunOutcome,
    )
    from artwork.runtime import (
        run_configured_artwork_manager,
    )
    from artwork.targets import (
        ArtworkTarget,
        MediaType,
    )

    runtime = SimpleNamespace(
        provider=object(),
        tmdb_client=None,
        apply_mode=(
            ArtworkApplyMode.AUTO
        ),
    )

    monkeypatch.setattr(
        "artwork.runtime."
        "build_artwork_runtime",
        lambda config, environ=None:
            runtime,
    )

    target = ArtworkTarget(
        name="Series",
        library="Series",
        media_type=MediaType.SHOW,
        output_path=Path(
            "/metadata/artwork-series"
        ),
    )

    monkeypatch.setattr(
        "artwork.runtime."
        "discover_artwork_targets",
        lambda plex, config: (
            target,
        ),
    )

    workflow = SimpleNamespace(
        library="Series",
    )

    monkeypatch.setattr(
        "artwork.runtime."
        "build_artwork_target_workflow",
        lambda **kwargs:
            workflow,
    )

    library_result = SimpleNamespace(
        library="Series",
        outcome=(
            ArtworkRunOutcome
            .NO_CHANGES
        ),
    )

    monkeypatch.setattr(
        "artwork.runtime."
        "execute_artwork_library_workflow",
        lambda value, *, apply_mode:
            library_result,
    )

    seen = {}

    def fake_history(
        value,
        *,
        directory,
    ):
        seen["result"] = value
        seen["directory"] = (
            directory
        )

    monkeypatch.setattr(
        "artwork.runtime."
        "write_artwork_run_history",
        fake_history,
    )

    directory = (
        tmp_path
        / "artwork-manager"
    )

    returned = (
        run_configured_artwork_manager(
            plex=object(),
            config=_config(),
            environ={},
            history_directory=(
                directory
            ),
        )
    )

    assert returned is not None

    assert (
        returned.libraries
        == (
            library_result,
        )
    )

    assert seen == {
        "result":
            returned,

        "directory":
            directory,
    }



def test_configured_runner_continues_after_library_bootstrap_block(
    monkeypatch,
):
    from pathlib import Path

    from artwork.apply_policy import (
        ArtworkApplyMode,
    )
    from artwork.managed_state import (
        ArtworkStateBootstrapRequiredError,
    )
    from artwork.runner import (
        ArtworkLibraryRunFailure,
        ArtworkRunOutcome,
    )
    from artwork.runtime import (
        run_configured_artwork_manager,
    )
    from artwork.targets import (
        ArtworkTarget,
        MediaType,
    )

    runtime = SimpleNamespace(
        provider=object(),
        tmdb_client=None,
        apply_mode=(
            ArtworkApplyMode.AUTO
        ),
    )

    monkeypatch.setattr(
        "artwork.runtime."
        "build_artwork_runtime",
        lambda config, environ=None:
            runtime,
    )

    blocked_target = ArtworkTarget(
        name="Needs Bootstrap",
        library="Needs Bootstrap",
        media_type=MediaType.SHOW,
        output_path=Path(
            "/metadata/artwork-needs-bootstrap"
        ),
    )

    healthy_target = ArtworkTarget(
        name="Healthy Series",
        library="Healthy Series",
        media_type=MediaType.SHOW,
        output_path=Path(
            "/metadata/artwork-healthy-series"
        ),
    )

    monkeypatch.setattr(
        "artwork.runtime."
        "discover_artwork_targets",
        lambda plex, config: (
            blocked_target,
            healthy_target,
        ),
    )

    healthy_run = SimpleNamespace(
        library="Healthy Series",
    )

    def fake_build(
        **kwargs,
    ):
        target = kwargs[
            "target"
        ]

        if (
            target.library
            == "Needs Bootstrap"
        ):
            raise (
                ArtworkStateBootstrapRequiredError(
                    "explicit legacy bootstrap "
                    "metadata is required"
                )
            )

        return healthy_run

    monkeypatch.setattr(
        "artwork.runtime."
        "build_artwork_target_workflow",
        fake_build,
    )

    executed = []

    def fake_execute(
        run,
        *,
        apply_mode,
    ):
        executed.append(
            run.library
        )

        return SimpleNamespace(
            library=run.library,
            outcome=(
                ArtworkRunOutcome
                .NO_CHANGES
            ),
        )

    monkeypatch.setattr(
        "artwork.runtime."
        "execute_artwork_library_workflow",
        fake_execute,
    )

    result = (
        run_configured_artwork_manager(
            plex=object(),
            config=_config(),
            environ={},
        )
    )

    assert result is not None

    assert len(
        result.libraries
    ) == 2

    blocked = (
        result.libraries[0]
    )

    assert isinstance(
        blocked,
        ArtworkLibraryRunFailure,
    )

    assert (
        blocked.library
        == "Needs Bootstrap"
    )

    assert (
        blocked.outcome
        is ArtworkRunOutcome.BLOCKED
    )

    assert (
        blocked.error_type
        == (
            "ArtworkStateBootstrapRequiredError"
        )
    )

    assert executed == [
        "Healthy Series"
    ]

    assert (
        result.blocked_count
        == 1
    )

    assert (
        result.no_changes_count
        == 1
    )


def test_generator_is_disabled_by_default():
    runtime = build_artwork_runtime(
        _config(),
        environ={},
    )

    assert runtime is not None
    assert not runtime.generator_enabled
    assert runtime.generator_options is None


def test_runtime_builds_generator_options(
    tmp_path,
):
    config = _config()

    config["plex"] = {
        "url": "http://plex:32400",
        "token": "plex-token",
    }

    config["kometa_config"] = {
        "asset_directory":
            "/kometa/assets",
    }

    creative = (
        tmp_path
        / "artwork-generator.yaml"
    )

    creative.write_text(
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

    config[
        "services"
    ][
        "artwork_manager"
    ][
        "generated_episode_cards"
    ] = {
        "enabled": True,
        "kometa_asset_directory":
            "/config/assets",
        "config_file": str(
            creative
        ),
    }

    runtime = build_artwork_runtime(
        config,
        environ={},
    )

    assert runtime is not None
    assert runtime.generator_enabled

    options = (
        runtime.generator_options
    )

    assert options is not None

    assert str(
        options.local_root
    ) == (
        "/kometa/assets/"
        "generated-artwork"
    )

    assert options.kometa_root == (
        "/config/assets/"
        "generated-artwork"
    )

    assert (
        options.plex_base_url
        == "http://plex:32400"
    )

    assert (
        options.plex_token
        == "plex-token"
    )

    assert options.font_key is None

    assert (
        options.creative_config
        .resolve_style(
            library="TV",
        )
        .font
        == "marcellus"
    )

    assert (
        options.creative_config
        .resolve_style(
            library="Anime",
        )
        .font
        == "cormorant_garamond"
    )

    assert (
        options.creative_config
        .resolve_style(
            library="Anime",
            show_id="tmdb:1398",
        )
        .font
        == "prata"
    )


def test_generator_missing_creative_file_uses_safe_defaults(
    tmp_path,
):
    config = _config()

    config["plex"] = {
        "url": "http://plex:32400",
        "token": "plex-token",
    }

    config["kometa_config"] = {
        "asset_directory":
            "/kometa/assets",
    }

    config[
        "services"
    ][
        "artwork_manager"
    ][
        "generated_episode_cards"
    ] = {
        "enabled": True,
        "kometa_asset_directory":
            "/config/assets",
        "config_file": str(
            tmp_path
            / "missing.yaml"
        ),
    }

    runtime = build_artwork_runtime(
        config,
        environ={},
    )

    assert runtime is not None

    assert (
        runtime
        .generator_options
        .creative_config
        .resolve_style()
        .font
        == "marcellus"
    )


@pytest.mark.parametrize(
    "missing_field",
    (
        "plex_url",
        "plex_token",
        "dakosys_assets",
        "kometa_assets",
    ),
)
def test_enabled_generator_requires_runtime_paths_and_plex(
    tmp_path,
    missing_field,
):
    config = _config()

    config["plex"] = {
        "url": "http://plex:32400",
        "token": "plex-token",
    }

    config["kometa_config"] = {
        "asset_directory":
            "/kometa/assets",
    }

    generated = {
        "enabled": True,
        "kometa_asset_directory":
            "/config/assets",
        "config_file": str(
            tmp_path
            / "missing.yaml"
        ),
    }

    config[
        "services"
    ][
        "artwork_manager"
    ][
        "generated_episode_cards"
    ] = generated

    if missing_field == "plex_url":
        config["plex"].pop("url")

    elif missing_field == "plex_token":
        config["plex"].pop("token")

    elif missing_field == "dakosys_assets":
        config[
            "kometa_config"
        ].pop(
            "asset_directory"
        )

    elif missing_field == "kometa_assets":
        generated.pop(
            "kometa_asset_directory"
        )

    with pytest.raises(
        ValueError,
    ):
        build_artwork_runtime(
            config,
            environ={},
        )


def test_generator_enabled_must_be_boolean():
    config = _config()

    config[
        "services"
    ][
        "artwork_manager"
    ][
        "generated_episode_cards"
    ] = {
        "enabled": "false",
    }

    with pytest.raises(
        ValueError,
        match="boolean",
    ):
        build_artwork_runtime(
            config,
            environ={},
        )
