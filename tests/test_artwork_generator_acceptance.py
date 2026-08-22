"""Cross-boundary acceptance semantics for Artwork Generator 3.1."""

from artwork.generator_inputs import (
    EpisodeGenerationPath,
    resolve_episode_generation_input,
)
from artwork.inventory import (
    EpisodeInventory,
)
from artwork.models import (
    ArtworkAsset,
    ArtworkKind,
    ArtworkQuality,
    ArtworkSource,
)
from artwork.providers.tmdb import (
    TMDBEpisodeArtwork,
)
from artwork.source_policy import (
    prefer_stored_or_primary_asset,
)


def _card(
    *,
    source: ArtworkSource,
    identifier: str,
    quality: ArtworkQuality,
) -> ArtworkAsset:
    return ArtworkAsset(
        kind=ArtworkKind.EPISODE_CARD,
        source=source,
        url=(
            "https://example.test/"
            f"{identifier}.jpg"
        ),
        provider_asset_id=identifier,
        quality=quality,
    )


def test_manual_episode_artwork_is_never_replaced_by_generator():
    manual = _card(
        source=ArtworkSource.MANUAL,
        identifier="manual",
        quality=ArtworkQuality.EXISTING,
    )

    plex_episode = EpisodeInventory(
        episode_number=1,
        title="Pilot",
        plex_thumb=(
            "/library/metadata/"
            "100/episode/1/thumb"
        ),
    )

    tmdb_episode = TMDBEpisodeArtwork(
        episode_number=1,
        title="TMDB Pilot",
        card=_card(
            source=ArtworkSource.TMDB,
            identifier="tmdb-still",
            quality=ArtworkQuality.RAW_STILL,
        ),
    )

    result = (
        resolve_episode_generation_input(
            episode_number=1,
            plex_episode=plex_episode,
            tmdb_episode=tmdb_episode,
            current_card=manual,
        )
    )

    assert (
        result.path
        is EpisodeGenerationPath.KEEP_PRIMARY
    )

    assert not result.should_generate
    assert result.current_card is manual


def test_generated_episode_card_upgrades_when_mediux_later_appears():
    generated = _card(
        source=ArtworkSource.GENERATED,
        identifier="generated",
        quality=ArtworkQuality.GENERATED,
    )

    mediux = _card(
        source=ArtworkSource.MEDIUX,
        identifier="mediux",
        quality=ArtworkQuality.CURATED,
    )

    selected = (
        prefer_stored_or_primary_asset(
            generated,
            mediux,
            primary_provider=(
                ArtworkSource.MEDIUX
            ),
        )
    )

    assert selected is mediux
    assert (
        selected.source
        is ArtworkSource.MEDIUX
    )
