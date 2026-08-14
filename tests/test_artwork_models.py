from artwork.models import (
    ArtworkAsset,
    ArtworkKind,
    ArtworkQuality,
    ArtworkSource,
    EpisodeArtwork,
    SeasonArtwork,
    ShowArtworkState,
)


def test_show_artwork_state_can_hold_episode_card():
    card = ArtworkAsset(
        kind=ArtworkKind.EPISODE_CARD,
        source=ArtworkSource.MEDIUX,
        url="https://example.test/card.jpg",
        quality=ArtworkQuality.CURATED,
    )

    episode = EpisodeArtwork(
        episode_number=1,
        card=card,
    )

    season = SeasonArtwork(
        season_number=1,
        episodes={1: episode},
    )

    show = ShowArtworkState(
        title="Example Show",
        tvdb_id=12345,
        seasons={1: season},
    )

    assert show.tvdb_id == 12345
    assert show.seasons[1].episodes[1].card is card
    assert (
        show.seasons[1]
        .episodes[1]
        .card.source
        is ArtworkSource.MEDIUX
    )
