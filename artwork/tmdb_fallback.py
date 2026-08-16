"""Fill unresolved episode-card gaps with TMDB stills."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import Enum

from artwork.inventory import ShowInventory
from artwork.models import (
    EpisodeArtwork,
    SeasonArtwork,
    ShowArtworkState,
)
from artwork.providers.tmdb import (
    TMDBArtworkClient,
)


class TMDBFallbackPath(
    str,
    Enum,
):
    NO_GAPS = "no_gaps"
    NO_TMDB_ID = "no_tmdb_id"
    IDENTITY_MISMATCH = (
        "identity_mismatch"
    )
    FILLED_ALL = "filled_all"
    FILLED_PARTIAL = "filled_partial"
    NO_STILLS = "no_stills"
    PROVIDER_ERROR = "provider_error"


@dataclass(frozen=True)
class TMDBSeasonFailure:
    season_number: int
    error_type: str
    error_message: str


@dataclass(frozen=True)
class TMDBFallbackResult:
    """Result of resolving missing episode cards through TMDB."""

    state: ShowArtworkState
    path: TMDBFallbackPath

    gaps_before: int
    gaps_filled: int
    gaps_remaining: int

    season_request_count: int = 0

    failures: tuple[
        TMDBSeasonFailure,
        ...,
    ] = ()

    @property
    def changed(self) -> bool:
        return self.gaps_filled > 0

    @property
    def provider_error_count(
        self,
    ) -> int:
        return len(
            self.failures
        )


def _has_card(
    state: ShowArtworkState,
    *,
    season_number: int,
    episode_number: int,
) -> bool:
    season = state.seasons.get(
        season_number
    )

    if season is None:
        return False

    episode = season.episodes.get(
        episode_number
    )

    if (
        episode is None
        or episode.card is None
    ):
        return False

    return episode.card.available


def _missing_expected_episodes(
    *,
    inventory: ShowInventory,
    state: ShowArtworkState,
) -> dict[int, frozenset[int]]:
    expected = (
        inventory.expected_episodes()
    )

    missing: dict[
        int,
        frozenset[int],
    ] = {}

    for (
        season_number,
        episode_numbers,
    ) in expected.items():
        gaps = frozenset(
            episode_number
            for episode_number
            in episode_numbers
            if not _has_card(
                state,
                season_number=(
                    season_number
                ),
                episode_number=(
                    episode_number
                ),
            )
        )

        if gaps:
            missing[
                season_number
            ] = gaps

    return missing


def fill_tmdb_episode_gaps(
    *,
    inventory: ShowInventory,
    state: ShowArtworkState,
    client: TMDBArtworkClient,
) -> TMDBFallbackResult:
    """Fill only missing expected episode cards with TMDB stills.

    Existing usable cards are never replaced.

    Provider failure for one season does not discard artwork resolved
    for another season.
    """

    missing = (
        _missing_expected_episodes(
            inventory=inventory,
            state=state,
        )
    )

    gaps_before = sum(
        len(episodes)
        for episodes in missing.values()
    )

    if gaps_before == 0:
        return TMDBFallbackResult(
            state=state,
            path=(
                TMDBFallbackPath.NO_GAPS
            ),
            gaps_before=0,
            gaps_filled=0,
            gaps_remaining=0,
        )

    state_tmdb_id = state.tmdb_id
    plex_tmdb_id = (
        inventory.identity.tmdb_id
    )

    if (
        state_tmdb_id is not None
        and plex_tmdb_id is not None
        and state_tmdb_id
        != plex_tmdb_id
    ):
        return TMDBFallbackResult(
            state=state,
            path=(
                TMDBFallbackPath
                .IDENTITY_MISMATCH
            ),
            gaps_before=gaps_before,
            gaps_filled=0,
            gaps_remaining=gaps_before,
        )

    tmdb_id = (
        state_tmdb_id
        if state_tmdb_id is not None
        else plex_tmdb_id
    )

    # Artwork inventories may have a stable TVDB or IMDb identity even
    # when Plex supplied no direct TMDB GUID. Reuse Dakosys's existing
    # exact external-ID resolver rather than falling back to title
    # search or fuzzy matching.
    if tmdb_id is None:
        tmdb_id, _resolution_source = (
            client.resolve_tmdb_id(
                inventory.identity
            )
        )

    if tmdb_id is None:
        return TMDBFallbackResult(
            state=state,
            path=(
                TMDBFallbackPath
                .NO_TMDB_ID
            ),
            gaps_before=gaps_before,
            gaps_filled=0,
            gaps_remaining=gaps_before,
        )

    resolved = deepcopy(
        state
    )

    # Preserve successfully resolved identity in durable output when
    # the input state did not already know its TMDB ID.
    if resolved.tmdb_id is None:
        resolved.tmdb_id = tmdb_id

    filled = 0
    requests = 0

    failures: list[
        TMDBSeasonFailure
    ] = []

    for season_number in sorted(
        missing
    ):
        requests += 1

        try:
            candidates = (
                client
                .get_season_episode_cards(
                    tmdb_id=tmdb_id,
                    season_number=(
                        season_number
                    ),
                )
            )

        except Exception as exc:
            failures.append(
                TMDBSeasonFailure(
                    season_number=(
                        season_number
                    ),
                    error_type=(
                        type(exc).__name__
                    ),
                    error_message=str(
                        exc
                    ),
                )
            )

            continue

        for episode_number in sorted(
            missing[season_number]
        ):
            card = candidates.get(
                episode_number
            )

            if (
                card is None
                or not card.available
            ):
                continue

            # Re-check against the copied state so this remains safe
            # even if the resolver changes to aggregate providers later.
            if _has_card(
                resolved,
                season_number=(
                    season_number
                ),
                episode_number=(
                    episode_number
                ),
            ):
                continue

            season = (
                resolved.seasons.get(
                    season_number
                )
            )

            if season is None:
                season = SeasonArtwork(
                    season_number=(
                        season_number
                    )
                )

                resolved.seasons[
                    season_number
                ] = season

            episode = (
                season.episodes.get(
                    episode_number
                )
            )

            if episode is None:
                episode = EpisodeArtwork(
                    episode_number=(
                        episode_number
                    )
                )

                season.episodes[
                    episode_number
                ] = episode

            episode.card = card
            filled += 1

    remaining = (
        gaps_before
        - filled
    )

    if remaining == 0:
        path = (
            TMDBFallbackPath
            .FILLED_ALL
        )

    elif filled > 0:
        path = (
            TMDBFallbackPath
            .FILLED_PARTIAL
        )

    elif (
        failures
        and len(failures)
        == requests
    ):
        path = (
            TMDBFallbackPath
            .PROVIDER_ERROR
        )

    else:
        path = (
            TMDBFallbackPath
            .NO_STILLS
        )

    return TMDBFallbackResult(
        state=resolved,
        path=path,
        gaps_before=gaps_before,
        gaps_filled=filled,
        gaps_remaining=remaining,
        season_request_count=requests,
        failures=tuple(
            failures
        ),
    )
