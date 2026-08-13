from __future__ import annotations

import unittest
from typing import Any

from tv_metadata import (
    EpisodeState,
    ShowIdentity,
    ShowLifecycle,
)
from tv_metadata.providers import SonarrProvider


class FakeResponse:
    def __init__(
        self,
        data: Any,
        *,
        status_code: int = 200,
    ) -> None:
        self._data = data
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(
                f"HTTP {self.status_code}"
            )

    def json(self) -> Any:
        return self._data


class FakeSession:
    def __init__(
        self,
        *,
        series: list[dict[str, Any]],
        episodes: dict[
            int,
            list[dict[str, Any]],
        ] | None = None,
    ) -> None:
        self.headers: dict[str, str] = {}
        self.series = series
        self.episodes = episodes or {}
        self.calls: list[
            tuple[
                str,
                dict[str, Any] | None,
            ]
        ] = []

    def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> FakeResponse:
        del timeout

        self.calls.append(
            (url, params)
        )

        if url.endswith(
            "/api/v3/series"
        ):
            return FakeResponse(
                self.series
            )

        if url.endswith(
            "/api/v3/episode"
        ):
            assert params is not None

            series_id = params[
                "seriesId"
            ]

            return FakeResponse(
                self.episodes.get(
                    series_id,
                    [],
                )
            )

        raise AssertionError(
            f"Unexpected URL: {url}"
        )


def identity(
    *,
    tvdb_id: int | None = 12345,
) -> ShowIdentity:
    return ShowIdentity(
        title="Example Show",
        year=2025,
        library="TV",
        plex_rating_key="1",
        tvdb_id=tvdb_id,
    )


def series_record(
    *,
    status: str = "continuing",
    next_airing: str | None = None,
) -> dict[str, Any]:
    return {
        "id": 42,
        "title": "Example Show",
        "tvdbId": 12345,
        "status": status,
        "nextAiring": next_airing,
    }


def episode_record(
    *,
    season: int = 2,
    episode: int = 5,
    air_datetime: str = (
        "2026-09-01T20:00:00Z"
    ),
    finale_type: str | None = None,
) -> dict[str, Any]:
    return {
        "id": 99,
        "seriesId": 42,
        "seasonNumber": season,
        "episodeNumber": episode,
        "title": "Example Episode",
        "airDateUtc": air_datetime,
        "finaleType": finale_type,
    }


