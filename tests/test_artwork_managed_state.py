from pathlib import Path

import json
import pytest

from artwork.item_store import (
    MANIFEST_NAME,
)
from artwork.managed_state import (
    ArtworkStateBootstrapRequiredError,
    InconsistentManagedStateError,
    ManagedStateBaselineSource,
    load_show_managed_state_baseline,
)
from artwork.state_store import (
    STATE_NAME,
)


def _manifest(
    *,
    rating_key="1",
    tvdb_id=100,
):
    return {
        "schema_version": 1,
        "library": "TV",
        "items": {
            rating_key: {
                "tvdb_id":
                    tvdb_id,
                "file":
                    (
                        "example"
                        f"--tvdb-{tvdb_id}.yaml"
                    ),
                "sha256":
                    ("0" * 64),
            },
        },
    }


def _state_store(
    *,
    rating_key="1",
    tvdb_id=100,
):
    return {
        "schema_version": 1,
        "library": "TV",
        "items": {
            rating_key: {
                "title":
                    "Example",
                "tvdb_id":
                    tvdb_id,
                "tmdb_id":
                    None,
                "imdb_id":
                    None,
                "poster":
                    None,
                "background":
                    None,
                "seasons":
                    {},
                "selected_set_id":
                    "123",
                "selected_set_source":
                    "mediux",
                "selected_creator":
                    "Creator",
                "selection_mode":
                    "auto",
                "episode_selection":
                    None,
                "presentation_selection":
                    None,
            },
        },
    }


def _write_json(
    path,
    document,
):
    path.write_text(
        json.dumps(
            document
        ),
        encoding="utf-8",
    )


def test_new_library_without_legacy_starts_empty(
    tmp_path,
):
    baseline = (
        load_show_managed_state_baseline(
            directory=(
                tmp_path
                / "artwork-tv"
            ),
            library="TV",
        )
    )

    assert (
        baseline.source
        is
        ManagedStateBaselineSource
        .NEW_LIBRARY
    )

    assert baseline.states == ()
    assert baseline.manifest is None
    assert baseline.state_store is None


def test_existing_manifest_requires_bootstrap_when_state_missing(
    tmp_path,
):
    directory = (
        tmp_path
        / "artwork-tv"
    )

    directory.mkdir()

    _write_json(
        directory
        / MANIFEST_NAME,
        _manifest(),
    )

    with pytest.raises(
        ArtworkStateBootstrapRequiredError,
        match="bootstrap",
    ):
        load_show_managed_state_baseline(
            directory=directory,
            library="TV",
        )


def test_durable_state_is_authoritative_and_legacy_is_not_read(
    tmp_path,
):
    directory = (
        tmp_path
        / "artwork-tv"
    )

    directory.mkdir()

    _write_json(
        directory
        / MANIFEST_NAME,
        _manifest(),
    )

    _write_json(
        directory
        / STATE_NAME,
        _state_store(),
    )

    # Deliberately nonexistent. If durable state is authoritative,
    # this path must never be opened.
    nonexistent_legacy = (
        tmp_path
        / "does-not-exist.yml"
    )

    baseline = (
        load_show_managed_state_baseline(
            directory=directory,
            library="TV",
            legacy_metadata=(
                nonexistent_legacy
            ),
        )
    )

    assert (
        baseline.source
        is
        ManagedStateBaselineSource
        .DURABLE_STATE
    )

    assert baseline.state_count == 1

    state = baseline.states[0]

    assert state.tvdb_id == 100
    assert (
        state.selected_set_id
        == "123"
    )


def test_durable_state_without_manifest_is_rejected(
    tmp_path,
):
    directory = (
        tmp_path
        / "artwork-tv"
    )

    directory.mkdir()

    _write_json(
        directory
        / STATE_NAME,
        _state_store(),
    )

    with pytest.raises(
        InconsistentManagedStateError,
        match="without an ownership manifest",
    ):
        load_show_managed_state_baseline(
            directory=directory,
            library="TV",
        )


def test_manifest_state_identity_disagreement_is_rejected(
    tmp_path,
):
    directory = (
        tmp_path
        / "artwork-tv"
    )

    directory.mkdir()

    _write_json(
        directory
        / MANIFEST_NAME,
        _manifest(
            tvdb_id=100,
        ),
    )

    _write_json(
        directory
        / STATE_NAME,
        _state_store(
            tvdb_id=200,
        ),
    )

    with pytest.raises(
        InconsistentManagedStateError,
        match="disagree",
    ):
        load_show_managed_state_baseline(
            directory=directory,
            library="TV",
        )


def test_existing_manifest_can_bootstrap_from_legacy(
    tmp_path,
):
    directory = (
        tmp_path
        / "artwork-tv"
    )

    directory.mkdir()

    _write_json(
        directory
        / MANIFEST_NAME,
        _manifest(),
    )

    legacy = (
        tmp_path
        / "mediux-tv.yml"
    )

    legacy.write_text(
        """
metadata:
  100: # TVDB id for Example. Set by Creator on MediUX https://mediux.pro/sets/123
    seasons:
      1:
        episodes:
          1:
            url_poster: https://api.mediux.pro/assets/example
""".lstrip(),
        encoding="utf-8",
    )

    baseline = (
        load_show_managed_state_baseline(
            directory=directory,
            library="TV",
            legacy_metadata=legacy,
        )
    )

    assert (
        baseline.source
        is
        ManagedStateBaselineSource
        .LEGACY_MIGRATION
    )

    assert baseline.state_count == 1

    state = baseline.states[0]

    assert state.tvdb_id == 100
    assert (
        state.selected_set_id
        == "123"
    )
