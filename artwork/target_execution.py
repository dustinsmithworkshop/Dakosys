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
from artwork.identity_enrichment import (
    ShowIdentityEnrichment,
    enrich_show_inventory_tvdb,
)
from artwork.identity_resolution import (
    resolve_duplicate_tvdb_candidates,
)
from artwork.inventory import ShowInventory
from artwork.models import ShowArtworkState
from artwork.progress import (
    ArtworkProgressCallback,
    ArtworkScanPhase,
    emit_artwork_progress,
)
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

    # Exact pre-reconciliation identity enrichment.
    #
    # When a TMDB client is available, Plex items missing TVDB identity
    # may recover it through their exact TMDB series ID.
    identity_enrichment: tuple[
        ShowIdentityEnrichment,
        ...,
    ] = ()

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
    def identity_enriched_count(
        self,
    ) -> int:
        return sum(
            1
            for result
            in self.identity_enrichment
            if result.enriched
        )

    @property
    def identity_enrichment_request_count(
        self,
    ) -> int:
        return sum(
            1
            for result
            in self.identity_enrichment
            if result.provider_requested
        )

    @property
    def identity_enrichment_error_count(
        self,
    ) -> int:
        return sum(
            1
            for result
            in self.identity_enrichment
            if result.error_type is not None
        )

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
    def provider_unavailable_count(
        self,
    ) -> int:
        """Non-fatal item-level primary-provider unavailability."""

        return (
            self.managed
            .provider_unavailable_count
            + self.discovery
            .provider_unavailable_count
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
    progress_callback: ArtworkProgressCallback | None = None,
) -> ShowTargetExecution:
    """Reconcile and execute one Plex show-library target.

    Existing managed shows are reevaluated.

    Previously unmanaged shows are sent through primary-provider
    discovery.

    When a TMDB artwork client is supplied, inventories missing TVDB
    identity are first given an exact TMDB external-ID enrichment
    opportunity before reconciliation. No title or fuzzy matching is
    performed.

    Every safely resolved managed state and every unmanaged inventory is
    then passed through episode-card coverage enrichment:

    - existing artwork is never replaced;
    - TMDB fills only remaining expected episode gaps;
    - unmanaged shows with no primary artwork can still become useful
      TMDB-only states;
    - empty identity-only states are never persisted;
    - managed items missing required durable set context remain
      unresolved and are not silently repaired through fallback.

    Identities that remain unresolved after exact enrichment, ambiguous
    managed matches, and orphaned durable state remain explicit
    reconciliation outcomes and are never guessed.

    This function performs no file writes and makes no Plex changes.
    """

    inventory_tuple = tuple(
        inventories
    )

    if tmdb_client is None:
        identity_enrichment = ()
        execution_inventories = (
            inventory_tuple
        )

    else:
        identity_results: list[
            ShowIdentityEnrichment
        ] = []

        total_identity = len(
            inventory_tuple
        )

        for index, inventory in enumerate(
            inventory_tuple,
            start=1,
        ):
            result = (
                enrich_show_inventory_tvdb(
                    inventory=inventory,
                    tmdb_client=tmdb_client,
                )
            )

            identity_results.append(
                result
            )

            emit_artwork_progress(
                progress_callback,
                library=target.library,
                phase=(
                    ArtworkScanPhase
                    .IDENTITY
                ),
                completed=index,
                total=total_identity,
                message=(
                    "Resolving exact show identities"
                ),
                current_title=(
                    inventory.identity.title
                ),
            )

        identity_enrichment = tuple(
            identity_results
        )

        execution_inventories = tuple(
            result.inventory
            for result
            in identity_enrichment
        )

    # Plex may expose multiple exact TVDB GUIDs for one item.  Resolve
    # existing canonical collisions only when those candidates imply one
    # unique one-to-one assignment.  Ambiguous collisions are deliberately
    # left unchanged for downstream safety checks to block.
    execution_inventories = (
        resolve_duplicate_tvdb_candidates(
            execution_inventories
        )
    )

    reconciliation = reconcile_show_target(
        target=target,
        inventories=execution_inventories,
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
        progress_callback=(
            progress_callback
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
        progress_callback=(
            progress_callback
        ),
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
            identity_enrichment=(
                identity_enrichment
            ),
        )

    # ------------------------------------------------------------------
    # Managed coverage
    #
    # Only safely resolved managed states enter fallback. In particular,
    # MISSING_SET_CONTEXT remains unresolved rather than allowing TMDB
    # fallback to bypass durable-state safety requirements.
    # ------------------------------------------------------------------

    managed_candidates = tuple(
        result
        for result in managed.results
        if result.state is not None
    )

    managed_coverage_results: list[
        EpisodeCoverageResult
    ] = []

    managed_coverage_total = len(
        managed_candidates
    )

    for index, result in enumerate(
        managed_candidates,
        start=1,
    ):
        coverage = (
            resolve_episode_coverage(
                inventory=result.inventory,
                state=result.state,
                tmdb_client=tmdb_client,
            )
        )

        managed_coverage_results.append(
            coverage
        )

        emit_artwork_progress(
            progress_callback,
            library=target.library,
            phase=(
                ArtworkScanPhase
                .TMDB_MANAGED
            ),
            completed=index,
            total=managed_coverage_total,
            message=(
                "Checking managed episode "
                "gaps with TMDB"
            ),
            current_title=(
                result.inventory
                .identity.title
            ),
        )

    managed_coverage = tuple(
        managed_coverage_results
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

    discovery_coverage_results: list[
        EpisodeCoverageResult
    ] = []

    discovery_coverage_total = len(
        discovery.results
    )

    for index, result in enumerate(
        discovery.results,
        start=1,
    ):
        coverage = (
            resolve_episode_coverage(
                inventory=result.inventory,
                state=result.state,
                tmdb_client=tmdb_client,
            )
        )

        discovery_coverage_results.append(
            coverage
        )

        emit_artwork_progress(
            progress_callback,
            library=target.library,
            phase=(
                ArtworkScanPhase
                .TMDB_DISCOVERY
            ),
            completed=index,
            total=discovery_coverage_total,
            message=(
                "Checking unmanaged episode "
                "gaps with TMDB"
            ),
            current_title=(
                result.inventory
                .identity.title
            ),
        )

    discovery_coverage = tuple(
        discovery_coverage_results
    )

    return ShowTargetExecution(
        reconciliation=reconciliation,
        managed=managed,
        discovery=discovery,
        identity_enrichment=(
            identity_enrichment
        ),
        managed_coverage=(
            managed_coverage
        ),
        discovery_coverage=(
            discovery_coverage
        ),
        coverage_enabled=True,
    )
