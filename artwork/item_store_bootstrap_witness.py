"""Historical continuity witness for pre-state-store Artwork Manager data.

An older monolithic MediUX metadata file may retain an explicit
historical set ID that no longer can be reconstructed from current
MediUX set membership.

That historical identity is usable only when the current manifest-owned
Artwork Manager output shows non-contradictory continuity with the
legacy family:

- exact artwork identity;
- current artwork is a subset of legacy artwork; or
- legacy artwork is a subset of current artwork.

Partial overlap is deliberately insufficient because it may represent a
real artwork-set migration after the legacy metadata snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse

from artwork.item_store_bootstrap import (
    ShowItemStoreBootstrapSeed,
)
from artwork.item_store_bootstrap_match import (
    MediuxBootstrapFamily,
)
from artwork.models import (
    ArtworkSource,
    ShowArtworkState,
)


class LegacyBootstrapContinuityPath(
    str,
    Enum,
):
    NO_CURRENT_EVIDENCE = (
        "no_current_evidence"
    )
    NO_LEGACY_STATE = (
        "no_legacy_state"
    )
    IDENTITY_MISMATCH = (
        "identity_mismatch"
    )
    NO_MEDIUX_SELECTION = (
        "no_mediux_selection"
    )
    NO_LEGACY_EVIDENCE = (
        "no_legacy_evidence"
    )

    EXACT = "exact"

    CURRENT_SUBSET_OF_LEGACY = (
        "current_subset_of_legacy"
    )

    LEGACY_SUBSET_OF_CURRENT = (
        "legacy_subset_of_current"
    )

    PARTIAL_OVERLAP = (
        "partial_overlap"
    )

    DISJOINT = "disjoint"


_RECOVERABLE_PATHS = {
    LegacyBootstrapContinuityPath.EXACT,
    (
        LegacyBootstrapContinuityPath
        .CURRENT_SUBSET_OF_LEGACY
    ),
    (
        LegacyBootstrapContinuityPath
        .LEGACY_SUBSET_OF_CURRENT
    ),
}


@dataclass(frozen=True)
class LegacyBootstrapFamilyWitness:
    """Historical set-identity evidence for one artwork family."""

    family: MediuxBootstrapFamily

    path: LegacyBootstrapContinuityPath

    current_asset_ids: frozenset[str]

    legacy_asset_ids: frozenset[str]

    historical_set_id: str | None = None

    historical_creator: str | None = None

    @property
    def recovered(self) -> bool:
        return (
            self.path
            in _RECOVERABLE_PATHS
            and self.historical_set_id
            is not None
        )

    @property
    def recovered_set_id(
        self,
    ) -> str | None:
        if not self.recovered:
            return None

        return self.historical_set_id

    @property
    def blocks_bootstrap(self) -> bool:
        if not self.current_asset_ids:
            return False

        return not self.recovered


def _mediux_asset_id_from_url(
    url,
) -> str | None:
    if not isinstance(
        url,
        str,
    ):
        return None

    normalized = url.strip()

    if not normalized:
        return None

    parsed = urlparse(
        normalized
    )

    host = (
        parsed.hostname
        or ""
    ).casefold()

    if host != "api.mediux.pro":
        return None

    parts = tuple(
        part
        for part in parsed.path.split("/")
        if part
    )

    if (
        len(parts) != 2
        or parts[0].casefold()
        != "assets"
    ):
        return None

    asset_id = parts[1].strip()

    return asset_id or None


def _asset_mediux_id(
    asset,
) -> str | None:
    if asset is None:
        return None

    return _mediux_asset_id_from_url(
        getattr(
            asset,
            "url",
            None,
        )
    )


def legacy_mediux_family_asset_ids(
    state: ShowArtworkState,
    *,
    family: MediuxBootstrapFamily,
) -> frozenset[str]:
    """Return MediUX asset IDs retained by one legacy state family.

    URL identity is used intentionally rather than ArtworkAsset.source.
    The old monolithic importer predates mixed-provider durable state and
    therefore labels imported URLs as MediUX even when a URL is TMDB.
    """

    values: set[str] = set()

    if (
        family
        is MediuxBootstrapFamily.PRESENTATION
    ):
        for asset in (
            state.poster,
            state.background,
        ):
            asset_id = (
                _asset_mediux_id(
                    asset
                )
            )

            if asset_id is not None:
                values.add(
                    asset_id
                )

        for season in (
            state.seasons.values()
        ):
            asset_id = (
                _asset_mediux_id(
                    season.poster
                )
            )

            if asset_id is not None:
                values.add(
                    asset_id
                )

    elif (
        family
        is MediuxBootstrapFamily.EPISODE
    ):
        for season in (
            state.seasons.values()
        ):
            for episode in (
                season.episodes.values()
            ):
                asset_id = (
                    _asset_mediux_id(
                        episode.card
                    )
                )

                if asset_id is not None:
                    values.add(
                        asset_id
                    )

    else:
        raise ValueError(
            "unsupported MediUX bootstrap "
            f"family: {family!r}"
        )

    return frozenset(
        values
    )


def _current_family_asset_ids(
    seed: ShowItemStoreBootstrapSeed,
    *,
    family: MediuxBootstrapFamily,
) -> frozenset[str]:
    if (
        family
        is MediuxBootstrapFamily.EPISODE
    ):
        return (
            seed
            .mediux_episode_asset_ids
        )

    if (
        family
        is MediuxBootstrapFamily.PRESENTATION
    ):
        return (
            seed
            .mediux_presentation_asset_ids
        )

    raise ValueError(
        "unsupported MediUX bootstrap "
        f"family: {family!r}"
    )


def _historical_set_id(
    state: ShowArtworkState,
) -> str | None:
    raw = state.selected_set_id

    if raw is None:
        return None

    value = str(
        raw
    ).strip()

    return value or None


def match_legacy_bootstrap_family_witness(
    *,
    seed: ShowItemStoreBootstrapSeed,
    legacy_state: ShowArtworkState | None,
    family: MediuxBootstrapFamily,
) -> LegacyBootstrapFamilyWitness:
    """Use explicit legacy identity only when asset continuity proves it."""

    current = (
        _current_family_asset_ids(
            seed,
            family=family,
        )
    )

    if not current:
        return (
            LegacyBootstrapFamilyWitness(
                family=family,
                path=(
                    LegacyBootstrapContinuityPath
                    .NO_CURRENT_EVIDENCE
                ),
                current_asset_ids=current,
                legacy_asset_ids=(
                    frozenset()
                ),
            )
        )

    if legacy_state is None:
        return (
            LegacyBootstrapFamilyWitness(
                family=family,
                path=(
                    LegacyBootstrapContinuityPath
                    .NO_LEGACY_STATE
                ),
                current_asset_ids=current,
                legacy_asset_ids=(
                    frozenset()
                ),
            )
        )

    if (
        legacy_state.tvdb_id
        != seed.tvdb_id
    ):
        return (
            LegacyBootstrapFamilyWitness(
                family=family,
                path=(
                    LegacyBootstrapContinuityPath
                    .IDENTITY_MISMATCH
                ),
                current_asset_ids=current,
                legacy_asset_ids=(
                    frozenset()
                ),
            )
        )

    set_id = _historical_set_id(
        legacy_state
    )

    if (
        set_id is None
        or legacy_state.selected_set_source
        is not ArtworkSource.MEDIUX
    ):
        return (
            LegacyBootstrapFamilyWitness(
                family=family,
                path=(
                    LegacyBootstrapContinuityPath
                    .NO_MEDIUX_SELECTION
                ),
                current_asset_ids=current,
                legacy_asset_ids=(
                    frozenset()
                ),
                historical_set_id=(
                    set_id
                ),
                historical_creator=(
                    legacy_state
                    .selected_creator
                ),
            )
        )

    legacy = (
        legacy_mediux_family_asset_ids(
            legacy_state,
            family=family,
        )
    )

    if not legacy:
        return (
            LegacyBootstrapFamilyWitness(
                family=family,
                path=(
                    LegacyBootstrapContinuityPath
                    .NO_LEGACY_EVIDENCE
                ),
                current_asset_ids=current,
                legacy_asset_ids=legacy,
                historical_set_id=set_id,
                historical_creator=(
                    legacy_state
                    .selected_creator
                ),
            )
        )

    if current == legacy:
        path = (
            LegacyBootstrapContinuityPath
            .EXACT
        )

    elif current < legacy:
        path = (
            LegacyBootstrapContinuityPath
            .CURRENT_SUBSET_OF_LEGACY
        )

    elif legacy < current:
        path = (
            LegacyBootstrapContinuityPath
            .LEGACY_SUBSET_OF_CURRENT
        )

    elif current & legacy:
        path = (
            LegacyBootstrapContinuityPath
            .PARTIAL_OVERLAP
        )

    else:
        path = (
            LegacyBootstrapContinuityPath
            .DISJOINT
        )

    return LegacyBootstrapFamilyWitness(
        family=family,
        path=path,
        current_asset_ids=current,
        legacy_asset_ids=legacy,
        historical_set_id=set_id,
        historical_creator=(
            legacy_state.selected_creator
        ),
    )
