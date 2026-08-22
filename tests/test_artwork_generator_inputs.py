import pytest

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
    SelectionMode,
)
from artwork.providers.tmdb import (
    TMDBEpisodeArtwork,
)


def _card(
    *,
    source,
    quality,
    url="https://example.test/card.jpg",
    provider_asset_id=None,
):
    return ArtworkAsset(
        kind=ArtworkKind.EPISODE_CARD,
        source=source,
        quality=quality,
        url=url,
        provider_asset_id=(
            provider_asset_id
        ),
    )


def _plex(
    *,
    episode_number=1,
    title="Plex Episode Title",
    thumb="/library/metadata/123/thumb/456",
):
    return EpisodeInventory(
        episode_number=episode_number,
        title=title,
        plex_thumb=thumb,
    )


def _tmdb(
    *,
    episode_number=1,
    title="TMDB Episode Title",
    still=True,
):
    card = None

    if still:
        card = _card(
            source=ArtworkSource.TMDB,
            quality=ArtworkQuality.RAW_STILL,
            url=(
                "https://image.tmdb.org/"
                "t/p/original/still.jpg"
            ),
            provider_asset_id=(
                "/still.jpg"
            ),
        )

    return TMDBEpisodeArtwork(
        episode_number=episode_number,
        title=title,
        card=card,
    )


def test_missing_card_generates_from_tmdb_still_with_plex_title():
    result = (
        resolve_episode_generation_input(
            episode_number=1,
            plex_episode=_plex(),
            tmdb_episode=_tmdb(),
            current_card=None,
        )
    )

    assert (
        result.path
        is EpisodeGenerationPath
        .GENERATE_MISSING
    )
    assert result.should_generate

    assert (
        result.title
        == "Plex Episode Title"
    )
    assert (
        result.title_source
        is ArtworkSource.PLEX
    )

    assert (
        result.image_source
        is ArtworkSource.TMDB
    )
    assert result.image_ref == (
        "https://image.tmdb.org/"
        "t/p/original/still.jpg"
    )
    assert (
        result.image_provider_asset_id
        == "/still.jpg"
    )


def test_tmdb_still_is_preferred_over_plex_thumbnail():
    result = (
        resolve_episode_generation_input(
            episode_number=1,
            plex_episode=_plex(
                thumb=(
                    "/library/metadata/"
                    "123/thumb/456"
                )
            ),
            tmdb_episode=_tmdb(
                still=True
            ),
            current_card=None,
        )
    )

    assert (
        result.image_source
        is ArtworkSource.TMDB
    )


def test_plex_thumbnail_is_used_when_tmdb_has_no_still():
    result = (
        resolve_episode_generation_input(
            episode_number=1,
            plex_episode=_plex(
                thumb=(
                    "/library/metadata/"
                    "123/thumb/456"
                )
            ),
            tmdb_episode=_tmdb(
                still=False
            ),
            current_card=None,
        )
    )

    assert result.should_generate
    assert (
        result.image_source
        is ArtworkSource.PLEX
    )
    assert result.image_ref == (
        "/library/metadata/123/thumb/456"
    )


def test_tmdb_title_is_fallback_when_plex_title_missing():
    result = (
        resolve_episode_generation_input(
            episode_number=1,
            plex_episode=_plex(
                title=None
            ),
            tmdb_episode=_tmdb(
                title="TMDB Fallback Title"
            ),
            current_card=None,
        )
    )

    assert result.should_generate
    assert (
        result.title
        == "TMDB Fallback Title"
    )
    assert (
        result.title_source
        is ArtworkSource.TMDB
    )


def test_existing_mediux_card_is_never_replaced():
    current = _card(
        source=ArtworkSource.MEDIUX,
        quality=ArtworkQuality.CURATED,
    )

    result = (
        resolve_episode_generation_input(
            episode_number=1,
            plex_episode=_plex(),
            tmdb_episode=_tmdb(),
            current_card=current,
        )
    )

    assert (
        result.path
        is EpisodeGenerationPath
        .KEEP_PRIMARY
    )
    assert not result.should_generate


def test_any_curated_card_is_never_replaced():
    current = _card(
        source=ArtworkSource.TMDB,
        quality=ArtworkQuality.CURATED,
    )

    result = (
        resolve_episode_generation_input(
            episode_number=1,
            plex_episode=_plex(),
            tmdb_episode=_tmdb(),
            current_card=current,
        )
    )

    assert (
        result.path
        is EpisodeGenerationPath
        .KEEP_PRIMARY
    )
    assert not result.should_generate


