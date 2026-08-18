"""Persistent run history for Artwork Manager."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import (
    datetime,
    timezone,
)
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from artwork.runner import (
    ArtworkLibraryRunResult,
    ArtworkManagerRunResult,
)
from artwork.serialization import (
    serialize_artwork_library,
    serialize_skipped_target,
)


RUN_HISTORY_SCHEMA_VERSION = 1

LATEST_NAME = "latest.json"
HISTORY_DIRECTORY_NAME = "history"

_RUN_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9_-]{1,128}$"
)


class ArtworkRunHistoryError(
    RuntimeError
):
    """Base class for Artwork Manager history failures."""


class InvalidArtworkRunHistoryError(
    ArtworkRunHistoryError
):
    """Persisted Artwork Manager history is invalid."""


@dataclass(frozen=True)
class ArtworkRunHistoryWrite:
    """Paths and record produced by one history write."""

    record: dict

    latest_path: Path
    history_path: Path


def _value(
    value,
):
    return getattr(
        value,
        "value",
        value,
    )


def _normalize_generated_at(
    value: datetime | None,
) -> datetime:
    if value is None:
        return datetime.now(
            timezone.utc
        )

    if (
        value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(
            "Artwork Manager history "
            "timestamp must be timezone-aware"
        )

    return value


def _normalize_run_id(
    value: str | None,
) -> str:
    if value is None:
        return uuid4().hex

    if not isinstance(
        value,
        str,
    ):
        raise ValueError(
            "Artwork Manager run ID "
            "must be a string"
        )

    normalized = value.strip()

    if not _RUN_ID_PATTERN.fullmatch(
        normalized
    ):
        raise ValueError(
            "Artwork Manager run ID may "
            "contain only letters, numbers, "
            "underscores, and hyphens"
        )

    return normalized


def _serialize_apply_result(
    result,
) -> dict | None:
    if result is None:
        return None

    rollback = (
        result.retained_rollback_path
    )

    return {
        "changed":
            result.changed,

        "directory":
            str(
                result.directory
            ),

        "manifest_path":
            str(
                result.manifest_path
            ),

        "desired":
            result.desired_count,

        "added":
            result.added_count,

        "updated":
            result.updated_count,

        "unchanged":
            result.unchanged_count,

        "removed":
            result.removed_count,

        "retained_rollback_path":
            (
                str(
                    rollback
                )
                if rollback is not None
                else None
            ),
    }


def serialize_artwork_library_run(
    result: ArtworkLibraryRunResult,
) -> dict:
    """Serialize one operational library outcome."""

    payload = (
        serialize_artwork_library(
            result.workflow
        )
    )

    # serialize_artwork_library() describes the live workflow object.
    # After an automatic apply, its dynamic filesystem check may now be
    # false. History instead records the pre-action decision snapshot.
    payload[
        "output"
    ][
        "needs_apply"
    ] = result.needs_apply

    payload[
        "decision"
    ] = {
        "apply_mode":
            _value(
                result.apply_mode
            ),

        "outcome":
            _value(
                result.outcome
            ),

        "safe_to_apply":
            result.safe_to_apply,

        "needs_apply":
            result.needs_apply,

        "review_fingerprint":
            result.review_fingerprint,
    }

    payload[
        "apply_result"
    ] = (
        _serialize_apply_result(
            result.apply_result
        )
    )

    payload[
        "error"
    ] = (
        {
            "type":
                result.error_type,

            "message":
                result.error_message,
        }
        if (
            result.error_type
            or result.error_message
        )
        else None
    )

    return payload


def build_artwork_run_record(
    result: ArtworkManagerRunResult,
    *,
    generated_at: datetime | None = None,
    run_id: str | None = None,
) -> dict:
    """Build a JSON-safe persistent record for one manager run."""

    timestamp = (
        _normalize_generated_at(
            generated_at
        )
    )

    normalized_run_id = (
        _normalize_run_id(
            run_id
        )
    )

    return {
        "schema_version":
            RUN_HISTORY_SCHEMA_VERSION,

        "run_id":
            normalized_run_id,

        "generated_at":
            timestamp.isoformat(
                timespec="microseconds"
            ),

        "apply_mode":
            _value(
                result.apply_mode
            ),

        "summary": {
            "library_count":
                len(
                    result.libraries
                ),

            "skipped_count":
                len(
                    result.skipped
                ),

            "applied":
                result.applied_count,

            "no_changes":
                result.no_changes_count,

            "pending_review":
                result.pending_review_count,

            "blocked":
                result.blocked_count,

            "failed":
                result.failed_count,
        },

        "libraries": [
            serialize_artwork_library_run(
                library
            )
            for library
            in result.libraries
        ],

        "skipped": [
            serialize_skipped_target(
                skipped
            )
            for skipped
            in result.skipped
        ],
    }


def _history_filename(
    record: dict,
) -> str:
    try:
        timestamp = datetime.fromisoformat(
            record[
                "generated_at"
            ]
        )
    except (
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise InvalidArtworkRunHistoryError(
            "Artwork Manager run record "
            "has invalid generated_at"
        ) from exc

    if (
        timestamp.tzinfo is None
        or timestamp.utcoffset() is None
    ):
        raise InvalidArtworkRunHistoryError(
            "Artwork Manager run record "
            "timestamp is not timezone-aware"
        )

    utc_timestamp = (
        timestamp.astimezone(
            timezone.utc
        )
    )

    stamp = utc_timestamp.strftime(
        "%Y%m%dT%H%M%S.%fZ"
    )

    run_id = _normalize_run_id(
        record.get(
            "run_id"
        )
    )

    return (
        f"{stamp}-"
        f"{run_id}.json"
    )


def _fsync_directory(
    directory: Path,
) -> None:
    try:
        descriptor = os.open(
            directory,
            os.O_RDONLY,
        )
    except OSError:
        return

    try:
        os.fsync(
            descriptor
        )
    except OSError:
        pass

    finally:
        os.close(
            descriptor
        )


def _write_json_atomic(
    path: Path,
    payload: dict,
) -> None:
    contents = (
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    )

    temporary = (
        path.parent
        / (
            f".{path.name}."
            f"{uuid4().hex}.tmp"
        )
    )

    try:
        with temporary.open(
            "x",
            encoding="utf-8",
        ) as handle:
            handle.write(
                contents
            )

            handle.flush()

            os.fsync(
                handle.fileno()
            )

        os.replace(
            temporary,
            path,
        )

        _fsync_directory(
            path.parent
        )

    finally:
        if temporary.exists():
            temporary.unlink(
                missing_ok=True
            )


def write_artwork_run_history(
    result: ArtworkManagerRunResult,
    *,
    directory: str | Path,
    generated_at: datetime | None = None,
    run_id: str | None = None,
) -> ArtworkRunHistoryWrite:
    """Persist immutable history plus the latest-run snapshot.

    The immutable history record is written first. ``latest.json`` is
    updated only after the history record exists.
    """

    root = Path(
        directory
    )

    history_directory = (
        root
        / HISTORY_DIRECTORY_NAME
    )

    history_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    record = (
        build_artwork_run_record(
            result,
            generated_at=generated_at,
            run_id=run_id,
        )
    )

    history_path = (
        history_directory
        / _history_filename(
            record
        )
    )

    if history_path.exists():
        raise ArtworkRunHistoryError(
            "Artwork Manager history "
            "record already exists: "
            f"{history_path.name}"
        )

    latest_path = (
        root
        / LATEST_NAME
    )

    # Preserve the historical record before advancing the latest pointer.
    _write_json_atomic(
        history_path,
        record,
    )

    _write_json_atomic(
        latest_path,
        record,
    )

    return ArtworkRunHistoryWrite(
        record=record,
        latest_path=latest_path,
        history_path=history_path,
    )


def _load_record(
    path: Path,
) -> dict:
    try:
        payload = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise InvalidArtworkRunHistoryError(
            "Could not read Artwork Manager "
            f"history record: {path}"
        ) from exc

    if not isinstance(
        payload,
        dict,
    ):
        raise InvalidArtworkRunHistoryError(
            "Artwork Manager history "
            "record must be a JSON object"
        )

    if (
        payload.get(
            "schema_version"
        )
        != RUN_HISTORY_SCHEMA_VERSION
    ):
        raise InvalidArtworkRunHistoryError(
            "Unsupported Artwork Manager "
            "history schema version"
        )

    return payload


def load_latest_artwork_run(
    directory: str | Path,
) -> dict | None:
    """Load the most recently persisted Artwork Manager run."""

    path = (
        Path(
            directory
        )
        / LATEST_NAME
    )

    if not path.exists():
        return None

    return _load_record(
        path
    )


def list_artwork_run_history(
    directory: str | Path,
    *,
    limit: int | None = None,
) -> tuple[dict, ...]:
    """Load history newest-first."""

    if (
        limit is not None
        and (
            not isinstance(
                limit,
                int,
            )
            or isinstance(
                limit,
                bool,
            )
            or limit <= 0
        )
    ):
        raise ValueError(
            "Artwork Manager history "
            "limit must be a positive integer"
        )

    history_directory = (
        Path(
            directory
        )
        / HISTORY_DIRECTORY_NAME
    )

    if not history_directory.exists():
        return ()

    paths = sorted(
        history_directory.glob(
            "*.json"
        ),
        key=lambda path:
            path.name,
        reverse=True,
    )

    if limit is not None:
        paths = paths[
            :limit
        ]

    return tuple(
        _load_record(
            path
        )
        for path
        in paths
    )
