import json
from datetime import (
    datetime,
    timezone,
)
from pathlib import Path
from types import SimpleNamespace

import pytest

from artwork.apply_policy import (
    ArtworkApplyMode,
)
from artwork.item_store_apply import (
    ItemStoreApplyResult,
)
from artwork.run_history import (
    build_artwork_run_record,
    list_artwork_run_history,
    load_latest_artwork_run,
    write_artwork_run_history,
)
from artwork.runner import (
    ArtworkLibraryRunResult,
    ArtworkManagerRunResult,
    ArtworkRunOutcome,
)


def _workflow(
    *,
    library="Series",
):
    return SimpleNamespace(
        library=library,
        safe_to_apply=True,
    )


def _manager_result(
    *,
    outcome=(
        ArtworkRunOutcome
        .PENDING_REVIEW
    ),
    apply_result=None,
    review_fingerprint=(
        "review-abc"
    ),
    error_type=None,
    error_message=None,
):
    library = (
        ArtworkLibraryRunResult(
            workflow=_workflow(),
            apply_mode=(
                ArtworkApplyMode
                .MANUAL
            ),
            outcome=outcome,
            apply_result=apply_result,
            error_type=error_type,
            error_message=error_message,
            review_fingerprint=(
                review_fingerprint
            ),
            planned_needs_apply=True,
        )
    )

    return ArtworkManagerRunResult(
        apply_mode=(
            ArtworkApplyMode.MANUAL
        ),
        libraries=(
            library,
        ),
        skipped=(),
    )


def _fake_serialized_library():
    return {
        "library":
            "Series",

        "output": {
            # History must overwrite this with the runner snapshot.
            "needs_apply":
                False,
        },
    }


def test_run_record_captures_pending_review_identity(
    monkeypatch,
):
    monkeypatch.setattr(
        "artwork.run_history."
        "serialize_artwork_library",
        lambda workflow:
            _fake_serialized_library(),
    )

    timestamp = datetime(
        2026,
        8,
        18,
        4,
        30,
        0,
        tzinfo=timezone.utc,
    )

    record = (
        build_artwork_run_record(
            _manager_result(),
            generated_at=timestamp,
            run_id="run-one",
        )
    )

    assert (
        record["run_id"]
        == "run-one"
    )

    assert (
        record["apply_mode"]
        == "manual"
    )

    assert record["summary"] == {
        "library_count": 1,
        "skipped_count": 0,
        "applied": 0,
        "no_changes": 0,
        "pending_review": 1,
        "blocked": 0,
        "failed": 0,
    }

    library = (
        record["libraries"][0]
    )

    assert (
        library["decision"]
        ["outcome"]
        == "pending_review"
    )

    assert (
        library["decision"]
        ["needs_apply"]
        is True
    )

    assert (
        library["output"]
        ["needs_apply"]
        is True
    )

    assert (
        library["decision"]
        ["review_fingerprint"]
        == "review-abc"
    )


def test_run_record_captures_apply_result(
    monkeypatch,
):
    monkeypatch.setattr(
        "artwork.run_history."
        "serialize_artwork_library",
        lambda workflow:
            _fake_serialized_library(),
    )

    apply_result = (
        ItemStoreApplyResult(
            directory=Path(
                "/metadata/artwork-series"
            ),
            manifest_path=Path(
                "/metadata/artwork-series/"
                ".dakosys-manifest.json"
            ),
            changed=True,
            desired_count=5,
            added_count=1,
            updated_count=2,
            unchanged_count=2,
            removed_count=0,
        )
    )

    record = (
        build_artwork_run_record(
            _manager_result(
                outcome=(
                    ArtworkRunOutcome
                    .APPLIED
                ),
                apply_result=(
                    apply_result
                ),
                review_fingerprint=None,
            ),
            generated_at=datetime(
                2026,
                8,
                18,
                4,
                31,
                tzinfo=timezone.utc,
            ),
            run_id="run-two",
        )
    )

    applied = (
        record["libraries"][0]
        ["apply_result"]
    )

    assert applied == {
        "changed": True,
        "directory":
            "/metadata/artwork-series",
        "manifest_path":
            (
                "/metadata/artwork-series/"
                ".dakosys-manifest.json"
            ),
        "desired": 5,
        "added": 1,
        "updated": 2,
        "unchanged": 2,
        "removed": 0,
        "retained_rollback_path":
            None,
    }


