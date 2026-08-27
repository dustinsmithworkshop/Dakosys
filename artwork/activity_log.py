"""Process-safe operational logging for Artwork Manager."""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - Linux is the production target.
    fcntl = None


DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 5


def _rotate(
    path: Path,
    *,
    backup_count: int,
) -> None:
    if not path.exists():
        return

    if backup_count <= 0:
        path.unlink()
        return

    oldest = Path(
        f"{path}.{backup_count}"
    )

    if oldest.exists():
        oldest.unlink()

    for index in range(
        backup_count - 1,
        0,
        -1,
    ):
        source = Path(
            f"{path}.{index}"
        )

        if source.exists():
            source.replace(
                Path(
                    f"{path}.{index + 1}"
                )
            )

    path.replace(
        Path(
            f"{path}.1"
        )
    )


def write_artwork_activity(
    log_file: str | os.PathLike[str],
    level: str,
    message: str,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
) -> None:
    """Append one single-line Artwork Manager activity record."""

    if max_bytes <= 0:
        raise ValueError(
            "max_bytes must be positive"
        )

    path = Path(
        log_file
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    lock_path = Path(
        f"{path}.lock"
    )

    normalized_level = (
        str(level)
        .strip()
        .upper()
        or "INFO"
    )

    normalized_message = (
        " | ".join(
            str(message).splitlines()
        )
    )

    with lock_path.open(
        "a+",
        encoding="utf-8",
    ) as lock_file:
        if fcntl is not None:
            fcntl.flock(
                lock_file.fileno(),
                fcntl.LOCK_EX,
            )

        try:
            if (
                path.exists()
                and path.stat().st_size
                >= max_bytes
            ):
                _rotate(
                    path,
                    backup_count=backup_count,
                )

            timestamp = (
                datetime.now()
                .strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )

            with path.open(
                "a",
                encoding="utf-8",
            ) as log:
                log.write(
                    f"{timestamp} "
                    f"[{normalized_level}] "
                    f"{normalized_message}\n"
                )
                log.flush()

        finally:
            if fcntl is not None:
                fcntl.flock(
                    lock_file.fileno(),
                    fcntl.LOCK_UN,
                )