def test_existing_generated_card_is_reevaluated():
    current = _card(
        source=ArtworkSource.GENERATED,
        quality=ArtworkQuality.GENERATED,
    )

    result = (
        resolve_episode_generation_input(
            episode_number=1,
            plex_episode=_plex(),
            tmdb_episode=_tmdb(),
            current_card=current,
        )
    )

    assert (
        result.path
        is EpisodeGenerationPath
        .REFRESH_GENERATED
    )
    assert result.should_generate


def test_existing_generated_card_is_kept_when_source_is_unavailable():
    current = _card(
        source=ArtworkSource.GENERATED,
        quality=ArtworkQuality.GENERATED,
    )

    result = (
        resolve_episode_generation_input(
            episode_number=1,
            plex_episode=_plex(
                thumb=None
            ),
            tmdb_episode=_tmdb(
                still=False
            ),
            current_card=current,
        )
    )

    assert (
        result.path
        is EpisodeGenerationPath
        .KEEP_GENERATED
    )
    assert not result.should_generate


def test_existing_generated_card_is_kept_when_title_is_unavailable():
    current = _card(
        source=ArtworkSource.GENERATED,
        quality=ArtworkQuality.GENERATED,
    )

    result = (
        resolve_episode_generation_input(
            episode_number=1,
            plex_episode=_plex(
                title=None
            ),
            tmdb_episode=_tmdb(
                title=None
            ),
            current_card=current,
        )
    )

    assert (
        result.path
        is EpisodeGenerationPath
        .KEEP_GENERATED
    )
    assert not result.should_generate


def test_existing_tmdb_raw_still_is_eligible_for_upgrade():
    current = _card(
        source=ArtworkSource.TMDB,
        quality=ArtworkQuality.RAW_STILL,
        url=(
            "https://image.tmdb.org/"
            "t/p/original/old.jpg"
        ),
        provider_asset_id="/old.jpg",
    )

    result = (
        resolve_episode_generation_input(
            episode_number=1,
            plex_episode=_plex(),
            tmdb_episode=_tmdb(),
            current_card=current,
        )
    )

    assert (
        result.path
        is EpisodeGenerationPath
        .UPGRADE_FALLBACK
    )
    assert result.should_generate
    assert (
        result.image_source
        is ArtworkSource.TMDB
    )


def test_existing_tmdb_fallback_can_supply_source_image():
    current = _card(
        source=ArtworkSource.TMDB,
        quality=ArtworkQuality.RAW_STILL,
        url=(
            "https://image.tmdb.org/"
            "t/p/original/existing.jpg"
        ),
        provider_asset_id=(
            "/existing.jpg"
        ),
    )

    result = (
        resolve_episode_generation_input(
            episode_number=1,
            plex_episode=_plex(),
            tmdb_episode=_tmdb(
                still=False
            ),
            current_card=current,
        )
    )

    assert result.should_generate
    assert (
        result.image_source
        is ArtworkSource.TMDB
    )
    assert result.image_ref == (
        "https://image.tmdb.org/"
        "t/p/original/existing.jpg"
    )


def test_locked_state_is_never_generated():
    result = (
        resolve_episode_generation_input(
            episode_number=1,
            plex_episode=_plex(),
            tmdb_episode=_tmdb(),
            current_card=None,
            selection_mode=(
                SelectionMode.LOCKED
            ),
        )
    )

    assert (
        result.path
        is EpisodeGenerationPath.LOCKED
    )
    assert not result.should_generate


def test_missing_title_preserves_raw_fallback():
    result = (
        resolve_episode_generation_input(
            episode_number=1,
            plex_episode=_plex(
                title=None
            ),
            tmdb_episode=_tmdb(
                title=None
            ),
            current_card=None,
        )
    )

    assert (
        result.path
        is EpisodeGenerationPath.NO_TITLE
    )
    assert not result.should_generate


def test_missing_tmdb_and_plex_image_cannot_generate():
    result = (
        resolve_episode_generation_input(
            episode_number=1,
            plex_episode=_plex(
                thumb=None
            ),
            tmdb_episode=_tmdb(
                still=False
            ),
            current_card=None,
        )
    )

    assert (
        result.path
        is EpisodeGenerationPath
        .NO_SOURCE_IMAGE
    )
    assert not result.should_generate


def test_episode_identity_mismatch_is_rejected():
    with pytest.raises(
        ValueError,
        match="Plex episode number",
    ):
        resolve_episode_generation_input(
            episode_number=1,
            plex_episode=_plex(
                episode_number=2
            ),
            tmdb_episode=None,
            current_card=None,
        )
