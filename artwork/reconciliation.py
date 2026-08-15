"""Reconcile Plex library inventory with managed artwork state."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from artwork.coverage import (
    ArtworkSetCoverage,
    analyze_set_coverage,
)
from artwork.inventory import ShowInventory
from artwork.models import (
    ArtworkSet,
    ArtworkSource,
    ShowArtworkState,
)
from artwork.targets import (
    ArtworkTarget,
    MediaType,
)


@dataclass(frozen=True)
class ReconciledShow:
    """One Plex show matched to existing managed artwork."""

    inventory: ShowInventory
    artwork: ShowArtworkState
    coverage: ArtworkSetCoverage


@dataclass(frozen=True)
class AmbiguousManagedMatch:
    """Legacy artwork that matches multiple Plex items."""

    tvdb_id: int
    artwork: ShowArtworkState
    inventories: tuple[ShowInventory, ...]


@dataclass(frozen=True)
class TargetReconciliation:
    """Read-only reconciliation result for one Plex library."""

    target: ArtworkTarget

    matched: tuple[ReconciledShow, ...]
    unmanaged: tuple[ShowInventory, ...]
    missing_identity: tuple[ShowInventory, ...]
    ambiguous: tuple[AmbiguousManagedMatch, ...]
    orphaned: tuple[ShowArtworkState, ...]

    @property
    def ambiguous_match_count(self) -> int:
        """Number of managed records with ambiguous Plex matches."""

        return len(self.ambiguous)

    @property
    def ambiguous_plex_show_count(self) -> int:
        """Number of Plex items involved in ambiguous matches."""

        return sum(
            len(item.inventories)
            for item in self.ambiguous
        )

    @property
    def plex_show_count(self) -> int:
        return (
            len(self.matched)
            + len(self.unmanaged)
            + len(self.missing_identity)
            + self.ambiguous_plex_show_count
        )

    @property
    def managed_show_count(self) -> int:
        return len(self.matched)

    @property
    def unmanaged_show_count(self) -> int:
        return len(self.unmanaged)

    @property
    def missing_identity_count(self) -> int:
        return len(self.missing_identity)

    @property
    def orphaned_show_count(self) -> int:
        return len(self.orphaned)

    @property
    def complete_show_count(self) -> int:
        return sum(
            1
            for item in self.matched
            if item.coverage.complete
        )

    @property
    def incomplete_show_count(self) -> int:
        return sum(
            1
            for item in self.matched
            if not item.coverage.complete
        )

    @property
    def expected_episode_count(self) -> int:
        return sum(
            item.coverage.expected_episode_count
            for item in self.matched
        )

    @property
    def available_episode_count(self) -> int:
        return sum(
            item.coverage.available_episode_count
            for item in self.matched
        )

    @property
    def missing_episode_count(self) -> int:
        return sum(
            item.coverage.missing_episode_count
            for item in self.matched
        )

    @property
    def coverage_ratio(self) -> float:
        expected = self.expected_episode_count

        if expected == 0:
            return 0.0

        return (
            self.available_episode_count
            / expected
        )


def _artwork_set_from_state(
    state: ShowArtworkState,
) -> ArtworkSet:
    """Adapt selected managed state to the coverage engine."""

    source = (
        state.selected_set_source
        or ArtworkSource.MANUAL
    )

    set_id = (
        state.selected_set_id
        or (
            f"managed-{state.tvdb_id}"
            if state.tvdb_id is not None
            else "managed-unknown"
        )
    )

    return ArtworkSet(
        provider=source,
        set_id=set_id,
        creator=state.selected_creator,
        seasons=state.seasons,
    )


def _inventory_sort_key(
    inventory: ShowInventory,
) -> tuple[str, str]:
    return (
        inventory.identity.title.casefold(),
        inventory.identity.plex_rating_key,
    )


def reconcile_show_target(
    *,
    target: ArtworkTarget,
    inventories: Iterable[ShowInventory],
    managed_shows: Iterable[ShowArtworkState],
) -> TargetReconciliation:
    """Reconcile one show-type Plex library.

    Plex library + Plex rating key identifies the actual Plex item.

    TVDB is used only as a migration/matching signal for legacy managed
    artwork. Multiple Plex items may legitimately expose the same TVDB
    ID. Such duplicates are harmless unless a managed legacy record must
    be assigned to one of them; that case is reported as ambiguous rather
    than guessed.
    """

    if target.media_type is not MediaType.SHOW:
        raise ValueError(
            "reconcile_show_target requires a show target"
        )

    target_inventories = [
        inventory
        for inventory in inventories
        if (
            inventory.identity.library
            == target.library
        )
    ]

    missing_identity: list[
        ShowInventory
    ] = []

    plex_by_tvdb: dict[
        int,
        list[ShowInventory],
    ] = defaultdict(list)

    for inventory in target_inventories:
        tvdb_id = inventory.identity.tvdb_id

        if tvdb_id is None:
            missing_identity.append(
                inventory
            )
            continue

        plex_by_tvdb[tvdb_id].append(
            inventory
        )

    managed_list = list(
        managed_shows
    )

    managed_by_tvdb: dict[
        int,
        ShowArtworkState,
    ] = {}

    managed_without_identity: list[
        ShowArtworkState
    ] = []

    for state in managed_list:
        if state.tvdb_id is None:
            managed_without_identity.append(
                state
            )
            continue

        if state.tvdb_id in managed_by_tvdb:
            raise ValueError(
                "duplicate managed TVDB ID "
                f"{state.tvdb_id}"
            )

        managed_by_tvdb[
            state.tvdb_id
        ] = state

    matched: list[
        ReconciledShow
    ] = []

    ambiguous: list[
        AmbiguousManagedMatch
    ] = []

    orphaned: list[
        ShowArtworkState
    ] = list(managed_without_identity)

    consumed_rating_keys: set[str] = set()

    for tvdb_id, state in managed_by_tvdb.items():
        candidates = plex_by_tvdb.get(
            tvdb_id,
            [],
        )

        if not candidates:
            orphaned.append(
                state
            )
            continue

        if len(candidates) > 1:
            ordered = tuple(
                sorted(
                    candidates,
                    key=_inventory_sort_key,
                )
            )

            ambiguous.append(
                AmbiguousManagedMatch(
                    tvdb_id=tvdb_id,
                    artwork=state,
                    inventories=ordered,
                )
            )

            for inventory in ordered:
                consumed_rating_keys.add(
                    inventory.identity.plex_rating_key
                )

            continue

        inventory = candidates[0]

        coverage = analyze_set_coverage(
            _artwork_set_from_state(
                state
            ),
            inventory.expected_episodes(),
        )

        matched.append(
            ReconciledShow(
                inventory=inventory,
                artwork=state,
                coverage=coverage,
            )
        )

        consumed_rating_keys.add(
            inventory.identity.plex_rating_key
        )

    unmanaged = [
        inventory
        for inventory in target_inventories
        if (
            inventory.identity.tvdb_id is not None
            and inventory.identity.plex_rating_key
            not in consumed_rating_keys
        )
    ]

    matched.sort(
        key=lambda item: (
            item.inventory.identity.title.casefold(),
            item.inventory.identity.plex_rating_key,
        )
    )

    unmanaged.sort(
        key=_inventory_sort_key
    )

    missing_identity.sort(
        key=_inventory_sort_key
    )

    ambiguous.sort(
        key=lambda item: (
            item.artwork.title or ""
        ).casefold()
    )

    orphaned.sort(
        key=lambda item: (
            (item.title or "").casefold()
        )
    )

    return TargetReconciliation(
        target=target,
        matched=tuple(matched),
        unmanaged=tuple(unmanaged),
        missing_identity=tuple(
            missing_identity
        ),
        ambiguous=tuple(ambiguous),
        orphaned=tuple(orphaned),
    )
