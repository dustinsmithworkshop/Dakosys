"""Common contract for Artwork Manager providers."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from artwork.models import ArtworkSet, ShowArtworkState


@runtime_checkable
class ArtworkProvider(Protocol):
    """Contract implemented by external artwork providers."""

    name: str

    def find_sets(
        self,
        show: ShowArtworkState,
    ) -> list[ArtworkSet]:
        """Return artwork sets matching the supplied show."""
        ...
