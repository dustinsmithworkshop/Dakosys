"""Configured runtime construction for Artwork Manager.

This module is the configuration boundary between Dakosys and the
Artwork Manager workflow.

It constructs provider clients from normal Dakosys configuration and
environment variables, then exposes a configured workflow entry point.

Library discovery, artwork decisions, preview safety, and persistence
remain in the workflow/domain layers.
"""

from __future__ import annotations

import os
from collections.abc import (
    Iterable,
    Mapping,
)
from dataclasses import dataclass
from pathlib import Path

from artwork.apply_policy import (
    ArtworkApplyMode,
    resolve_artwork_apply_mode,
)
from artwork.episode_coverage import (
    EpisodeGeneratorOptions,
)
from artwork.generator_config import (
    load_artwork_generator_config,
)
from artwork.item_store import (
    ItemStoreError,
)
from artwork.managed_state import (
    ManagedStateBaselineError,
)
from artwork.progress import (
    ArtworkProgressCallback,
)
from artwork.providers.base import (
    ArtworkProvider,
)
from artwork.providers.mediux import (
    MediuxClient,
    MediuxProvider,
)
from artwork.providers.tmdb import (
    TMDBArtworkClient,
)
from artwork.runner import (
    ArtworkLibraryRunFailure,
    ArtworkManagerRunResult,
    ArtworkRunOutcome,
    execute_artwork_library_workflow,
)
from artwork.run_history import (
    write_artwork_run_history,
)
from artwork.state_store import (
    ArtworkStateStoreError,
)
from artwork.targets import (
    MediaType,
    discover_artwork_targets,
)
from artwork.workflow import (
    ArtworkManagerWorkflow,
    ArtworkWorkflowSkipReason,
    SkippedArtworkWorkflowTarget,
    build_artwork_manager_workflow,
    build_artwork_target_workflow,
    resolve_artwork_workflow_targets,
)


@dataclass(frozen=True)
class ArtworkRuntime:
    """Configured provider runtime for Artwork Manager."""

    provider: ArtworkProvider
    tmdb_client: TMDBArtworkClient | None
    apply_mode: ArtworkApplyMode

    generator_options: (
        EpisodeGeneratorOptions
        | None
    ) = None

    @property
    def generator_enabled(
        self,
    ) -> bool:
        return bool(
            self.generator_options
            is not None
            and self.generator_options.enabled
        )

    @property
    def primary_provider_name(self) -> str:
        return str(
            getattr(
                self.provider,
                "name",
                "",
            )
        )

    @property
    def tmdb_enabled(self) -> bool:
        return self.tmdb_client is not None


def _mapping(
    value,
    *,
    field: str,
) -> dict:
    """Normalize an optional configuration mapping."""

    if value is None:
        return {}

    if not isinstance(
        value,
        Mapping,
    ):
        raise ValueError(
            f"{field} must be a mapping"
        )

    return dict(value)


def _boolean(
    value,
    *,
    field: str,
    default: bool = False,
) -> bool:
    """Return one strict boolean configuration value."""

    if value is None:
        return default

    if not isinstance(
        value,
        bool,
    ):
        raise ValueError(
            f"{field} must be a boolean"
        )

    return value


def _optional_string(
    value,
    *,
    field: str,
) -> str | None:
    """Return one normalized optional string configuration value."""

    if value is None:
        return None

    if not isinstance(
        value,
        str,
    ):
        raise ValueError(
            f"{field} must be a string"
        )

    normalized = value.strip()

    return normalized or None


