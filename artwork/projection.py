"""Project resolved artwork state onto the current Plex inventory.

Providers and imported durable state may contain seasons or episodes that
are not present in Plex. Artwork Manager output is Plex-backed: only
current Plex season/episode identities are eligible for generated Kometa
metadata.

Projection never mutates the input state.
"""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

from artwork.models import ShowArtworkState

if TYPE_CHECKING:
    from artwork.inventory import ShowInventory
    from artwork.target_execution import ShowTargetExecution


def project_show_state_to_inventory(
    *,
    inventory: ShowInventory,
    state: ShowArtworkState,
) -> ShowArtworkState:
    """Return a copy containing only Plex-backed season/episode state.

    Show-level artwork and selection provenance are preserved.

    A season is retained only when it exists in Plex and already has
    artwork state. Within that season, only Plex-expected episode
    identities are retained.

    Season posters for current Plex seasons are preserved even when that
    season has no resolved episode cards.
    """

    projected = deepcopy(
        state
    )

    seasons = {}

    for expected_season in (
        inventory.seasons
    ):
        season_number = (
            expected_season
            .season_number
        )

        season = (
            projected.seasons.get(
                season_number
            )
        )

        if season is None:
            continue

        expected_episodes = (
            expected_season
            .episode_numbers
        )

        season.episodes = {
            episode_number: episode
            for (
                episode_number,
                episode,
            ) in season.episodes.items()
            if (
                episode_number
                in expected_episodes
            )
        }

        seasons[
            season_number
        ] = season

    projected.seasons = seasons

    return projected


def project_show_target_items(
    execution: ShowTargetExecution,
) -> tuple[
    tuple[
        ShowInventory,
        ShowArtworkState,
    ],
    ...,
]:
    """Return projected inventory/state pairs for one target execution."""

    if execution.coverage_enabled:
        results = (
            execution.managed_coverage
            + execution.discovery_coverage
        )
    else:
        results = (
            execution.managed.results
            + execution.discovery.results
        )

    projected = []
    seen = set()

    for result in results:
        if result.state is None:
            continue

        inventory = (
            result.inventory
        )

        key = (
            inventory.identity.library,
            str(
                inventory.identity
                .plex_rating_key
            ),
        )

        if key in seen:
            raise ValueError(
                "duplicate Plex identity while "
                "projecting artwork output: "
                f"{key!r}"
            )

        seen.add(
            key
        )

        projected.append(
            (
                inventory,
                project_show_state_to_inventory(
                    inventory=inventory,
                    state=result.state,
                ),
            )
        )

    return tuple(
        projected
    )


def project_show_target_states(
    execution: ShowTargetExecution,
) -> tuple[
    ShowArtworkState,
    ...,
]:
    """Return projected states ready for Kometa rendering."""

    return tuple(
        state
        for (
            _inventory,
            state,
        ) in project_show_target_items(
            execution
        )
    )
