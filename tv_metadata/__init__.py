"""TV metadata provider framework for Dakosys."""

from .identity import build_show_identity

from .models import (
    EpisodeState,
    NextAiringEntry,
    NextEpisode,
    ProviderResult,
    ShowIdentity,
    ShowLifecycle,
    ShowStatus,
)

__all__ = [
    "build_show_identity",
    "EpisodeState",
    "NextAiringEntry",
    "NextEpisode",
    "ProviderResult",
    "ShowIdentity",
    "ShowLifecycle",
    "ShowStatus",
]
