from types import SimpleNamespace

from artwork.inventory import (
    SeasonInventory,
    ShowInventory,
)
from artwork.models import (
    ArtworkAsset,
    ArtworkKind,
    ArtworkQuality,
    ArtworkSource,
    EpisodeArtwork,
    SeasonArtwork,
    ShowArtworkState,
)
from artwork.projection import (
    project_show_state_to_inventory,
    project_show_target_states,
)


def _card(
    asset_id,
):
    return ArtworkAsset(
        kind=ArtworkKind.EPISODE_CARD,
        source=ArtworkSource.MEDIUX,
        url=(
            "https://example/"
            f"{asset_id}.jpg"
        ),
        provider_asset_id=asset_id,
        quality=ArtworkQuality.CURATED,
    )


def _season_poster():
    return ArtworkAsset(
        kind=ArtworkKind.SEASON_POSTER,
        source=ArtworkSource.MEDIUX,
        url="https://example/season.jpg",
        provider_asset_id="season",
        quality=ArtworkQuality.CURATED,
    )


def _inventory():
    return ShowInventory(
        identity=SimpleNamespace(
            library="TV",
            plex_rating_key="1",
            title="Example",
            tvdb_id=100,
        ),
        seasons=(
            SeasonInventory(
                season_number=1,
                episode_numbers=frozenset(
                    {
                        1,
                        3,
                    }
                ),
            ),
            SeasonInventory(
                season_number=2,
                episode_numbers=frozenset(
                    {
                        1,
                    }
                ),
            ),
        ),
    )


def _state():
    return ShowArtworkState(
        title="Example",
        tvdb_id=100,
        seasons={
            0: SeasonArtwork(
                season_number=0,
                episodes={
                    1: EpisodeArtwork(
                        episode_number=1,
                        card=_card(
                            "special"
                        ),
                    ),
                },
            ),
            1: SeasonArtwork(
                season_number=1,
                poster=_season_poster(),
                episodes={
                    1: EpisodeArtwork(
                        episode_number=1,
                        card=_card(
                            "s1e1"
                        ),
                    ),
                    2: EpisodeArtwork(
                        episode_number=2,
                        card=_card(
                            "provider-extra"
                        ),
                    ),
                    3: EpisodeArtwork(
                        episode_number=3,
                        card=_card(
                            "s1e3"
                        ),
                    ),
                },
            ),
            2: SeasonArtwork(
                season_number=2,
                poster=_season_poster(),
                episodes={},
            ),
            3: SeasonArtwork(
                season_number=3,
                poster=_season_poster(),
                episodes={
                    1: EpisodeArtwork(
                        episode_number=1,
                        card=_card(
                            "provider-season"
                        ),
                    ),
                },
            ),
        },
    )


def test_projection_drops_provider_only_seasons():
    projected = (
        project_show_state_to_inventory(
            inventory=_inventory(),
            state=_state(),
        )
    )

    assert set(
        projected.seasons
    ) == {
        1,
        2,
    }


def test_projection_drops_provider_only_episode_numbers():
    projected = (
        project_show_state_to_inventory(
            inventory=_inventory(),
            state=_state(),
        )
    )

    assert set(
        projected
        .seasons[1]
        .episodes
    ) == {
        1,
        3,
    }


def test_projection_preserves_current_season_poster_without_cards():
    projected = (
        project_show_state_to_inventory(
            inventory=_inventory(),
            state=_state(),
        )
    )

    season = (
        projected.seasons[2]
    )

    assert season.poster is not None
    assert season.poster.available
    assert season.episodes == {}


def test_projection_does_not_mutate_input_state():
    state = _state()

    projected = (
        project_show_state_to_inventory(
            inventory=_inventory(),
            state=state,
        )
    )

    assert set(
        state.seasons
    ) == {
        0,
        1,
        2,
        3,
    }

    assert set(
        state
        .seasons[1]
        .episodes
    ) == {
        1,
        2,
        3,
    }

    assert projected is not state


def test_target_projection_uses_resolved_inventory_pairs():
    inventory = _inventory()
    state = _state()

    result = SimpleNamespace(
        inventory=inventory,
        state=state,
    )

    execution = SimpleNamespace(
        coverage_enabled=True,
        managed_coverage=(
            result,
        ),
        discovery_coverage=(),
    )

    projected = (
        project_show_target_states(
            execution
        )
    )

    assert len(projected) == 1

    assert set(
        projected[0].seasons
    ) == {
        1,
        2,
    }

    assert set(
        projected[0]
        .seasons[1]
        .episodes
    ) == {
        1,
        3,
    }


def test_projection_drops_empty_current_plex_season():
    inventory = ShowInventory(
        identity=SimpleNamespace(
            library="Anime",
            plex_rating_key="135795",
            title="Example",
            tvdb_id=100,
        ),
        seasons=(
            SeasonInventory(
                season_number=0,
                episode_numbers=frozenset(
                    {
                        1,
                    }
                ),
            ),
            SeasonInventory(
                season_number=1,
                episode_numbers=frozenset(
                    {
                        1,
                    }
                ),
            ),
        ),
    )

    state = ShowArtworkState(
        title="Example",
        tvdb_id=100,
        seasons={
            0: SeasonArtwork(
                season_number=0,
                poster=None,
                episodes={},
            ),
            1: SeasonArtwork(
                season_number=1,
                episodes={
                    1: EpisodeArtwork(
                        episode_number=1,
                        card=_card(
                            "s1e1"
                        ),
                    ),
                },
            ),
        },
    )

    projected = (
        project_show_state_to_inventory(
            inventory=inventory,
            state=state,
        )
    )

    assert set(
        projected.seasons
    ) == {
        1,
    }

    assert (
        projected
        .seasons[1]
        .episodes[1]
        .card
        .available
    )
