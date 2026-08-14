from __future__ import annotations

import unittest
from datetime import date, datetime, timezone

from tv_metadata import (
    EpisodeState,
    NextEpisode,
    ShowLifecycle,
    ShowStatus,
)
from tv_metadata.presentation import (
    present_show_status,
)


LABELS = {
    "ended": "E N D E D",
    "cancelled": "C A N C E L L E D",
    "returning": "R E T U R N I N G",
    "airing": "AIRING",
    "season_finale": "SEASON FINALE",
    "mid_season_finale": "MID SEASON FINALE",
    "final_episode": "FINAL EPISODE",
    "season_premiere": "SEASON PREMIERE",
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


def present(
    status: ShowStatus,
    *,
    date_format: str = "DD/MM",
):
    return present_show_status(
        status,
        labels=LABELS,
        colors=COLORS,
        font="font.ttf",
        timezone_name="America/Chicago",
        date_format=date_format,
    )


class TVStatusPresentationTests(
    unittest.TestCase
):
    def test_ended(self):
        result = present(
            ShowStatus(
                lifecycle=ShowLifecycle.ENDED,
                lifecycle_source="sonarr",
            )
        )

        self.assertEqual(
            result,
            {
                "text_content": "E N D E D",
                "back_color": "#111111",
                "font": "font.ttf",
                "status_type": "ENDED",
            },
        )

    def test_returning_without_episode(self):
        result = present(
            ShowStatus(
                lifecycle=ShowLifecycle.RETURNING,
                lifecycle_source="sonarr",
            )
        )

        self.assertEqual(
            result["text_content"],
            "R E T U R N I N G",
        )
        self.assertEqual(
            result["status_type"],
            "RETURNING",
        )

    def test_unknown_without_episode_has_no_overlay(self):
        result = present(
            ShowStatus(
                lifecycle=ShowLifecycle.UNKNOWN,
                lifecycle_source=None,
            )
        )

        self.assertIsNone(result)

    def test_airing_date_only(self):
        result = present(
            ShowStatus(
                lifecycle=ShowLifecycle.RETURNING,
                lifecycle_source="tmdb",
                next_episode=NextEpisode(
                    source="tmdb",
                    season=2,
                    episode=5,
                    air_date=date(2026, 9, 27),
                    state=EpisodeState.AIRING,
                ),
            )
        )

        self.assertEqual(
            result["text_content"],
            "AIRING 27/09",
        )
        self.assertEqual(
            result["status_type"],
            "AIRING",
        )

    def test_mm_dd_date_format(self):
        result = present(
            ShowStatus(
                lifecycle=ShowLifecycle.RETURNING,
                lifecycle_source="tmdb",
                next_episode=NextEpisode(
                    source="tmdb",
                    air_date=date(2026, 9, 27),
                    state=EpisodeState.AIRING,
                ),
            ),
            date_format="MM/DD",
        )

        self.assertEqual(
            result["text_content"],
            "AIRING 09/27",
        )

    def test_timestamp_converts_to_configured_timezone(self):
        # Midnight UTC on 9/28 is still 9/27 in Chicago.
        result = present(
            ShowStatus(
                lifecycle=ShowLifecycle.RETURNING,
                lifecycle_source="tvmaze",
                next_episode=NextEpisode(
                    source="tvmaze",
                    air_date=date(2026, 9, 27),
                    air_datetime=datetime(
                        2026,
                        9,
                        28,
                        0,
                        0,
                        tzinfo=timezone.utc,
                    ),
                    state=EpisodeState.SEASON_PREMIERE,
                ),
            )
        )

        self.assertEqual(
            result["text_content"],
            "SEASON PREMIERE 27/09",
        )

    def test_local_timestamp_date_beats_provider_calendar_date(
        self,
    ):
        result = present(
            ShowStatus(
                lifecycle=ShowLifecycle.RETURNING,
                lifecycle_source="tmdb",
                next_episode=NextEpisode(
                    source="sonarr",
                    air_date=date(
                        2026,
                        9,
                        3,
                    ),
                    air_datetime=datetime(
                        2026,
                        9,
                        3,
                        2,
                        0,
                        tzinfo=timezone.utc,
                    ),
                    state=(
                        EpisodeState.SEASON_PREMIERE
                    ),
                ),
            )
        )

        # 02:00 UTC on September 3 is still September 2
        # in America/Chicago.
        self.assertEqual(
            result["text_content"],
            "SEASON PREMIERE 02/09",
        )


    def test_special_episode_states(self):
        cases = [
            (
                EpisodeState.SEASON_PREMIERE,
                "SEASON PREMIERE 01/09",
                "SEASON_PREMIERE",
            ),
            (
                EpisodeState.SEASON_FINALE,
                "SEASON FINALE 01/09",
                "SEASON_FINALE",
            ),
            (
                EpisodeState.MID_SEASON_FINALE,
                "MID SEASON FINALE 01/09",
                "MID_SEASON_FINALE",
            ),
            (
                EpisodeState.SERIES_FINALE,
                "FINAL EPISODE 01/09",
                "FINAL_EPISODE",
            ),
        ]

        for state, text, status_type in cases:
            with self.subTest(state=state):
                result = present(
                    ShowStatus(
                        lifecycle=ShowLifecycle.RETURNING,
                        lifecycle_source="sonarr",
                        next_episode=NextEpisode(
                            source="sonarr",
                            air_date=date(
                                2026,
                                9,
                                1,
                            ),
                            state=state,
                        ),
                    )
                )

                self.assertEqual(
                    result["text_content"],
                    text,
                )
                self.assertEqual(
                    result["status_type"],
                    status_type,
                )

    def test_future_episode_beats_ended_lifecycle(
        self,
    ):
        result = present(
            ShowStatus(
                lifecycle=ShowLifecycle.ENDED,
                lifecycle_source="tmdb",
                next_episode=NextEpisode(
                    source="sonarr",
                    air_date=date(
                        2026,
                        8,
                        14,
                    ),
                    state=EpisodeState.AIRING,
                ),
            )
        )

        self.assertEqual(
            result["text_content"],
            "AIRING 14/08",
        )

        self.assertEqual(
            result["status_type"],
            "AIRING",
        )


    def test_unknown_episode_state_defaults_to_airing(self):
        result = present(
            ShowStatus(
                lifecycle=ShowLifecycle.RETURNING,
                lifecycle_source="tmdb",
                next_episode=NextEpisode(
                    source="tmdb",
                    air_date=date(2026, 9, 1),
                    state=EpisodeState.UNKNOWN,
                ),
            )
        )

        self.assertEqual(
            result["text_content"],
            "AIRING 01/09",
        )
        self.assertEqual(
            result["status_type"],
            "AIRING",
        )

    def test_episode_without_date_falls_back_to_returning(self):
        result = present(
            ShowStatus(
                lifecycle=ShowLifecycle.RETURNING,
                lifecycle_source="tmdb",
                next_episode=NextEpisode(
                    source="tmdb",
                    state=EpisodeState.AIRING,
                ),
            )
        )

        self.assertEqual(
            result["text_content"],
            "R E T U R N I N G",
        )
        self.assertEqual(
            result["status_type"],
            "RETURNING",
        )


if __name__ == "__main__":
    unittest.main()
