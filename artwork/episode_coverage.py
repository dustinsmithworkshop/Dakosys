"""Post-resolution artwork coverage enrichment."""

from __future__ import annotations

from dataclasses import dataclass

from artwork.inventory import ShowInventory
from artwork.models import ShowArtworkState
from artwork.providers.tmdb import TMDBArtworkClient
from artwork.tmdb_fallback import (
    TMDBFallbackPath,
    TMDBFallbackResult,
    fill_tmdb_episode_gaps,
)


@dataclass(frozen=True)
class EpisodeCoverageResult:
    """Result of filling unresolved episode artwork after primary resolution."""

    inventory: ShowInventory

    initial_state: ShowArtworkState | None
    state: ShowArtworkState | None

    tmdb: TMDBFallbackResult

    @property
    def resolved(self) -> bool:
        """Whether useful durable state exists after coverage resolution."""

        return self.state is not None

    @property
    def changed(self) -> bool:
        """Whether fallback added at least one episode card."""

        return self.tmdb.changed

    @property
    def created(self) -> bool:
        """Whether fallback created state for a previously unmanaged show."""

        return (
            self.initial_state is None
            and self.state is not None
        )

    @property
    def gaps_before(self) -> int:
        return self.tmdb.gaps_before

    @property
    def gaps_filled(self) -> int:
        return self.tmdb.gaps_filled

    @property
    def gaps_remaining(self) -> int:
        return self.tmdb.gaps_remaining

    @property
    def season_request_count(self) -> int:
        return self.tmdb.season_request_count

    @property
    def provider_error_count(self) -> int:
        return self.tmdb.provider_error_count

    @property
    def tmdb_path(self) -> TMDBFallbackPath:
        return self.tmdb.path


def _identity_state(
    inventory: ShowInventory,
) -> ShowArtworkState:
    """Create temporary state used only while resolving fallback artwork."""

    identity = inventory.identity

    return ShowArtworkState(
        title=identity.title,
        tvdb_id=identity.tvdb_id,
        tmdb_id=identity.tmdb_id,
        imdb_id=identity.imdb_id,
    )


def resolve_episode_coverage(
    *,
    inventory: ShowInventory,
    state: ShowArtworkState | None,
    tmdb_client: TMDBArtworkClient,
) -> EpisodeCoverageResult:
    """Fill unresolved episode cards after primary artwork resolution.

    Existing artwork always wins.

    When no primary artwork state exists, a temporary identity-only state
    is used for TMDB resolution. That temporary state becomes durable only
    when TMDB actually contributes artwork.

    This function performs no file writes and makes no Plex changes.
    """

    if (
        state is not None
        and state.tvdb_id is not None
        and inventory.identity.tvdb_id is not None
        and state.tvdb_id
        != inventory.identity.tvdb_id
    ):
        raise ValueError(
            "artwork state TVDB ID does not "
            "match Plex inventory"
        )

    working_state = (
        state
        if state is not None
        else _identity_state(
            inventory
        )
    )

    tmdb_result = (
        fill_tmdb_episode_gaps(
            inventory=inventory,
            state=working_state,
            client=tmdb_client,
        )
    )

    # Existing durable state is always preserved, regardless of whether
    # TMDB contributed anything or encountered a transient failure.
    if state is not None:
        resolved_state = (
            tmdb_result.state
        )

    # A show with no primary artwork becomes managed only when fallback
    # actually contributes useful episode artwork. Do not persist an
    # empty identity shell.
    elif tmdb_result.changed:
        resolved_state = (
            tmdb_result.state
        )

    else:
        resolved_state = None

    return EpisodeCoverageResult(
        inventory=inventory,
        initial_state=state,
        state=resolved_state,
        tmdb=tmdb_result,
    )
