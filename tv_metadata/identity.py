"""Build provider-independent TV identities from Plex objects."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .models import ShowIdentity


def _guid_text(guid: Any) -> str:
    """Return the string value of a Plex GUID object."""
    value = getattr(guid, "id", guid)

    if value is None:
        return ""

    return str(value).strip()


def _guid_value(raw_value: str) -> str:
    """Strip URL-like suffixes from a Plex external-ID GUID."""
    value = raw_value.split("?", 1)[0]
    return value.strip().strip("/")


def _integer_id(value: str) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None

    if parsed <= 0:
        return None

    return parsed


def build_show_identity(
    show: Any,
    library: str,
    *,
    library_roles: Iterable[str] = (),
) -> ShowIdentity:
    """Create a normalized ShowIdentity from a Plex show.

    Plex remains the source of truth for the item being processed.
    External IDs are collected independently so providers do not need
    to inspect Plex objects or perform fuzzy title matching.
    """

    title = getattr(show, "title", None)

    if not title:
        raise ValueError(
            "Plex show is missing a title."
        )

    rating_key = getattr(
        show,
        "ratingKey",
        None,
    )

    if rating_key is None:
        rating_key = getattr(
            show,
            "rating_key",
            None,
        )

    if rating_key is None:
        raise ValueError(
            f"Plex show {title!r} is missing a rating key."
        )

    raw_year = getattr(
        show,
        "year",
        None,
    )

    year: int | None

    if raw_year is None:
        year = None
    else:
        try:
            year = int(raw_year)
        except (TypeError, ValueError):
            year = None

    tmdb_id: int | None = None
    tvdb_id: int | None = None
    imdb_id: str | None = None

    guids = (
        getattr(show, "guids", None)
        or ()
    )

    for guid in guids:
        raw_guid = _guid_text(guid)

        if "://" not in raw_guid:
            continue

        source, value = raw_guid.split(
            "://",
            1,
        )

        source = source.casefold()
        value = _guid_value(value)

        if not value:
            continue

        if (
            source == "tmdb"
            and tmdb_id is None
        ):
            tmdb_id = _integer_id(value)

        elif (
            source == "tvdb"
            and tvdb_id is None
        ):
            tvdb_id = _integer_id(value)

        elif (
            source == "imdb"
            and imdb_id is None
        ):
            imdb_id = value

    roles = tuple(
        dict.fromkeys(
            str(role)
            for role in library_roles
            if role
        )
    )

    return ShowIdentity(
        title=str(title),
        year=year,
        library=str(library),
        plex_rating_key=str(
            rating_key
        ),
        tmdb_id=tmdb_id,
        tvdb_id=tvdb_id,
        imdb_id=imdb_id,
        library_roles=roles,
    )
