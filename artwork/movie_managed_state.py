"""Resolve durable managed-state baseline for one movie library."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from artwork.managed_state import (
    ArtworkStateBootstrapRequiredError,
    InconsistentManagedStateError,
    ManagedStateBaselineSource,
)
from artwork.movie_item_store import (
    MovieItemStoreManifest,
    load_movie_item_store_manifest,
)
from artwork.movie_kometa import (
    movie_mapping_id,
)
from artwork.movie_state_store import (
    MovieArtworkStateStore,
    StoredMovieArtworkState,
    load_movie_state_store,
)


@dataclass(frozen=True)
class MovieManagedStateBaseline:
    """Resolved starting state for one movie execution."""

    library: str

    items: tuple[
        StoredMovieArtworkState,
        ...,
    ]

    source: ManagedStateBaselineSource

    manifest: MovieItemStoreManifest | None = None

    state_store: MovieArtworkStateStore | None = None

    @property
    def states(self):
        return tuple(
            item.state
            for item in self.items
        )

    @property
    def state_count(
        self,
    ) -> int:
        return len(
            self.items
        )


def _validate_manifest_state_identity(
    *,
    manifest: MovieItemStoreManifest,
    state_store: MovieArtworkStateStore,
) -> None:
    manifest_items = {
        item.plex_rating_key:
            item.mapping_id
        for item
        in manifest.items
    }

    state_items = {
        item.plex_rating_key:
            movie_mapping_id(
                item.state
            )
        for item
        in state_store.items
    }

    if manifest_items != state_items:
        raise InconsistentManagedStateError(
            "Artwork Manager movie ownership "
            "manifest and durable semantic "
            "state disagree"
        )


def load_movie_managed_state_baseline(
    *,
    directory: str | Path,
    library: str,
) -> MovieManagedStateBaseline:
    """Resolve authoritative movie managed state."""

    directory = Path(
        directory
    )

    manifest = (
        load_movie_item_store_manifest(
            directory,
            expected_library=library,
        )
    )

    state_store = (
        load_movie_state_store(
            directory,
            expected_library=library,
        )
    )

    if state_store is not None:
        if manifest is None:
            raise InconsistentManagedStateError(
                "Artwork Manager movie durable "
                "state exists without an "
                "ownership manifest"
            )

        _validate_manifest_state_identity(
            manifest=manifest,
            state_store=state_store,
        )

        return MovieManagedStateBaseline(
            library=library,
            items=state_store.items,
            source=(
                ManagedStateBaselineSource
                .DURABLE_STATE
            ),
            manifest=manifest,
            state_store=state_store,
        )

    if manifest is not None:
        raise ArtworkStateBootstrapRequiredError(
            "existing Artwork Manager movie "
            "item store has no durable semantic "
            "state"
        )

    return MovieManagedStateBaseline(
        library=library,
        items=(),
        source=(
            ManagedStateBaselineSource
            .NEW_LIBRARY
        ),
    )
