from pathlib import Path
from types import SimpleNamespace

import json
import pytest
import yaml

from artwork.inventory import (
    SeasonInventory,
    ShowInventory,
)
from artwork.item_store import (
    MANIFEST_NAME,
    InvalidItemStoreManifestError,
    ItemStoreCollisionError,
    build_show_item_store_plan,
    format_item_store_plan,
    item_store_directory_for_target,
    show_item_filename,
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
from artwork.targets import (
    ArtworkTarget,
    MediaType,
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


def _inventory(
    rating_key,
    tvdb_id,
):
    return ShowInventory(
        identity=SimpleNamespace(
            library="TV",
            plex_rating_key=rating_key,
            title=(
                f"Show {rating_key}"
            ),
            tvdb_id=tvdb_id,
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


def _state(
    tvdb_id,
    asset_id,
):
    return ShowArtworkState(
        title=f"TVDB {tvdb_id}",
        tvdb_id=tvdb_id,
        seasons={
            1: SeasonArtwork(
                season_number=1,
                episodes={
                    1: EpisodeArtwork(
                        episode_number=1,
                        card=_card(
                            asset_id
                        ),
                    ),
                },
            ),
        },
    )


def _target():
    return ArtworkTarget(
        name="TV",
        library="TV",
        media_type=MediaType.SHOW,
        output_path=Path(
            "/kometa/metadata/"
            "artwork-tv.yaml"
        ),
    )


def _execution(
    items,
):
    results = tuple(
        SimpleNamespace(
            inventory=inventory,
            state=state,
        )
        for (
            inventory,
            state,
        ) in items
    )

    return SimpleNamespace(
        reconciliation=(
            SimpleNamespace(
                target=_target(),
            )
        ),
        coverage_enabled=True,
        managed_coverage=results,
        discovery_coverage=(),
    )


def _two_show_execution():
    return _execution(
        (
            (
                _inventory(
                    "1",
                    100,
                ),
                _state(
                    100,
                    "one",
                ),
            ),
            (
                _inventory(
                    "2",
                    200,
                ),
                _state(
                    200,
                    "two",
                ),
            ),
        )
    )


def _write_plan(
    plan,
):
    plan.directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    for item in plan.files:
        (
            plan.directory
            / item.filename
        ).write_text(
            item.contents,
            encoding="utf-8",
        )

    (
        plan.directory
        / MANIFEST_NAME
    ).write_text(
        plan.manifest.to_json(),
        encoding="utf-8",
    )


def test_item_store_directory_derives_from_target_yaml():
    assert (
        item_store_directory_for_target(
            _target()
        )
        == Path(
            "/kometa/metadata/"
            "artwork-tv"
        )
    )


def test_new_store_plans_one_file_per_show(
    tmp_path,
):
    plan = (
        build_show_item_store_plan(
            _two_show_execution(),
            directory=(
                tmp_path
                / "artwork-tv"
            ),
        )
    )

    assert (
        plan.desired_count
        == 2
    )

    assert set(
        plan.added
    ) == {
        "show-1--tvdb-100.yaml",
        "show-2--tvdb-200.yaml",
    }

    assert plan.updated == ()
    assert plan.unchanged == ()
    assert plan.removed == ()

    assert {
        item.filename
        for item in plan.files
    } == {
        "show-1--tvdb-100.yaml",
        "show-2--tvdb-200.yaml",
    }

    for item in plan.files:
        document = yaml.safe_load(
            item.contents
        )

        assert set(
            document["metadata"]
        ) == {
            item.tvdb_id,
        }


def test_manifest_is_deterministic_and_keyed_by_plex_identity(
    tmp_path,
):
    plan = (
        build_show_item_store_plan(
            _two_show_execution(),
            directory=(
                tmp_path
                / "artwork-tv"
            ),
        )
    )

    document = json.loads(
        plan.manifest.to_json()
    )

    assert (
        document["schema_version"]
        == 1
    )

    assert (
        document["library"]
        == "TV"
    )

    assert set(
        document["items"]
    ) == {
        "1",
        "2",
    }

    assert (
        document[
            "items"
        ]["1"]["tvdb_id"]
        == 100
    )

    assert (
        document[
            "items"
        ]["1"]["file"]
        == "show-1--tvdb-100.yaml"
    )


def test_existing_identical_store_is_unchanged(
    tmp_path,
):
    directory = (
        tmp_path
        / "artwork-tv"
    )

    first = (
        build_show_item_store_plan(
            _two_show_execution(),
            directory=directory,
        )
    )

    _write_plan(
        first
    )

    second = (
        build_show_item_store_plan(
            _two_show_execution(),
            directory=directory,
        )
    )

    assert second.added == ()
    assert second.updated == ()
    assert second.removed == ()

    assert set(
        second.unchanged
    ) == {
        "show-1--tvdb-100.yaml",
        "show-2--tvdb-200.yaml",
    }


def test_changed_owned_file_is_planned_as_update(
    tmp_path,
):
    directory = (
        tmp_path
        / "artwork-tv"
    )

    first = (
        build_show_item_store_plan(
            _two_show_execution(),
            directory=directory,
        )
    )

    _write_plan(
        first
    )

    (
        directory
        / "show-1--tvdb-100.yaml"
    ).write_text(
        "tampered\n",
        encoding="utf-8",
    )

    second = (
        build_show_item_store_plan(
            _two_show_execution(),
            directory=directory,
        )
    )

    assert second.updated == (
        "show-1--tvdb-100.yaml",
    )

    assert second.unchanged == (
        "show-2--tvdb-200.yaml",
    )


def test_previous_owned_file_missing_from_execution_is_removed(
    tmp_path,
):
    directory = (
        tmp_path
        / "artwork-tv"
    )

    first = (
        build_show_item_store_plan(
            _two_show_execution(),
            directory=directory,
        )
    )

    _write_plan(
        first
    )

    one_show = _execution(
        (
            (
                _inventory(
                    "1",
                    100,
                ),
                _state(
                    100,
                    "one",
                ),
            ),
        )
    )

    second = (
        build_show_item_store_plan(
            one_show,
            directory=directory,
        )
    )

    assert second.removed == (
        "show-2--tvdb-200.yaml",
    )


def test_unowned_files_are_preserved_and_never_adopted(
    tmp_path,
):
    directory = (
        tmp_path
        / "artwork-tv"
    )

    directory.mkdir()

    (
        directory
        / "manual-notes.yaml"
    ).write_text(
        "manual: true\n",
        encoding="utf-8",
    )

    plan = (
        build_show_item_store_plan(
            _two_show_execution(),
            directory=directory,
        )
    )

    assert (
        plan.preserved_unowned
        == (
            "manual-notes.yaml",
        )
    )

    assert (
        "manual-notes.yaml"
        not in plan.added
    )


def test_unowned_desired_filename_collision_is_blocked(
    tmp_path,
):
    directory = (
        tmp_path
        / "artwork-tv"
    )

    directory.mkdir()

    (
        directory
        / "show-1--tvdb-100.yaml"
    ).write_text(
        "manual: true\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ItemStoreCollisionError,
        match="unowned",
    ):
        build_show_item_store_plan(
            _two_show_execution(),
            directory=directory,
        )


def test_manifest_for_different_library_is_rejected(
    tmp_path,
):
    directory = (
        tmp_path
        / "artwork-tv"
    )

    directory.mkdir()

    (
        directory
        / MANIFEST_NAME
    ).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "library": "Anime",
                "items": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        InvalidItemStoreManifestError,
        match="different library",
    ):
        build_show_item_store_plan(
            _two_show_execution(),
            directory=directory,
        )


def test_formatted_item_store_plan_is_read_only(
    tmp_path,
):
    plan = (
        build_show_item_store_plan(
            _two_show_execution(),
            directory=(
                tmp_path
                / "artwork-tv"
            ),
        )
    )

    text = (
        format_item_store_plan(
            plan
        )
    )

    assert (
        "Desired show files:     2"
        in text
    )

    assert (
        "Added:                  2"
        in text
    )

    assert (
        "WRITE: disabled"
        in text
    )


def test_show_item_filename_is_human_readable():
    assert (
        show_item_filename(
            title=(
                "Star Trek: "
                "Strange New Worlds"
            ),
            tvdb_id=371572,
        )
        == (
            "star-trek-strange-new-worlds"
            "--tvdb-371572.yaml"
        )
    )

    assert (
        show_item_filename(
            title="Bob's Burgers",
            tvdb_id=194031,
        )
        == (
            "bobs-burgers"
            "--tvdb-194031.yaml"
        )
    )


def test_same_title_remains_unique_by_tvdb_identity():
    first = show_item_filename(
        title="Example",
        tvdb_id=100,
    )

    second = show_item_filename(
        title="Example",
        tvdb_id=200,
    )

    assert first == (
        "example--tvdb-100.yaml"
    )

    assert second == (
        "example--tvdb-200.yaml"
    )

    assert first != second


def test_title_change_plans_owned_filename_replacement(
    tmp_path,
):
    directory = (
        tmp_path
        / "artwork-tv"
    )

    original_inventory = (
        _inventory(
            "1",
            100,
        )
    )

    original_inventory.identity.title = (
        "Stranger Things"
    )

    original = _execution(
        (
            (
                original_inventory,
                _state(
                    100,
                    "one",
                ),
            ),
        )
    )

    first = (
        build_show_item_store_plan(
            original,
            directory=directory,
        )
    )

    assert first.added == (
        "stranger-things"
        "--tvdb-100.yaml",
    )

    _write_plan(
        first
    )

    renamed_inventory = (
        _inventory(
            "1",
            100,
        )
    )

    renamed_inventory.identity.title = (
        "Stranger Things (2016)"
    )

    renamed = _execution(
        (
            (
                renamed_inventory,
                _state(
                    100,
                    "one",
                ),
            ),
        )
    )

    second = (
        build_show_item_store_plan(
            renamed,
            directory=directory,
        )
    )

    assert second.added == (
        "stranger-things-2016"
        "--tvdb-100.yaml",
    )

    assert second.removed == (
        "stranger-things"
        "--tvdb-100.yaml",
    )


def test_show_item_filename_handles_empty_and_long_titles():
    assert (
        show_item_filename(
            title=" !!! ",
            tvdb_id=123,
        )
        == "show--tvdb-123.yaml"
    )

    long_name = (
        show_item_filename(
            title="界" * 500,
            tvdb_id=456,
        )
    )

    assert (
        len(
            long_name.encode(
                "utf-8"
            )
        )
        < 255
    )

    assert long_name.endswith(
        "--tvdb-456.yaml"
    )
