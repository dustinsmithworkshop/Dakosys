from __future__ import annotations

import os
import unittest
from datetime import date
from unittest.mock import patch

from tv_metadata import (
    EpisodeState,
    NextEpisode,
    ShowLifecycle,
    ShowStatus,
)
from tv_status_tracker import (
    TVStatusTracker,
)


LABELS = {
    "ended": "E N D E D",
    "cancelled": "C A N C E L L E D",
    "returning": "R E T U R N I N G",
    "airing": "AIRING",
    "season_finale": "SEASON FINALE",
    "mid_season_finale": (
        "MID SEASON FINALE"
    ),
    "final_episode": "FINAL EPISODE",
    "season_premiere": (
        "SEASON PREMIERE"
    ),
}

COLORS = {
    "ENDED": "#111111",
    "CANCELLED": "#222222",
    "RETURNING": "#333333",
    "AIRING": "#444444",
    "SEASON_FINALE": "#555555",
    "MID_SEASON_FINALE": "#666666",
    "FINAL_EPISODE": "#777777",
    "SEASON_PREMIERE": "#888888",
}


class FakeGuid:
    def __init__(
        self,
        value,
    ):
        self.id = value


class FakeShow:
    title = "Example Show"
    year = 2025
    ratingKey = "123"

    guids = [
        FakeGuid("tmdb://100"),
        FakeGuid("tvdb://200"),
        FakeGuid("imdb://tt1234567"),
    ]


class CapturingResolver:
    def __init__(
        self,
        result,
    ):
        self.result = result
        self.identity = None

    def resolve(
        self,
        identity,
    ):
        self.identity = identity
        return self.result


def make_tracker(
    resolver,
):
    tracker = object.__new__(
        TVStatusTracker
    )

    tracker.config = {
        "plex": {
            "libraries": {
                "anime": [
                    "Anime",
                    "Cartoons",
                ],
                "tv": [
                    "TV",
                    "Cartoons",
                ],
            }
        },
        "date_format": "MM/DD",
    }

    tracker.metadata_resolver = resolver
    tracker.labels = LABELS
    tracker.colors = COLORS
    tracker.font_path_yaml = "font.ttf"
    tracker.timezone = (
        "America/Chicago"
    )

    return tracker


class TrackerMetadataTests(
    unittest.TestCase
):
    def test_builds_identity_with_library_roles(
        self,
    ):
        resolver = CapturingResolver(
            ShowStatus(
                lifecycle=(
                    ShowLifecycle.RETURNING
                ),
                lifecycle_source="sonarr",
            )
        )

        tracker = make_tracker(
            resolver
        )

        tracker.resolve_show_status(
            FakeShow(),
            "Cartoons",
        )

        identity = resolver.identity

        self.assertIsNotNone(
            identity
        )

        self.assertEqual(
            identity.tmdb_id,
            100,
        )

        self.assertEqual(
            identity.tvdb_id,
            200,
        )

        self.assertEqual(
            identity.imdb_id,
            "tt1234567",
        )

        self.assertEqual(
            identity.library_roles,
            (
                "anime",
                "tv",
            ),
        )

    def test_resolver_result_uses_legacy_presentation(
        self,
    ):
        resolver = CapturingResolver(
            ShowStatus(
                lifecycle=(
                    ShowLifecycle.RETURNING
                ),
                lifecycle_source="sonarr",
                next_episode=(
                    NextEpisode(
                        source="tmdb",
                        season=38,
                        episode=1,
                        air_date=date(
                            2026,
                            9,
                            27,
                        ),
                        state=(
                            EpisodeState.SEASON_PREMIERE
                        ),
                    )
                ),
            )
        )

        tracker = make_tracker(
            resolver
        )

        result = (
            tracker.resolve_show_info(
                FakeShow(),
                "TV",
            )
        )

        self.assertEqual(
            result["text_content"],
            "SEASON PREMIERE 09/27",
        )

        self.assertEqual(
            result["status_type"],
            "SEASON_PREMIERE",
        )

        self.assertEqual(
            result["font"],
            "font.ttf",
        )

    def test_disabled_resolver_returns_none(
        self,
    ):
        tracker = make_tracker(
            None
        )

        result = (
            tracker.resolve_show_status(
                FakeShow(),
                "TV",
            )
        )

        self.assertIsNone(result)

    def test_factory_provider_order(
        self,
    ):
        tracker = object.__new__(
            TVStatusTracker
        )

        with patch.dict(
            os.environ,
            {
                "SONARR_URL": (
                    "http://sonarr.example"
                ),
                "SONARR_API_KEY": (
                    "test-key"
                ),
                "TMDB_TOKEN": (
                    "test-token"
                ),
            },
            clear=True,
        ):
            resolver = (
                tracker
                ._build_metadata_resolver()
            )

        self.assertIsNotNone(
            resolver
        )

        self.assertEqual(
            [
                provider.name
                for provider
                in resolver.providers
            ],
            [
                "sonarr",
                "tmdb",
                "tvmaze",
            ],
        )

    def test_factory_stays_disabled_without_primary_provider(
        self,
    ):
        tracker = object.__new__(
            TVStatusTracker
        )

        with patch.dict(
            os.environ,
            {},
            clear=True,
        ):
            resolver = (
                tracker
                ._build_metadata_resolver()
            )

        self.assertIsNone(
            resolver
        )


if __name__ == "__main__":
    unittest.main()
