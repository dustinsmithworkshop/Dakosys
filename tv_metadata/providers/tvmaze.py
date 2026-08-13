"""TVmaze TV metadata provider."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import urlparse

import requests

from ..models import (
    EpisodeState,
    NextEpisode,
    ProviderResult,
    ShowIdentity,
    ShowLifecycle,
)


TVMAZE_BASE_URL = "https://api.tvmaze.com"


def _normalize_title(
    value: str | None,
) -> str:
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


def _parse_datetime(
    value: str | None,
) -> datetime | None:
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00",
            )
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

    if value == "running":
        return ShowLifecycle.RETURNING

    # TVmaze also uses values such as
    # "To Be Determined". Do not guess.
    return ShowLifecycle.UNKNOWN


def _normalize_episode_state(
    episode: dict[str, Any],
) -> EpisodeState:
    # TVmaze does not give us the same
    # finale semantics that Sonarr does.
    if episode.get("number") == 1:
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

    tvmaze_title = _normalize_title(
        show.get("name")
    )

    if (
        plex_title
        and tvmaze_title
        and plex_title != tvmaze_title
    ):
        warnings.append(
            "title_differs"
        )

    tvmaze_year = _year_from_date(
        show.get("premiered")
    )

    if (
        identity.year is not None
        and tvmaze_year is not None
        and identity.year != tvmaze_year
    ):
        warnings.append(
            f"year_differs:"
            f"{identity.year}->{tvmaze_year}"
        )

    return tuple(warnings)


class TVmazeProvider:
    """Read-only TVmaze metadata provider.

    Identity resolution:
    1. Exact TVDB lookup.
    2. Exact IMDb lookup when TVDB is unavailable or not found.
    3. No title search or fuzzy matching.

    If a TVDB result has suspicious title/year metadata and Plex also has
    an IMDb ID, the IMDb ID is cross-checked. Conflicting TVmaze show IDs
    are exposed as a warning rather than silently changing the match.
    """

    name = "tvmaze"

    def __init__(
        self,
        *,
        base_url: str = TVMAZE_BASE_URL,
        session: requests.Session | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

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

    def _get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        allow_redirects: bool = True,
    ) -> Any:
        return self.session.get(
            f"{self.base_url}{path}",
            params=params,
            timeout=self.timeout,
            allow_redirects=allow_redirects,
        )

    def _lookup_id(
        self,
        source: str,
        value: str | int,
    ) -> int | None:
        if source == "tvdb":
            params = {
                "thetvdb": str(value),
            }
        elif source == "imdb":
            params = {
                "imdb": str(value),
            }
        else:
            raise ValueError(
                f"Unsupported TVmaze "
                f"lookup source: {source}"
            )

        response = self._get(
            "/lookup/shows",
            params=params,
            allow_redirects=False,
        )

        if response.status_code == 404:
            return None

        if response.status_code == 200:
            data = response.json()
            tvmaze_id = data.get("id")

            if isinstance(tvmaze_id, int):
                return tvmaze_id

            return None

        if response.status_code in {
            301,
            302,
            307,
            308,
        }:
            location = (
                response.headers.get(
                    "Location",
                    "",
                )
            )

            parsed = urlparse(location)

            match = re.search(
                r"/shows/(\d+)",
                parsed.path,
            )

            if not match:
                raise RuntimeError(
                    "TVmaze lookup redirect "
                    "did not contain a show ID"
                )

            return int(
                match.group(1)
            )

        response.raise_for_status()

        return None

    def _fetch_show(
        self,
        tvmaze_id: int,
    ) -> dict[str, Any] | None:
        response = self._get(
            f"/shows/{tvmaze_id}",
            params={
                "embed": "nextepisode",
            },
            allow_redirects=False,
        )

        if response.status_code == 404:
            return None

        response.raise_for_status()

        return response.json()

    def _resolve_show_id(
        self,
        identity: ShowIdentity,
    ) -> tuple[
        int | None,
        str | None,
    ]:
        if identity.tvdb_id is not None:
            tvmaze_id = self._lookup_id(
                "tvdb",
                identity.tvdb_id,
            )

            if tvmaze_id is not None:
                return tvmaze_id, "tvdb"

        if identity.imdb_id:
            tvmaze_id = self._lookup_id(
                "imdb",
                identity.imdb_id,
            )

            if tvmaze_id is not None:
                return tvmaze_id, "imdb"

        return None, None

    def _normalize_next_episode(
        self,
        episode: dict[str, Any],
    ) -> NextEpisode:
        provider_episode_id = (
            str(episode["id"])
            if episode.get("id") is not None
            else None
        )

        raw_type = episode.get("type")

        return NextEpisode(
            source=self.name,
            season=episode.get("season"),
            episode=episode.get("number"),
            air_date=_parse_date(
                episode.get("airdate")
            ),
            air_datetime=_parse_datetime(
                episode.get("airstamp")
            ),
            title=episode.get("name"),
            state=_normalize_episode_state(
                episode
            ),
            provider_episode_id=(
                provider_episode_id
            ),
            raw_episode_type=raw_type,
        )

    def get_metadata(
        self,
        identity: ShowIdentity,
    ) -> ProviderResult:
        if (
            identity.tvdb_id is None
            and not identity.imdb_id
        ):
            return ProviderResult(
                source=self.name,
                matched=False,
                lifecycle=ShowLifecycle.UNKNOWN,
                reason="no_supported_id",
            )

        tvmaze_id, lookup_source = (
            self._resolve_show_id(
                identity
            )
        )

        if tvmaze_id is None:
            return ProviderResult(
                source=self.name,
                matched=False,
                lifecycle=ShowLifecycle.UNKNOWN,
                reason="not_found",
            )

        show = self._fetch_show(
            tvmaze_id
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

        warnings = list(
            _identity_warnings(
                identity,
                show,
            )
        )

        # Our audit exposed a real-world case where
        # Plex's TVDB and IMDb IDs map to different
        # TVmaze records. Cross-check only when the
        # TVDB result already looks suspicious.
        if (
            lookup_source == "tvdb"
            and warnings
            and identity.imdb_id
        ):
            imdb_tvmaze_id = (
                self._lookup_id(
                    "imdb",
                    identity.imdb_id,
                )
            )

            if (
                imdb_tvmaze_id is not None
                and imdb_tvmaze_id
                != tvmaze_id
            ):
                warnings.append(
                    "identity_conflict:"
                    f"tvdb={tvmaze_id},"
                    f"imdb={imdb_tvmaze_id}"
                )

        next_episode = None

        embedded = (
            show.get("_embedded")
            or {}
        )

        raw_next_episode = (
            embedded.get(
                "nextepisode"
            )
        )

        if raw_next_episode:
            next_episode = (
                self._normalize_next_episode(
                    raw_next_episode
                )
            )

        return ProviderResult(
            source=self.name,
            matched=True,
            lifecycle=lifecycle,
            next_episode=next_episode,
            provider_show_id=str(
                show.get(
                    "id",
                    tvmaze_id,
                )
            ),
            warnings=tuple(warnings),
        )
