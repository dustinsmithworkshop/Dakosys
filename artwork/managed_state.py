"""Resolve the durable managed-state baseline for one show library.

Normal operation uses the Artwork Manager state sidecar.

Legacy Kometa/MediUX metadata is accepted only as an explicit bootstrap
source when durable state does not exist yet. Once durable state exists,
legacy metadata is ignored.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from artwork.item_store import (
    ItemStoreManifest,
    load_item_store_manifest,
)
from artwork.migration import (
    import_mediux_metadata,
)
from artwork.models import (
    ShowArtworkState,
)
from artwork.state_store import (
    ArtworkStateStore,
    load_show_state_store,
)


class ManagedStateBaselineError(
    RuntimeError
):
    """Base class for managed-state baseline failures."""


class ArtworkStateBootstrapRequiredError(
    ManagedStateBaselineError
):
    """An existing item store needs one-time semantic-state bootstrap."""


class InconsistentManagedStateError(
    ManagedStateBaselineError
):
    """Ownership and semantic state disagree."""


class ManagedStateBaselineSource(
    str,
    Enum,
):
    DURABLE_STATE = "durable_state"
    ITEM_STORE_BOOTSTRAP = "item_store_bootstrap"
    LEGACY_MIGRATION = "legacy_migration"
    NEW_LIBRARY = "new_library"


@dataclass(frozen=True)
class ManagedStateBaseline:
    """Resolved starting state for one Artwork Manager execution."""

    library: str

    states: tuple[
        ShowArtworkState,
        ...,
    ]

    source: ManagedStateBaselineSource

    manifest: ItemStoreManifest | None = None
    state_store: ArtworkStateStore | None = None

    @property
    def state_count(
        self,
    ) -> int:
        return len(
            self.states
        )


def _validate_manifest_state_identity(
    *,
    manifest: ItemStoreManifest,
    state_store: ArtworkStateStore,
) -> None:
    manifest_items = {
        item.plex_rating_key:
            item.tvdb_id
        for item
        in manifest.items
    }

    state_items = {
        item.plex_rating_key:
            item.state.tvdb_id
        for item
        in state_store.items
    }

    if manifest_items != state_items:
        raise InconsistentManagedStateError(
            "Artwork Manager ownership manifest "
            "and durable semantic state disagree"
        )


def load_show_managed_state_baseline(
    *,
    directory: str | Path,
    library: str,
    legacy_metadata: str | Path | None = None,
) -> ManagedStateBaseline:
    """Resolve the authoritative managed-state baseline.

    Priority:

    1. Existing durable state sidecar.
    2. Explicit legacy metadata bootstrap.
    3. Empty state for a genuinely new item store.

    An existing manifest without durable state may never silently become
    an empty/new-library baseline.
    """

    directory = Path(
        directory
    )

    manifest = (
        load_item_store_manifest(
            directory,
            expected_library=library,
        )
    )

    state_store = (
        load_show_state_store(
            directory,
            expected_library=library,
        )
    )

    if state_store is not None:
        if manifest is None:
            raise InconsistentManagedStateError(
                "Artwork Manager durable state "
                "exists without an ownership manifest"
            )

        _validate_manifest_state_identity(
            manifest=manifest,
            state_store=state_store,
        )

        return ManagedStateBaseline(
            library=library,
            states=(
                state_store.states
            ),
            source=(
                ManagedStateBaselineSource
                .DURABLE_STATE
            ),
            manifest=manifest,
            state_store=state_store,
        )

    # Existing generated output proves this is not a new library.
    # Without the semantic sidecar we require an explicit bootstrap.
    #
    # The old monolithic metadata is only a historical provenance
    # witness for a pre-state-store item store. It must never replace
    # the current manifest-owned split YAML as authoritative artwork.
    if manifest is not None:
        if legacy_metadata is None:
            raise (
                ArtworkStateBootstrapRequiredError(
                    "existing Artwork Manager "
                    "item store has no durable "
                    "semantic state; explicit "
                    "legacy bootstrap metadata "
                    "is required"
                )
            )

        return ManagedStateBaseline(
            library=library,
            states=(),
            source=(
                ManagedStateBaselineSource
                .ITEM_STORE_BOOTSTRAP
            ),
            manifest=manifest,
        )

    # No Artwork Manager store exists yet. An explicitly supplied
    # migration file may seed first-run state; otherwise this is simply
    # a new unmanaged library.
    if legacy_metadata is not None:
        states = tuple(
            import_mediux_metadata(
                legacy_metadata
            )
        )

        return ManagedStateBaseline(
            library=library,
            states=states,
            source=(
                ManagedStateBaselineSource
                .LEGACY_MIGRATION
            ),
        )

    return ManagedStateBaseline(
        library=library,
        states=(),
        source=(
            ManagedStateBaselineSource
            .NEW_LIBRARY
        ),
    )
