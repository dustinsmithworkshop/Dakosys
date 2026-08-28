"""Platform-neutral media-server read contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import FrozenSet, Sequence

from mosaic.core import (
    ExternalId,
    ImageInfo,
    ImageType,
    MediaItem,
    MediaLibrary,
    MediaSource,
)


class MediaServerCapability(str, Enum):
    """Read capabilities an adapter may expose."""

    LIBRARIES = "libraries"
    MOVIES = "movies"
    SHOWS = "shows"
    SEASONS = "seasons"
    EPISODES = "episodes"
    ITEM_DETAILS = "item_details"
    EXTERNAL_IDS = "external_ids"
    MEDIA_SOURCES = "media_sources"
    IMAGE_INFO = "image_info"
    IMAGE_CONTENT = "image_content"


class MediaServerError(RuntimeError):
    """Base normalized error raised at the media-server boundary."""

    def __init__(
        self,
        message: str,
        *,
        server_type: str | None = None,
        server_instance: str | None = None,
        operation: str | None = None,
    ) -> None:
        super().__init__(message)
        self.server_type = server_type
        self.server_instance = server_instance
        self.operation = operation


class MediaServerConnectionError(MediaServerError):
    """The configured server could not be reached."""


class MediaServerAuthenticationError(MediaServerError):
    """The configured server rejected authentication."""


class MediaServerItemNotFoundError(MediaServerError):
    """A requested library item no longer exists on the server."""


class UnsupportedMediaServerCapabilityError(MediaServerError):
    """The adapter does not support a requested read capability."""

    def __init__(
        self,
        capability: MediaServerCapability,
        *,
        server_type: str,
        server_instance: str,
    ) -> None:
        self.capability = capability
        super().__init__(
            (
                f"{server_type} server {server_instance!r} does not support "
                f"the {capability.value!r} capability"
            ),
            server_type=server_type,
            server_instance=server_instance,
            operation=capability.value,
        )


class MediaServer(ABC):
    """Read-only boundary between MOSAIC core logic and a media server.

    Adapters translate platform-specific API objects into the normalized
    records in :mod:`mosaic.core`. Mutation belongs to output adapters and is
    intentionally absent from this interface.
    """

    @property
    @abstractmethod
    def server_type(self) -> str:
        """Stable adapter type such as ``plex`` or ``jellyfin``."""

    @property
    @abstractmethod
    def instance_name(self) -> str:
        """Configured server-instance name, unique within a MOSAIC run."""

    @property
    @abstractmethod
    def capabilities(self) -> FrozenSet[MediaServerCapability]:
        """Capabilities implemented by this adapter instance."""

    def supports(self, capability: MediaServerCapability) -> bool:
        """Return whether this adapter advertises ``capability``."""

        return capability in self.capabilities

    def require_capability(
        self,
        capability: MediaServerCapability,
    ) -> None:
        """Fail with a normalized error if ``capability`` is unavailable."""

        if not self.supports(capability):
            raise UnsupportedMediaServerCapabilityError(
                capability,
                server_type=self.server_type,
                server_instance=self.instance_name,
            )

    @abstractmethod
    def list_libraries(self) -> Sequence[MediaLibrary]:
        """Return normalized libraries visible to this server connection."""

    @abstractmethod
    def list_movies(self, library_id: str) -> Sequence[MediaItem]:
        """Return normalized movies from one library."""

    @abstractmethod
    def list_shows(self, library_id: str) -> Sequence[MediaItem]:
        """Return normalized shows from one library."""

    @abstractmethod
    def list_seasons(self, show_id: str) -> Sequence[MediaItem]:
        """Return normalized seasons belonging to one show."""

    @abstractmethod
    def list_episodes(self, show_id: str) -> Sequence[MediaItem]:
        """Return normalized episodes belonging to one show."""

    @abstractmethod
    def get_item(self, item_id: str) -> MediaItem:
        """Return one item or raise ``MediaServerItemNotFoundError``."""

    @abstractmethod
    def get_external_ids(self, item_id: str) -> Sequence[ExternalId]:
        """Return exact provider-ID evidence for an item.

        Multiple records for the same provider are allowed and must not be
        collapsed by the adapter. M4-04 owns the stronger cross-server
        identity and candidate-selection semantics.
        """

    @abstractmethod
    def get_media_sources(self, item_id: str) -> Sequence[MediaSource]:
        """Return normalized media sources for an item."""

    @abstractmethod
    def get_image_info(
        self,
        item_id: str,
        image_type: ImageType,
    ) -> ImageInfo | None:
        """Return metadata for a currently-applied image, if present."""

    @abstractmethod
    def get_image(
        self,
        item_id: str,
        image_type: ImageType,
    ) -> bytes:
        """Return the bytes of a currently-applied image."""
