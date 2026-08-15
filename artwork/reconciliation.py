"""Reconcile Plex library inventory with managed artwork state."""

from __future__ import annotations

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
class TargetReconciliation:
    """Read-only reconciliation result for one Plex library."""

    target: ArtworkTarget

    matched: tuple[ReconciledShow, ...]
    unmanaged: tuple[ShowInventory, ...]
    missing_identity: tuple[ShowInventory, ...]
    orphaned: tuple[ShowArtworkState, ...]

    @property
    def plex_show_count(self) -> int:
        return (
            len(self.matched)
            + len(self.unmanaged)
            + len(self.missing_identity)
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


def reconcile_show_target(
    *,
    target: ArtworkTarget,
    inventories: Iterable[ShowInventory],
    managed_shows: Iterable[ShowArtworkState],
) -> TargetReconciliation:
    """Reconcile one show-type Plex library.

    Plex library membership determines routing. TVDB IDs are used here
    only to join existing legacy managed state to Plex during migration.
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

    plex_by_tvdb: dict[
        int,
        ShowInventory,
    ] = {}

    missing_identity: list[
        ShowInventory
    ] = []

    for inventory in target_inventories:
        tvdb_id = inventory.identity.tvdb_id

        if tvdb_id is None:
            missing_identity.append(
                inventory
            )
            continue

        if tvdb_id in plex_by_tvdb:
            raise ValueError(
                "duplicate TVDB ID "
                f"{tvdb_id} in Plex library "
                f"{target.library!r}"
            )

        plex_by_tvdb[tvdb_id] = inventory

    managed_list = list(
        managed_shows
    )

    managed_by_tvdb: dict[
        int,
        ShowArtworkState,
    ] = {}

    for state in managed_list:
        if state.tvdb_id is None:
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

    matched_tvdb_ids: set[int] = set()

    for tvdb_id, inventory in plex_by_tvdb.items():
        state = managed_by_tvdb.get(
            tvdb_id
        )

        if state is None:
            continue

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

        matched_tvdb_ids.add(
            tvdb_id
        )

    unmanaged = [
        inventory
        for tvdb_id, inventory
        in plex_by_tvdb.items()
        if tvdb_id not in matched_tvdb_ids
    ]

    orphaned = [
        state
        for state in managed_list
        if (
            state.tvdb_id is None
            or state.tvdb_id
            not in matched_tvdb_ids
        )
    ]

    matched.sort(
        key=lambda item: (
            item.inventory.identity.title.casefold()
        )
    )

    unmanaged.sort(
        key=lambda item: (
            item.identity.title.casefold()
        )
    )

    missing_identity.sort(
        key=lambda item: (
            item.identity.title.casefold()
        )
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
        orphaned=tuple(orphaned),
    )
