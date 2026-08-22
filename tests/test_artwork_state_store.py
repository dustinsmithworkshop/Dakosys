from pathlib import Path
from types import SimpleNamespace

import json
import pytest

from artwork.inventory import (
    SeasonInventory,
    ShowInventory,
)
from artwork.models import (
    ArtworkAsset,
    ArtworkKind,
    ArtworkQuality,
    ArtworkSetSelection,
    ArtworkSource,
    EpisodeArtwork,
    SeasonArtwork,
    SelectionMode,
    ShowArtworkState,
)
from artwork.state_store import (
    STATE_NAME,
    InvalidArtworkStateStoreError,
    build_show_state_store,
    load_show_state_store,
)
from artwork.targets import (
    ArtworkTarget,
    MediaType,
)


def _asset(
    kind,
    asset_id,
):
    return ArtworkAsset(
        kind=kind,
        source=ArtworkSource.MEDIUX,
        url=(
            "https://api.mediux.pro/assets/"
            f"{asset_id}"
        ),
        provider_asset_id=asset_id,
        quality=ArtworkQuality.CURATED,
    )


def _execution(
    tmp_path,
):
    target = ArtworkTarget(
        name="TV",
        library="TV",
        media_type=MediaType.SHOW,
        output_path=(
            tmp_path
            / "artwork-tv"
        ),
    )

    inventory = ShowInventory(
        identity=SimpleNamespace(
            library="TV",
            plex_rating_key="12345",
            title="Example Show",
            tvdb_id=100,
        ),
        seasons=(
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

    selection = ArtworkSetSelection(
        provider=ArtworkSource.MEDIUX,
        set_id="9001",
        creator="Example Creator",
        mode=SelectionMode.AUTO,
    )

    state = ShowArtworkState(
        title="Example Show",
        tvdb_id=100,
        tmdb_id=200,
        imdb_id="tt1234567",
        poster=_asset(
            ArtworkKind.SHOW_POSTER,
            "poster",
        ),
        background=_asset(
            ArtworkKind.SHOW_BACKGROUND,
            "background",
        ),
        seasons={
            1: SeasonArtwork(
                season_number=1,
                poster=_asset(
                    ArtworkKind.SEASON_POSTER,
                    "season",
                ),
                episodes={
                    1: EpisodeArtwork(
                        episode_number=1,
                        card=_asset(
                            ArtworkKind.EPISODE_CARD,
                            "episode",
                        ),
                    ),
                },
            ),
        },
        selected_set_id="9001",
        selected_set_source=ArtworkSource.MEDIUX,
        selected_creator="Example Creator",
        selection_mode=SelectionMode.AUTO,
        episode_selection=selection,
        presentation_selection=selection,
    )

    result = SimpleNamespace(
        inventory=inventory,
        state=state,
    )

    return SimpleNamespace(
        reconciliation=SimpleNamespace(
            target=target,
        ),
        coverage_enabled=True,
        managed_coverage=(
            result,
        ),
        discovery_coverage=(),
    )


def test_state_store_round_trip_preserves_provenance(
    tmp_path,
):
    execution = _execution(
        tmp_path
    )

    store = build_show_state_store(
        execution
    )

    assert store.library == "TV"
    assert len(store.items) == 1

    document = json.loads(
        store.to_json()
    )

    assert document[
        "schema_version"
    ] == 2

    assert document[
        "items"
    ][
        "12345"
    ][
        "selected_set_id"
    ] == "9001"

    assert document[
        "items"
    ][
        "12345"
    ][
        "episode_selection"
    ][
        "provider"
    ] == "mediux"

    directory = (
        tmp_path
        / "artwork-tv"
    )

    directory.mkdir()

    (
        directory
        / STATE_NAME
    ).write_text(
        store.to_json(),
        encoding="utf-8",
    )

    loaded = load_show_state_store(
        directory,
        expected_library="TV",
    )

    assert loaded is not None
    assert loaded == store


def test_state_store_is_deterministic(
    tmp_path,
):
    execution = _execution(
        tmp_path
    )

    first = build_show_state_store(
        execution
    ).to_json()

    second = build_show_state_store(
        execution
    ).to_json()

    assert first == second


def test_wrong_library_state_is_rejected(
    tmp_path,
):
    execution = _execution(
        tmp_path
    )

    store = build_show_state_store(
        execution
    )

    document = json.loads(
        store.to_json()
    )

    document["library"] = "Anime"

    directory = (
        tmp_path
        / "artwork-tv"
    )

    directory.mkdir()

    (
        directory
        / STATE_NAME
    ).write_text(
        json.dumps(
            document
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        InvalidArtworkStateStoreError,
        match="different library",
    ):
        load_show_state_store(
            directory,
            expected_library="TV",
        )


def test_corrupt_state_is_rejected(
    tmp_path,
):
    directory = (
        tmp_path
        / "artwork-tv"
    )

    directory.mkdir()

    (
        directory
        / STATE_NAME
    ).write_text(
        "{not json",
        encoding="utf-8",
    )

    with pytest.raises(
        InvalidArtworkStateStoreError,
        match="could not read",
    ):
        load_show_state_store(
            directory,
            expected_library="TV",
        )


def test_state_store_reads_legacy_schema_v1(
    tmp_path,
):
    execution = _execution(
        tmp_path
    )

    store = build_show_state_store(
        execution
    )

    document = store.to_dict()

    document[
        "schema_version"
    ] = 1

    def remove_file_path(value):
        if isinstance(
            value,
            dict,
        ):
            value.pop(
                "file_path",
                None,
            )

            for child in value.values():
                remove_file_path(
                    child
                )

        elif isinstance(
            value,
            list,
        ):
            for child in value:
                remove_file_path(
                    child
                )

    remove_file_path(
        document
    )

    directory = (
        tmp_path
        / "artwork-tv"
    )

    directory.mkdir()

    (
        directory
        / STATE_NAME
    ).write_text(
        json.dumps(
            document
        ),
        encoding="utf-8",
    )

    loaded = load_show_state_store(
        directory,
        expected_library="TV",
    )

    assert loaded is not None

    card = (
        loaded
        .items[0]
        .state
        .seasons[1]
        .episodes[1]
        .card
    )

    assert card is not None
    assert card.file_path is None


def test_state_store_preserves_generated_file_path(
    tmp_path,
):
    execution = _execution(
        tmp_path
    )

    state = (
        execution
        .managed_coverage[0]
        .state
    )

    state.seasons[
        1
    ].episodes[
        1
    ].card = ArtworkAsset(
        kind=(
            ArtworkKind
            .EPISODE_CARD
        ),
        source=(
            ArtworkSource
            .GENERATED
        ),
        provider_asset_id=(
            "generated-fingerprint"
        ),
        quality=(
            ArtworkQuality
            .GENERATED
        ),
        file_path=(
            "/config/assets/"
            "generated/tv/"
            "tmdb-200/"
            "season-01/"
            "S01E01-test.jpg"
        ),
    )

    store = build_show_state_store(
        execution
    )

    directory = (
        tmp_path
        / "artwork-tv"
    )

    directory.mkdir()

    (
        directory
        / STATE_NAME
    ).write_text(
        store.to_json(),
        encoding="utf-8",
    )

    loaded = load_show_state_store(
        directory,
        expected_library="TV",
    )

    assert loaded is not None

    card = (
        loaded
        .items[0]
        .state
        .seasons[1]
        .episodes[1]
        .card
    )

    assert card is not None

    assert card.file_path == (
        "/config/assets/"
        "generated/tv/"
        "tmdb-200/"
        "season-01/"
        "S01E01-test.jpg"
    )

    assert card.available
