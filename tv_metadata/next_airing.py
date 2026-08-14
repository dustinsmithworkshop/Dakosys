"""Provider-independent local Next Airing collection support."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

import yaml

from .models import (
    NextAiringEntry,
    ShowIdentity,
    ShowStatus,
)


def build_next_airing_entry(
    identity: ShowIdentity,
    status: ShowStatus,
) -> NextAiringEntry | None:
    """Create an entry when a show has a dated upcoming episode."""
    episode = status.next_episode

    if episode is None:
        return None

    if (
        episode.air_date is None
        and episode.air_datetime is None
    ):
        return None

    return NextAiringEntry(
        title=identity.title,
        year=identity.year,
        library=identity.library,
        plex_rating_key=identity.plex_rating_key,
        next_episode=episode,
        tmdb_id=identity.tmdb_id,
        tvdb_id=identity.tvdb_id,
        imdb_id=identity.imdb_id,
    )


def next_airing_date(
    entry: NextAiringEntry,
    timezone_name: str,
) -> date | None:
    """Return the date Dakosys presents to the user."""
    episode = entry.next_episode

    if episode.air_datetime is not None:
        return (
            episode.air_datetime
            .astimezone(
                ZoneInfo(timezone_name)
            )
            .date()
        )

    return episode.air_date


def sort_next_airing(
    entries: Iterable[NextAiringEntry],
    timezone_name: str,
) -> list[NextAiringEntry]:
    """Sort by displayed local air date, then title."""
    return sorted(
        entries,
        key=lambda entry: (
            next_airing_date(
                entry,
                timezone_name,
            )
            or date.max,
            entry.title.casefold(),
            entry.year or 0,
        ),
    )


def group_next_airing_by_library(
    entries: Iterable[NextAiringEntry],
    timezone_name: str,
) -> dict[str, list[NextAiringEntry]]:
    """Group and sort entries by physical Plex library."""
    grouped: dict[
        str,
        list[NextAiringEntry],
    ] = defaultdict(list)

    for entry in entries:
        grouped[
            entry.library
        ].append(entry)

    return {
        library: sort_next_airing(
            library_entries,
            timezone_name,
        )
        for library, library_entries
        in grouped.items()
    }


def text_file_identifier(
    entry: NextAiringEntry,
) -> str:
    """Return the strongest Kometa-compatible show identifier.

    TVDb is preferred because nearly the entire current Plex inventory
    exposes a TVDb show ID. TMDb and IMDb provide independent fallbacks.
    """
    if entry.tvdb_id is not None:
        return f"tvdb:{entry.tvdb_id}"

    if entry.tmdb_id is not None:
        return f"tmdb:{entry.tmdb_id}"

    if entry.imdb_id:
        return f"imdb:{entry.imdb_id}"

    raise ValueError(
        "Next Airing entry has no Kometa-compatible "
        f"external ID: {entry.title!r}"
    )


def build_text_file_lines(
    entries: Iterable[NextAiringEntry],
    timezone_name: str,
) -> list[str]:
    """Build ordered Kometa text_file lines."""
    lines = []

    for entry in sort_next_airing(
        entries,
        timezone_name,
    ):
        identifier = text_file_identifier(
            entry
        )

        air_date = next_airing_date(
            entry,
            timezone_name,
        )

        comment = entry.title.replace(
            "\n",
            " ",
        )

        if air_date is not None:
            lines.append(
                f"{identifier}  "
                f"# {air_date.isoformat()} | "
                f"{comment}"
            )
        else:
            lines.append(
                f"{identifier}  # {comment}"
            )

    return lines


def build_kometa_collection(
    library_name: str,
    text_file_path: str,
    *,
    poster_path: str = (
        "config/assets/Next Airing/poster.jpg"
    ),
) -> dict:
    """Build Kometa YAML backed by an ordered local text file."""
    return {
        "collections": {
            f"Next Airing {library_name}": {
                "text_file": text_file_path,
                "file_poster": poster_path,
                "collection_order": "custom",
                "visible_home": True,
                "visible_shared": True,
                "sync_mode": "sync",
            }
        }
    }


def write_text_file(
    output_path: str | Path,
    entries: Iterable[NextAiringEntry],
    timezone_name: str,
) -> Path:
    """Write the ordered provider-independent membership file."""
    path = Path(output_path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    lines = build_text_file_lines(
        entries,
        timezone_name,
    )

    contents = "\n".join(lines)

    if contents:
        contents += "\n"

    path.write_text(
        contents,
        encoding="utf-8",
    )

    return path


def write_kometa_collection(
    output_path: str | Path,
    library_name: str,
    text_file_path: str,
    *,
    poster_path: str = (
        "config/assets/Next Airing/poster.jpg"
    ),
) -> Path:
    """Write the Kometa collection definition."""
    path = Path(output_path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    data = build_kometa_collection(
        library_name,
        text_file_path,
        poster_path=poster_path,
    )

    path.write_text(
        yaml.safe_dump(
            data,
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    return path


def write_next_airing_files(
    collections_dir: str | Path,
    library_name: str,
    entries: Iterable[NextAiringEntry],
    timezone_name: str,
    *,
    kometa_collection_dir: str = (
        "config/collections"
    ),
) -> tuple[Path, Path]:
    """Write the ordered text file and matching Kometa YAML."""
    directory = Path(
        collections_dir
    )

    slug = (
        library_name
        .lower()
        .replace(" ", "-")
    )

    text_filename = (
        f"{slug}-next-airing.txt"
    )

    yaml_filename = (
        f"{slug}-next-airing.yml"
    )

    text_path = (
        directory
        / text_filename
    )

    yaml_path = (
        directory
        / yaml_filename
    )

    write_text_file(
        text_path,
        entries,
        timezone_name,
    )

    kometa_text_path = (
        f"{kometa_collection_dir.rstrip('/')}/"
        f"{text_filename}"
    )

    write_kometa_collection(
        yaml_path,
        library_name,
        kometa_text_path,
    )

    return yaml_path, text_path
