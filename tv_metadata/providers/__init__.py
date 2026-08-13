"""TV metadata provider interfaces and implementations."""

from typing import Protocol, runtime_checkable

from ..models import ProviderResult, ShowIdentity
from .sonarr import SonarrProvider


@runtime_checkable
class TVMetadataProvider(Protocol):
    """Contract implemented by TV metadata providers."""

    name: str

    def get_metadata(
        self,
        identity: ShowIdentity,
    ) -> ProviderResult:
        """Return metadata for one Plex show."""
        ...


__all__ = [
    "SonarrProvider",
    "TVMetadataProvider",
]
