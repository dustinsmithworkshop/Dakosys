"""TMDB TV metadata provider."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import requests

from ..models import (
    EpisodeState,
    NextEpisode,
    ProviderResult,
    ShowIdentity,
    ShowLifecycle,
)


TMDB_BASE_URL = "https://api.themoviedb.org/3"


def _normalize_title(value: str | None) -> str:
    if not value:
        return ""

    return re.sub(
        r"[^a-z0-9]+",
        "",
        value.casefold(),
    )


def _year_from_date(
    value: str | None,
) -> int | None:
    if not value:
        return None

    try:
        return int(value[:4])
    except (TypeError, ValueError):
        return None


def _parse_date(
    value: str | None,
) -> date | None:
    if not value:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _normalize_lifecycle(
    status: str | None,
) -> ShowLifecycle:
    value = (status or "").casefold()

    if value in {
        "ended",
        "canceled",
        "cancelled",
    }:
        return ShowLifecycle.ENDED

    if value in {
        "returning series",
        "in production",
    }:
        return ShowLifecycle.RETURNING

    return ShowLifecycle.UNKNOWN


def _normalize_episode_state(
    episode: dict[str, Any],
) -> EpisodeState:
    raw_type = (
        episode.get("episode_type")
        or ""
    ).casefold()

    # TMDB currently exposes a less granular finale
    # type than Sonarr. Do not infer a series finale
    # unless TMDB explicitly supplies that meaning.
    if raw_type == "series_finale":
        return EpisodeState.SERIES_FINALE

    if raw_type in {
        "finale",
        "season_finale",
    }:
        return EpisodeState.SEASON_FINALE

    if raw_type in {
        "mid_season",
        "midseason",
        "mid_season_finale",
    }:
        return EpisodeState.MID_SEASON_FINALE

    if episode.get("episode_number") == 1:
        return EpisodeState.SEASON_PREMIERE

    return EpisodeState.AIRING


def _identity_warnings(
    identity: ShowIdentity,
    show: dict[str, Any],
) -> tuple[str, ...]:
    warnings: list[str] = []

    plex_title = _normalize_title(
        identity.title
    )

    tmdb_titles = {
        _normalize_title(
            show.get("name")
        ),
        _normalize_title(
            show.get("original_name")
        ),
    }

    tmdb_titles.discard("")

    if (
        plex_title
        and tmdb_titles
        and plex_title not in tmdb_titles
    ):
        warnings.append(
            "title_differs"
        )

    tmdb_year = _year_from_date(
        show.get("first_air_date")
    )

    if (
        identity.year is not None
        and tmdb_year is not None
        and identity.year != tmdb_year
    ):
        warnings.append(
            f"year_differs:"
            f"{identity.year}->{tmdb_year}"
        )

    return tuple(warnings)


class TMDBProvider:
    """Read-only TMDB metadata provider.

    Identity resolution:
    1. Direct Plex TMDB ID.
    2. Exact TVDB external-ID lookup when TMDB ID is absent.
    3. Exact IMDb external-ID lookup when prior lookup fails.

    No title search or fuzzy matching is performed.
    """

    name = "tmdb"

    def __init__(
        self,
        access_token: str | None = None,
        *,
        api_key: str | None = None,
        base_url: str = TMDB_BASE_URL,
        session: requests.Session | None = None,
        timeout: float = 30.0,
    ) -> None:
        if not access_token and not api_key:
            raise ValueError(
                "TMDB access token or API key is required"
            )

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        # Bearer authentication takes precedence when both are
        # supplied. The existing Dakosys tmdb_api_key setting
        # remains supported through the v3 api_key query parameter.
        self.api_key = (
            None
            if access_token
            else api_key
        )

        self.session = (
            session
            if session is not None
            else requests.Session()
        )

        self.session.headers.update(
            {
                "Accept": "application/json",
            }
        )

        if access_token:
            self.session.headers[
                "Authorization"
            ] = f"Bearer {access_token}"

    def _get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> requests.Response:
        request_params = dict(
            params or {}
        )

        if self.api_key:
            request_params[
                "api_key"
            ] = self.api_key

        return self.session.get(
            f"{self.base_url}{path}",
            params=(
                request_params
                or None
            ),
            timeout=self.timeout,
        )

    def _fetch_show(
        self,
        tmdb_id: int,
    ) -> dict[str, Any] | None:
        response = self._get(
            f"/tv/{tmdb_id}"
        )

        if response.status_code == 404:
            return None

        response.raise_for_status()

        return response.json()

    def _find_external_id(
        self,
        source: str,
        value: str | int,
    ) -> tuple[int | None, str | None]:
        if source == "tvdb":
            external_source = "tvdb_id"
        elif source == "imdb":
            external_source = "imdb_id"
        else:
            raise ValueError(
                f"Unsupported external "
                f"source: {source}"
            )

        response = self._get(
            f"/find/{value}",
            params={
                "external_source": (
                    external_source
                ),
            },
        )

        response.raise_for_status()

        results = (
            response.json().get(
                "tv_results"
            )
            or []
        )

        if not results:
            return None, "not_found"

        if len(results) > 1:
            return (
                None,
                "ambiguous_external_id",
            )

        tmdb_id = results[0].get("id")

        if not isinstance(tmdb_id, int):
            return None, "invalid_result"

        return tmdb_id, None

    def _resolve_tmdb_id(
        self,
        identity: ShowIdentity,
    ) -> tuple[int | None, str | None]:
        if identity.tmdb_id is not None:
            return (
                identity.tmdb_id,
                "tmdb",
            )

        attempts: list[
            tuple[str, str | int]
        ] = []

        if identity.tvdb_id is not None:
            attempts.append(
                (
                    "tvdb",
                    identity.tvdb_id,
                )
            )

        if identity.imdb_id:
            attempts.append(
                (
                    "imdb",
                    identity.imdb_id,
                )
            )

        if not attempts:
            return None, None

        for source, value in attempts:
            tmdb_id, _reason = (
                self._find_external_id(
                    source,
                    value,
                )
            )

            if tmdb_id is not None:
                return tmdb_id, source

        return None, "external_lookup_failed"

    def _normalize_next_episode(
        self,
        episode: dict[str, Any],
    ) -> NextEpisode:
        provider_episode_id = (
            str(episode["id"])
            if episode.get("id") is not None
            else None
        )

        raw_episode_type = (
            episode.get("episode_type")
        )

        return NextEpisode(
            source=self.name,
            season=episode.get(
                "season_number"
            ),
            episode=episode.get(
                "episode_number"
            ),
            air_date=_parse_date(
                episode.get("air_date")
            ),
            air_datetime=None,
            title=episode.get("name"),
            state=_normalize_episode_state(
                episode
            ),
            provider_episode_id=(
                provider_episode_id
            ),
            raw_episode_type=(
                raw_episode_type
            ),
        )

    def get_metadata(
        self,
        identity: ShowIdentity,
    ) -> ProviderResult:
        tmdb_id, resolution = (
            self._resolve_tmdb_id(
                identity
            )
        )

        if tmdb_id is None:
            reason = (
                "no_supported_id"
                if resolution is None
                else "external_id_lookup_failed"
            )

            return ProviderResult(
                source=self.name,
                matched=False,
                lifecycle=ShowLifecycle.UNKNOWN,
                reason=reason,
            )

        show = self._fetch_show(
            tmdb_id
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

        raw_next_episode = (
            show.get(
                "next_episode_to_air"
            )
        )

        if raw_next_episode:
            next_episode = (
                self._normalize_next_episode(
                    raw_next_episode
                )
            )

        warnings = _identity_warnings(
            identity,
            show,
        )

        return ProviderResult(
            source=self.name,
            matched=True,
            lifecycle=lifecycle,
            next_episode=next_episode,
            provider_show_id=str(
                show.get("id", tmdb_id)
            ),
            warnings=warnings,
        )
