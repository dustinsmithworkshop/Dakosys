"""Execute Artwork Manager for one reconciled show-library target."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from artwork.execution import (
    ManagedLibraryExecution,
    execute_managed_library,
)
from artwork.inventory import ShowInventory
from artwork.models import ShowArtworkState
from artwork.providers.base import ArtworkProvider
from artwork.reconciliation import (
    TargetReconciliation,
    reconcile_show_target,
)
from artwork.targets import ArtworkTarget


@dataclass(frozen=True)
class ShowTargetExecution:
    """Reconciliation plus managed execution for one show target."""

    reconciliation: TargetReconciliation
    managed: ManagedLibraryExecution

    @property
    def matched_count(self) -> int:
        return len(
            self.reconciliation.matched
        )

    @property
    def unmanaged_count(self) -> int:
        return len(
            self.reconciliation.unmanaged
        )

    @property
    def missing_identity_count(self) -> int:
        return len(
            self.reconciliation.missing_identity
        )

    @property
    def ambiguous_count(self) -> int:
        return len(
            self.reconciliation.ambiguous
        )

    @property
    def orphaned_count(self) -> int:
        return len(
            self.reconciliation.orphaned
        )

    @property
    def resolved_states(
        self,
    ) -> tuple[ShowArtworkState, ...]:
        return self.managed.resolved_states


def execute_show_target(
    *,
    target: ArtworkTarget,
    inventories: Iterable[ShowInventory],
    managed_shows: Iterable[ShowArtworkState],
    provider: ArtworkProvider,
    incomplete_migration_threshold: float = 0.25,
) -> ShowTargetExecution:
    """Reconcile and execute managed shows for one Plex library.

    Only unambiguous managed matches are sent to providers.

    Unmanaged shows, missing identities, ambiguities, and orphaned
    durable state remain explicit reconciliation outcomes for later
    orchestration/reporting.

    This function performs no file writes and makes no Plex changes.
    """

    reconciliation = reconcile_show_target(
        target=target,
        inventories=inventories,
        managed_shows=managed_shows,
    )

    items = tuple(
        (
            reconciled.inventory,
            reconciled.artwork,
        )
        for reconciled
        in reconciliation.matched
    )

    managed = execute_managed_library(
        items=items,
        provider=provider,
        incomplete_migration_threshold=(
            incomplete_migration_threshold
        ),
    )

    if (
        managed.managed_count
        != len(reconciliation.matched)
    ):
        raise RuntimeError(
            "managed execution count does not "
            "match reconciliation"
        )

    return ShowTargetExecution(
        reconciliation=reconciliation,
        managed=managed,
    )
