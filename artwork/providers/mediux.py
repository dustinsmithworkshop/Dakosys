"""MediUX artwork provider.

This module implements the current MediUX GraphQL contract used by
AURA, but does not assume that GraphQL asset fields are directly usable
as public Kometa image URLs.

Provider asset IDs are retained so URL/download materialization can be
handled independently.
"""

from __future__ import annotations

import json
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import (
    Request,
    urlopen,
)

from artwork.models import (
    ArtworkAsset,
    ArtworkKind,
    ArtworkQuality,
    ArtworkSet,
    ArtworkSource,
    EpisodeArtwork,
    SeasonArtwork,
)
from artwork.search import ArtworkSearchRequest


MEDIUX_GRAPHQL_ENDPOINT = (
    "https://images.mediux.io/graphql"
)


SHOW_SETS_QUERY = """
query getShowItemSetsByTMDBID($tmdb_id: ID!) {
  shows_by_id(id: $tmdb_id) {
    id
    title
    tvdb_id
    imdb_id

    show_sets(
      filter: {
        _or: [
          { show_poster: { id: { _nnull: true } } }
          { show_backdrop: { id: { _nnull: true } } }
          { season_posters: { id: { _nnull: true } } }
          { titlecards: { id: { _nnull: true } } }
        ]
      }
    ) {
      id
      set_title

      user_created {
        username
      }

      show_poster {
        id
        src
        modified_on
      }

      show_backdrop {
        id
        src
        modified_on
      }

      season_posters(
        filter: {
          season: {
            season_number: {
              _nnull: true
            }
          }
        }
      ) {
        id
        src
        modified_on

        season {
          season_number
        }
      }

      titlecards(
        filter: {
          episode: {
            episode_number: {
              _nnull: true
            }
            season_id: {
              season_number: {
                _nnull: true
              }
            }
          }
        }
      ) {
        id
        src
        modified_on

        episode {
          episode_number

          season_id {
            season_number
          }
        }
      }
    }
  }
}
"""


TVDB_TO_TMDB_QUERY = """
query findShowTMDBIDByTVDBID($tvdb_id: String!) {
  shows(
    filter: {
      tvdb_id: {
        _eq: $tvdb_id
      }
    }
  ) {
    id
    tvdb_id
  }
}
"""


class MediuxError(RuntimeError):
    """Base error raised by the MediUX provider."""


class MediuxAuthenticationError(MediuxError):
    """MediUX rejected the configured credential."""


class MediuxResponseError(MediuxError):
    """MediUX returned an invalid or unsuccessful response."""


