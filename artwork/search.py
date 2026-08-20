"""Provider-neutral artwork search requests.

Artwork Manager planning determines which Plex items need provider work.
This module converts those plan items into immutable provider search
requests.

No provider-specific API concepts belong here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from artwork.inventory import SeasonInventory
from artwork.models import (
    ArtworkSource,
    SelectionMode,
)
from artwork.planner import (
    PlanAction,
    PlanReason,
    TargetPlan,
)
from artwork.targets import MediaType


class ArtworkSearchKind(str, Enum):
    """Why artwork providers are being queried."""

    DISCOVERY = "discovery"
    REEVALUATION = "reevaluation"


@dataclass(frozen=True)
class ArtworkSearchRequest:
    """Provider-neutral request for artwork candidates.

    Plex library + rating key is the permanent correlation identity.
    External IDs are matching signals supplied to artwork providers.
    """

    library: str
    plex_rating_key: str

    title: str
    year: int | None

    tvdb_id: int | None
    tmdb_id: int | None
    imdb_id: str | None

    seasons: tuple[SeasonInventory, ...]

    kind: ArtworkSearchKind

    media_type: MediaType = MediaType.SHOW

    current_set_id: str | None = None
    current_set_source: ArtworkSource | None = None
    current_creator: str | None = None
    selection_mode: SelectionMode = SelectionMode.AUTO

    @property
    def plex_identity(
        self,
    ) -> tuple[str, str]:
        """Stable identity of the Plex item being processed."""

        return (
            self.library,
            self.plex_rating_key,
        )

    @property
    def expected_episode_count(
        self,
    ) -> int:
        return sum(
            len(season.episode_numbers)
            for season in self.seasons
        )

    def expected_episodes(
        self,
    ) -> dict[int, frozenset[int]]:
        """Return the actual Plex episode inventory by season."""

        return {
            season.season_number:
                season.episode_numbers
            for season in self.seasons
        }


def build_provider_search_requests(
    plan: TargetPlan,
) -> tuple[ArtworkSearchRequest, ...]:
    """Convert provider-search plan items to request payloads."""

    requests: list[
        ArtworkSearchRequest
    ] = []

    seen_plex_identities: set[
        tuple[str, str]
    ] = set()

    for item in plan.items:
        if (
            item.action
            is not PlanAction.PROVIDER_SEARCH
        ):
            continue

        if (
            item.library
            != plan.target.library
        ):
            raise ValueError(
                "Artwork plan item library does not "
                "match its target library"
            )

        if len(
            item.plex_rating_keys
        ) != 1:
            raise ValueError(
                "provider search requires exactly one "
                "Plex rating key"
            )

        if (
            item.reason
            is PlanReason.UNMANAGED
        ):
            kind = (
                ArtworkSearchKind.DISCOVERY
            )

        elif (
            item.reason
            is PlanReason.INCOMPLETE_COVERAGE
        ):
            kind = (
                ArtworkSearchKind.REEVALUATION
            )

        else:
            raise ValueError(
                "provider-search plan item has "
                f"unsupported reason {item.reason.value!r}"
            )

        plex_rating_key = (
            item.plex_rating_keys[0]
        )

        plex_identity = (
            item.library,
            plex_rating_key,
        )

        if (
            plex_identity
            in seen_plex_identities
        ):
            raise ValueError(
                "duplicate provider search request "
                "for Plex identity "
                f"{plex_identity!r}"
            )

        seen_plex_identities.add(
            plex_identity
        )

        requests.append(
            ArtworkSearchRequest(
                library=item.library,
                plex_rating_key=plex_rating_key,
                title=item.title,
                year=item.year,
                tvdb_id=item.tvdb_id,
                tmdb_id=item.tmdb_id,
                imdb_id=item.imdb_id,
                seasons=item.seasons,
                kind=kind,
                media_type=plan.target.media_type,
                current_set_id=(
                    item.selected_set_id
                ),
                current_set_source=(
                    item.selected_set_source
                ),
                current_creator=(
                    item.selected_creator
                ),
                selection_mode=(
                    item.selection_mode
                ),
            )
        )

    return tuple(
        requests
    )
