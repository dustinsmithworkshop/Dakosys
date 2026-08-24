"""Canonical Artwork Manager configuration status."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from artwork.apply_policy import (
    resolve_artwork_apply_mode,
)
from artwork.runtime import (
    build_artwork_runtime,
)
from artwork.targets import (
    discover_artwork_targets,
)


def _mapping(
    value,
) -> dict:
    if isinstance(
        value,
        Mapping,
    ):
        return dict(value)

    return {}


def build_artwork_status(
    *,
    config: dict,
    plex=None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build one canonical Artwork Manager/Generator status payload."""

    services = _mapping(
        config.get("services")
    )

    service = _mapping(
        services.get(
            "artwork_manager"
        )
    )

    enabled = bool(
        service.get(
            "enabled",
            False,
        )
    )

    scheduler = _mapping(
        config.get("scheduler")
    )

    schedule = scheduler.get(
        "artwork_manager"
    )

    base = {
        "enabled": enabled,
        "apply_mode": (
            resolve_artwork_apply_mode(
                config
            ).value
        ),
        "schedule": schedule,
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

    if not enabled:
        return base

    runtime = build_artwork_runtime(
        config,
        environ=environ,
    )

    if runtime is None:
        return base

    base[
        "primary_provider"
    ] = runtime.primary_provider_name

    base[
        "tmdb_enabled"
    ] = runtime.tmdb_enabled

    options = runtime.generator_options

    if (
        runtime.generator_enabled
        and options is not None
    ):
        generated = _mapping(
            service.get(
                "generated_episode_cards"
            )
        )

        config_file = (
            generated.get(
                "config_file"
            )
            or "config/artwork-generator.yaml"
        )

        base["generator"] = {
            "enabled": True,
            "config_file": str(
                config_file
            ),
            "local_asset_root": str(
                options.local_root
            ),
            "kometa_asset_root": str(
                options.kometa_root
            ),
            "default_font": (
                options
                .creative_config
                .defaults
                .font
            ),
        }

    if plex is not None:
        targets = tuple(
            discover_artwork_targets(
                plex,
                config,
            )
        )

        base["libraries"] = [
            {
                "library":
                    target.library,
                "media_type":
                    target.media_type.value,
                "output_path":
                    str(
                        target.output_path
                    ),
                "supported":
                    True,
                "skip_reason":
                    None,
            }
            for target in targets
        ]

    return base
