"""Normalized Plex movie inventory for Artwork Manager."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MovieIdentity:
    """Stable identity for one Plex movie."""

    title: str
    year: int | None
    library: str
    plex_rating_key: str

    tmdb_id: int | None = None
    imdb_id: str | None = None

    tmdb_id_candidates: tuple[int, ...] = field(
        default_factory=tuple,
        compare=False,
    )

    imdb_id_candidates: tuple[str, ...] = field(
        default_factory=tuple,
        compare=False,
    )


@dataclass(frozen=True)
class MovieInventory:
    """Normalized movie inventory consumed by Artwork Manager."""

    identity: MovieIdentity


def _guid_text(guid: Any) -> str:
    value = getattr(
        guid,
        "id",
        guid,
    )

    if value is None:
        return ""

    return str(value).strip()


def _guid_value(
    raw_value: str,
) -> str:
    value = raw_value.split(
        "?",
        1,
    )[0]

    return (
        value
        .strip()
        .strip("/")
    )


def _integer_id(
    value: str,
) -> int | None:
    try:
        parsed = int(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        return None

    if parsed <= 0:
        return None

    return parsed


def _year(
    value,
) -> int | None:
    if value is None:
        return None

    try:
        return int(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        return None


def build_movie_identity(
    movie,
    library: str,
) -> MovieIdentity:
    """Build a normalized identity from one Plex movie."""

    title = getattr(
        movie,
        "title",
        None,
    )

    if not title:
        raise ValueError(
            "Plex movie is missing a title."
        )

    rating_key = getattr(
        movie,
        "ratingKey",
        None,
    )

    if rating_key is None:
        rating_key = getattr(
            movie,
            "rating_key",
            None,
        )

    if rating_key is None:
        raise ValueError(
            f"Plex movie {title!r} "
            "is missing a rating key."
        )

    tmdb_id = None
    imdb_id = None

    tmdb_candidates = []
    imdb_candidates = []

    guids = (
        getattr(
            movie,
            "guids",
            None,
        )
        or ()
    )

    for guid in guids:
        raw_guid = _guid_text(
            guid
        )

        if "://" not in raw_guid:
            continue

        source, raw_value = (
            raw_guid.split(
                "://",
                1,
            )
        )

        source = (
            source.casefold()
        )

        value = _guid_value(
            raw_value
        )

        if not value:
            continue

        if source == "tmdb":
            parsed = (
                _integer_id(
                    value
                )
            )

            if (
                parsed is not None
                and parsed
                not in tmdb_candidates
            ):
                tmdb_candidates.append(
                    parsed
                )

            if (
                tmdb_id is None
                and parsed is not None
            ):
                tmdb_id = parsed

        elif source == "imdb":
            if (
                value
                not in imdb_candidates
            ):
                imdb_candidates.append(
                    value
                )

            if imdb_id is None:
                imdb_id = value

    return MovieIdentity(
        title=str(
            title
        ),
        year=_year(
            getattr(
                movie,
                "year",
                None,
            )
        ),
        library=str(
            library
        ),
        plex_rating_key=str(
            rating_key
        ),
        tmdb_id=tmdb_id,
        imdb_id=imdb_id,
        tmdb_id_candidates=tuple(
            tmdb_candidates
        ),
        imdb_id_candidates=tuple(
            imdb_candidates
        ),
    )


def build_movie_inventory(
    movie,
    library: str,
) -> MovieInventory:
    """Build normalized Artwork Manager inventory for one Plex movie."""

    return MovieInventory(
        identity=(
            build_movie_identity(
                movie,
                library,
            )
        )
    )