def test_history_write_creates_immutable_and_latest_records(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        "artwork.run_history."
        "serialize_artwork_library",
        lambda workflow:
            _fake_serialized_library(),
    )

    root = (
        tmp_path
        / "artwork-manager"
    )

    written = (
        write_artwork_run_history(
            _manager_result(),
            directory=root,
            generated_at=datetime(
                2026,
                8,
                18,
                4,
                32,
                tzinfo=timezone.utc,
            ),
            run_id="first",
        )
    )

    assert (
        written.latest_path
        == root / "latest.json"
    )

    assert (
        written.history_path.exists()
    )

    assert (
        written.latest_path.exists()
    )

    history_payload = json.loads(
        written.history_path.read_text(
            encoding="utf-8"
        )
    )

    latest_payload = json.loads(
        written.latest_path.read_text(
            encoding="utf-8"
        )
    )

    assert (
        history_payload
        == latest_payload
        == written.record
    )


def test_second_history_write_preserves_first_and_advances_latest(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        "artwork.run_history."
        "serialize_artwork_library",
        lambda workflow:
            _fake_serialized_library(),
    )

    root = (
        tmp_path
        / "artwork-manager"
    )

    first = (
        write_artwork_run_history(
            _manager_result(),
            directory=root,
            generated_at=datetime(
                2026,
                8,
                18,
                4,
                32,
                tzinfo=timezone.utc,
            ),
            run_id="first",
        )
    )

    second = (
        write_artwork_run_history(
            _manager_result(),
            directory=root,
            generated_at=datetime(
                2026,
                8,
                18,
                4,
                33,
                tzinfo=timezone.utc,
            ),
            run_id="second",
        )
    )

    assert first.history_path.exists()
    assert second.history_path.exists()

    latest = (
        load_latest_artwork_run(
            root
        )
    )

    assert latest is not None

    assert (
        latest["run_id"]
        == "second"
    )

    history = (
        list_artwork_run_history(
            root
        )
    )

    assert [
        item["run_id"]
        for item
        in history
    ] == [
        "second",
        "first",
    ]


def test_history_list_limit_is_newest_first(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        "artwork.run_history."
        "serialize_artwork_library",
        lambda workflow:
            _fake_serialized_library(),
    )

    root = (
        tmp_path
        / "artwork-manager"
    )

    for minute, run_id in (
        (30, "one"),
        (31, "two"),
        (32, "three"),
    ):
        write_artwork_run_history(
            _manager_result(),
            directory=root,
            generated_at=datetime(
                2026,
                8,
                18,
                4,
                minute,
                tzinfo=timezone.utc,
            ),
            run_id=run_id,
        )

    history = (
        list_artwork_run_history(
            root,
            limit=2,
        )
    )

    assert [
        item["run_id"]
        for item
        in history
    ] == [
        "three",
        "two",
    ]


def test_history_rejects_naive_timestamp(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        "artwork.run_history."
        "serialize_artwork_library",
        lambda workflow:
            _fake_serialized_library(),
    )

    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        write_artwork_run_history(
            _manager_result(),
            directory=tmp_path,
            generated_at=datetime(
                2026,
                8,
                18,
                4,
                30,
            ),
        )


def test_run_record_serializes_pre_workflow_block(
    monkeypatch,
):
    from artwork.targets import (
        ArtworkTarget,
        MediaType,
    )
    from artwork.runner import (
        ArtworkLibraryRunFailure,
    )

    target = ArtworkTarget(
        name="Animation Archive",
        library="Animation Archive",
        media_type=MediaType.SHOW,
        output_path=Path(
            "/metadata/artwork-animation-archive"
        ),
    )

    blocked = (
        ArtworkLibraryRunFailure(
            target=target,
            apply_mode=(
                ArtworkApplyMode.AUTO
            ),
            outcome=(
                ArtworkRunOutcome.BLOCKED
            ),
            error_type=(
                "ArtworkStateBootstrapRequiredError"
            ),
            error_message=(
                "explicit legacy bootstrap metadata is required"
            ),
        )
    )

    result = ArtworkManagerRunResult(
        apply_mode=(
            ArtworkApplyMode.AUTO
        ),
        libraries=(
            blocked,
        ),
        skipped=(),
    )

    record = build_artwork_run_record(
        result,
        generated_at=datetime(
            2026,
            8,
            18,
            20,
            0,
            tzinfo=timezone.utc,
        ),
        run_id="blocked-library",
    )

    assert (
        record["summary"]["blocked"]
        == 1
    )

    library = (
        record["libraries"][0]
    )

    assert (
        library["library"]
        == "Animation Archive"
    )

    assert (
        library["output_path"]
        == (
            "/metadata/"
            "artwork-animation-archive"
        )
    )

    assert (
        library["decision"]["outcome"]
        == "blocked"
    )

    assert (
        library["decision"]["safe_to_apply"]
        is False
    )

    assert (
        library["decision"]["needs_apply"]
        is False
    )

    assert (
        library["safety"]["issues"][0]["code"]
        == "setup_required"
    )

    assert (
        library["error"]["type"]
        == (
            "ArtworkStateBootstrapRequiredError"
        )
    )
