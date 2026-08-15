"""Read-only Artwork Manager planning.

The planner converts reconciliation facts into work that Artwork Manager
may perform later. It does not contact providers, modify Plex, or write
Kometa metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from artwork.inventory import SeasonInventory
from artwork.models import (
    ArtworkSource,
    SelectionMode,
)
from artwork.reconciliation import TargetReconciliation
from artwork.targets import ArtworkTarget


class PlanAction(str, Enum):
    """Next category of work for one artwork item."""

    NONE = "none"
    PROVIDER_SEARCH = "provider_search"
    RESOLVE_IDENTITY = "resolve_identity"
    REVIEW_AMBIGUITY = "review_ambiguity"
    REVIEW_ORPHAN = "review_orphan"


class PlanReason(str, Enum):
    """Why the planner selected an action."""

    COMPLETE = "complete"
    INCOMPLETE_COVERAGE = "incomplete_coverage"
    UNMANAGED = "unmanaged"
    MISSING_IDENTITY = "missing_identity"
    AMBIGUOUS_MANAGED_MATCH = "ambiguous_managed_match"
    ORPHANED_MANAGED_STATE = "orphaned_managed_state"


@dataclass(frozen=True)
class ArtworkPlanItem:
    """One read-only Artwork Manager planning item."""

    library: str
    title: str
    action: PlanAction
    reason: PlanReason

    plex_rating_keys: tuple[str, ...] = ()

    year: int | None = None
    tvdb_id: int | None = None
    tmdb_id: int | None = None
    imdb_id: str | None = None

    seasons: tuple[SeasonInventory, ...] = ()

    selected_set_id: str | None = None
    selected_set_source: ArtworkSource | None = None
    selected_creator: str | None = None
    selection_mode: SelectionMode = SelectionMode.AUTO

    expected_episode_count: int | None = None
    managed_card_count: int | None = None
    missing_managed_card_count: int | None = None


@dataclass(frozen=True)
class TargetPlan:
    """Read-only work plan for one Plex library."""

    target: ArtworkTarget
    items: tuple[ArtworkPlanItem, ...]

    @property
    def item_count(self) -> int:
        return len(self.items)

    def count(
        self,
        action: PlanAction,
    ) -> int:
        return sum(
            1
            for item in self.items
            if item.action is action
        )

    @property
    def stable_count(self) -> int:
        return self.count(
            PlanAction.NONE
        )

    @property
    def provider_search_count(self) -> int:
        return self.count(
            PlanAction.PROVIDER_SEARCH
        )

    @property
    def identity_review_count(self) -> int:
        return self.count(
            PlanAction.RESOLVE_IDENTITY
        )

    @property
    def ambiguity_review_count(self) -> int:
        return self.count(
            PlanAction.REVIEW_AMBIGUITY
        )

    @property
    def orphan_review_count(self) -> int:
        return self.count(
            PlanAction.REVIEW_ORPHAN
        )


def _inventory_episode_count(
    inventory,
) -> int:
    return sum(
        len(season.episode_numbers)
        for season in inventory.seasons
    )


def build_target_plan(
    reconciliation: TargetReconciliation,
) -> TargetPlan:
    """Build a read-only plan from one reconciled Plex library."""

    library = reconciliation.target.library

    items: list[ArtworkPlanItem] = []

    for reconciled in reconciliation.matched:
        inventory = reconciled.inventory
        identity = inventory.identity
        artwork = reconciled.artwork
        coverage = reconciled.coverage

        if coverage.complete:
            action = PlanAction.NONE
            reason = PlanReason.COMPLETE
        else:
            action = PlanAction.PROVIDER_SEARCH
            reason = PlanReason.INCOMPLETE_COVERAGE

        items.append(
            ArtworkPlanItem(
                library=library,
                title=identity.title,
                action=action,
                reason=reason,
                plex_rating_keys=(
                    identity.plex_rating_key,
                ),
                year=identity.year,
                tvdb_id=identity.tvdb_id,
                tmdb_id=identity.tmdb_id,
                imdb_id=identity.imdb_id,
                seasons=inventory.seasons,
                selected_set_id=artwork.selected_set_id,
                selected_set_source=(
                    artwork.selected_set_source
                ),
                selected_creator=artwork.selected_creator,
                selection_mode=artwork.selection_mode,
                expected_episode_count=(
                    coverage.expected_episode_count
                ),
                managed_card_count=(
                    coverage.available_episode_count
                ),
                missing_managed_card_count=(
                    coverage.missing_episode_count
                ),
            )
        )

    for inventory in reconciliation.unmanaged:
        identity = inventory.identity
        expected = _inventory_episode_count(
            inventory
        )

        items.append(
            ArtworkPlanItem(
                library=library,
                title=identity.title,
                action=PlanAction.PROVIDER_SEARCH,
                reason=PlanReason.UNMANAGED,
                plex_rating_keys=(
                    identity.plex_rating_key,
                ),
                year=identity.year,
                tvdb_id=identity.tvdb_id,
                tmdb_id=identity.tmdb_id,
                imdb_id=identity.imdb_id,
                seasons=inventory.seasons,
                expected_episode_count=expected,
                managed_card_count=0,
                missing_managed_card_count=expected,
            )
        )

    for inventory in reconciliation.missing_identity:
        identity = inventory.identity

        items.append(
            ArtworkPlanItem(
                library=library,
                title=identity.title,
                action=PlanAction.RESOLVE_IDENTITY,
                reason=PlanReason.MISSING_IDENTITY,
                plex_rating_keys=(
                    identity.plex_rating_key,
                ),
                year=identity.year,
                tvdb_id=identity.tvdb_id,
                tmdb_id=identity.tmdb_id,
                imdb_id=identity.imdb_id,
                seasons=inventory.seasons,
                expected_episode_count=(
                    _inventory_episode_count(
                        inventory
                    )
                ),
            )
        )

    for ambiguous in reconciliation.ambiguous:
        items.append(
            ArtworkPlanItem(
                library=library,
                title=(
                    ambiguous.artwork.title
                    or "Unknown"
                ),
                action=PlanAction.REVIEW_AMBIGUITY,
                reason=(
                    PlanReason.AMBIGUOUS_MANAGED_MATCH
                ),
                plex_rating_keys=tuple(
                    inventory.identity.plex_rating_key
                    for inventory
                    in ambiguous.inventories
                ),
                tvdb_id=ambiguous.tvdb_id,
                selected_set_id=(
                    ambiguous.artwork.selected_set_id
                ),
                selected_set_source=(
                    ambiguous.artwork.selected_set_source
                ),
                selected_creator=(
                    ambiguous.artwork.selected_creator
                ),
                selection_mode=(
                    ambiguous.artwork.selection_mode
                ),
            )
        )

    for artwork in reconciliation.orphaned:
        items.append(
            ArtworkPlanItem(
                library=library,
                title=artwork.title or "Unknown",
                action=PlanAction.REVIEW_ORPHAN,
                reason=(
                    PlanReason.ORPHANED_MANAGED_STATE
                ),
                tvdb_id=artwork.tvdb_id,
                tmdb_id=artwork.tmdb_id,
                imdb_id=artwork.imdb_id,
                selected_set_id=(
                    artwork.selected_set_id
                ),
                selected_set_source=(
                    artwork.selected_set_source
                ),
                selected_creator=(
                    artwork.selected_creator
                ),
                selection_mode=artwork.selection_mode,
            )
        )

    items.sort(
        key=lambda item: (
            item.title.casefold(),
            item.plex_rating_keys,
        )
    )

    return TargetPlan(
        target=reconciliation.target,
        items=tuple(items),
    )
