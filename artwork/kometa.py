"""Generate Kometa metadata from normalized Artwork Manager state."""

from __future__ import annotations

from collections.abc import Iterable

import yaml

from artwork.models import ShowArtworkState


def _asset_url(asset):
    if asset is None:
        return None

    return asset.url


def build_kometa_metadata(
    shows: Iterable[ShowArtworkState],
) -> dict:
    """Build a deterministic Kometa-compatible metadata mapping.

    Shows without a TVDB identity are omitted because Kometa cannot
    address them through this metadata format.

    Duplicate TVDB identities are rejected rather than silently
    overwriting one show's output with another.
    """

    metadata: dict[int, dict] = {}

    for show in shows:
        if show.tvdb_id is None:
            continue

        if show.tvdb_id in metadata:
            raise ValueError(
                "duplicate TVDB identity in "
                "Kometa artwork output: "
                f"{show.tvdb_id}"
            )

        show_entry: dict = {}

        poster_url = _asset_url(
            show.poster
        )

        if poster_url:
            show_entry[
                "url_poster"
            ] = poster_url

        background_url = _asset_url(
            show.background
        )

        if background_url:
            show_entry[
                "url_background"
            ] = background_url

        seasons: dict[int, dict] = {}

        for (
            season_number,
            season,
        ) in sorted(
            show.seasons.items()
        ):
            season_entry: dict = {}

            season_poster = (
                _asset_url(
                    season.poster
                )
            )

            if season_poster:
                season_entry[
                    "url_poster"
                ] = season_poster

            episodes: dict[
                int,
                dict,
            ] = {}

            for (
                episode_number,
                episode,
            ) in sorted(
                season.episodes.items()
            ):
                card_url = (
                    _asset_url(
                        episode.card
                    )
                )

                if not card_url:
                    continue

                episodes[
                    episode_number
                ] = {
                    "url_poster":
                        card_url,
                }

            if episodes:
                season_entry[
                    "episodes"
                ] = episodes

            if season_entry:
                seasons[
                    season_number
                ] = season_entry

        if seasons:
            show_entry[
                "seasons"
            ] = seasons

        metadata[
            show.tvdb_id
        ] = show_entry

    # Input order should never determine generated file order.
    metadata = dict(
        sorted(
            metadata.items()
        )
    )

    return {
        "metadata": metadata,
    }


def _validate_kometa_yaml(
    contents: str,
    expected: dict,
) -> None:
    """Verify rendered YAML parses back to the expected structure."""

    try:
        parsed = yaml.safe_load(
            contents
        )
    except yaml.YAMLError as exc:
        raise ValueError(
            "generated Kometa artwork YAML "
            "could not be parsed"
        ) from exc

    if parsed != expected:
        raise ValueError(
            "generated Kometa artwork YAML "
            "failed semantic round-trip validation"
        )


def _render_kometa_data(
    data: dict,
) -> str:
    """Render and validate normalized Kometa metadata."""

    contents = yaml.safe_dump(
        data,
        sort_keys=False,
        allow_unicode=True,
    )

    _validate_kometa_yaml(
        contents,
        data,
    )

    return contents


def render_kometa_metadata(
    shows: Iterable[ShowArtworkState],
) -> str:
    """Render validated Kometa YAML without touching the filesystem."""

    data = build_kometa_metadata(
        shows
    )

    return _render_kometa_data(
        data
    )
