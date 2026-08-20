import yaml
import pytest

from artwork.item_store import (
    MANIFEST_NAME,
    ItemStoreCollisionError,
    ItemStoreError,
)
from artwork.models import (
    ArtworkAsset,
    ArtworkKind,
    ArtworkQuality,
    ArtworkSource,
    MovieArtworkState,
)
from artwork.movie_inventory import (
    MovieIdentity,
    MovieInventory,
)
from artwork.movie_item_store import (
    build_movie_item_store_plan,
    load_movie_item_store_manifest,
    movie_item_filename,
)
from artwork.movie_kometa import (
    build_movie_kometa_metadata,
    render_movie_kometa_metadata,
)
from artwork.state_store import (
    STATE_NAME,
)


def _inventory(
    *,
    title="Blade Runner",
    rating_key="123",
    tmdb_id=78,
    imdb_id="tt0083658",
):
    return MovieInventory(
        identity=MovieIdentity(
            title=title,
            year=1982,
            library="Movies",
            plex_rating_key=(
                rating_key
            ),
            tmdb_id=tmdb_id,
            imdb_id=imdb_id,
        )
    )


def _state(
    *,
    tmdb_id=78,
    imdb_id="tt0083658",
):
    return MovieArtworkState(
        title="Blade Runner",
        tmdb_id=tmdb_id,
        imdb_id=imdb_id,
        poster=ArtworkAsset(
            kind=(
                ArtworkKind
                .MOVIE_POSTER
            ),
            source=(
                ArtworkSource.MEDIUX
            ),
            url=(
                "https://example/"
                "poster.jpg"
            ),
            provider_asset_id=(
                "poster-1"
            ),
            quality=(
                ArtworkQuality.CURATED
            ),
        ),
        background=ArtworkAsset(
            kind=(
                ArtworkKind
                .MOVIE_BACKGROUND
            ),
            source=(
                ArtworkSource.MEDIUX
            ),
            url=(
                "https://example/"
                "background.jpg"
            ),
            provider_asset_id=(
                "background-1"
            ),
            quality=(
                ArtworkQuality.CURATED
            ),
        ),
    )


def test_movie_kometa_uses_tmdb_mapping():
    data = (
        build_movie_kometa_metadata(
            [
                _state()
            ]
        )
    )

    assert data == {
        "metadata": {
            78: {
                "url_poster": (
                    "https://example/"
                    "poster.jpg"
                ),
                "url_background": (
                    "https://example/"
                    "background.jpg"
                ),
            }
        }
    }

    rendered = (
        render_movie_kometa_metadata(
            [
                _state()
            ]
        )
    )

    assert (
        yaml.safe_load(
            rendered
        )
        == data
    )


def test_movie_kometa_uses_imdb_fallback():
    state = _state(
        tmdb_id=None,
        imdb_id="TT0083658",
    )

    data = (
        build_movie_kometa_metadata(
            [
                state
            ]
        )
    )

    assert (
        "tt0083658"
        in data["metadata"]
    )


def test_movie_item_filename():
    assert (
        movie_item_filename(
            title="Blade Runner",
            tmdb_id=78,
            imdb_id="tt0083658",
        )
        == (
            "blade-runner"
            "--tmdb-78.yaml"
        )
    )

    assert (
        movie_item_filename(
            title="Alien",
            imdb_id="tt0078748",
        )
        == (
            "alien"
            "--imdb-tt0078748.yaml"
        )
    )


def test_movie_manifest_round_trip(
    tmp_path,
):
    plan = (
        build_movie_item_store_plan(
            library="Movies",
            directory=tmp_path,
            items=[
                (
                    _inventory(),
                    _state(),
                )
            ],
        )
    )

    (
        tmp_path
        / MANIFEST_NAME
    ).write_text(
        plan.manifest.to_json(),
        encoding="utf-8",
    )

    loaded = (
        load_movie_item_store_manifest(
            tmp_path,
            expected_library="Movies",
        )
    )

    assert loaded is not None
    assert len(loaded.items) == 1

    entry = loaded.items[0]

    assert (
        entry.plex_rating_key
        == "123"
    )

    assert entry.mapping_id == 78

    assert (
        entry.filename
        == (
            "blade-runner"
            "--tmdb-78.yaml"
        )
    )


def test_movie_item_store_initial_plan(
    tmp_path,
):
    plan = (
        build_movie_item_store_plan(
            library="Movies",
            directory=tmp_path,
            items=[
                (
                    _inventory(),
                    _state(),
                )
            ],
        )
    )

    assert plan.desired_count == 1
    assert plan.added_count == 1
    assert plan.updated_count == 0
    assert plan.unchanged_count == 0
    assert plan.removed_count == 0

    assert (
        plan.added
        == (
            "blade-runner"
            "--tmdb-78.yaml",
        )
    )

    assert (
        plan.state_store
        .items[0]
        .plex_rating_key
        == "123"
    )


def test_movie_item_store_detects_unchanged(
    tmp_path,
):
    inventory = _inventory()
    state = _state()

    first = (
        build_movie_item_store_plan(
            library="Movies",
            directory=tmp_path,
            items=[
                (
                    inventory,
                    state,
                )
            ],
        )
    )

    for item in first.files:
        (
            tmp_path
            / item.filename
        ).write_text(
            item.contents,
            encoding="utf-8",
        )

    (
        tmp_path
        / MANIFEST_NAME
    ).write_text(
        first.manifest.to_json(),
        encoding="utf-8",
    )

    (
        tmp_path
        / STATE_NAME
    ).write_text(
        first.state_store.to_json(),
        encoding="utf-8",
    )

    second = (
        build_movie_item_store_plan(
            library="Movies",
            directory=tmp_path,
            items=[
                (
                    inventory,
                    state,
                )
            ],
        )
    )

    assert second.added_count == 0
    assert second.updated_count == 0
    assert second.unchanged_count == 1
    assert second.removed_count == 0


def test_movie_item_store_blocks_unowned_collision(
    tmp_path,
):
    filename = (
        "blade-runner"
        "--tmdb-78.yaml"
    )

    (
        tmp_path
        / filename
    ).write_text(
        "unowned\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ItemStoreCollisionError,
        match="unowned movie",
    ):
        build_movie_item_store_plan(
            library="Movies",
            directory=tmp_path,
            items=[
                (
                    _inventory(),
                    _state(),
                )
            ],
        )


def test_movie_item_store_requires_external_identity(
    tmp_path,
):
    with pytest.raises(
        ItemStoreError,
        match="lacks TMDB/IMDb identity",
    ):
        build_movie_item_store_plan(
            library="Movies",
            directory=tmp_path,
            items=[
                (
                    _inventory(
                        tmdb_id=None,
                        imdb_id=None,
                    ),
                    _state(
                        tmdb_id=None,
                        imdb_id=None,
                    ),
                )
            ],
        )
