"""Import existing Kometa/MediUX metadata into Artwork Manager state."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from artwork.models import (
    ArtworkAsset,
    ArtworkKind,
    ArtworkQuality,
    ArtworkSource,
    EpisodeArtwork,
    SeasonArtwork,
    ShowArtworkState,
)


_MEDIUX_SET_RE = re.compile(
    r"https?://(?:www\.)?mediux\.pro/sets/(?P<set_id>\d+)",
    re.IGNORECASE,
)

_CREATOR_RE = re.compile(
    r"Set by (?P<creator>.+?) on MediUX",
    re.IGNORECASE,
)


def _mediux_asset(
    *,
    kind: ArtworkKind,
    url: str | None,
) -> ArtworkAsset | None:
    if not url:
        return None

    return ArtworkAsset(
        kind=kind,
        source=ArtworkSource.MEDIUX,
        url=url,
        quality=ArtworkQuality.CURATED,
    )


def _extract_comment_metadata(
    text: str,
    tvdb_id: int,
) -> tuple[str | None, str | None, str | None]:
    """Return title, MediUX set ID, and creator from inline metadata comment."""

    pattern = re.compile(
        rf"^\s*{re.escape(str(tvdb_id))}\s*:\s*#(?P<comment>.*)$",
        re.MULTILINE,
    )

    match = pattern.search(text)

    if match is None:
        return None, None, None

    comment = match.group("comment").strip()

    title = None
    title_match = re.search(
        r"TVDB id for (?P<title>.+?)\.\s+Set by ",
        comment,
        re.IGNORECASE,
    )

    if title_match is not None:
        title = title_match.group("title").strip()

    set_id = None
    set_match = _MEDIUX_SET_RE.search(comment)

    if set_match is not None:
        set_id = set_match.group("set_id")

    creator = None
    creator_match = _CREATOR_RE.search(comment)

    if creator_match is not None:
        creator = creator_match.group("creator").strip()

    return title, set_id, creator


def import_mediux_metadata(
    path: str | Path,
) -> list[ShowArtworkState]:
    """Import Kometa metadata containing MediUX artwork."""

    path = Path(path)

    raw_text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw_text) or {}

    metadata = data.get("metadata") or {}

    shows: list[ShowArtworkState] = []

    for raw_tvdb_id, raw_show in metadata.items():
        try:
            tvdb_id = int(raw_tvdb_id)
        except (TypeError, ValueError):
            continue

        show_data = raw_show or {}

        title, set_id, creator = _extract_comment_metadata(
            raw_text,
            tvdb_id,
        )

        seasons: dict[int, SeasonArtwork] = {}

        for raw_season_number, raw_season in (
            show_data.get("seasons") or {}
        ).items():
            try:
                season_number = int(raw_season_number)
            except (TypeError, ValueError):
                continue

            season_data = raw_season or {}

            episodes: dict[int, EpisodeArtwork] = {}

            for raw_episode_number, raw_episode in (
                season_data.get("episodes") or {}
            ).items():
                try:
                    episode_number = int(raw_episode_number)
                except (TypeError, ValueError):
                    continue

                episode_data = raw_episode or {}

                episodes[episode_number] = EpisodeArtwork(
                    episode_number=episode_number,
                    card=_mediux_asset(
                        kind=ArtworkKind.EPISODE_CARD,
                        url=episode_data.get("url_poster"),
                    ),
                )

            seasons[season_number] = SeasonArtwork(
                season_number=season_number,
                poster=_mediux_asset(
                    kind=ArtworkKind.SEASON_POSTER,
                    url=season_data.get("url_poster"),
                ),
                episodes=episodes,
            )

        shows.append(
            ShowArtworkState(
                title=title,
                tvdb_id=tvdb_id,
                poster=_mediux_asset(
                    kind=ArtworkKind.SHOW_POSTER,
                    url=show_data.get("url_poster"),
                ),
                background=_mediux_asset(
                    kind=ArtworkKind.SHOW_BACKGROUND,
                    url=show_data.get("url_background"),
                ),
                seasons=seasons,
                selected_set_id=set_id,
                selected_set_source=(
                    ArtworkSource.MEDIUX
                    if set_id is not None
                    else None
                ),
                selected_creator=creator,
            )
        )

    return shows
