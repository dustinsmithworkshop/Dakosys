"""Deterministic MediUX set recovery for pre-state-store evidence.

Persisted Artwork Manager 3.0 YAML retains MediUX asset IDs in its
public asset URLs but does not retain the cohesive set ID.

A historical set is recoverable only when the persisted MediUX asset
IDs for one artwork family uniquely identify one currently discoverable
MediUX set.

No ranking or best-effort guessing is performed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from artwork.item_store_bootstrap import (
    ShowItemStoreBootstrapSeed,
)
from artwork.models import (
    ArtworkSet,
    ArtworkSource,
)


class MediuxBootstrapFamily(
    str,
    Enum,
):
    EPISODE = "episode"
    PRESENTATION = "presentation"


class MediuxBootstrapMatchPath(
    str,
    Enum,
):
    NO_EVIDENCE = "no_evidence"
    MATCHED = "matched"
    UNRESOLVED = "unresolved"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class MediuxBootstrapFamilyMatch:
    """Result of matching one persisted artwork family."""

    family: MediuxBootstrapFamily

    path: MediuxBootstrapMatchPath

    evidence_asset_ids: frozenset[str]

    candidate_set_ids: tuple[
        str,
        ...,
    ] = ()

    matched_set: ArtworkSet | None = None

    @property
    def matched(self) -> bool:
        return (
            self.path
            is MediuxBootstrapMatchPath.MATCHED
        )

    @property
    def blocks_bootstrap(self) -> bool:
        return self.path in {
            MediuxBootstrapMatchPath.UNRESOLVED,
            MediuxBootstrapMatchPath.AMBIGUOUS,
        }


def _mediux_asset_id(
    asset,
) -> str | None:
    if asset is None:
        return None

    if (
        getattr(
            asset,
            "source",
            None,
        )
        is not ArtworkSource.MEDIUX
    ):
        return None

    raw = getattr(
        asset,
        "provider_asset_id",
        None,
    )

    if raw is None:
        return None

    value = str(
        raw
    ).strip()

    return value or None


def mediux_candidate_family_asset_ids(
    artwork_set: ArtworkSet,
    *,
    family: MediuxBootstrapFamily,
) -> frozenset[str]:
    """Return MediUX provider asset IDs present in one set family."""

    if (
        artwork_set.provider
        is not ArtworkSource.MEDIUX
    ):
        return frozenset()

    values: set[str] = set()

    if (
        family
        is MediuxBootstrapFamily.PRESENTATION
    ):
        for asset in (
            artwork_set.poster,
            artwork_set.background,
        ):
            asset_id = (
                _mediux_asset_id(
                    asset
                )
            )

            if asset_id is not None:
                values.add(
                    asset_id
                )

        for season in (
            artwork_set
            .seasons
            .values()
        ):
            asset_id = (
                _mediux_asset_id(
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
            artwork_set
            .seasons
            .values()
        ):
            for episode in (
                season
                .episodes
                .values()
            ):
                asset_id = (
                    _mediux_asset_id(
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


def _seed_evidence(
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


def match_mediux_bootstrap_family(
    *,
    seed: ShowItemStoreBootstrapSeed,
    candidates: Iterable[
        ArtworkSet
    ],
    family: MediuxBootstrapFamily,
) -> MediuxBootstrapFamilyMatch:
    """Match persisted family evidence to exactly one MediUX set.

    Persisted IDs are treated as a subset rather than requiring exact
    equality because the live MediUX set may have gained artwork since
    the pre-state-store YAML was written.
    """

    evidence = _seed_evidence(
        seed,
        family=family,
    )

    if not evidence:
        return MediuxBootstrapFamilyMatch(
            family=family,
            path=(
                MediuxBootstrapMatchPath
                .NO_EVIDENCE
            ),
            evidence_asset_ids=evidence,
        )

    matches: list[
        ArtworkSet
    ] = []

    for artwork_set in candidates:
        if (
            artwork_set.provider
            is not ArtworkSource.MEDIUX
        ):
            continue

        available = (
            mediux_candidate_family_asset_ids(
                artwork_set,
                family=family,
            )
        )

        if evidence.issubset(
            available
        ):
            matches.append(
                artwork_set
            )

    matches.sort(
        key=lambda artwork_set: (
            str(
                artwork_set.set_id
            ),
            str(
                artwork_set.creator
                or ""
            ).casefold(),
            str(
                artwork_set.title
                or ""
            ).casefold(),
        )
    )

    match_ids = tuple(
        str(
            artwork_set.set_id
        )
        for artwork_set in matches
    )

    if not matches:
        return MediuxBootstrapFamilyMatch(
            family=family,
            path=(
                MediuxBootstrapMatchPath
                .UNRESOLVED
            ),
            evidence_asset_ids=evidence,
        )

    if len(
        matches
    ) > 1:
        return MediuxBootstrapFamilyMatch(
            family=family,
            path=(
                MediuxBootstrapMatchPath
                .AMBIGUOUS
            ),
            evidence_asset_ids=evidence,
            candidate_set_ids=(
                match_ids
            ),
        )

    return MediuxBootstrapFamilyMatch(
        family=family,
        path=(
            MediuxBootstrapMatchPath
            .MATCHED
        ),
        evidence_asset_ids=evidence,
        candidate_set_ids=(
            match_ids
        ),
        matched_set=matches[0],
    )


def match_mediux_bootstrap_families(
    *,
    seed: ShowItemStoreBootstrapSeed,
    candidates: Iterable[
        ArtworkSet
    ],
) -> tuple[
    MediuxBootstrapFamilyMatch,
    MediuxBootstrapFamilyMatch,
]:
    """Match episode and presentation evidence independently."""

    candidate_tuple = tuple(
        candidates
    )

    return (
        match_mediux_bootstrap_family(
            seed=seed,
            candidates=candidate_tuple,
            family=(
                MediuxBootstrapFamily
                .EPISODE
            ),
        ),
        match_mediux_bootstrap_family(
            seed=seed,
            candidates=candidate_tuple,
            family=(
                MediuxBootstrapFamily
                .PRESENTATION
            ),
        ),
    )
