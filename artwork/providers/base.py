"""Artwork provider protocol."""

from __future__ import annotations

from typing import (
    Protocol,
    runtime_checkable,
)

from artwork.models import ArtworkSet
from artwork.search import ArtworkSearchRequest


class ArtworkProviderUnavailableError(
    RuntimeError
):
    """Provider cannot supply this specific item.

    The provider itself may still be healthy. Callers should preserve
    existing durable state or continue with configured fallback rather
    than treating this as a library-wide provider failure.
    """


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
