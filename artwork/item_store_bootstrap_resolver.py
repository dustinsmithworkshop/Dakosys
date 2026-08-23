"""Resolve a pre-state-store Artwork Manager show baseline safely.

This combines verified manifest-owned item-store evidence with current
Plex inventory and current provider discovery.

Recovery order for each MediUX artwork family:

1. Unique current-provider asset-set proof.
2. Explicit historical set identity with non-contradictory asset
   continuity.
3. Otherwise fail closed.

The current split item-store YAML remains authoritative for artwork
assets. Provider and historical metadata are used only to recover
semantic provenance.

This module performs no filesystem writes.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from artwork.inventory import (
    ShowInventory,
)
from artwork.item_store_bootstrap import (
    ShowItemStoreBootstrapSeed,
)
from artwork.item_store_bootstrap_match import (
    MediuxBootstrapFamily,
    MediuxBootstrapFamilyMatch,
    MediuxBootstrapMatchPath,
    match_mediux_bootstrap_families,
)
from artwork.item_store_bootstrap_state import (
    build_show_state_from_item_store_seed,
)
from artwork.item_store_bootstrap_witness import (
    match_legacy_bootstrap_family_witness,
)
from artwork.models import (
    ArtworkSetSelection,
    ArtworkSource,
    ShowArtworkState,
)
from artwork.providers.base import (
    ArtworkProvider,
)
from artwork.search import (
    ArtworkSearchKind,
    ArtworkSearchRequest,
)
from artwork.targets import (
    MediaType,
)


class ArtworkItemStoreBootstrapResolutionError(
    RuntimeError
):
    """Pre-state-store semantic identity could not be proven safely."""


class BootstrapRecoverySource(
    str,
    Enum,
):
    CURRENT_PROVIDER = "current_provider"
    HISTORICAL_WITNESS = (
        "historical_witness"
    )
    NO_EVIDENCE = "no_evidence"


@dataclass(frozen=True)
class BootstrapFamilyRecovery:
    plex_rating_key: str
    tvdb_id: int
    family: MediuxBootstrapFamily
    source: BootstrapRecoverySource
    selection: ArtworkSetSelection | None


@dataclass(frozen=True)
class ShowItemStoreBootstrapResolution:
    states: tuple[
        ShowArtworkState,
        ...,
    ]

    recoveries: tuple[
        BootstrapFamilyRecovery,
        ...,
    ]

    provider_request_count: int

    def recovery_count(
        self,
        *,
        family: MediuxBootstrapFamily,
        source: BootstrapRecoverySource,
    ) -> int:
        return sum(
            1
            for recovery in self.recoveries
            if (
                recovery.family is family
                and recovery.source
                is source
            )
        )

    @property
    def recovery_counts(
        self,
    ) -> Counter:
        return Counter(
            (
                recovery.family.value,
                recovery.source.value,
            )
            for recovery
            in self.recoveries
        )


def _selection_from_current_match(
    match: MediuxBootstrapFamilyMatch,
) -> ArtworkSetSelection | None:
    if (
        match.path
        is not MediuxBootstrapMatchPath.MATCHED
    ):
        return None

    artwork_set = match.matched_set

    if artwork_set is None:
        raise (
            ArtworkItemStoreBootstrapResolutionError(
                "matched MediUX bootstrap "
                "result has no ArtworkSet"
            )
        )

    return ArtworkSetSelection(
        provider=ArtworkSource.MEDIUX,
        set_id=str(
            artwork_set.set_id
        ),
        creator=artwork_set.creator,
    )


def _recover_family(
    *,
    seed: ShowItemStoreBootstrapSeed,
    match: MediuxBootstrapFamilyMatch,
    legacy_state: ShowArtworkState | None,
) -> tuple[
    ArtworkSetSelection | None,
    BootstrapRecoverySource,
]:
    if (
        match.path
        is MediuxBootstrapMatchPath.NO_EVIDENCE
    ):
        return (
            None,
            BootstrapRecoverySource.NO_EVIDENCE,
        )

    selection = (
        _selection_from_current_match(
            match
        )
    )

    if selection is not None:
        return (
            selection,
            BootstrapRecoverySource
            .CURRENT_PROVIDER,
        )

    witness = (
        match_legacy_bootstrap_family_witness(
            seed=seed,
            legacy_state=legacy_state,
            family=match.family,
        )
    )

    if witness.recovered:
        set_id = (
            witness.recovered_set_id
        )

        if set_id is None:
            raise (
                ArtworkItemStoreBootstrapResolutionError(
                    "recovered historical "
                    "witness has no set ID"
                )
            )

        return (
            ArtworkSetSelection(
                provider=(
                    ArtworkSource.MEDIUX
                ),
                set_id=set_id,
                creator=(
                    witness
                    .historical_creator
                ),
            ),
            BootstrapRecoverySource
            .HISTORICAL_WITNESS,
        )

    candidates = (
        ", ".join(
            match.candidate_set_ids
        )
        if match.candidate_set_ids
        else "none"
    )

    raise (
        ArtworkItemStoreBootstrapResolutionError(
            "could not prove pre-state-store "
            "MediUX selection for "
            f"rating_key={seed.plex_rating_key} "
            f"tvdb={seed.tvdb_id} "
            f"family={match.family.value}: "
            f"provider={match.path.value}, "
            f"provider_candidates={candidates}, "
            f"historical={witness.path.value}"
        )
    )


def resolve_show_item_store_bootstrap(
    *,
    seeds: Iterable[
        ShowItemStoreBootstrapSeed
    ],
    inventories: Iterable[
        ShowInventory
    ],
    provider: ArtworkProvider,
    legacy_states: Iterable[
        ShowArtworkState
    ] = (),
) -> ShowItemStoreBootstrapResolution:
    """Reconstruct semantic state for one verified v3.0 item store."""

    seed_tuple = tuple(
        seeds
    )

    inventory_tuple = tuple(
        inventories
    )

    legacy_tuple = tuple(
        legacy_states
    )

    inventories_by_rating_key = {}

    for inventory in inventory_tuple:
        rating_key = str(
            inventory
            .identity
            .plex_rating_key
        )

        if (
            rating_key
            in inventories_by_rating_key
        ):
            raise (
                ArtworkItemStoreBootstrapResolutionError(
                    "duplicate Plex inventory "
                    "rating key during bootstrap: "
                    f"{rating_key}"
                )
            )

        inventories_by_rating_key[
            rating_key
        ] = inventory

    legacy_by_tvdb = {}

    for legacy_state in legacy_tuple:
        tvdb_id = (
            legacy_state.tvdb_id
        )

        if tvdb_id is None:
            continue

        if tvdb_id in legacy_by_tvdb:
            raise (
                ArtworkItemStoreBootstrapResolutionError(
                    "duplicate historical "
                    "TVDB identity during bootstrap: "
                    f"{tvdb_id}"
                )
            )

        legacy_by_tvdb[
            tvdb_id
        ] = legacy_state

    states = []
    recoveries = []
    provider_requests = 0

    for seed in seed_tuple:
        inventory = (
            inventories_by_rating_key.get(
                seed.plex_rating_key
            )
        )

        if inventory is None:
            raise (
                ArtworkItemStoreBootstrapResolutionError(
                    "manifest-owned show is "
                    "missing from current Plex "
                    "inventory: "
                    f"rating_key="
                    f"{seed.plex_rating_key}, "
                    f"tvdb={seed.tvdb_id}"
                )
            )

        has_mediux = (
            bool(
                seed
                .mediux_episode_asset_ids
            )
            or bool(
                seed
                .mediux_presentation_asset_ids
            )
        )

        if has_mediux:
            identity = (
                inventory.identity
            )

            request = (
                ArtworkSearchRequest(
                    library=(
                        identity.library
                    ),
                    plex_rating_key=str(
                        identity
                        .plex_rating_key
                    ),
                    title=identity.title,
                    year=identity.year,
                    tvdb_id=(
                        identity.tvdb_id
                    ),
                    tmdb_id=(
                        identity.tmdb_id
                    ),
                    imdb_id=(
                        identity.imdb_id
                    ),
                    seasons=(
                        inventory.seasons
                    ),
                    kind=(
                        ArtworkSearchKind
                        .DISCOVERY
                    ),
                    media_type=(
                        MediaType.SHOW
                    ),
                )
            )

            provider_requests += 1

            try:
                candidates = tuple(
                    provider.find_sets(
                        request
                    )
                )

            except Exception as exc:
                raise (
                    ArtworkItemStoreBootstrapResolutionError(
                        "primary provider failed "
                        "during pre-state-store "
                        "bootstrap for "
                        f"rating_key="
                        f"{seed.plex_rating_key}, "
                        f"tvdb={seed.tvdb_id}: "
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    )
                ) from exc

        else:
            candidates = ()

        (
            episode_match,
            presentation_match,
        ) = (
            match_mediux_bootstrap_families(
                seed=seed,
                candidates=candidates,
            )
        )

        legacy_state = (
            legacy_by_tvdb.get(
                seed.tvdb_id
            )
        )

        (
            episode_selection,
            episode_source,
        ) = _recover_family(
            seed=seed,
            match=episode_match,
            legacy_state=legacy_state,
        )

        (
            presentation_selection,
            presentation_source,
        ) = _recover_family(
            seed=seed,
            match=presentation_match,
            legacy_state=legacy_state,
        )

        state = (
            build_show_state_from_item_store_seed(
                seed=seed,
                inventory=inventory,
                episode_selection=(
                    episode_selection
                ),
                presentation_selection=(
                    presentation_selection
                ),
            )
        )

        states.append(
            state
        )

        recoveries.extend(
            (
                BootstrapFamilyRecovery(
                    plex_rating_key=(
                        seed
                        .plex_rating_key
                    ),
                    tvdb_id=(
                        seed.tvdb_id
                    ),
                    family=(
                        MediuxBootstrapFamily
                        .EPISODE
                    ),
                    source=(
                        episode_source
                    ),
                    selection=(
                        episode_selection
                    ),
                ),
                BootstrapFamilyRecovery(
                    plex_rating_key=(
                        seed
                        .plex_rating_key
                    ),
                    tvdb_id=(
                        seed.tvdb_id
                    ),
                    family=(
                        MediuxBootstrapFamily
                        .PRESENTATION
                    ),
                    source=(
                        presentation_source
                    ),
                    selection=(
                        presentation_selection
                    ),
                ),
            )
        )

    return (
        ShowItemStoreBootstrapResolution(
            states=tuple(
                states
            ),
            recoveries=tuple(
                recoveries
            ),
            provider_request_count=(
                provider_requests
            ),
        )
    )
