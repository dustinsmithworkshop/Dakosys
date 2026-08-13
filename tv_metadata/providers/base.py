"""Common contract for Dakosys TV metadata providers."""

from typing import Protocol, runtime_checkable

from tv_metadata.models import (
    ProviderResult,
    ShowIdentity,
)


@runtime_checkable
class TVMetadataProvider(Protocol):
    """Contract implemented by every TV metadata provider."""

    name: str

    def get_metadata(
        self,
        identity: ShowIdentity,
    ) -> ProviderResult:
        """Return normalized metadata for a Plex show."""
        ...