class MediuxClient:
    """Small GraphQL transport for MediUX."""

    def __init__(
        self,
        api_token: str,
        *,
        endpoint: str = MEDIUX_GRAPHQL_ENDPOINT,
        timeout: float = 30.0,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        token = str(
            api_token or ""
        ).strip()

        if not token:
            raise ValueError(
                "MediUX API token cannot be empty"
            )

        self.api_token = token
        self.endpoint = endpoint
        self.timeout = timeout
        self._opener = opener

    def _graphql(
        self,
        *,
        query: str,
        variables: dict[str, Any],
        query_name: str,
    ) -> dict[str, Any]:
        body = json.dumps(
            {
                "query": query,
                "variables": variables,
                "query_name": query_name,
            }
        ).encode("utf-8")

        request = Request(
            self.endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": (
                    f"Bearer {self.api_token}"
                ),
                "Content-Type": (
                    "application/json"
                ),
                "Accept": (
                    "application/json"
                ),
                "User-Agent": (
                    "Dakosys-ArtworkManager"
                ),
            },
        )

        try:
            with self._opener(
                request,
                timeout=self.timeout,
            ) as response:
                status = getattr(
                    response,
                    "status",
                    200,
                )

                raw = response.read()

        except HTTPError as exc:
            if exc.code in {
                401,
                403,
            }:
                raise MediuxAuthenticationError(
                    "MediUX rejected the API token"
                ) from exc

            raise MediuxResponseError(
                "MediUX returned HTTP "
                f"{exc.code}"
            ) from exc

        except URLError as exc:
            raise MediuxResponseError(
                "Could not connect to MediUX"
            ) from exc

        if status < 200 or status >= 300:
            raise MediuxResponseError(
                "MediUX returned HTTP "
                f"{status}"
            )

        try:
            payload = json.loads(
                raw
            )
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise MediuxResponseError(
                "MediUX returned invalid JSON"
            ) from exc

        if not isinstance(
            payload,
            dict,
        ):
            raise MediuxResponseError(
                "MediUX returned an invalid "
                "GraphQL payload"
            )

        errors = payload.get(
            "errors"
        ) or []

        if errors:
            messages = []

            for error in errors:
                if isinstance(
                    error,
                    dict,
                ):
                    messages.append(
                        str(
                            error.get(
                                "message"
                            )
                            or error
                        )
                    )
                else:
                    messages.append(
                        str(error)
                    )

            raise MediuxResponseError(
                "MediUX GraphQL error: "
                + "; ".join(messages)
            )

        return payload

    def get_show_sets(
        self,
        tmdb_id: int | str,
    ) -> dict[str, Any]:
        """Return the raw MediUX show-set response."""

        return self._graphql(
            query=SHOW_SETS_QUERY,
            variables={
                "tmdb_id": str(
                    tmdb_id
                ),
            },
            query_name=(
                "getShowItemSetsByTMDBID"
            ),
        )

    def resolve_show_tmdb_id(
        self,
        tvdb_id: int | str,
    ) -> int | None:
        """Resolve a TVDB show ID through MediUX."""

        payload = self._graphql(
            query=TVDB_TO_TMDB_QUERY,
            variables={
                "tvdb_id": str(
                    tvdb_id
                ),
            },
            query_name=(
                "findShowTMDBIDByTVDBID"
            ),
        )

        shows = (
            payload
            .get("data", {})
            .get("shows")
            or []
        )

        if not shows:
            return None

        raw_id = (
            shows[0]
            .get("id")
        )

        try:
            return int(
                raw_id
            )
        except (
            TypeError,
            ValueError,
        ):
            raise MediuxResponseError(
                "MediUX returned an invalid "
                "TMDB ID"
            )


def _external_url(
    value: Any,
) -> str | None:
    """Preserve src only when MediUX returned a complete URL."""

    if not isinstance(
        value,
        str,
    ):
        return None

    value = value.strip()

    if value.startswith(
        (
            "https://",
            "http://",
        )
    ):
        return value

    return None


def _asset(
    raw: Any,
    kind: ArtworkKind,
) -> ArtworkAsset | None:
    if not isinstance(
        raw,
        dict,
    ):
        return None

    raw_id = raw.get(
        "id"
    )

    if raw_id is None:
        return None

    asset_id = str(
        raw_id
    ).strip()

    if not asset_id:
        return None

    return ArtworkAsset(
        kind=kind,
        source=ArtworkSource.MEDIUX,
        url=_external_url(
            raw.get("src")
        ),
        provider_asset_id=asset_id,
        quality=ArtworkQuality.CURATED,
    )


def _first_asset(
    values: Any,
    kind: ArtworkKind,
) -> ArtworkAsset | None:
    if not isinstance(
        values,
        list,
    ):
        return None

    for value in values:
        asset = _asset(
            value,
            kind,
        )

        if asset is not None:
            return asset

    return None


