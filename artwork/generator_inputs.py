"""Resolve inputs and eligibility for generated episode title cards."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from artwork.inventory import (
    EpisodeInventory,
)
from artwork.models import (
    ArtworkAsset,
    ArtworkQuality,
    ArtworkSource,
    SelectionMode,
)
from artwork.providers.tmdb import (
    TMDBEpisodeArtwork,
)
from artwork.source_policy import (
    UPGRADEABLE_FALLBACK_SOURCES,
)


class EpisodeGenerationPath(
    str,
    Enum,
):
    """Why one episode will or will not use Artwork Generator."""

    LOCKED = "locked"
    KEEP_PRIMARY = "keep_primary"
    KEEP_GENERATED = "keep_generated"

    NO_TITLE = "no_title"
    NO_SOURCE_IMAGE = "no_source_image"

    GENERATE_MISSING = "generate_missing"
    UPGRADE_FALLBACK = "upgrade_fallback"


@dataclass(frozen=True)
class EpisodeGenerationInput:
    """Resolved generation decision for one episode."""

    episode_number: int
    path: EpisodeGenerationPath

    title: str | None = None
    title_source: ArtworkSource | None = None

    image_ref: str | None = None
    image_source: ArtworkSource | None = None

    image_provider_asset_id: str | None = None

    current_card: ArtworkAsset | None = None

    @property
    def should_generate(
        self,
    ) -> bool:
        return self.path in {
            EpisodeGenerationPath
            .GENERATE_MISSING,
            EpisodeGenerationPath
            .UPGRADE_FALLBACK,
        }


def resolve_episode_generation_input(
    *,
    episode_number: int,
    plex_episode: EpisodeInventory | None,
    tmdb_episode: TMDBEpisodeArtwork | None,
    current_card: ArtworkAsset | None,
    selection_mode: SelectionMode = (
        SelectionMode.AUTO
    ),
) -> EpisodeGenerationInput:
    """Resolve generation eligibility and source priority.

    Final-artwork priority is intentionally handled separately from
    cohesive provider selection:

        curated primary artwork
            >
        generated artwork
            >
        raw fallback artwork

    Generator input priority is:

        title:
            Plex
                >
            TMDB

        base image:
            TMDB still
                >
            Plex thumbnail
    """

    _validate_episode_number(
        episode_number
    )

    _validate_episode_identity(
        episode_number=episode_number,
        plex_episode=plex_episode,
        tmdb_episode=tmdb_episode,
    )

    if (
        selection_mode
        is SelectionMode.LOCKED
    ):
        return EpisodeGenerationInput(
            episode_number=(
                episode_number
            ),
            path=(
                EpisodeGenerationPath
                .LOCKED
            ),
            current_card=current_card,
        )

    current_available = (
        current_card is not None
        and current_card.available
    )

    if current_available:
        if (
            current_card.source
            is ArtworkSource.GENERATED
        ):
            return EpisodeGenerationInput(
                episode_number=(
                    episode_number
                ),
                path=(
                    EpisodeGenerationPath
                    .KEEP_GENERATED
                ),
                current_card=current_card,
            )

        if (
            current_card.quality
            is ArtworkQuality.CURATED
            or current_card.source
            in {
                ArtworkSource.MEDIUX,
                ArtworkSource.POSTERDB,
                ArtworkSource.MANUAL,
            }
            or current_card.source
            not in UPGRADEABLE_FALLBACK_SOURCES
        ):
            return EpisodeGenerationInput(
                episode_number=(
                    episode_number
                ),
                path=(
                    EpisodeGenerationPath
                    .KEEP_PRIMARY
                ),
                current_card=current_card,
            )

    title, title_source = (
        _resolve_title(
            plex_episode=plex_episode,
            tmdb_episode=tmdb_episode,
        )
    )

    if title is None:
        return EpisodeGenerationInput(
            episode_number=(
                episode_number
            ),
            path=(
                EpisodeGenerationPath
                .NO_TITLE
            ),
            current_card=current_card,
        )

    (
        image_ref,
        image_source,
        image_provider_asset_id,
    ) = _resolve_source_image(
        plex_episode=plex_episode,
        tmdb_episode=tmdb_episode,
        current_card=current_card,
    )

    if (
        image_ref is None
        or image_source is None
    ):
        return EpisodeGenerationInput(
            episode_number=(
                episode_number
            ),
            path=(
                EpisodeGenerationPath
                .NO_SOURCE_IMAGE
            ),
            title=title,
            title_source=title_source,
            current_card=current_card,
        )

    path = (
        EpisodeGenerationPath
        .UPGRADE_FALLBACK
        if current_available
        else EpisodeGenerationPath
        .GENERATE_MISSING
    )

    return EpisodeGenerationInput(
        episode_number=episode_number,
        path=path,
        title=title,
        title_source=title_source,
        image_ref=image_ref,
        image_source=image_source,
        image_provider_asset_id=(
            image_provider_asset_id
        ),
        current_card=current_card,
    )


def _resolve_title(
    *,
    plex_episode: EpisodeInventory | None,
    tmdb_episode: TMDBEpisodeArtwork | None,
) -> tuple[
    str | None,
    ArtworkSource | None,
]:
    if (
        plex_episode is not None
        and plex_episode.title
    ):
        return (
            plex_episode.title,
            ArtworkSource.PLEX,
        )

    if (
        tmdb_episode is not None
        and tmdb_episode.title
    ):
        return (
            tmdb_episode.title,
            ArtworkSource.TMDB,
        )

    return (
        None,
        None,
    )


def _resolve_source_image(
    *,
    plex_episode: EpisodeInventory | None,
    tmdb_episode: TMDBEpisodeArtwork | None,
    current_card: ArtworkAsset | None,
) -> tuple[
    str | None,
    ArtworkSource | None,
    str | None,
]:
    # Fresh TMDB season metadata is always preferred when it has a
    # usable episode still.
    if (
        tmdb_episode is not None
        and tmdb_episode.card is not None
        and tmdb_episode.card.available
    ):
        ref = _asset_reference(
            tmdb_episode.card
        )

        if ref is not None:
            return (
                ref,
                ArtworkSource.TMDB,
                (
                    tmdb_episode
                    .card
                    .provider_asset_id
                ),
            )

    # Existing v3.0 TMDB raw fallback is already a valid gathered TMDB
    # still. Reuse it when upgrading an existing installation even if
    # the current TMDB season request no longer returns the still.
    if (
        current_card is not None
        and current_card.available
        and current_card.source
        is ArtworkSource.TMDB
        and current_card.quality
        is not ArtworkQuality.CURATED
    ):
        ref = _asset_reference(
            current_card
        )

        if ref is not None:
            return (
                ref,
                ArtworkSource.TMDB,
                current_card.provider_asset_id,
            )

    # Plex is the fallback source image when TMDB has no usable still.
    if (
        plex_episode is not None
        and plex_episode.plex_thumb
    ):
        return (
            plex_episode.plex_thumb,
            ArtworkSource.PLEX,
            None,
        )

    return (
        None,
        None,
        None,
    )


def _asset_reference(
    asset: ArtworkAsset,
) -> str | None:
    if (
        asset.url
        and asset.url.strip()
    ):
        return asset.url.strip()

    if (
        asset.provider_asset_id
        and asset.provider_asset_id.strip()
    ):
        return (
            asset
            .provider_asset_id
            .strip()
        )

    return None


def _validate_episode_number(
    episode_number: int,
) -> None:
    if (
        not isinstance(
            episode_number,
            int,
        )
        or isinstance(
            episode_number,
            bool,
        )
        or episode_number <= 0
    ):
        raise ValueError(
            "episode number must be "
            "a positive integer"
        )


def _validate_episode_identity(
    *,
    episode_number: int,
    plex_episode: EpisodeInventory | None,
    tmdb_episode: TMDBEpisodeArtwork | None,
) -> None:
    if (
        plex_episode is not None
        and plex_episode.episode_number
        != episode_number
    ):
        raise ValueError(
            "Plex episode number does not "
            "match generation target"
        )

    if (
        tmdb_episode is not None
        and tmdb_episode.episode_number
        != episode_number
    ):
        raise ValueError(
            "TMDB episode number does not "
            "match generation target"
        )
