import json

import pytest

from artwork.models import (
    ArtworkAsset,
    ArtworkKind,
    ArtworkQuality,
    ArtworkSource,
    MovieArtworkState,
    SelectionMode,
)
from artwork.movie_state_store import (
    build_movie_state_store,
    load_movie_state_store,
)
from artwork.state_store import (
    STATE_NAME,
    ArtworkStateStoreError,
    InvalidArtworkStateStoreError,
)


def _state():
    return MovieArtworkState(
        title="Blade Runner",
        tmdb_id=78,
        imdb_id="tt0083658",
        poster=ArtworkAsset(
            kind=(
                ArtworkKind.MOVIE_POSTER
            ),
            source=ArtworkSource.MEDIUX,
            provider_asset_id="poster-1",
            quality=ArtworkQuality.CURATED,
        ),
        background=ArtworkAsset(
            kind=(
                ArtworkKind.MOVIE_BACKGROUND
            ),
            source=ArtworkSource.MEDIUX,
            provider_asset_id="backdrop-1",
            quality=ArtworkQuality.CURATED,
        ),
        selected_set_id="set-1",
        selected_set_source=(
            ArtworkSource.MEDIUX
        ),
        selected_creator="creator",
        selection_mode=SelectionMode.AUTO,
    )


def test_movie_state_store_round_trip(
    tmp_path,
):
    store = build_movie_state_store(
        library="Movies",
        items=[
            (
                "123",
                _state(),
            ),
        ],
    )

    (
        tmp_path
        / STATE_NAME
    ).write_text(
        store.to_json(),
        encoding="utf-8",
    )

    loaded = load_movie_state_store(
        tmp_path,
        expected_library="Movies",
    )

    assert loaded is not None
    assert loaded.library == "Movies"
    assert len(loaded.items) == 1

    item = loaded.items[0]

    assert item.plex_rating_key == "123"
    assert item.state.title == "Blade Runner"
    assert item.state.tmdb_id == 78

    assert (
        item.state.poster.kind
        is ArtworkKind.MOVIE_POSTER
    )

    assert (
        item.state.background.kind
        is ArtworkKind.MOVIE_BACKGROUND
    )

    assert (
        item.state.selected_set_source
        is ArtworkSource.MEDIUX
    )


def test_movie_state_store_allows_no_external_id(
    tmp_path,
):
    state = MovieArtworkState(
        title="Unknown Movie",
    )

    store = build_movie_state_store(
        library="Movies",
        items=[
            (
                "7",
                state,
            ),
        ],
    )

    (
        tmp_path
        / STATE_NAME
    ).write_text(
        store.to_json(),
        encoding="utf-8",
    )

    loaded = load_movie_state_store(
        tmp_path,
        expected_library="Movies",
    )

    assert loaded is not None
    assert loaded.items[0].state.tmdb_id is None
    assert loaded.items[0].state.imdb_id is None


def test_movie_state_store_rejects_show_artwork_kind(
    tmp_path,
):
    raw = {
        "schema_version": 1,
        "media_type": "movie",
        "library": "Movies",
        "items": {
            "1": {
                "title": "Alien",
                "tmdb_id": 348,
                "imdb_id": "tt0078748",
                "poster": {
                    "kind": "show_poster",
                    "source": "mediux",
                    "url": None,
                    "provider_asset_id": "bad",
                    "quality": "curated",
                },
                "background": None,
                "selected_set_id": None,
                "selected_set_source": None,
                "selected_creator": None,
                "selection_mode": "auto",
            },
        },
    }

    (
        tmp_path
        / STATE_NAME
    ).write_text(
        json.dumps(
            raw
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        InvalidArtworkStateStoreError,
        match="wrong artwork kind",
    ):
        load_movie_state_store(
            tmp_path,
            expected_library="Movies",
        )


def test_movie_state_store_rejects_wrong_media_type(
    tmp_path,
):
    raw = {
        "schema_version": 1,
        "library": "Movies",
        "items": {},
    }

    (
        tmp_path
        / STATE_NAME
    ).write_text(
        json.dumps(
            raw
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        InvalidArtworkStateStoreError,
        match="not a movie state store",
    ):
        load_movie_state_store(
            tmp_path,
            expected_library="Movies",
        )


def test_movie_state_store_rejects_duplicate_plex_key():
    with pytest.raises(
        ArtworkStateStoreError,
        match="duplicate movie artwork",
    ):
        build_movie_state_store(
            library="Movies",
            items=[
                (
                    "5",
                    _state(),
                ),
                (
                    "5",
                    _state(),
                ),
            ],
        )


def test_movie_state_store_rejects_wrong_library(
    tmp_path,
):
    store = build_movie_state_store(
        library="Movies",
        items=[],
    )

    (
        tmp_path
        / STATE_NAME
    ).write_text(
        store.to_json(),
        encoding="utf-8",
    )

    with pytest.raises(
        InvalidArtworkStateStoreError,
        match="different library",
    ):
        load_movie_state_store(
            tmp_path,
            expected_library="Films",
        )
