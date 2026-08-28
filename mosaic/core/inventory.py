"""Platform-neutral inventory records for MOSAIC media-server adapters."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LibraryKind(str, Enum):
    """Normalized high-level type of a media library."""

    MOVIES = "movies"
    SHOWS = "shows"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class MediaItemKind(str, Enum):
    """Normalized type of an item returned by a media server."""

    MOVIE = "movie"
    SHOW = "show"
    SEASON = "season"
    EPISODE = "episode"


class ImageType(str, Enum):
    """Common image roles used by MOSAIC read adapters."""

    PRIMARY = "primary"
    BACKDROP = "backdrop"
    THUMB = "thumb"
    BANNER = "banner"
    LOGO = "logo"


@dataclass(frozen=True)
class MediaLibrary:
    """One normalized media-server library."""

    server_library_id: str
    name: str
    kind: LibraryKind = LibraryKind.UNKNOWN


@dataclass(frozen=True)
class MediaItem:
    """One normalized media item.

    ``server_item_id`` is deliberately only a server-local identifier.
    Cross-server identity and migration semantics are defined by M4-04 rather
    than being guessed by this inventory contract.
    """

    server_item_id: str
    library_id: str
    kind: MediaItemKind
    title: str

    year: int | None = None
    parent_id: str | None = None
    season_number: int | None = None
    episode_number: int | None = None
    path: str | None = None


@dataclass(frozen=True)
class ExternalId:
    """One exact external-provider identifier attached to an item.

    A sequence is used instead of a provider->value mapping so adapters can
    preserve multiple exact candidates for the same provider without losing
    evidence. M4-04 will define how these records participate in durable
    cross-server identity.
    """

    provider: str
    value: str


@dataclass(frozen=True)
class MediaSource:
    """Normalized physical/logical media source attached to an item."""

    source_id: str | None = None
    path: str | None = None
    size_bytes: int | None = None
    container: str | None = None


@dataclass(frozen=True)
class ImageInfo:
    """Normalized metadata about one currently-applied image."""

    image_type: ImageType
    tag: str | None = None
    path: str | None = None
    width: int | None = None
    height: int | None = None
    size_bytes: int | None = None
