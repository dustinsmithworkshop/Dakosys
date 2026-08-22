import json
from hashlib import sha256
from pathlib import Path

import pytest
import yaml

from artwork.item_store_bootstrap import (
    ArtworkItemStoreBootstrapError,
    load_show_item_store_bootstrap_seeds,
)
from artwork.models import (
    ArtworkKind,
    ArtworkSource,
)


def _write_store(
    tmp_path: Path,
    *,
    payload: dict,
    library: str = "TV",
    rating_key: str = "100",
    tvdb_id: int = 71489,
):
    directory = (
        tmp_path
        / "artwork-tv"
    )

    directory.mkdir()

    filename = (
        "example--tvdb-71489.yaml"
    )

    contents = yaml.safe_dump(
        payload,
        sort_keys=False,
    )

    path = (
        directory
        / filename
    )

    path.write_text(
        contents,
        encoding="utf-8",
    )

    digest = sha256(
        contents.encode(
            "utf-8"
        )
    ).hexdigest()

    manifest = {
        "schema_version": 1,
        "library": library,
        "items": {
            rating_key: {
                "tvdb_id": tvdb_id,
                "file": filename,
                "sha256": digest,
            },
        },
    }

    (
        directory
        / ".dakosys-manifest.json"
    ).write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    return (
        directory,
        path,
    )


def _mixed_payload():
    return {
        "metadata": {
            71489: {
                "url_poster": (
                    "https://api.mediux.pro/"
                    "assets/show-poster"
                ),
                "url_background": (
                    "https://api.mediux.pro/"
                    "assets/show-background"
                ),
                "seasons": {
                    1: {
                        "url_poster": (
                            "https://api.mediux.pro/"
                            "assets/season-poster"
                        ),
                        "episodes": {
                            1: {
                                "url_poster": (
                                    "https://image.tmdb.org/"
                                    "t/p/original/still.jpg"
                                ),
                            },
                            2: {
                                "url_poster": (
                                    "https://api.mediux.pro/"
                                    "assets/episode-card"
                                ),
                            },
                        },
                    },
                },
            },
        },
    }


def test_loads_mixed_mediux_and_tmdb_evidence(
    tmp_path,
):
    (
        directory,
        _,
    ) = _write_store(
        tmp_path,
        payload=_mixed_payload(),
    )

    seeds = (
        load_show_item_store_bootstrap_seeds(
            directory=directory,
            expected_library="TV",
        )
    )

    assert len(
        seeds
    ) == 1

    seed = seeds[0]

    assert seed.plex_rating_key == "100"
    assert seed.tvdb_id == 71489

    assert len(
        seed.assets
    ) == 5

    by_kind = {}

    for asset in seed.assets:
        by_kind.setdefault(
            asset.kind,
            [],
        ).append(
            asset
        )

    assert (
        by_kind[
            ArtworkKind.SHOW_POSTER
        ][0].source
        is ArtworkSource.MEDIUX
    )

    assert (
        by_kind[
            ArtworkKind.SHOW_BACKGROUND
        ][0].source
        is ArtworkSource.MEDIUX
    )

    assert (
        by_kind[
            ArtworkKind.SEASON_POSTER
        ][0].source
        is ArtworkSource.MEDIUX
    )

    cards = by_kind[
        ArtworkKind.EPISODE_CARD
    ]

    assert {
        card.source
        for card in cards
    } == {
        ArtworkSource.MEDIUX,
        ArtworkSource.TMDB,
    }

    assert (
        seed.mediux_presentation_asset_ids
        == {
            "show-poster",
            "show-background",
            "season-poster",
        }
    )

    assert (
        seed.mediux_episode_asset_ids
        == {
            "episode-card",
        }
    )


def test_manifest_hash_mismatch_blocks_bootstrap(
    tmp_path,
):
    (
        directory,
        path,
    ) = _write_store(
        tmp_path,
        payload=_mixed_payload(),
    )

    path.write_text(
        "metadata: {}\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ArtworkItemStoreBootstrapError,
        match="recorded hash",
    ):
        load_show_item_store_bootstrap_seeds(
            directory=directory,
            expected_library="TV",
        )


def test_unknown_provider_url_blocks_bootstrap(
    tmp_path,
):
    payload = {
        "metadata": {
            71489: {
                "url_poster": (
                    "https://example.invalid/"
                    "poster.jpg"
                ),
            },
        },
    }

    (
        directory,
        _,
    ) = _write_store(
        tmp_path,
        payload=payload,
    )

    with pytest.raises(
        ArtworkItemStoreBootstrapError,
        match="cannot safely infer",
    ):
        load_show_item_store_bootstrap_seeds(
            directory=directory,
            expected_library="TV",
        )


def test_local_file_poster_blocks_pre_state_bootstrap(
    tmp_path,
):
    payload = {
        "metadata": {
            71489: {
                "seasons": {
                    1: {
                        "episodes": {
                            1: {
                                "file_poster": (
                                    "/config/assets/"
                                    "generated.jpg"
                                ),
                            },
                        },
                    },
                },
            },
        },
    }

    (
        directory,
        _,
    ) = _write_store(
        tmp_path,
        payload=payload,
    )

    with pytest.raises(
        ArtworkItemStoreBootstrapError,
        match="file_poster",
    ):
        load_show_item_store_bootstrap_seeds(
            directory=directory,
            expected_library="TV",
        )


def test_missing_manifest_is_not_bootstrap_evidence(
    tmp_path,
):
    assert (
        load_show_item_store_bootstrap_seeds(
            directory=tmp_path,
            expected_library="TV",
        )
        == ()
    )
