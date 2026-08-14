"""Generate Kometa metadata from normalized Artwork Manager state."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import yaml

from artwork.models import ShowArtworkState


def _asset_url(asset):
    if asset is None:
        return None

    return asset.url


def build_kometa_metadata(
    shows: Iterable[ShowArtworkState],
) -> dict:
    """Build a Kometa-compatible metadata mapping."""

    metadata: dict[int, dict] = {}

    for show in shows:
        if show.tvdb_id is None:
            continue

        show_entry: dict = {}

        poster_url = _asset_url(show.poster)
        if poster_url:
            show_entry["url_poster"] = poster_url

        background_url = _asset_url(show.background)
        if background_url:
            show_entry["url_background"] = background_url

        seasons: dict[int, dict] = {}

        for season_number, season in sorted(show.seasons.items()):
            season_entry: dict = {}

            season_poster = _asset_url(season.poster)
            if season_poster:
                season_entry["url_poster"] = season_poster

            episodes: dict[int, dict] = {}

            for episode_number, episode in sorted(
                season.episodes.items()
            ):
                card_url = _asset_url(episode.card)

                if not card_url:
                    continue

                episodes[episode_number] = {
                    "url_poster": card_url,
                }

            if episodes:
                season_entry["episodes"] = episodes

            if season_entry:
                seasons[season_number] = season_entry

        if seasons:
            show_entry["seasons"] = seasons

        metadata[show.tvdb_id] = show_entry

    return {
        "metadata": metadata,
    }


def write_kometa_metadata(
    shows: Iterable[ShowArtworkState],
    path: str | Path,
) -> Path:
    """Write Kometa-compatible metadata YAML."""

    path = Path(path)
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    data = build_kometa_metadata(shows)

    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(
            data,
            handle,
            sort_keys=False,
            allow_unicode=True,
        )

    return path
