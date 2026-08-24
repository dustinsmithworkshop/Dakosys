"""Durable cached current-state previews for Artwork Manager."""

from __future__ import annotations

from datetime import (
    datetime,
    timezone,
)
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import uuid4


CURRENT_STATE_SCHEMA_VERSION = 2
CURRENT_STATE_DIRECTORY_NAME = "current-state"


class ArtworkCurrentStateError(
    RuntimeError
):
    """Base class for durable current-state failures."""


class InvalidArtworkCurrentStateError(
    ArtworkCurrentStateError
):
    """A cached current-state record is malformed."""


def _library_key(
    library: str,
) -> str:
    if not isinstance(
        library,
        str,
    ):
        raise ValueError(
            "Artwork Manager library "
            "must be a string"
        )

    normalized = (
        library.strip()
    )

    if not normalized:
        raise ValueError(
            "Artwork Manager library "
            "cannot be empty"
        )

    digest = sha256(
        normalized.encode(
            "utf-8"
        )
    ).hexdigest()[:20]

    return digest


def _normalize_timestamp(
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
            "Artwork Manager current-state "
            "timestamp must be timezone-aware"
        )

    return value


def _record_path(
    directory: str | Path,
    library: str,
) -> Path:
    return (
        Path(
            directory
        )
        / CURRENT_STATE_DIRECTORY_NAME
        / f"{_library_key(library)}.json"
    )


def _write_json_atomic(
    path: Path,
    payload: dict,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = (
        path.parent
        / (
            f".{path.name}."
            f"{uuid4().hex}.tmp"
        )
    )

    contents = (
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
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

    finally:
        temporary.unlink(
            missing_ok=True
        )


def build_artwork_current_state_record(
    *,
    library: str,
    preview: dict,
    scanned_at: datetime | None = None,
) -> dict:
    """Build one JSON-safe cached current-state record."""

    if not isinstance(
        preview,
        dict,
    ):
        raise ValueError(
            "Artwork Manager current-state "
            "preview must be a mapping"
        )

    timestamp = (
        _normalize_timestamp(
            scanned_at
        )
    )

    return {
        "schema_version":
            CURRENT_STATE_SCHEMA_VERSION,

        "library":
            library,

        "scanned_at":
            timestamp.isoformat(
                timespec="microseconds"
            ),

        "preview":
            preview,
    }


def write_artwork_current_state(
    *,
    directory: str | Path,
    library: str,
    preview: dict,
    scanned_at: datetime | None = None,
) -> dict:
    """Persist the latest successful current-state result."""

    record = (
        build_artwork_current_state_record(
            library=library,
            preview=preview,
            scanned_at=scanned_at,
        )
    )

    path = _record_path(
        directory,
        library,
    )

    _write_json_atomic(
        path,
        record,
    )

    return record


def load_artwork_current_state(
    *,
    directory: str | Path,
    library: str,
) -> dict | None:
    """Load the last successful current-state result for one library."""

    path = _record_path(
        directory,
        library,
    )

    if not path.exists():
        return None

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
        raise InvalidArtworkCurrentStateError(
            "Could not read Artwork Manager "
            f"current state for {library!r}"
        ) from exc

    if not isinstance(
        payload,
        dict,
    ):
        raise InvalidArtworkCurrentStateError(
            "Artwork Manager current-state "
            "record must be a JSON object"
        )

    schema_version = payload.get(
        "schema_version"
    )

    if (
        isinstance(
            schema_version,
            int,
        )
        and not isinstance(
            schema_version,
            bool,
        )
        and schema_version
        < CURRENT_STATE_SCHEMA_VERSION
    ):
        # Older cached previews are stale after a schema upgrade.
        # Treat them as absent so callers can transparently rebuild
        # current state using the current serializer.
        return None

    if (
        schema_version
        != CURRENT_STATE_SCHEMA_VERSION
    ):
        raise InvalidArtworkCurrentStateError(
            "Unsupported Artwork Manager "
            "current-state schema version"
        )

    if (
        payload.get(
            "library"
        )
        != library
    ):
        raise InvalidArtworkCurrentStateError(
            "Artwork Manager current-state "
            "library identity does not match"
        )

    if not isinstance(
        payload.get(
            "preview"
        ),
        dict,
    ):
        raise InvalidArtworkCurrentStateError(
            "Artwork Manager current-state "
            "preview is invalid"
        )

    return payload
