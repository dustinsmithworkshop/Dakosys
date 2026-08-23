"""Reconstruct semantic show state from verified v3.0 item-store evidence.

Current manifest-owned Kometa YAML remains authoritative for artwork
assets. Provider matching supplies only cohesive-set provenance.

This module performs no provider calls and no filesystem writes.
"""

from __future__ import annotations

from artwork.inventory import (
    ShowInventory,
)
from artwork.item_store_bootstrap import (
    PersistedArtworkEvidence,
    ShowItemStoreBootstrapSeed,
)
from artwork.models import (
    ArtworkAsset,
    ArtworkKind,
    ArtworkQuality,
    ArtworkSetSelection,
    ArtworkSource,
    EpisodeArtwork,
    SeasonArtwork,
    SelectionMode,
    ShowArtworkState,
)


class ArtworkItemStoreStateBootstrapError(
    RuntimeError
):
    """Verified item-store evidence cannot form safe semantic state."""


def _asset_from_evidence(
    evidence: PersistedArtworkEvidence,
) -> ArtworkAsset:
    if evidence.source is ArtworkSource.MEDIUX:
        quality = ArtworkQuality.CURATED

    elif evidence.source is ArtworkSource.TMDB:
        quality = ArtworkQuality.RAW_STILL

    else:
        raise ArtworkItemStoreStateBootstrapError(
            "unsupported pre-state-store "
            "artwork source "
            f"{evidence.source.value!r}"
        )

    provider_asset_id = (
        evidence.provider_asset_id
        or ""
    ).strip()

    if not provider_asset_id:
        raise ArtworkItemStoreStateBootstrapError(
            "persisted artwork evidence "
            "has no stable provider asset identity: "
            f"{evidence.url!r}"
        )

    return ArtworkAsset(
        kind=evidence.kind,
        source=evidence.source,
        url=evidence.url,
        provider_asset_id=(
            provider_asset_id
        ),
        quality=quality,
    )


def _validate_selection(
    *,
    family: str,
    has_mediux_evidence: bool,
    selection: ArtworkSetSelection | None,
) -> None:
    if has_mediux_evidence:
        if selection is None:
            raise ArtworkItemStoreStateBootstrapError(
                f"{family} MediUX artwork "
                "has no recovered cohesive-set identity"
            )

        if (
            selection.provider
            is not ArtworkSource.MEDIUX
        ):
            raise ArtworkItemStoreStateBootstrapError(
                f"{family} selection is not MediUX"
            )

        return

    if selection is not None:
        raise ArtworkItemStoreStateBootstrapError(
            f"{family} selection was supplied "
            "without persisted MediUX evidence"
        )


def build_show_state_from_item_store_seed(
    *,
    seed: ShowItemStoreBootstrapSeed,
    inventory: ShowInventory,
    episode_selection: ArtworkSetSelection | None = None,
    presentation_selection: ArtworkSetSelection | None = None,
) -> ShowArtworkState:
    """Reconstruct one durable state from current v3.0 output."""

    identity = inventory.identity

    if (
        str(
            identity.plex_rating_key
        )
        != seed.plex_rating_key
    ):
        raise ArtworkItemStoreStateBootstrapError(
            "item-store Plex rating key "
            "does not match current inventory"
        )

    if (
        identity.tvdb_id is not None
        and identity.tvdb_id
        != seed.tvdb_id
    ):
        raise ArtworkItemStoreStateBootstrapError(
            "item-store TVDB identity "
            "does not match current inventory"
        )

    _validate_selection(
        family="episode",
        has_mediux_evidence=bool(
            seed.mediux_episode_asset_ids
        ),
        selection=episode_selection,
    )

    _validate_selection(
        family="presentation",
        has_mediux_evidence=bool(
            seed.mediux_presentation_asset_ids
        ),
        selection=(
            presentation_selection
        ),
    )

    poster = None
    background = None

    seasons: dict[
        int,
        SeasonArtwork,
    ] = {}

    def season_for(
        season_number: int,
    ) -> SeasonArtwork:
        season = seasons.get(
            season_number
        )

        if season is None:
            season = SeasonArtwork(
                season_number=(
                    season_number
                )
            )

            seasons[
                season_number
            ] = season

        return season

    for evidence in seed.assets:
        asset = _asset_from_evidence(
            evidence
        )

        if (
            evidence.kind
            is ArtworkKind.SHOW_POSTER
        ):
            if poster is not None:
                raise ArtworkItemStoreStateBootstrapError(
                    "duplicate show poster evidence"
                )

            poster = asset
            continue

        if (
            evidence.kind
            is ArtworkKind.SHOW_BACKGROUND
        ):
            if background is not None:
                raise ArtworkItemStoreStateBootstrapError(
                    "duplicate show background evidence"
                )

            background = asset
            continue

        season_number = (
            evidence.season_number
        )

        if season_number is None:
            raise ArtworkItemStoreStateBootstrapError(
                "season-scoped artwork "
                "has no season number"
            )

        season = season_for(
            season_number
        )

        if (
            evidence.kind
            is ArtworkKind.SEASON_POSTER
        ):
            if season.poster is not None:
                raise ArtworkItemStoreStateBootstrapError(
                    "duplicate season poster evidence "
                    f"for season {season_number}"
                )

            season.poster = asset
            continue

        if (
            evidence.kind
            is ArtworkKind.EPISODE_CARD
        ):
            episode_number = (
                evidence.episode_number
            )

            if episode_number is None:
                raise ArtworkItemStoreStateBootstrapError(
                    "episode card has no "
                    "episode number"
                )

            if (
                episode_number
                in season.episodes
            ):
                raise ArtworkItemStoreStateBootstrapError(
                    "duplicate episode-card "
                    "evidence for "
                    f"S{season_number:02d}"
                    f"E{episode_number:02d}"
                )

            season.episodes[
                episode_number
            ] = EpisodeArtwork(
                episode_number=(
                    episode_number
                ),
                card=asset,
            )

            continue

        raise ArtworkItemStoreStateBootstrapError(
            "unsupported show artwork kind "
            f"{evidence.kind.value!r}"
        )

    # Match normal discovery semantics exactly:
    # episode provenance is compatibility-primary when available;
    # otherwise presentation provenance fills the legacy fields.
    legacy_selection = (
        episode_selection
        or presentation_selection
    )

    return ShowArtworkState(
        title=identity.title,
        tvdb_id=seed.tvdb_id,
        tmdb_id=identity.tmdb_id,
        imdb_id=identity.imdb_id,
        poster=poster,
        background=background,
        seasons={
            number: seasons[number]
            for number
            in sorted(
                seasons
            )
        },
        selected_set_id=(
            legacy_selection.set_id
            if legacy_selection
            is not None
            else None
        ),
        selected_set_source=(
            legacy_selection.provider
            if legacy_selection
            is not None
            else None
        ),
        selected_creator=(
            legacy_selection.creator
            if legacy_selection
            is not None
            else None
        ),
        selection_mode=(
            SelectionMode.AUTO
        ),
        episode_selection=(
            episode_selection
        ),
        presentation_selection=(
            presentation_selection
        ),
    )
