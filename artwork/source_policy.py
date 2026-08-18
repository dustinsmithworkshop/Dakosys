"""Artwork source-priority rules used during managed refreshes."""

from __future__ import annotations

from artwork.models import (
    ArtworkAsset,
    ArtworkSet,
    ArtworkSource,
)


# These sources are useful fallback, but may be replaced in-place when
# the currently selected primary provider later supplies artwork for the
# same slot.
UPGRADEABLE_FALLBACK_SOURCES = frozenset(
    {
        ArtworkSource.TMDB,
        ArtworkSource.TVDB,
        ArtworkSource.PLEX,
        ArtworkSource.GENERATED,
    }
)


def is_upgradeable_fallback_asset(
    asset: ArtworkAsset | None,
    *,
    primary_provider: ArtworkSource,
) -> bool:
    """Whether one usable asset is lower-priority fallback."""

    return (
        asset is not None
        and asset.available
        and asset.source is not primary_provider
        and asset.source
        in UPGRADEABLE_FALLBACK_SOURCES
    )


def prefer_stored_or_primary_asset(
    stored: ArtworkAsset | None,
    live: ArtworkAsset | None,
    *,
    primary_provider: ArtworkSource,
) -> ArtworkAsset | None:
    """Merge one same-set artwork slot without destructive churn.

    Durable primary/curated/manual artwork wins normally.

    A live asset from the currently selected primary provider may replace
    a stored lower-priority fallback asset in the same slot.
    """

    stored_available = (
        stored is not None
        and stored.available
    )

    live_available = (
        live is not None
        and live.available
    )

    if stored_available:
        if (
            is_upgradeable_fallback_asset(
                stored,
                primary_provider=primary_provider,
            )
            and live_available
            and live.source
            is primary_provider
        ):
            return live

        return stored

    if live_available:
        return live

    return stored or live


def artwork_set_upgradeable_fallback_count(
    artwork_set: ArtworkSet,
) -> int:
    """Count fallback assets that could later upgrade to the set provider."""

    primary_provider = (
        artwork_set.provider
    )

    count = 0

    def inspect(
        asset: ArtworkAsset | None,
    ) -> None:
        nonlocal count

        if is_upgradeable_fallback_asset(
            asset,
            primary_provider=primary_provider,
        ):
            count += 1

    inspect(
        artwork_set.poster
    )
    inspect(
        artwork_set.background
    )

    for season in (
        artwork_set.seasons.values()
    ):
        inspect(
            season.poster
        )

        for episode in (
            season.episodes.values()
        ):
            inspect(
                episode.card
            )

    return count


def artwork_set_has_upgradeable_fallback(
    artwork_set: ArtworkSet,
) -> bool:
    """Whether a selected set still contains lower-priority fallback."""

    return (
        artwork_set_upgradeable_fallback_count(
            artwork_set
        )
        > 0
    )
