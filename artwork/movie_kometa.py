"""Generate Kometa metadata from normalized movie artwork state."""

from __future__ import annotations

from collections.abc import Iterable

import yaml

from artwork.models import (
    MovieArtworkState,
)


def _asset_url(
    asset,
) -> str | None:
    if asset is None:
        return None

    return asset.url


def movie_mapping_id(
    state: MovieArtworkState,
) -> int | str | None:
    """Return the preferred Kometa mapping identity for one movie."""

    tmdb_id = state.tmdb_id

    if (
        isinstance(
            tmdb_id,
            int,
        )
        and not isinstance(
            tmdb_id,
            bool,
        )
        and tmdb_id > 0
    ):
        return tmdb_id

    imdb_id = state.imdb_id

    if not isinstance(
        imdb_id,
        str,
    ):
        return None

    imdb_id = (
        imdb_id
        .strip()
        .casefold()
    )

    if (
        len(imdb_id) > 2
        and imdb_id.startswith(
            "tt"
        )
        and imdb_id[2:].isdigit()
    ):
        return imdb_id

    return None


def build_movie_kometa_metadata(
    movies: Iterable[
        MovieArtworkState
    ],
) -> dict:
    """Build deterministic Kometa-compatible movie metadata."""

    metadata: dict[
        int | str,
        dict,
    ] = {}

    for movie in movies:
        mapping_id = (
            movie_mapping_id(
                movie
            )
        )

        if mapping_id is None:
            continue

        if mapping_id in metadata:
            raise ValueError(
                "duplicate movie mapping identity "
                "in Kometa artwork output: "
                f"{mapping_id!r}"
            )

        entry: dict = {}

        poster_url = _asset_url(
            movie.poster
        )

        if poster_url:
            entry[
                "url_poster"
            ] = poster_url

        background_url = (
            _asset_url(
                movie.background
            )
        )

        if background_url:
            entry[
                "url_background"
            ] = background_url

        metadata[
            mapping_id
        ] = entry

    metadata = dict(
        sorted(
            metadata.items(),
            key=lambda item: (
                (
                    0,
                    item[0],
                )
                if isinstance(
                    item[0],
                    int,
                )
                else (
                    1,
                    item[0],
                )
            ),
        )
    )

    return {
        "metadata":
            metadata,
    }


def render_movie_kometa_metadata(
    movies: Iterable[
        MovieArtworkState
    ],
) -> str:
    """Render validated Kometa movie YAML without filesystem writes."""

    data = (
        build_movie_kometa_metadata(
            movies
        )
    )

    contents = yaml.safe_dump(
        data,
        sort_keys=False,
        allow_unicode=True,
    )

    try:
        parsed = yaml.safe_load(
            contents
        )

    except yaml.YAMLError as exc:
        raise ValueError(
            "generated Kometa movie artwork "
            "YAML could not be parsed"
        ) from exc

    if parsed != data:
        raise ValueError(
            "generated Kometa movie artwork "
            "YAML failed semantic "
            "round-trip validation"
        )

    return contents
