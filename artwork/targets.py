"""Artwork Manager output targets.

Plex is the source of truth for which media libraries exist.

Artwork Manager automatically discovers supported Plex libraries and
creates one independent Kometa metadata output per library. Configuration
may restrict or override discovered targets, but library names and media
types are not hard-coded by Dakosys.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class MediaType(str, Enum):
    SHOW = "show"
    MOVIE = "movie"


_PLEX_MEDIA_TYPES = {
    "show": MediaType.SHOW,
    "movie": MediaType.MOVIE,
}


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

        if output_path.suffix.casefold() in {
            ".yaml",
            ".yml",
        }:
            raise ValueError(
                "Artwork target output must be an item-store "
                "directory, not a YAML file"
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
    """Create a filesystem-friendly slug from a Plex library name.

    Unicode letters and numbers are preserved so library discovery is not
    limited to English or ASCII library names.
    """

    normalized = unicodedata.normalize(
        "NFKC",
        value,
    ).casefold()

    result: list[str] = []
    previous_separator = False

    for character in normalized:
        if character.isalnum():
            result.append(character)
            previous_separator = False
            continue

        if result and not previous_separator:
            result.append("-")
            previous_separator = True

    return "".join(result).strip("-")


def _library_name_list(
    value,
    *,
    field: str,
) -> tuple[str, ...] | None:
    """Normalize an optional configuration list of Plex library names."""

    if value is None:
        return None

    if not isinstance(value, list):
        raise ValueError(
            f"{field} must be a list"
        )

    names: list[str] = []

    for raw_name in value:
        if not isinstance(raw_name, str):
            raise ValueError(
                f"{field} entries must be strings"
            )

        name = raw_name.strip()

        if not name:
            raise ValueError(
                f"{field} cannot contain an empty library name"
            )

        if name not in names:
            names.append(name)

    return tuple(names)


def _library_overrides(
    value,
) -> dict[str, dict]:
    """Normalize per-library Artwork Manager overrides."""

    if value is None:
        return {}

    if not isinstance(value, dict):
        raise ValueError(
            "services.artwork_manager.libraries.overrides "
            "must be a mapping"
        )

    overrides: dict[str, dict] = {}

    for raw_name, raw_settings in value.items():
        if not isinstance(raw_name, str):
            raise ValueError(
                "Artwork Manager override library names "
                "must be strings"
            )

        name = raw_name.strip()

        if not name:
            raise ValueError(
                "Artwork Manager override library name "
                "cannot be empty"
            )

        settings = raw_settings or {}

        if not isinstance(settings, dict):
            raise ValueError(
                f"Artwork Manager override for {name!r} "
                "must be a mapping"
            )

        if name in overrides:
            raise ValueError(
                f"duplicate Artwork Manager override for {name!r}"
            )

        overrides[name] = settings

    return overrides


def _artwork_output_dir(
    service: dict,
) -> Path:
    """Resolve the directory used for generated artwork metadata.

    Artwork metadata is a distinct Kometa concern from overlays and
    collections, so Artwork Manager requires its own explicit output
    directory.
    """

    raw_output_dir = service.get(
        "output_dir"
    )

    if not raw_output_dir:
        raise ValueError(
            "services.artwork_manager.output_dir "
            "is required when Artwork Manager is enabled"
        )

    value = str(
        raw_output_dir
    ).strip()

    if not value:
        raise ValueError(
            "Artwork Manager output directory "
            "cannot be empty"
        )

    return Path(value)


def discover_artwork_targets(
    plex,
    config: dict,
) -> tuple[ArtworkTarget, ...]:
    """Discover Artwork Manager targets from the connected Plex server.

    Plex library sections are authoritative for library names and media
    types.

    By default all supported movie and show libraries are managed.

    Optional configuration may:
    - include only specified Plex libraries
    - exclude specified Plex libraries
    - override an individual library's output path

    Music and photo libraries are ignored unless explicitly referenced,
    in which case an unsupported-type error is raised.
    """

    services = config.get("services") or {}

    service = (
        services.get("artwork_manager")
        or {}
    )

    if not service.get("enabled", False):
        return ()

    output_dir = _artwork_output_dir(
        service,
    )

    library_config = (
        service.get("libraries")
        or {}
    )

    if not isinstance(
        library_config,
        dict,
    ):
        raise ValueError(
            "services.artwork_manager.libraries "
            "must be a mapping"
        )

    include = _library_name_list(
        library_config.get("include"),
        field=(
            "services.artwork_manager."
            "libraries.include"
        ),
    )

    exclude = _library_name_list(
        library_config.get(
            "exclude",
            [],
        ),
        field=(
            "services.artwork_manager."
            "libraries.exclude"
        ),
    )

    assert exclude is not None

    overrides = _library_overrides(
        library_config.get(
            "overrides"
        )
    )

    sections = list(
        plex.library.sections()
    )

    sections_by_title = {}

    for section in sections:
        title = str(
            getattr(
                section,
                "title",
                "",
            )
            or ""
        ).strip()

        if not title:
            raise ValueError(
                "Plex returned a library section "
                "without a title"
            )

        if title in sections_by_title:
            raise ValueError(
                f"Plex returned duplicate library title "
                f"{title!r}"
            )

        sections_by_title[
            title
        ] = section

    referenced_names = set(
        exclude
    ) | set(
        overrides
    )

    if include is not None:
        referenced_names.update(
            include
        )

    missing_names = sorted(
        referenced_names
        - set(sections_by_title)
    )

    if missing_names:
        formatted = ", ".join(
            repr(name)
            for name in missing_names
        )

        raise ValueError(
            "Artwork Manager references Plex "
            "libraries that do not exist: "
            f"{formatted}"
        )

    targets: list[
        ArtworkTarget
    ] = []

    output_owners: dict[
        Path,
        str,
    ] = {}

    for section in sections:
        library = str(
            section.title
        ).strip()

        plex_type = str(
            getattr(
                section,
                "type",
                "",
            )
            or ""
        ).casefold()

        media_type = _PLEX_MEDIA_TYPES.get(
            plex_type
        )

        explicitly_included = (
            include is not None
            and library in include
        )

        explicitly_overridden = (
            library in overrides
        )

        if media_type is None:
            if (
                explicitly_included
                or explicitly_overridden
            ):
                raise ValueError(
                    f"Plex library {library!r} "
                    f"has unsupported type "
                    f"{plex_type!r}"
                )

            continue

        if (
            include is not None
            and library not in include
        ):
            continue

        if library in exclude:
            continue

        settings = overrides.get(
            library,
            {},
        )

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
                    f"Plex library {library!r} "
                    "cannot produce a valid "
                    "artwork output directory"
                )

            output_path = (
                output_dir
                / f"artwork-{slug}"
            )

        target = ArtworkTarget(
            name=library,
            library=library,
            media_type=media_type,
            output_path=output_path,
        )

        existing_owner = (
            output_owners.get(
                target.output_path
            )
        )

        if existing_owner is not None:
            raise ValueError(
                "Artwork Manager output collision: "
                f"{existing_owner!r} and "
                f"{library!r} both map to "
                f"{target.output_path}"
            )

        output_owners[
            target.output_path
        ] = library

        targets.append(
            target
        )

    return tuple(targets)