def _number(
    value: Any,
    *,
    minimum: int,
) -> int | None:
    try:
        number = int(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return None

    if number < minimum:
        return None

    return number


def parse_mediux_show_sets(
    payload: dict[str, Any],
    *,
    expected_tmdb_id: int | str | None = None,
) -> list[ArtworkSet]:
    """Convert MediUX GraphQL show sets to Dakosys models."""

    errors = payload.get(
        "errors"
    ) or []

    if errors:
        raise MediuxResponseError(
            "Cannot parse MediUX response "
            "containing GraphQL errors"
        )

    show = (
        payload
        .get("data", {})
        .get("shows_by_id")
    )

    if not show:
        return []

    if not isinstance(
        show,
        dict,
    ):
        raise MediuxResponseError(
            "MediUX shows_by_id payload "
            "is invalid"
        )

    if (
        expected_tmdb_id
        is not None
        and str(
            show.get("id")
        )
        != str(expected_tmdb_id)
    ):
        raise MediuxResponseError(
            "TMDB ID mismatch in MediUX "
            "show response"
        )

    raw_sets = (
        show.get("show_sets")
        or []
    )

    if not isinstance(
        raw_sets,
        list,
    ):
        raise MediuxResponseError(
            "MediUX show_sets payload "
            "is invalid"
        )

    results: list[
        ArtworkSet
    ] = []

    for raw_set in raw_sets:
        if not isinstance(
            raw_set,
            dict,
        ):
            continue

        raw_set_id = raw_set.get(
            "id"
        )

        if raw_set_id is None:
            continue

        set_id = str(
            raw_set_id
        ).strip()

        if not set_id:
            continue

        user = raw_set.get(
            "user_created"
        ) or {}

        creator = None

        if isinstance(
            user,
            dict,
        ):
            raw_creator = user.get(
                "username"
            )

            if raw_creator:
                creator = str(
                    raw_creator
                ).strip() or None

        raw_title = raw_set.get(
            "set_title"
        )

        title = (
            str(raw_title).strip()
            if raw_title is not None
            else None
        )

        if title == "":
            title = None

        artwork_set = ArtworkSet(
            provider=ArtworkSource.MEDIUX,
            set_id=set_id,
            creator=creator,
            title=title,
            poster=_first_asset(
                raw_set.get(
                    "show_poster"
                ),
                ArtworkKind.SHOW_POSTER,
            ),
            background=_first_asset(
                raw_set.get(
                    "show_backdrop"
                ),
                ArtworkKind.SHOW_BACKGROUND,
            ),
        )

        for raw_poster in (
            raw_set.get(
                "season_posters"
            )
            or []
        ):
            if not isinstance(
                raw_poster,
                dict,
            ):
                continue

            season_info = (
                raw_poster.get(
                    "season"
                )
                or {}
            )

            if not isinstance(
                season_info,
                dict,
            ):
                continue

            season_number = _number(
                season_info.get(
                    "season_number"
                ),
                minimum=0,
            )

            if season_number is None:
                continue

            poster = _asset(
                raw_poster,
                ArtworkKind.SEASON_POSTER,
            )

            if poster is None:
                continue

            season = (
                artwork_set.seasons
                .setdefault(
                    season_number,
                    SeasonArtwork(
                        season_number=(
                            season_number
                        ),
                    ),
                )
            )

            if season.poster is None:
                season.poster = poster

        for raw_card in (
            raw_set.get(
                "titlecards"
            )
            or []
        ):
            if not isinstance(
                raw_card,
                dict,
            ):
                continue

            episode_info = (
                raw_card.get(
                    "episode"
                )
                or {}
            )

            if not isinstance(
                episode_info,
                dict,
            ):
                continue

            season_info = (
                episode_info.get(
                    "season_id"
                )
                or {}
            )

            if not isinstance(
                season_info,
                dict,
            ):
                continue

            season_number = _number(
                season_info.get(
                    "season_number"
                ),
                minimum=0,
            )

            episode_number = _number(
                episode_info.get(
                    "episode_number"
                ),
                minimum=1,
            )

            if (
                season_number is None
                or episode_number is None
            ):
                continue

            card = _asset(
                raw_card,
                ArtworkKind.EPISODE_CARD,
            )

            if card is None:
                continue

            season = (
                artwork_set.seasons
                .setdefault(
                    season_number,
                    SeasonArtwork(
                        season_number=(
                            season_number
                        ),
                    ),
                )
            )

            if (
                episode_number
                not in season.episodes
            ):
                season.episodes[
                    episode_number
                ] = EpisodeArtwork(
                    episode_number=(
                        episode_number
                    ),
                    card=card,
                )

        results.append(
            artwork_set
        )

    return results


class MediuxProvider:
    """MediUX implementation of ArtworkProvider."""

    name = "mediux"

    def __init__(
        self,
        client: MediuxClient,
    ) -> None:
        self.client = client

    def find_sets(
        self,
        request: ArtworkSearchRequest,
    ) -> list[ArtworkSet]:
        tmdb_id = request.tmdb_id

        if (
            tmdb_id is None
            and request.tvdb_id is not None
        ):
            tmdb_id = (
                self.client
                .resolve_show_tmdb_id(
                    request.tvdb_id
                )
            )

        if tmdb_id is None:
            return []

        payload = (
            self.client
            .get_show_sets(
                tmdb_id
            )
        )

        return parse_mediux_show_sets(
            payload,
            expected_tmdb_id=tmdb_id,
        )