def build_artwork_runtime(
    config: dict,
    *,
    environ: Mapping[str, str] | None = None,
) -> ArtworkRuntime | None:
    """Construct Artwork Manager providers from Dakosys configuration.

    Returns ``None`` when Artwork Manager is disabled.

    MediUX is currently the required primary provider.

    MediUX credential precedence:
    1. MEDIUX_API_TOKEN environment variable
    2. services.artwork_manager.providers.mediux.api_token

    TMDB credential precedence:
    1. TMDB_TOKEN bearer-token environment variable
    2. top-level tmdb_api_key

    TMDB remains optional. When no TMDB credential exists, primary
    MediUX execution remains available but TMDB identity enrichment and
    episode-card fallback are disabled.
    """

    if not isinstance(
        config,
        Mapping,
    ):
        raise ValueError(
            "Dakosys config must be a mapping"
        )

    services = _mapping(
        config.get("services"),
        field="services",
    )

    service = _mapping(
        services.get(
            "artwork_manager"
        ),
        field=(
            "services.artwork_manager"
        ),
    )

    if not service.get(
        "enabled",
        False,
    ):
        return None

    apply_mode = (
        resolve_artwork_apply_mode(
            config
        )
    )

    providers = _mapping(
        service.get("providers"),
        field=(
            "services.artwork_manager."
            "providers"
        ),
    )

    mediux = _mapping(
        providers.get("mediux"),
        field=(
            "services.artwork_manager."
            "providers.mediux"
        ),
    )

    environment = (
        os.environ
        if environ is None
        else environ
    )

    mediux_environment_token = (
        _optional_string(
            environment.get(
                "MEDIUX_API_TOKEN"
            ),
            field="MEDIUX_API_TOKEN",
        )
    )

    mediux_config_token = (
        _optional_string(
            mediux.get(
                "api_token"
            ),
            field=(
                "services.artwork_manager."
                "providers.mediux."
                "api_token"
            ),
        )
    )

    mediux_token = (
        mediux_environment_token
        or mediux_config_token
    )

    if mediux_token is None:
        raise ValueError(
            "Artwork Manager requires a "
            "MediUX API token via "
            "MEDIUX_API_TOKEN or "
            "services.artwork_manager."
            "providers.mediux.api_token"
        )

    provider = MediuxProvider(
        MediuxClient(
            mediux_token
        )
    )

    tmdb_access_token = (
        _optional_string(
            environment.get(
                "TMDB_TOKEN"
            ),
            field="TMDB_TOKEN",
        )
    )

    tmdb_api_key = (
        _optional_string(
            config.get(
                "tmdb_api_key"
            ),
            field="tmdb_api_key",
        )
    )

    tmdb_client = None

    if tmdb_access_token is not None:
        tmdb_client = (
            TMDBArtworkClient(
                access_token=(
                    tmdb_access_token
                )
            )
        )

    elif tmdb_api_key is not None:
        tmdb_client = (
            TMDBArtworkClient(
                api_key=tmdb_api_key
            )
        )

    generated_episode_cards = _mapping(
        service.get(
            "generated_episode_cards"
        ),
        field=(
            "services.artwork_manager."
            "generated_episode_cards"
        ),
    )

    generator_enabled = _boolean(
        generated_episode_cards.get(
            "enabled"
        ),
        field=(
            "services.artwork_manager."
            "generated_episode_cards.enabled"
        ),
        default=False,
    )

    generator_options = None

    if generator_enabled:
        plex_config = _mapping(
            config.get("plex"),
            field="plex",
        )

        plex_url = _optional_string(
            plex_config.get("url"),
            field="plex.url",
        )

        plex_token = _optional_string(
            plex_config.get("token"),
            field="plex.token",
        )

        if plex_url is None:
            raise ValueError(
                "Artwork Generator requires "
                "plex.url"
            )

        if plex_token is None:
            raise ValueError(
                "Artwork Generator requires "
                "plex.token"
            )

        kometa_config = _mapping(
            config.get(
                "kometa_config"
            ),
            field="kometa_config",
        )

        dakosys_asset_directory = (
            _optional_string(
                kometa_config.get(
                    "asset_directory"
                ),
                field=(
                    "kometa_config."
                    "asset_directory"
                ),
            )
        )

        if (
            dakosys_asset_directory
            is None
        ):
            raise ValueError(
                "Artwork Generator requires "
                "kometa_config.asset_directory"
            )

        kometa_asset_directory = (
            _optional_string(
                generated_episode_cards.get(
                    "kometa_asset_directory"
                ),
                field=(
                    "services.artwork_manager."
                    "generated_episode_cards."
                    "kometa_asset_directory"
                ),
            )
        )

        if kometa_asset_directory is None:
            raise ValueError(
                "Artwork Generator requires "
                "services.artwork_manager."
                "generated_episode_cards."
                "kometa_asset_directory"
            )

        dakosys_asset_root = Path(
            dakosys_asset_directory
        )

        if not (
            dakosys_asset_root
            .is_absolute()
        ):
            raise ValueError(
                "kometa_config.asset_directory "
                "must be an absolute path for "
                "Artwork Generator"
            )

        if not (
            kometa_asset_directory
            .startswith("/")
        ):
            raise ValueError(
                "generated_episode_cards."
                "kometa_asset_directory must "
                "be an absolute POSIX path"
            )

        creative_config_file = (
            _optional_string(
                generated_episode_cards.get(
                    "config_file"
                ),
                field=(
                    "services.artwork_manager."
                    "generated_episode_cards."
                    "config_file"
                ),
            )
            or "config/artwork-generator.yaml"
        )

        creative_config = (
            load_artwork_generator_config(
                Path(
                    creative_config_file
                )
            )
        )

        generator_options = (
            EpisodeGeneratorOptions(
                enabled=True,
                local_root=(
                    dakosys_asset_root
                    / "generated-artwork"
                ),
                kometa_root=(
                    kometa_asset_directory
                    .rstrip("/")
                    + "/generated-artwork"
                ),
                creative_config=(
                    creative_config
                ),
                plex_base_url=plex_url,
                plex_token=plex_token,
            )
        )

    return ArtworkRuntime(
        provider=provider,
        tmdb_client=tmdb_client,
        apply_mode=apply_mode,
        generator_options=(
            generator_options
        ),
    )


