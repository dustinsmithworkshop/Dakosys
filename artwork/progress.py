"""Progress reporting for read-only Artwork Manager scans."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum


class ArtworkScanPhase(str, Enum):
    """Meaningful phases of one library current-state scan."""

    INVENTORY = "inventory"
    IDENTITY = "identity"
    PRIMARY_MANAGED = "primary_managed"
    PRIMARY_DISCOVERY = "primary_discovery"
    TMDB_MANAGED = "tmdb_managed"
    TMDB_DISCOVERY = "tmdb_discovery"
    PLANNING = "planning"
    COMPLETE = "complete"


@dataclass(frozen=True)
class ArtworkScanProgress:
    """One truthful progress update from the scan pipeline."""

    library: str
    phase: ArtworkScanPhase
    completed: int
    total: int

    message: str = ""
    current_title: str | None = None

    @property
    def fraction(self) -> float | None:
        """Return phase-local completion when a meaningful total exists."""

        if self.total <= 0:
            return None

        return min(
            1.0,
            max(
                0.0,
                self.completed
                / self.total,
            ),
        )


ArtworkProgressCallback = Callable[
    [ArtworkScanProgress],
    None,
]


def emit_artwork_progress(
    callback: ArtworkProgressCallback | None,
    *,
    library: str,
    phase: ArtworkScanPhase,
    completed: int,
    total: int,
    message: str = "",
    current_title: str | None = None,
) -> None:
    """Emit progress when a caller supplied a callback."""

    if callback is None:
        return

    callback(
        ArtworkScanProgress(
            library=library,
            phase=phase,
            completed=completed,
            total=total,
            message=message,
            current_title=current_title,
        )
    )
