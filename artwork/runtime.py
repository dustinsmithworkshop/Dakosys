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
from artwork.workflow import (
    ArtworkManagerWorkflow,
    build_artwork_manager_workflow,
)


@dataclass(frozen=True)
class ArtworkRuntime:
    """Configured provider runtime for Artwork Manager."""

    provider: ArtworkProvider
    tmdb_client: TMDBArtworkClient | None
    apply_mode: ArtworkApplyMode

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

    return ArtworkRuntime(
        provider=provider,
        tmdb_client=tmdb_client,
        apply_mode=apply_mode,
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
        selected_libraries=(
            selected_libraries
        ),
        legacy_metadata_by_library=(
            legacy_metadata_by_library
        ),
        incomplete_migration_threshold=(
            incomplete_migration_threshold
        ),
    )
