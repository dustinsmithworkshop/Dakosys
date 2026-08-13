"""Presentation adapter for Dakosys TV status overlays."""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

from .models import (
    EpisodeState,
    ShowLifecycle,
    ShowStatus,
)


def _episode_air_date(
    status: ShowStatus,
    timezone_name: str,
) -> date | None:
    episode = status.next_episode

    if episode is None:
        return None

    # Prefer the actual timestamp when a provider supplies one.
    # This preserves the existing Dakosys behavior of converting
    # UTC airing times into the configured local timezone.
    if episode.air_datetime is not None:
        return episode.air_datetime.astimezone(
            ZoneInfo(timezone_name)
        ).date()

    return episode.air_date


def _format_date(
    value: date,
    date_format: str,
) -> str:
    if date_format.upper() == "MM/DD":
        return value.strftime("%m/%d")

    return value.strftime("%d/%m")


def present_show_status(
    status: ShowStatus,
    *,
    labels: dict[str, str],
    colors: dict[str, str],
    font: str,
    timezone_name: str,
    date_format: str = "DD/MM",
) -> dict[str, str] | None:
    """Translate normalized metadata into legacy tracker presentation.

    Returns the existing structure consumed by tv_status_tracker:

        {
            "text_content": ...,
            "back_color": ...,
            "font": ...,
            "status_type": ...,
        }

    UNKNOWN lifecycle with no upcoming episode produces no overlay.
    """

    episode = status.next_episode

    if status.lifecycle is ShowLifecycle.ENDED:
        return {
            "text_content": labels["ended"],
            "back_color": colors["ENDED"],
            "font": font,
            "status_type": "ENDED",
        }

    if episode is None:
        if status.lifecycle is ShowLifecycle.RETURNING:
            return {
                "text_content": labels["returning"],
                "back_color": colors["RETURNING"],
                "font": font,
                "status_type": "RETURNING",
            }

        return None

    air_date = _episode_air_date(
        status,
        timezone_name,
    )

    # An episode without a usable air date cannot reproduce
    # the existing dated overlay. Fall back to RETURNING when
    # we at least know the series is active.
    if air_date is None:
        if status.lifecycle is ShowLifecycle.RETURNING:
            return {
                "text_content": labels["returning"],
                "back_color": colors["RETURNING"],
                "font": font,
                "status_type": "RETURNING",
            }

        return None

    date_text = _format_date(
        air_date,
        date_format,
    )

    presentation = {
        EpisodeState.SEASON_FINALE: (
            "season_finale",
            "SEASON_FINALE",
        ),
        EpisodeState.MID_SEASON_FINALE: (
            "mid_season_finale",
            "MID_SEASON_FINALE",
        ),
        EpisodeState.SERIES_FINALE: (
            "final_episode",
            "FINAL_EPISODE",
        ),
        EpisodeState.SEASON_PREMIERE: (
            "season_premiere",
            "SEASON_PREMIERE",
        ),
    }

    label_key, status_type = presentation.get(
        episode.state,
        (
            "airing",
            "AIRING",
        ),
    )

    return {
        "text_content": (
            f"{labels[label_key]} {date_text}"
        ),
        "back_color": colors[status_type],
        "font": font,
        "status_type": status_type,
    }
