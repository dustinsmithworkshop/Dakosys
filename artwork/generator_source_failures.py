"""Temporary negative cache for invalid Artwork Generator sources."""

from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
    timezone,
)
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from artwork.generator_inputs import (
    EpisodeGenerationInput,
)


CACHE_VERSION = 1
FAILURE_DIRECTORY_NAME = ".source-failures"

DEFAULT_INVALID_SOURCE_TTL = (
    timedelta(hours=24)
)


def generation_source_identity(
    generation_input: EpisodeGenerationInput,
) -> tuple[str, str]:
    """Return the exact source identity used by one generation input."""

    source = (
        generation_input.image_source
    )

    if source is None:
        raise ValueError(
            "generation input has no image source"
        )

    identity = (
        generation_input.image_provider_asset_id
        or generation_input.image_ref
    )

    if not isinstance(
        identity,
        str,
    ):
        raise ValueError(
            "generation input has no image identity"
        )

    identity = identity.strip()

    if not identity:
        raise ValueError(
            "generation input has no image identity"
        )

    return (
        source.value,
        identity,
    )


def source_failure_marker_path(
    *,
    root: str | Path,
    generation_input: EpisodeGenerationInput,
) -> Path:
    """Return deterministic marker path for one exact source."""

    source, identity = (
        generation_source_identity(
            generation_input
        )
    )

    payload = json.dumps(
        {
            "source": source,
            "identity": identity,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    digest = hashlib.sha256(
        payload
    ).hexdigest()

    return (
        Path(root)
        / FAILURE_DIRECTORY_NAME
        / f"{digest}.json"
    )


def record_invalid_generation_source(
    *,
    root: str | Path,
    generation_input: EpisodeGenerationInput,
    reason: str,
    now: datetime | None = None,
) -> Path:
    """Atomically mark one exact generation source temporarily invalid."""

    source, identity = (
        generation_source_identity(
            generation_input
        )
    )

    recorded_at = (
        _normalized_now(
            now
        )
    )

    marker = (
        source_failure_marker_path(
            root=root,
            generation_input=(
                generation_input
            ),
        )
    )

    marker.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    document = {
        "version": CACHE_VERSION,
        "source": source,
        "identity": identity,
        "reason": str(reason),
        "recorded_at": (
            recorded_at.isoformat()
        ),
    }

    temporary = marker.with_name(
        (
            f".{marker.name}."
            f"tmp-{uuid4().hex}"
        )
    )

    try:
        temporary.write_text(
            json.dumps(
                document,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        os.replace(
            temporary,
            marker,
        )

    finally:
        temporary.unlink(
            missing_ok=True
        )

    return marker


def is_generation_source_known_invalid(
    *,
    root: str | Path,
    generation_input: EpisodeGenerationInput,
    ttl: timedelta = (
        DEFAULT_INVALID_SOURCE_TTL
    ),
    now: datetime | None = None,
) -> bool:
    """Whether one exact source has a fresh invalid-source marker.

    Reads are intentionally fail-open. A malformed or unreadable
    derived cache entry must never block Artwork Manager planning.
    """

    if (
        not isinstance(
            ttl,
            timedelta,
        )
        or ttl.total_seconds() <= 0
    ):
        raise ValueError(
            "invalid source TTL must be positive"
        )

    marker = (
        source_failure_marker_path(
            root=root,
            generation_input=(
                generation_input
            ),
        )
    )

    try:
        document = json.loads(
            marker.read_text(
                encoding="utf-8"
            )
        )

    except (
        OSError,
        json.JSONDecodeError,
    ):
        return False

    try:
        source, identity = (
            generation_source_identity(
                generation_input
            )
        )

        if (
            document.get("version")
            != CACHE_VERSION
            or document.get("source")
            != source
            or document.get("identity")
            != identity
        ):
            return False

        recorded_at = datetime.fromisoformat(
            document["recorded_at"]
        )

        if (
            recorded_at.tzinfo
            is None
        ):
            return False

        age = (
            _normalized_now(now)
            - recorded_at.astimezone(
                timezone.utc
            )
        )

    except (
        KeyError,
        TypeError,
        ValueError,
    ):
        return False

    return (
        timedelta(0)
        <= age
        < ttl
    )


def _normalized_now(
    value: datetime | None,
) -> datetime:
    if value is None:
        return datetime.now(
            timezone.utc
        )

    if value.tzinfo is None:
        raise ValueError(
            "current time must be timezone-aware"
        )

    return value.astimezone(
        timezone.utc
    )
