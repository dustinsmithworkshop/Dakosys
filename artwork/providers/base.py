"""Artwork provider protocol."""

from __future__ import annotations

from typing import (
    Protocol,
    runtime_checkable,
)

from artwork.models import ArtworkSet
from artwork.search import ArtworkSearchRequest


@runtime_checkable
class ArtworkProvider(Protocol):
    """Provider capable of discovering cohesive artwork sets."""

    name: str

    def find_sets(
        self,
        request: ArtworkSearchRequest,
    ) -> list[ArtworkSet]:
        """Return candidate artwork sets for one Plex item."""

        ...
