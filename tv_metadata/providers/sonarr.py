"""Sonarr TV metadata provider."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import requests

from ..models import (
    EpisodeState,
    NextEpisode,
    ProviderResult,
    ShowIdentity,
    ShowLifecycle,
)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError:
        return None



def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed


def _normalize_lifecycle(
    status: str | None,
) -> ShowLifecycle:
    value = (status or "").casefold()

    if value == "ended":
        return ShowLifecycle.ENDED

    if value == "continuing":
        return ShowLifecycle.RETURNING

    return ShowLifecycle.UNKNOWN


def _normalize_episode_state(
    episode: dict[str, Any],
) -> EpisodeState:
    finale_type = (
        episode.get("finaleType")
        or ""
    ).casefold()

    if finale_type == "series":
        return EpisodeState.SERIES_FINALE

    if finale_type == "season":
        return EpisodeState.SEASON_FINALE

    if finale_type == "midseason":
        return EpisodeState.MID_SEASON_FINALE

    if episode.get("episodeNumber") == 1:
        return EpisodeState.SEASON_PREMIERE

    return EpisodeState.AIRING


class SonarrProvider:
    """Read-only Sonarr metadata provider.

    Shows are matched by exact TVDB ID. The Sonarr series inventory is
    loaded lazily and cached for the lifetime of the provider instance.
    """

    name = "sonarr"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        session: requests.Session | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

        self.session = (
            session
            if session is not None
            else requests.Session()
        )

        self.session.headers.update(
            {
                "X-Api-Key": self.api_key,
                "Accept": "application/json",
            }
        )

        self._series_by_tvdb: (
            dict[int, dict[str, Any]] | None
        ) = None

    def _get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        response = self.session.get(
            f"{self.base_url}{path}",
            params=params,
            timeout=self.timeout,
        )

        response.raise_for_status()

        return response.json()

    def _load_series(self) -> None:
        if self._series_by_tvdb is not None:
            return

        raw_series = self._get_json(
            "/api/v3/series"
        )

        by_tvdb: dict[
            int,
            dict[str, Any],
        ] = {}

        for show in raw_series:
            tvdb_id = show.get("tvdbId")

            if not isinstance(tvdb_id, int):
                continue

            if tvdb_id <= 0:
                continue

            by_tvdb[tvdb_id] = show

        self._series_by_tvdb = by_tvdb

    def _find_series(
        self,
        identity: ShowIdentity,
    ) -> dict[str, Any] | None:
        if identity.tvdb_id is None:
            return None

        self._load_series()

        assert self._series_by_tvdb is not None

        return self._series_by_tvdb.get(
            identity.tvdb_id
        )

    def _find_next_episode(
        self,
        show: dict[str, Any],
    ) -> dict[str, Any] | None:
        next_airing = _parse_datetime(
            show.get("nextAiring")
        )

        if next_airing is None:
            return None

        series_id = show.get("id")

        if series_id is None:
            return None

        episodes = self._get_json(
            "/api/v3/episode",
            params={
                "seriesId": series_id,
            },
        )

        for episode in episodes:
            air_datetime = _parse_datetime(
                episode.get("airDateUtc")
            )

            if air_datetime == next_airing:
                return episode

        return None

    def _normalize_next_episode(
        self,
        episode: dict[str, Any],
    ) -> NextEpisode:
        air_datetime = _parse_datetime(
            episode.get("airDateUtc")
        )

        provider_episode_id = (
            str(episode["id"])
            if episode.get("id") is not None
            else None
        )

        raw_finale_type = episode.get(
            "finaleType"
        )

        return NextEpisode(
            source=self.name,
            season=episode.get(
                "seasonNumber"
            ),
            episode=episode.get(
                "episodeNumber"
            ),
            air_date=(
                _parse_date(
                    episode.get("airDate")
                )
                if episode.get("airDate")
                else (
                    air_datetime.date()
                    if air_datetime is not None
                    else None
                )
            ),
            air_datetime=air_datetime,
            title=episode.get("title"),
            state=_normalize_episode_state(
                episode
            ),
            provider_episode_id=(
                provider_episode_id
            ),
            raw_episode_type=(
                raw_finale_type
            ),
        )

    def get_metadata(
        self,
        identity: ShowIdentity,
    ) -> ProviderResult:
        if identity.tvdb_id is None:
            return ProviderResult(
                source=self.name,
                matched=False,
                lifecycle=ShowLifecycle.UNKNOWN,
                reason="no_tvdb_id",
            )

        show = self._find_series(
            identity
        )

        if show is None:
            return ProviderResult(
                source=self.name,
                matched=False,
                lifecycle=ShowLifecycle.UNKNOWN,
                reason="not_found",
            )

        lifecycle = _normalize_lifecycle(
            show.get("status")
        )

        next_episode = None
        warnings: list[str] = []

        if show.get("nextAiring"):
            raw_episode = (
                self._find_next_episode(
                    show
                )
            )

            if raw_episode is not None:
                next_episode = (
                    self._normalize_next_episode(
                        raw_episode
                    )
                )
            else:
                warnings.append(
                    "next_airing_episode_not_found"
                )

        provider_show_id = (
            str(show["id"])
            if show.get("id") is not None
            else None
        )

        return ProviderResult(
            source=self.name,
            matched=True,
            lifecycle=lifecycle,
            next_episode=next_episode,
            provider_show_id=provider_show_id,
            warnings=tuple(warnings),
        )