def build_configured_artwork_manager_workflow(
    *,
    plex,
    config: dict,
    environ: Mapping[str, str] | None = None,
    selected_libraries: (
        str
        | Iterable[str]
        | None
    ) = None,
    legacy_metadata_by_library: (
        Mapping[
            str,
            str | Path,
        ]
        | None
    ) = None,
    incomplete_migration_threshold: (
        float
    ) = 0.25,
    progress_callback: (
        ArtworkProgressCallback
        | None
    ) = None,
) -> ArtworkManagerWorkflow:
    """Build a workflow using normal Dakosys configuration.

    This is the application-facing read-only entry point intended for
    CLI, scheduler, API, and GUI callers.

    When Artwork Manager is disabled, an empty workflow is returned.
    """

    runtime = build_artwork_runtime(
        config,
        environ=environ,
    )

    if runtime is None:
        return ArtworkManagerWorkflow(
            libraries=(),
            skipped=(),
        )

    return build_artwork_manager_workflow(
        plex=plex,
        config=config,
        provider=runtime.provider,
        tmdb_client=(
            runtime.tmdb_client
        ),
        generator_options=getattr(
            runtime,
            "generator_options",
            None,
        ),
        selected_libraries=(
            selected_libraries
        ),
        legacy_metadata_by_library=(
            legacy_metadata_by_library
        ),
        incomplete_migration_threshold=(
            incomplete_migration_threshold
        ),
        progress_callback=(
            progress_callback
        ),
    )


def run_configured_artwork_manager(
    *,
    plex,
    config: dict,
    environ: Mapping[str, str] | None = None,
    selected_libraries: (
        str
        | Iterable[str]
        | None
    ) = None,
    legacy_metadata_by_library: (
        Mapping[
            str,
            str | Path,
        ]
        | None
    ) = None,
    incomplete_migration_threshold: (
        float
    ) = 0.25,
    history_directory: (
        str
        | Path
        | None
    ) = None,
    progress_callback: (
        ArtworkProgressCallback
        | None
    ) = None,
) -> ArtworkManagerRunResult | None:
    """Execute configured Artwork Manager targets independently.

    Target discovery and selection happen once. Each discovered target
    then builds and executes independently so one library cannot prevent
    later libraries from reaching an operational result.

    Existing semantic-state, ownership, or filesystem integrity problems
    are BLOCKED. Unexpected build/provider failures are FAILED.

    Returns ``None`` when Artwork Manager is disabled.
    """

    runtime = build_artwork_runtime(
        config,
        environ=environ,
    )

    if runtime is None:
        return None

    targets = (
        discover_artwork_targets(
            plex,
            config,
        )
    )

    (
        execution_targets,
        legacy,
    ) = resolve_artwork_workflow_targets(
        targets,
        selected_libraries=(
            selected_libraries
        ),
        legacy_metadata_by_library=(
            legacy_metadata_by_library
        ),
    )

    libraries = []
    skipped = []

    blocking_errors = (
        ManagedStateBaselineError,
        ItemStoreError,
        ArtworkStateStoreError,
    )

    for target in execution_targets:
        try:
            run = (
                build_artwork_target_workflow(
                    plex=plex,
                    target=target,
                    provider=(
                        runtime.provider
                    ),
                    tmdb_client=(
                        runtime.tmdb_client
                    ),
                    generator_options=getattr(
                        runtime,
                        "generator_options",
                        None,
                    ),
                    legacy_metadata=(
                        legacy.get(
                            target.library
                        )
                    ),
                    incomplete_migration_threshold=(
                        incomplete_migration_threshold
                    ),
                    progress_callback=(
                        progress_callback
                    ),
                )
            )

        except blocking_errors as exc:
            libraries.append(
                ArtworkLibraryRunFailure(
                    target=target,
                    apply_mode=(
                        runtime.apply_mode
                    ),
                    outcome=(
                        ArtworkRunOutcome
                        .BLOCKED
                    ),
                    error_type=(
                        type(exc).__name__
                    ),
                    error_message=str(
                        exc
                    ),
                )
            )

            continue

        except Exception as exc:
            libraries.append(
                ArtworkLibraryRunFailure(
                    target=target,
                    apply_mode=(
                        runtime.apply_mode
                    ),
                    outcome=(
                        ArtworkRunOutcome
                        .FAILED
                    ),
                    error_type=(
                        type(exc).__name__
                    ),
                    error_message=str(
                        exc
                    ),
                )
            )

            continue

        try:
            library_result = (
                execute_artwork_library_workflow(
                    run,
                    apply_mode=(
                        runtime.apply_mode
                    ),
                )
            )

        except Exception as exc:
            # The normal executor already converts transactional apply
            # failures to FAILED. This final boundary protects the
            # aggregate run from unexpected policy/review failures too.
            libraries.append(
                ArtworkLibraryRunFailure(
                    target=target,
                    apply_mode=(
                        runtime.apply_mode
                    ),
                    outcome=(
                        ArtworkRunOutcome
                        .FAILED
                    ),
                    error_type=(
                        type(exc).__name__
                    ),
                    error_message=str(
                        exc
                    ),
                )
            )

            continue

        libraries.append(
            library_result
        )

    result = ArtworkManagerRunResult(
        apply_mode=(
            runtime.apply_mode
        ),
        libraries=tuple(
            libraries
        ),
        skipped=tuple(
            skipped
        ),
    )

    if history_directory is not None:
        write_artwork_run_history(
            result,
            directory=Path(
                history_directory
            ),
        )

    return result

