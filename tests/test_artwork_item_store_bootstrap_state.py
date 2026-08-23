from types import SimpleNamespace

import pytest

from artwork.item_store_bootstrap import (
    PersistedArtworkEvidence,
    ShowItemStoreBootstrapSeed,
)
from artwork.item_store_bootstrap_state import (
    ArtworkItemStoreStateBootstrapError,
    build_show_state_from_item_store_seed,
)
from artwork.kometa import (
    build_kometa_metadata,
)
from artwork.models import (
    ArtworkKind,
    ArtworkQuality,
    ArtworkSetSelection,
    ArtworkSource,
)


def _inventory(
    *,
    rating_key="10",
    tvdb_id=100,
):
    return SimpleNamespace(
        identity=SimpleNamespace(
            plex_rating_key=(
                rating_key
            ),
            title="Example Show",
            tvdb_id=tvdb_id,
            tmdb_id=200,
            imdb_id="tt0000200",
        )
    )


def _evidence(
    *,
    kind,
    source,
    url,
    provider_asset_id,
    season=None,
    episode=None,
):
    return PersistedArtworkEvidence(
        kind=kind,
        source=source,
        url=url,
        provider_asset_id=(
            provider_asset_id
        ),
        season_number=season,
        episode_number=episode,
    )


def _selection(
    set_id,
    creator,
):
    return ArtworkSetSelection(
        provider=ArtworkSource.MEDIUX,
        set_id=set_id,
        creator=creator,
    )


def test_reconstructs_mixed_current_store_state():
    seed = ShowItemStoreBootstrapSeed(
        plex_rating_key="10",
        tvdb_id=100,
        filename="example.yaml",
        assets=(
            _evidence(
                kind=(
                    ArtworkKind
                    .SHOW_POSTER
                ),
                source=(
                    ArtworkSource.MEDIUX
                ),
                url=(
                    "https://api.mediux.pro/"
                    "assets/show"
                ),
                provider_asset_id="show",
            ),
            _evidence(
                kind=(
                    ArtworkKind
                    .SEASON_POSTER
                ),
                source=(
                    ArtworkSource.MEDIUX
                ),
                url=(
                    "https://api.mediux.pro/"
                    "assets/season"
                ),
                provider_asset_id="season",
                season=1,
            ),
            _evidence(
                kind=(
                    ArtworkKind
                    .EPISODE_CARD
                ),
                source=(
                    ArtworkSource.MEDIUX
                ),
                url=(
                    "https://api.mediux.pro/"
                    "assets/e1"
                ),
                provider_asset_id="e1",
                season=1,
                episode=1,
            ),
            _evidence(
                kind=(
                    ArtworkKind
                    .EPISODE_CARD
                ),
                source=(
                    ArtworkSource.TMDB
                ),
                url=(
                    "https://image.tmdb.org/"
                    "t/p/original/still.jpg"
                ),
                provider_asset_id=(
                    "/still.jpg"
                ),
                season=1,
                episode=2,
            ),
        ),
    )

    episode = _selection(
        "EPISODES",
        "episode-user",
    )

    presentation = _selection(
        "PRESENTATION",
        "presentation-user",
    )

    state = (
        build_show_state_from_item_store_seed(
            seed=seed,
            inventory=_inventory(),
            episode_selection=episode,
            presentation_selection=(
                presentation
            ),
        )
    )

    assert state.title == "Example Show"
    assert state.tvdb_id == 100
    assert state.tmdb_id == 200
    assert state.imdb_id == "tt0000200"

    assert (
        state.selected_set_id
        == "EPISODES"
    )

    assert (
        state.episode_selection
        == episode
    )

    assert (
        state.presentation_selection
        == presentation
    )

    assert (
        state.poster.quality
        is ArtworkQuality.CURATED
    )

    tmdb = (
        state.seasons[
            1
        ].episodes[
            2
        ].card
    )

    assert (
        tmdb.source
        is ArtworkSource.TMDB
    )

    assert (
        tmdb.quality
        is ArtworkQuality.RAW_STILL
    )

    assert (
        tmdb.provider_asset_id
        == "/still.jpg"
    )

    assert (
        build_kometa_metadata(
            (state,)
        )
        == {
            "metadata": {
                100: {
                    "url_poster": (
                        "https://api.mediux.pro/"
                        "assets/show"
                    ),
                    "seasons": {
                        1: {
                            "url_poster": (
                                "https://api.mediux.pro/"
                                "assets/season"
                            ),
                            "episodes": {
                                1: {
                                    "url_poster": (
                                        "https://api.mediux.pro/"
                                        "assets/e1"
                                    ),
                                },
                                2: {
                                    "url_poster": (
                                        "https://image.tmdb.org/"
                                        "t/p/original/"
                                        "still.jpg"
                                    ),
                                },
                            },
                        },
                    },
                },
            },
        }
    )


