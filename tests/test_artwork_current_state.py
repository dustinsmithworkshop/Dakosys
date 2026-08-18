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
