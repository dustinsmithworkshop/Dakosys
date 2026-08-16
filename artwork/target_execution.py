"""Execute Artwork Manager for one reconciled show-library target."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from artwork.discovery import (
    LibraryDiscoveryExecution,
    discover_unmanaged_library,
)
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
    """Reconciliation plus artwork execution for one show target."""

    reconciliation: TargetReconciliation
    managed: ManagedLibraryExecution
    discovery: LibraryDiscoveryExecution

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
    def discovered_count(self) -> int:
        return self.discovery.selected_count

    @property
    def resolved_states(
        self,
    ) -> tuple[ShowArtworkState, ...]:
        """Prospective complete managed state for this target."""

        return (
            self.managed.resolved_states
            + self.discovery.selected_states
        )

    @property
    def resolved_count(self) -> int:
        return len(
            self.resolved_states
        )

    @property
    def provider_request_count(
        self,
    ) -> int:
        return (
            self.managed.provider_request_count
            + self.discovery.provider_request_count
        )

    @property
    def provider_error_count(
        self,
    ) -> int:
        return (
            self.managed.provider_error_count
            + self.discovery.provider_error_count
        )


def execute_show_target(
    *,
    target: ArtworkTarget,
    inventories: Iterable[ShowInventory],
    managed_shows: Iterable[ShowArtworkState],
    provider: ArtworkProvider,
    incomplete_migration_threshold: float = 0.25,
) -> ShowTargetExecution:
    """Reconcile and execute one Plex show-library target.

    Existing managed shows are reevaluated.

    Previously unmanaged shows are sent through discovery.

    Missing identities, ambiguous managed matches, and orphaned durable
    state remain explicit reconciliation outcomes and are never guessed.

    This function performs no file writes and makes no Plex changes.
    """

    reconciliation = reconcile_show_target(
        target=target,
        inventories=inventories,
        managed_shows=managed_shows,
    )

    managed_items = tuple(
        (
            reconciled.inventory,
            reconciled.artwork,
        )
        for reconciled
        in reconciliation.matched
    )

    managed = execute_managed_library(
        items=managed_items,
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

    discovery = discover_unmanaged_library(
        inventories=(
            reconciliation.unmanaged
        ),
        provider=provider,
    )

    if (
        discovery.unmanaged_count
        != len(reconciliation.unmanaged)
    ):
        raise RuntimeError(
            "discovery execution count does not "
            "match reconciliation"
        )

    return ShowTargetExecution(
        reconciliation=reconciliation,
        managed=managed,
        discovery=discovery,
    )
