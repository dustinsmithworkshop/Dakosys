"""Artwork Manager output targets.

A target represents one Plex library and one generated Kometa metadata
output. Providers are inputs to Artwork Manager; Plex libraries are the
output-routing boundary.
"""

from __future__ import annotations

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
