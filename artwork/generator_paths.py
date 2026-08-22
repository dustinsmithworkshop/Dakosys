"""Filesystem path translation for generated Artwork Generator assets."""

from __future__ import annotations

import posixpath
from pathlib import PurePosixPath


class GeneratedArtworkPathError(
    ValueError
):
    """Generated artwork path configuration is invalid."""


def translate_generated_artwork_path(
    *,
    local_path: str,
    local_root: str,
    kometa_root: str,
) -> str:
    """Translate Dakosys's generated file path into Kometa's view.

    Example:

        local_root:
            /kometa/assets/generated

        local_path:
            /kometa/assets/generated/tv/tmdb-1398/season-01/card.jpg

        kometa_root:
            /config/assets/generated

        result:
            /config/assets/generated/tv/tmdb-1398/season-01/card.jpg

    Translation is lexical and does not require the file to already
    exist, which allows preview/planning code to use it safely.
    """

    source = _absolute_path(
        local_path,
        label="local path",
    )

    source_root = _absolute_path(
        local_root,
        label="local root",
    )

    destination_root = _absolute_path(
        kometa_root,
        label="Kometa root",
    )

    try:
        relative = (
            source.relative_to(
                source_root
            )
        )

    except ValueError as exc:
        raise GeneratedArtworkPathError(
            "generated artwork path is "
            "outside configured local root"
        ) from exc

    if ".." in relative.parts:
        raise GeneratedArtworkPathError(
            "generated artwork path cannot "
            "escape configured local root"
        )

    destination = (
        destination_root
        / relative
    )

    return str(
        destination
    )


def _absolute_path(
    value,
    *,
    label: str,
) -> PurePosixPath:
    if not isinstance(
        value,
        str,
    ):
        raise GeneratedArtworkPathError(
            f"{label} must be a string"
        )

    value = value.strip()

    if not value:
        raise GeneratedArtworkPathError(
            f"{label} cannot be empty"
        )

    normalized = posixpath.normpath(
        value
    )

    path = PurePosixPath(
        normalized
    )

    if not path.is_absolute():
        raise GeneratedArtworkPathError(
            f"{label} must be an "
            "absolute POSIX path"
        )

    return path
