"""Media-server read adapter contracts."""

from .base import (
    MediaServer,
    MediaServerAuthenticationError,
    MediaServerCapability,
    MediaServerConnectionError,
    MediaServerError,
    MediaServerItemNotFoundError,
    UnsupportedMediaServerCapabilityError,
)

__all__ = [
    "MediaServer",
    "MediaServerAuthenticationError",
    "MediaServerCapability",
    "MediaServerConnectionError",
    "MediaServerError",
    "MediaServerItemNotFoundError",
    "UnsupportedMediaServerCapabilityError",
]
