"""Reconcile Plex movie inventory with durable movie artwork state."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from artwork.models import (
    MovieArtworkState,
)
from artwork.movie_inventory import (
    MovieInventory,
)
from artwork.movie_state_store import (
    StoredMovieArtworkState,
)
from artwork.targets import (
    ArtworkTarget,
    MediaType,
)


@dataclass(frozen=True)
class ReconciledMovie:
    """One Plex movie matched to durable managed artwork."""

    inventory: MovieInventory
    artwork: MovieArtworkState


@dataclass(frozen=True)
class MovieTargetReconciliation:
    """Read-only reconciliation result for one movie library."""

    target: ArtworkTarget

    matched: tuple[
        ReconciledMovie,
        ...,
    ]

    unmanaged: tuple[
        MovieInventory,
        ...,
    ]

    missing_identity: tuple[
        MovieInventory,
        ...,
    ]

    orphaned: tuple[
        StoredMovieArtworkState,
        ...,
    ]

    @property
    def plex_movie_count(
        self,
    ) -> int:
        return (
            len(self.matched)
            + len(self.unmanaged)
            + len(self.missing_identity)
        )

    @property
    def managed_movie_count(
        self,
    ) -> int:
        return len(
            self.matched
        )

    @property
    def unmanaged_movie_count(
        self,
    ) -> int:
        return len(
            self.unmanaged
        )

    @property
    def missing_identity_count(
        self,
    ) -> int:
        return len(
            self.missing_identity
        )

    @property
    def orphaned_movie_count(
        self,
    ) -> int:
        return len(
            self.orphaned
        )


def _inventory_sort_key(
    inventory: MovieInventory,
) -> tuple[str, str]:
    return (
        inventory.identity.title.casefold(),
        inventory.identity.plex_rating_key,
    )


def _has_external_identity(
    inventory: MovieInventory,
) -> bool:
    identity = inventory.identity

    return (
        identity.tmdb_id is not None
        or identity.imdb_id is not None
    )


def _validate_matched_identity(
    *,
    inventory: MovieInventory,
    state: MovieArtworkState,
) -> None:
    """Reject contradictory external IDs for the same Plex item."""

    identity = inventory.identity

    if (
        identity.tmdb_id is not None
        and state.tmdb_id is not None
        and identity.tmdb_id
        != state.tmdb_id
    ):
        raise ValueError(
            "movie durable state TMDB identity "
            "disagrees with Plex for rating key "
            f"{identity.plex_rating_key!r}"
        )

    if (
        identity.imdb_id is not None
        and state.imdb_id is not None
        and identity.imdb_id.casefold()
        != state.imdb_id.casefold()
    ):
        raise ValueError(
            "movie durable state IMDb identity "
            "disagrees with Plex for rating key "
            f"{identity.plex_rating_key!r}"
        )


def reconcile_movie_target(
    *,
    target: ArtworkTarget,
    inventories: Iterable[
        MovieInventory
    ],
    managed_items: Iterable[
        StoredMovieArtworkState
    ],
) -> MovieTargetReconciliation:
    """Reconcile one movie-type Plex library.

    Plex library + Plex rating key is authoritative identity.

    TMDB and IMDb IDs remain provider/mapping signals and are checked
    for contradictions when both Plex and durable state provide them.
    """

    if (
        target.media_type
        is not MediaType.MOVIE
    ):
        raise ValueError(
            "reconcile_movie_target requires "
            "a movie target"
        )

    target_inventories = [
        inventory
        for inventory in inventories
        if (
            inventory.identity.library
            == target.library
        )
    ]

    inventory_by_key = {}

    for inventory in target_inventories:
        rating_key = (
            inventory
            .identity
            .plex_rating_key
        )

        if rating_key in inventory_by_key:
            raise ValueError(
                "duplicate Plex movie rating key "
                f"{rating_key!r}"
            )

        inventory_by_key[
            rating_key
        ] = inventory

    managed_by_key = {}

    for item in managed_items:
        rating_key = (
            item.plex_rating_key
        )

        if rating_key in managed_by_key:
            raise ValueError(
                "duplicate durable movie rating key "
                f"{rating_key!r}"
            )

        managed_by_key[
            rating_key
        ] = item

    matched = []
    unmanaged = []
    missing_identity = []

    consumed = set()

    for inventory in target_inventories:
        rating_key = (
            inventory
            .identity
            .plex_rating_key
        )

        stored = managed_by_key.get(
            rating_key
        )

        if stored is not None:
            _validate_matched_identity(
                inventory=inventory,
                state=stored.state,
            )

            matched.append(
                ReconciledMovie(
                    inventory=inventory,
                    artwork=stored.state,
                )
            )

            consumed.add(
                rating_key
            )

            continue

        if not _has_external_identity(
            inventory
        ):
            missing_identity.append(
                inventory
            )
        else:
            unmanaged.append(
                inventory
            )

    orphaned = [
        item
        for rating_key, item
        in managed_by_key.items()
        if rating_key not in inventory_by_key
    ]

    matched.sort(
        key=lambda item:
            _inventory_sort_key(
                item.inventory
            )
    )

    unmanaged.sort(
        key=_inventory_sort_key
    )

    missing_identity.sort(
        key=_inventory_sort_key
    )

    orphaned.sort(
        key=lambda item: (
            (
                item.state.title
                or ""
            ).casefold(),
            item.plex_rating_key,
        )
    )

    return MovieTargetReconciliation(
        target=target,
        matched=tuple(
            matched
        ),
        unmanaged=tuple(
            unmanaged
        ),
        missing_identity=tuple(
            missing_identity
        ),
        orphaned=tuple(
            orphaned
        ),
    )
