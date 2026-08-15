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


def _import_episodes(
    raw_episodes: dict,
) -> dict[int, EpisodeArtwork]:
    """Normalize an episode mapping into EpisodeArtwork objects."""

    episodes: dict[int, EpisodeArtwork] = {}

    for raw_episode_number, raw_episode in raw_episodes.items():
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

    return episodes


def _has_numeric_season_keys(
    raw_seasons: dict,
) -> bool:
    for key in raw_seasons:
        try:
            int(key)
        except (TypeError, ValueError):
            continue
        else:
            return True

    return False


def import_mediux_metadata(
    path: str | Path,
) -> list[ShowArtworkState]:
    """Import Kometa metadata containing MediUX artwork.

    Legacy files sometimes place ``episodes`` directly below ``seasons``
    without a numeric season key. When that is the only season structure,
    normalize those episodes into Season 1.
    """

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

        raw_seasons = show_data.get("seasons") or {}

        # Normalize legacy structure:
        #
        # seasons:
        #   episodes:
        #     1: ...
        #
        # into Season 1, but only when no numeric season keys coexist.
        if (
            "episodes" in raw_seasons
            and not _has_numeric_season_keys(raw_seasons)
        ):
            seasons[1] = SeasonArtwork(
                season_number=1,
                episodes=_import_episodes(
                    raw_seasons.get("episodes") or {}
                ),
            )

        for raw_season_number, raw_season in raw_seasons.items():
            try:
                season_number = int(raw_season_number)
            except (TypeError, ValueError):
                continue

            season_data = raw_season or {}

            seasons[season_number] = SeasonArtwork(
                season_number=season_number,
                poster=_mediux_asset(
                    kind=ArtworkKind.SEASON_POSTER,
                    url=season_data.get("url_poster"),
                ),
                episodes=_import_episodes(
                    season_data.get("episodes") or {}
                ),
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