def test_tmdb_only_state_has_no_set_context():
    seed = ShowItemStoreBootstrapSeed(
        plex_rating_key="10",
        tvdb_id=100,
        filename="example.yaml",
        assets=(
            _evidence(
                kind=(
                    ArtworkKind
                    .EPISODE_CARD
                ),
                source=(
                    ArtworkSource.TMDB
                ),
                url=(
                    "https://image.tmdb.org/"
                    "t/p/original/still.jpg"
                ),
                provider_asset_id=(
                    "/still.jpg"
                ),
                season=1,
                episode=1,
            ),
        ),
    )

    state = (
        build_show_state_from_item_store_seed(
            seed=seed,
            inventory=_inventory(),
        )
    )

    assert state.selected_set_id is None
    assert (
        state.selected_set_source
        is None
    )
    assert state.episode_selection is None
    assert (
        state.presentation_selection
        is None
    )


def test_presentation_only_selection_populates_legacy_fields():
    seed = ShowItemStoreBootstrapSeed(
        plex_rating_key="10",
        tvdb_id=100,
        filename="example.yaml",
        assets=(
            _evidence(
                kind=(
                    ArtworkKind
                    .SHOW_POSTER
                ),
                source=(
                    ArtworkSource.MEDIUX
                ),
                url=(
                    "https://api.mediux.pro/"
                    "assets/poster"
                ),
                provider_asset_id="poster",
            ),
        ),
    )

    presentation = _selection(
        "PRESENTATION",
        "creator",
    )

    state = (
        build_show_state_from_item_store_seed(
            seed=seed,
            inventory=_inventory(),
            presentation_selection=(
                presentation
            ),
        )
    )

    assert state.episode_selection is None

    assert (
        state.presentation_selection
        == presentation
    )

    assert (
        state.selected_set_id
        == "PRESENTATION"
    )

    assert (
        state.selected_set_source
        is ArtworkSource.MEDIUX
    )


def test_mediux_evidence_requires_recovered_selection():
    seed = ShowItemStoreBootstrapSeed(
        plex_rating_key="10",
        tvdb_id=100,
        filename="example.yaml",
        assets=(
            _evidence(
                kind=(
                    ArtworkKind
                    .EPISODE_CARD
                ),
                source=(
                    ArtworkSource.MEDIUX
                ),
                url=(
                    "https://api.mediux.pro/"
                    "assets/e1"
                ),
                provider_asset_id="e1",
                season=1,
                episode=1,
            ),
        ),
    )

    with pytest.raises(
        ArtworkItemStoreStateBootstrapError,
        match="no recovered",
    ):
        build_show_state_from_item_store_seed(
            seed=seed,
            inventory=_inventory(),
        )


def test_selection_without_family_evidence_is_rejected():
    seed = ShowItemStoreBootstrapSeed(
        plex_rating_key="10",
        tvdb_id=100,
        filename="example.yaml",
        assets=(),
    )

    with pytest.raises(
        ArtworkItemStoreStateBootstrapError,
        match="without persisted",
    ):
        build_show_state_from_item_store_seed(
            seed=seed,
            inventory=_inventory(),
            episode_selection=(
                _selection(
                    "EPISODES",
                    "creator",
                )
            ),
        )


def test_plex_identity_mismatch_blocks_state():
    seed = ShowItemStoreBootstrapSeed(
        plex_rating_key="10",
        tvdb_id=100,
        filename="example.yaml",
        assets=(),
    )

    with pytest.raises(
        ArtworkItemStoreStateBootstrapError,
        match="TVDB identity",
    ):
        build_show_state_from_item_store_seed(
            seed=seed,
            inventory=_inventory(
                tvdb_id=999,
            ),
        )
