"""Artwork Manager output targets.

A target represents one Plex library and one generated Kometa metadata
output. Providers are inputs to Artwork Manager; Plex libraries are the
output-routing boundary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class MediaType(str, Enum):
    SHOW = "show"
    MOVIE = "movie"


@dataclass(frozen=True)
class ArtworkTarget:
    """One Plex library managed as an independent artwork output."""

    name: str
    library: str
    media_type: MediaType
    output_path: Path

    def __post_init__(self) -> None:
        name = str(self.name).strip()
        library = str(self.library).strip()
        output_path = Path(self.output_path)

        if not name:
            raise ValueError(
                "Artwork target name cannot be empty"
            )

        if not library:
            raise ValueError(
                "Artwork target library cannot be empty"
            )

        if output_path.suffix.casefold() not in {
            ".yaml",
            ".yml",
        }:
            raise ValueError(
                "Artwork target output must be a YAML file"
            )

        object.__setattr__(
            self,
            "name",
            name,
        )
        object.__setattr__(
            self,
            "library",
            library,
        )
        object.__setattr__(
            self,
            "output_path",
            output_path,
        )


def _target_slug(value: str) -> str:
    """Create a stable filename slug from a Plex library name."""

    slug = re.sub(
        r"[^a-z0-9]+",
        "-",
        value.casefold(),
    )

    return slug.strip("-")


def targets_from_config(
    config: dict,
) -> tuple[ArtworkTarget, ...]:
    """Build Artwork Manager targets from Dakosys configuration."""

    service = (
        (config.get("services") or {})
        .get("artwork_manager")
        or {}
    )

    if not service.get("enabled", False):
        return ()

    raw_output_dir = service.get(
        "output_dir"
    )

    if not raw_output_dir:
        raise ValueError(
            "services.artwork_manager.output_dir "
            "is required when Artwork Manager is enabled"
        )

    output_dir = Path(
        str(raw_output_dir)
    )

    raw_libraries = (
        service.get("libraries")
        or {}
    )

    if not isinstance(
        raw_libraries,
        dict,
    ):
        raise ValueError(
            "services.artwork_manager.libraries "
            "must be a mapping"
        )

    if not raw_libraries:
        raise ValueError(
            "services.artwork_manager.libraries "
            "must define at least one Plex library"
        )

    targets: list[
        ArtworkTarget
    ] = []

    output_paths: set[
        Path
    ] = set()

    for raw_library, raw_settings in (
        raw_libraries.items()
    ):
        library = str(
            raw_library
        ).strip()

        if not library:
            raise ValueError(
                "Artwork Manager library name "
                "cannot be empty"
            )

        settings = (
            raw_settings
            or {}
        )

        if not isinstance(
            settings,
            dict,
        ):
            raise ValueError(
                f"Artwork Manager settings for "
                f"{library!r} must be a mapping"
            )

        raw_media_type = settings.get(
            "media_type"
        )

        try:
            media_type = MediaType(
                str(raw_media_type).casefold()
            )
        except ValueError as exc:
            raise ValueError(
                f"Artwork Manager library "
                f"{library!r} has invalid "
                f"media_type {raw_media_type!r}"
            ) from exc

        raw_output = settings.get(
            "output"
        )

        if raw_output:
            output_path = Path(
                str(raw_output)
            )
        else:
            slug = _target_slug(
                library
            )

            if not slug:
                raise ValueError(
                    f"Artwork Manager library "
                    f"{library!r} cannot produce "
                    "a valid output filename"
                )

            output_path = (
                output_dir
                / f"artwork-{slug}.yaml"
            )

        if output_path in output_paths:
            raise ValueError(
                "Artwork Manager targets cannot "
                f"share output path {output_path}"
            )

        output_paths.add(
            output_path
        )

        targets.append(
            ArtworkTarget(
                name=library,
                library=library,
                media_type=media_type,
                output_path=output_path,
            )
        )

    return tuple(targets)
