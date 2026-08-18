"""Artwork Manager automatic-vs-manual apply policy."""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum


class ArtworkApplyMode(str, Enum):
    """How safe Artwork Manager changes are handled."""

    AUTO = "auto"
    MANUAL = "manual"


def resolve_artwork_apply_mode(
    config: Mapping,
) -> ArtworkApplyMode:
    """Resolve Artwork Manager apply mode.

    Automatic apply is the default. Manual review is explicit opt-in.
    """

    if not isinstance(
        config,
        Mapping,
    ):
        raise ValueError(
            "Dakosys config must be a mapping"
        )

    services = (
        config.get(
            "services",
            {},
        )
        or {}
    )

    if not isinstance(
        services,
        Mapping,
    ):
        raise ValueError(
            "services must be a mapping"
        )

    service = (
        services.get(
            "artwork_manager",
            {},
        )
        or {}
    )

    if not isinstance(
        service,
        Mapping,
    ):
        raise ValueError(
            "services.artwork_manager "
            "must be a mapping"
        )

    raw = service.get(
        "apply_mode",
        ArtworkApplyMode.AUTO.value,
    )

    if not isinstance(
        raw,
        str,
    ):
        raise ValueError(
            "services.artwork_manager.apply_mode "
            "must be a string"
        )

    normalized = (
        raw.strip()
        .casefold()
    )

    try:
        return ArtworkApplyMode(
            normalized
        )

    except ValueError as exc:
        raise ValueError(
            "services.artwork_manager.apply_mode "
            "must be 'auto' or 'manual'"
        ) from exc