class SonarrProviderTests(
    unittest.TestCase
):
    def make_provider(
        self,
        *,
        series: list[
            dict[str, Any]
        ],
        episodes: dict[
            int,
            list[dict[str, Any]],
        ] | None = None,
    ) -> tuple[
        SonarrProvider,
        FakeSession,
    ]:
        session = FakeSession(
            series=series,
            episodes=episodes,
        )

        provider = SonarrProvider(
            "http://sonarr.example",
            "test-key",
            session=session,
        )

        return provider, session

    def test_no_tvdb_id_does_not_call_sonarr(
        self,
    ) -> None:
        provider, session = (
            self.make_provider(
                series=[]
            )
        )

        result = provider.get_metadata(
            identity(tvdb_id=None)
        )

        self.assertFalse(
            result.matched
        )

        self.assertEqual(
            result.reason,
            "no_tvdb_id",
        )

        self.assertEqual(
            result.lifecycle,
            ShowLifecycle.UNKNOWN,
        )

        self.assertEqual(
            session.calls,
            [],
        )

    def test_exact_tvdb_not_found(
        self,
    ) -> None:
        provider, _ = (
            self.make_provider(
                series=[]
            )
        )

        result = provider.get_metadata(
            identity()
        )

        self.assertFalse(
            result.matched
        )

        self.assertEqual(
            result.reason,
            "not_found",
        )

    def test_ended_normalizes_to_ended(
        self,
    ) -> None:
        provider, _ = (
            self.make_provider(
                series=[
                    series_record(
                        status="ended"
                    )
                ]
            )
        )

        result = provider.get_metadata(
            identity()
        )

        self.assertTrue(
            result.matched
        )

        self.assertEqual(
            result.lifecycle,
            ShowLifecycle.ENDED,
        )

        self.assertIsNone(
            result.next_episode
        )

    def test_continuing_normalizes_to_returning(
        self,
    ) -> None:
        provider, _ = (
            self.make_provider(
                series=[
                    series_record(
                        status="continuing"
                    )
                ]
            )
        )

        result = provider.get_metadata(
            identity()
        )

        self.assertEqual(
            result.lifecycle,
            ShowLifecycle.RETURNING,
        )

    def test_unknown_status_stays_unknown(
        self,
    ) -> None:
        provider, _ = (
            self.make_provider(
                series=[
                    series_record(
                        status="mystery"
                    )
                ]
            )
        )

        result = provider.get_metadata(
            identity()
        )

        self.assertEqual(
            result.lifecycle,
            ShowLifecycle.UNKNOWN,
        )

    def test_episode_state_normalization(
        self,
    ) -> None:
        cases = [
            (
                "series",
                10,
                EpisodeState.SERIES_FINALE,
            ),
            (
                "season",
                10,
                EpisodeState.SEASON_FINALE,
            ),
            (
                "midseason",
                10,
                EpisodeState.MID_SEASON_FINALE,
            ),
            (
                None,
                1,
                EpisodeState.SEASON_PREMIERE,
            ),
            (
                None,
                5,
                EpisodeState.AIRING,
            ),
        ]

        for (
            finale_type,
            episode_number,
            expected,
        ) in cases:
            with self.subTest(
                finale_type=finale_type,
                episode=episode_number,
            ):
                next_airing = (
                    "2026-09-01T20:00:00Z"
                )

                episode = episode_record(
                    episode=episode_number,
                    air_datetime=next_airing,
                    finale_type=finale_type,
                )

                provider, _ = (
                    self.make_provider(
                        series=[
                            series_record(
                                next_airing=(
                                    next_airing
                                )
                            )
                        ],
                        episodes={
                            42: [episode]
                        },
                    )
                )

                result = (
                    provider.get_metadata(
                        identity()
                    )
                )

                self.assertIsNotNone(
                    result.next_episode
                )

                assert (
                    result.next_episode
                    is not None
                )

                self.assertEqual(
                    result.next_episode.state,
                    expected,
                )

                self.assertEqual(
                    result.next_episode.source,
                    "sonarr",
                )

                self.assertEqual(
                    result.next_episode.season,
                    2,
                )

                self.assertEqual(
                    result.next_episode.episode,
                    episode_number,
                )

                self.assertEqual(
                    result.next_episode.air_date.isoformat(),
                    "2026-09-01",
                )

                self.assertEqual(
                    result.next_episode.provider_episode_id,
                    "99",
                )

                self.assertEqual(
                    result.next_episode.raw_episode_type,
                    finale_type,
                )

    def test_next_airing_requires_exact_timestamp_match(
        self,
    ) -> None:
        provider, _ = (
            self.make_provider(
                series=[
                    series_record(
                        next_airing=(
                            "2026-09-01T20:00:00Z"
                        )
                    )
                ],
                episodes={
                    42: [
                        episode_record(
                            air_datetime=(
                                "2026-09-01T21:00:00Z"
                            )
                        )
                    ]
                },
            )
        )

        result = provider.get_metadata(
            identity()
        )

        self.assertTrue(
            result.matched
        )

        self.assertIsNone(
            result.next_episode
        )

        self.assertIn(
            "next_airing_episode_not_found",
            result.warnings,
        )

    def test_series_inventory_is_cached(
        self,
    ) -> None:
        provider, session = (
            self.make_provider(
                series=[
                    series_record()
                ]
            )
        )

        provider.get_metadata(
            identity()
        )

        provider.get_metadata(
            identity()
        )

        series_calls = [
            call
            for call in session.calls
            if call[0].endswith(
                "/api/v3/series"
            )
        ]

        self.assertEqual(
            len(series_calls),
            1,
        )


if __name__ == "__main__":
    unittest.main()
