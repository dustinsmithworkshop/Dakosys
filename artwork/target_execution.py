"""Execute Artwork Manager for one reconciled show-library target."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from artwork.discovery import (
    LibraryDiscoveryExecution,
    discover_unmanaged_library,
)
from artwork.episode_coverage import (
    EpisodeCoverageResult,
    resolve_episode_coverage,
)
from artwork.execution import (
    ManagedLibraryExecution,
    execute_managed_library,
)
from artwork.inventory import ShowInventory
from artwork.models import ShowArtworkState
from artwork.providers.base import ArtworkProvider
from artwork.providers.tmdb import (
    TMDBArtworkClient,
)
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

    # Optional post-provider episode coverage stage.
    #
    # These remain empty when no TMDB client was supplied so existing
    # callers retain the original target-execution behavior.
    managed_coverage: tuple[
        EpisodeCoverageResult,
        ...,
    ] = ()

    discovery_coverage: tuple[
        EpisodeCoverageResult,
        ...,
    ] = ()

    coverage_enabled: bool = False

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
        """Shows for which the primary provider selected artwork."""

        return self.discovery.selected_count

    @property
    def tmdb_created_count(self) -> int:
        """Previously unresolved shows made useful by TMDB alone."""

        return sum(
            1
            for result
            in self.discovery_coverage
            if result.created
        )

    @property
    def tmdb_changed_count(self) -> int:
        """Shows where TMDB added at least one episode card."""

        return sum(
            1
            for result
            in (
                self.managed_coverage
                + self.discovery_coverage
            )
            if result.changed
        )

    @property
    def tmdb_gap_fill_count(self) -> int:
        """Total missing episode cards filled by TMDB."""

        return sum(
            result.gaps_filled
            for result
            in (
                self.managed_coverage
                + self.discovery_coverage
            )
        )

    @property
    def tmdb_gap_remaining_count(
        self,
    ) -> int:
        """Total unresolved episode-card gaps after TMDB."""

        return sum(
            result.gaps_remaining
            for result
            in (
                self.managed_coverage
                + self.discovery_coverage
            )
        )

    @property
    def tmdb_request_count(self) -> int:
        """Number of TMDB season requests made for episode gaps."""

        return sum(
            result.season_request_count
            for result
            in (
                self.managed_coverage
                + self.discovery_coverage
            )
        )

    @property
    def tmdb_provider_error_count(
        self,
    ) -> int:
        return sum(
            result.provider_error_count
            for result
            in (
                self.managed_coverage
                + self.discovery_coverage
            )
        )

    @property
    def resolved_states(
        self,
    ) -> tuple[ShowArtworkState, ...]:
        """Prospective complete managed state for this target."""

        if not self.coverage_enabled:
            return (
                self.managed.resolved_states
                + self.discovery.selected_states
            )

        managed_states = tuple(
            result.state
            for result
            in self.managed_coverage
            if result.state is not None
        )

        discovery_states = tuple(
            result.state
            for result
            in self.discovery_coverage
            if result.state is not None
        )

        return (
            managed_states
            + discovery_states
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
        """Primary artwork-provider requests.

        TMDB fallback requests are reported independently through
        tmdb_request_count.
        """

        return (
            self.managed.provider_request_count
            + self.discovery.provider_request_count
        )

    @property
    def provider_error_count(
        self,
    ) -> int:
        """Primary artwork-provider failures.

        TMDB fallback failures are reported independently through
        tmdb_provider_error_count.
        """

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
    tmdb_client: TMDBArtworkClient | None = None,
    incomplete_migration_threshold: float = 0.25,
) -> ShowTargetExecution:
    """Reconcile and execute one Plex show-library target.

    Existing managed shows are reevaluated.

    Previously unmanaged shows are sent through primary-provider
    discovery.

    When a TMDB artwork client is supplied, every safely resolved
    managed state and every unmanaged inventory is then passed through
    episode-card coverage enrichment:

    - existing artwork is never replaced;
    - TMDB fills only remaining expected episode gaps;
    - unmanaged shows with no primary artwork can still become useful
      TMDB-only states;
    - empty identity-only states are never persisted;
    - managed items missing required durable set context remain
      unresolved and are not silently repaired through fallback.

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

    if tmdb_client is None:
        return ShowTargetExecution(
            reconciliation=reconciliation,
            managed=managed,
            discovery=discovery,
        )

    # ------------------------------------------------------------------
    # Managed coverage
    #
    # Only safely resolved managed states enter fallback. In particular,
    # MISSING_SET_CONTEXT remains unresolved rather than allowing TMDB
    # fallback to bypass durable-state safety requirements.
    # ------------------------------------------------------------------

    managed_coverage = tuple(
        resolve_episode_coverage(
            inventory=result.inventory,
            state=result.state,
            tmdb_client=tmdb_client,
        )
        for result in managed.results
        if result.state is not None
    )

    # ------------------------------------------------------------------
    # Unmanaged coverage
    #
    # Every reconciled unmanaged inventory gets a fallback opportunity.
    # A discovery result may contain:
    #
    #   state != None  -> enrich primary-provider artwork
    #   state == None  -> allow TMDB to create useful state
    # ------------------------------------------------------------------

    discovery_coverage = tuple(
        resolve_episode_coverage(
            inventory=result.inventory,
            state=result.state,
            tmdb_client=tmdb_client,
        )
        for result in discovery.results
    )

    return ShowTargetExecution(
        reconciliation=reconciliation,
        managed=managed,
        discovery=discovery,
        managed_coverage=(
            managed_coverage
        ),
        discovery_coverage=(
            discovery_coverage
        ),
        coverage_enabled=True,
    )
