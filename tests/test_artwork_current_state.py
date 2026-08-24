from datetime import (
    datetime,
    timezone,
)
import json

import pytest

from artwork.current_state import (
    InvalidArtworkCurrentStateError,
    load_artwork_current_state,
    write_artwork_current_state,
)


def test_current_state_round_trip(
    tmp_path,
):
    preview = {
        "library": "Series",
        "output": {
            "needs_apply": True,
        },
    }

    record = (
        write_artwork_current_state(
            directory=tmp_path,
            library="Series",
            preview=preview,
            scanned_at=datetime(
                2026,
                8,
                18,
                17,
                30,
                tzinfo=timezone.utc,
            ),
        )
    )

    loaded = (
        load_artwork_current_state(
            directory=tmp_path,
            library="Series",
        )
    )

    assert loaded == record

    assert (
        loaded["library"]
        == "Series"
    )

    assert (
        loaded["preview"]
        == preview
    )


def test_different_library_names_have_independent_cache_files(
    tmp_path,
):
    write_artwork_current_state(
        directory=tmp_path,
        library="TV",
        preview={
            "library": "TV",
        },
    )

    write_artwork_current_state(
        directory=tmp_path,
        library="Cartoons",
        preview={
            "library": "Cartoons",
        },
    )

    assert (
        load_artwork_current_state(
            directory=tmp_path,
            library="TV",
        )["preview"]["library"]
        == "TV"
    )

    assert (
        load_artwork_current_state(
            directory=tmp_path,
            library="Cartoons",
        )["preview"]["library"]
        == "Cartoons"
    )


def test_missing_current_state_returns_none(
    tmp_path,
):
    assert (
        load_artwork_current_state(
            directory=tmp_path,
            library="Never Scanned",
        )
        is None
    )


def test_corrupt_current_state_is_rejected(
    tmp_path,
):
    write_artwork_current_state(
        directory=tmp_path,
        library="Series",
        preview={
            "library": "Series",
        },
    )

    current_state = (
        tmp_path
        / "current-state"
    )

    path = next(
        current_state.glob(
            "*.json"
        )
    )

    path.write_text(
        "{broken",
        encoding="utf-8",
    )

    with pytest.raises(
        InvalidArtworkCurrentStateError
    ):
        load_artwork_current_state(
            directory=tmp_path,
            library="Series",
        )


def test_library_identity_mismatch_is_rejected(
    tmp_path,
):
    write_artwork_current_state(
        directory=tmp_path,
        library="Series",
        preview={
            "library": "Series",
        },
    )

    path = next(
        (
            tmp_path
            / "current-state"
        ).glob(
            "*.json"
        )
    )

    payload = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    payload[
        "library"
    ] = "Wrong"

    path.write_text(
        json.dumps(
            payload
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        InvalidArtworkCurrentStateError,
        match="identity",
    ):
        load_artwork_current_state(
            directory=tmp_path,
            library="Series",
        )


def test_pre_generator_current_state_schema_is_treated_as_stale(
    tmp_path,
):
    """3.0 GUI cache is stale and must trigger a fresh 3.1 scan."""

    from artwork.current_state import (
        CURRENT_STATE_SCHEMA_VERSION,
    )

    assert (
        CURRENT_STATE_SCHEMA_VERSION
        == 3
    )

    write_artwork_current_state(
        directory=tmp_path,
        library="TV",
        preview={
            "library": "TV",
            "generator": {
                "changed_shows": 0,
                "planned_cards": 0,
                "cached_cards": 0,
                "materialization_needed": 0,
                "failures": 0,
            },
        },
    )

    path = next(
        (
            tmp_path
            / "current-state"
        ).glob("*.json")
    )

    payload = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    # Simulate a persisted 3.0 GUI cache.
    payload["schema_version"] = 1
    payload["preview"].pop(
        "generator",
        None,
    )

    path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    assert (
        load_artwork_current_state(
            directory=tmp_path,
            library="TV",
        )
        is None
    )


def test_current_state_round_trips_review_fingerprint(
    tmp_path,
):
    record = (
        write_artwork_current_state(
            directory=tmp_path,
            library="Anime",
            preview={
                "library": "Anime",
            },
            review_fingerprint=(
                "reviewed-anime-plan"
            ),
        )
    )

    loaded = (
        load_artwork_current_state(
            directory=tmp_path,
            library="Anime",
        )
    )

    assert loaded == record

    assert (
        loaded[
            "review_fingerprint"
        ]
        == "reviewed-anime-plan"
    )


def test_schema_two_current_state_is_treated_as_stale(
    tmp_path,
):
    write_artwork_current_state(
        directory=tmp_path,
        library="Anime",
        preview={
            "library": "Anime",
        },
        review_fingerprint=(
            "reviewed-anime-plan"
        ),
    )

    path = next(
        (
            tmp_path
            / "current-state"
        ).glob("*.json")
    )

    payload = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    payload[
        "schema_version"
    ] = 2

    payload.pop(
        "review_fingerprint",
        None,
    )

    path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    assert (
        load_artwork_current_state(
            directory=tmp_path,
            library="Anime",
        )
        is None
    )


def test_schema_three_requires_review_fingerprint_field(
    tmp_path,
):
    write_artwork_current_state(
        directory=tmp_path,
        library="Anime",
        preview={
            "library": "Anime",
        },
    )

    path = next(
        (
            tmp_path
            / "current-state"
        ).glob("*.json")
    )

    payload = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    payload.pop(
        "review_fingerprint"
    )

    path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    with pytest.raises(
        InvalidArtworkCurrentStateError,
        match="fingerprint is missing",
    ):
        load_artwork_current_state(
            directory=tmp_path,
            library="Anime",
        )
