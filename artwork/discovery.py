"""Discover artwork for previously unmanaged Plex shows."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from artwork.assessment import (
    ArtworkSetAssessment,
    assess_artwork_set,
)
from artwork.inventory import ShowInventory
from artwork.models import (
    SelectionMode,
    ShowArtworkState,
)
from artwork.providers.base import ArtworkProvider
from artwork.search import (
    ArtworkSearchKind,
    ArtworkSearchRequest,
)
from artwork.selection import (
    choose_discovery_candidate,
)


class DiscoveryPath(str, Enum):
    """Outcome of artwork discovery for one unmanaged show."""

    SELECTED = "selected"
    NO_CANDIDATES = "no_candidates"
    NO_USABLE_CANDIDATE = (
        "no_usable_candidate"
    )
    PROVIDER_ERROR = "provider_error"


@dataclass(frozen=True)
class ShowDiscoveryExecution:
    """Result of provider discovery for one unmanaged Plex show."""

    inventory: ShowInventory
    state: ShowArtworkState | None
    path: DiscoveryPath

    selected: ArtworkSetAssessment | None = None

    provider_requested: bool = True
    provider_candidate_count: int = 0
    usable_candidate_count: int = 0

    error_type: str | None = None
    error_message: str | None = None

    @property
    def resolved(self) -> bool:
        """Whether discovery produced new managed artwork state."""

        return self.state is not None


@dataclass(frozen=True)
class LibraryDiscoveryExecution:
    """Aggregate discovery results for unmanaged Plex shows."""

    results: tuple[
        ShowDiscoveryExecution,
        ...,
    ]

    @property
    def unmanaged_count(self) -> int:
        return len(
            self.results
        )

    @property
    def selected_states(
        self,
    ) -> tuple[ShowArtworkState, ...]:
        return tuple(
            result.state
            for result in self.results
            if result.state is not None
        )

    @property
    def selected_count(self) -> int:
        return len(
            self.selected_states
        )

    @property
    def provider_request_count(self) -> int:
        return sum(
            1
            for result in self.results
            if result.provider_requested
        )

    @property
    def no_candidates_count(self) -> int:
        return sum(
            1
            for result in self.results
            if (
                result.path
                is DiscoveryPath.NO_CANDIDATES
            )
        )

    @property
    def no_usable_candidate_count(
        self,
    ) -> int:
        return sum(
            1
            for result in self.results
            if (
                result.path
                is DiscoveryPath.NO_USABLE_CANDIDATE
            )
        )

    @property
    def provider_error_count(self) -> int:
        return sum(
            1
            for result in self.results
            if (
                result.path
                is DiscoveryPath.PROVIDER_ERROR
            )
        )


def _has_usable_artwork(
    assessment: ArtworkSetAssessment,
) -> bool:
    """Whether a candidate contributes any managed artwork dimension."""

    if (
        assessment
        .episode_coverage
        .available_episode_count
        > 0
    ):
        return True

    if assessment.show_poster_available:
        return True

    if assessment.show_background_available:
        return True

    if assessment.season_poster_numbers:
        return True

    return False


def _state_from_discovery(
    *,
    inventory: ShowInventory,
    selected: ArtworkSetAssessment,
) -> ShowArtworkState:
    """Create initial durable state from a discovery selection."""

    identity = inventory.identity
    artwork_set = selected.artwork_set

    return ShowArtworkState(
        title=identity.title,
        tvdb_id=identity.tvdb_id,
        tmdb_id=identity.tmdb_id,
        imdb_id=identity.imdb_id,
        poster=artwork_set.poster,
        background=artwork_set.background,
        seasons=artwork_set.seasons,
        selected_set_id=artwork_set.set_id,
        selected_set_source=artwork_set.provider,
        selected_creator=artwork_set.creator,
        selection_mode=SelectionMode.AUTO,
    )


def discover_unmanaged_show(
    *,
    inventory: ShowInventory,
    provider: ArtworkProvider,
) -> ShowDiscoveryExecution:
    """Discover artwork for one previously unmanaged Plex show.

    This function performs no file writes and makes no Plex changes.
    """

    identity = inventory.identity

    request = ArtworkSearchRequest(
        library=identity.library,
        plex_rating_key=str(
            identity.plex_rating_key
        ),
        title=identity.title,
        year=identity.year,
        tvdb_id=identity.tvdb_id,
        tmdb_id=identity.tmdb_id,
        imdb_id=identity.imdb_id,
        seasons=inventory.seasons,
        kind=ArtworkSearchKind.DISCOVERY,
    )

    try:
        artwork_sets = provider.find_sets(
            request
        )

    except Exception as exc:
        return ShowDiscoveryExecution(
            inventory=inventory,
            state=None,
            path=DiscoveryPath.PROVIDER_ERROR,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )

    if not artwork_sets:
        return ShowDiscoveryExecution(
            inventory=inventory,
            state=None,
            path=DiscoveryPath.NO_CANDIDATES,
            provider_candidate_count=0,
            usable_candidate_count=0,
        )

    expected = inventory.expected_episodes()

    assessments = tuple(
        assess_artwork_set(
            artwork_set,
            expected,
        )
        for artwork_set in artwork_sets
    )

    usable = tuple(
        assessment
        for assessment in assessments
        if _has_usable_artwork(
            assessment
        )
    )

    if not usable:
        return ShowDiscoveryExecution(
            inventory=inventory,
            state=None,
            path=(
                DiscoveryPath
                .NO_USABLE_CANDIDATE
            ),
            provider_candidate_count=len(
                assessments
            ),
            usable_candidate_count=0,
        )

    selected = choose_discovery_candidate(
        usable
    )

    if selected is None:
        raise RuntimeError(
            "usable discovery candidates produced "
            "no selection"
        )

    state = _state_from_discovery(
        inventory=inventory,
        selected=selected,
    )

    return ShowDiscoveryExecution(
        inventory=inventory,
        state=state,
        path=DiscoveryPath.SELECTED,
        selected=selected,
        provider_candidate_count=len(
            assessments
        ),
        usable_candidate_count=len(
            usable
        ),
    )


def discover_unmanaged_library(
    *,
    inventories: Iterable[ShowInventory],
    provider: ArtworkProvider,
) -> LibraryDiscoveryExecution:
    """Discover artwork for already-reconciled unmanaged shows."""

    results = tuple(
        discover_unmanaged_show(
            inventory=inventory,
            provider=provider,
        )
        for inventory in inventories
    )

    return LibraryDiscoveryExecution(
        results=results
    )
