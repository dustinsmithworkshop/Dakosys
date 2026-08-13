from __future__ import annotations

import unittest
from typing import Any

from tv_metadata import (
    EpisodeState,
    ShowIdentity,
    ShowLifecycle,
)
from tv_metadata.providers import TMDBProvider


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
        shows: dict[
            int,
            dict[str, Any],
        ] | None = None,
        external: dict[
            tuple[str, str],
            list[dict[str, Any]],
        ] | None = None,
    ) -> None:
        self.headers: dict[str, str] = {}
        self.shows = shows or {}
        self.external = external or {}

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

        if "/tv/" in url:
            tmdb_id = int(
                url.rsplit("/", 1)[1]
            )

            show = self.shows.get(
                tmdb_id
            )

            if show is None:
                return FakeResponse(
                    {},
                    status_code=404,
                )

            return FakeResponse(show)

        if "/find/" in url:
            value = url.rsplit(
                "/",
                1,
            )[1]

            assert params is not None

            source = params[
                "external_source"
            ]

            return FakeResponse(
                {
                    "tv_results": (
                        self.external.get(
                            (
                                source,
                                value,
                            ),
                            [],
                        )
                    )
                }
            )

        raise AssertionError(
            f"Unexpected URL: {url}"
        )


def identity(
    *,
    title: str = "Example Show",
    year: int | None = 2025,
    tmdb_id: int | None = 100,
    tvdb_id: int | None = None,
    imdb_id: str | None = None,
) -> ShowIdentity:
    return ShowIdentity(
        title=title,
        year=year,
        library="TV",
        plex_rating_key="1",
        tmdb_id=tmdb_id,
        tvdb_id=tvdb_id,
        imdb_id=imdb_id,
    )


def show_record(
    *,
    tmdb_id: int = 100,
    name: str = "Example Show",
    original_name: str | None = None,
    first_air_date: str = "2025-01-01",
    status: str = "Returning Series",
    next_episode: (
        dict[str, Any] | None
    ) = None,
) -> dict[str, Any]:
    return {
        "id": tmdb_id,
        "name": name,
        "original_name": (
            original_name
            if original_name is not None
            else name
        ),
        "first_air_date": first_air_date,
        "status": status,
        "next_episode_to_air": (
            next_episode
        ),
    }


def episode_record(
    *,
    season: int = 2,
    episode: int = 5,
    air_date: str = "2026-09-01",
    episode_type: str = "standard",
) -> dict[str, Any]:
    return {
        "id": 999,
        "name": "Example Episode",
        "season_number": season,
        "episode_number": episode,
        "air_date": air_date,
        "episode_type": episode_type,
    }


class TMDBProviderTests(
    unittest.TestCase
):
    def make_provider(
        self,
        *,
        shows: dict[
            int,
            dict[str, Any],
        ] | None = None,
        external: dict[
            tuple[str, str],
            list[dict[str, Any]],
        ] | None = None,
    ) -> tuple[
        TMDBProvider,
        FakeSession,
    ]:
        session = FakeSession(
            shows=shows,
            external=external,
        )

        provider = TMDBProvider(
            "test-token",
            base_url=(
                "https://tmdb.example/3"
            ),
            session=session,
        )

        return provider, session

    def test_direct_tmdb_id_bypasses_find(
        self,
    ) -> None:
        provider, session = (
            self.make_provider(
                shows={
                    100: show_record()
                }
            )
        )

        result = provider.get_metadata(
            identity()
        )

        self.assertTrue(
            result.matched
        )

        self.assertEqual(
            result.provider_show_id,
            "100",
        )

        find_calls = [
            call
            for call in session.calls
            if "/find/" in call[0]
        ]

        self.assertEqual(
            find_calls,
            [],
        )

    def test_ended_and_canceled_normalize_to_ended(
        self,
    ) -> None:
        for status in [
            "Ended",
            "Canceled",
            "Cancelled",
        ]:
            with self.subTest(
                status=status
            ):
                provider, _ = (
                    self.make_provider(
                        shows={
                            100: show_record(
                                status=status
                            )
                        }
                    )
                )

                result = (
                    provider.get_metadata(
                        identity()
                    )
                )

                self.assertEqual(
                    result.lifecycle,
                    ShowLifecycle.ENDED,
                )

    def test_returning_states_normalize_to_returning(
        self,
    ) -> None:
        for status in [
            "Returning Series",
            "In Production",
        ]:
            with self.subTest(
                status=status
            ):
                provider, _ = (
                    self.make_provider(
                        shows={
                            100: show_record(
                                status=status
                            )
                        }
                    )
                )

                result = (
                    provider.get_metadata(
                        identity()
                    )
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
                shows={
                    100: show_record(
                        status="Planned"
                    )
                }
            )
        )

        result = provider.get_metadata(
            identity()
        )

        self.assertEqual(
            result.lifecycle,
            ShowLifecycle.UNKNOWN,
        )

    def test_tvdb_external_id_fallback(
        self,
    ) -> None:
        provider, session = (
            self.make_provider(
                shows={
                    456: show_record(
                        tmdb_id=456
                    )
                },
                external={
                    (
                        "tvdb_id",
                        "71663",
                    ): [
                        {"id": 456}
                    ]
                },
            )
        )

        result = provider.get_metadata(
            identity(
                tmdb_id=None,
                tvdb_id=71663,
            )
        )

        self.assertTrue(
            result.matched
        )

        self.assertEqual(
            result.provider_show_id,
            "456",
        )

        self.assertTrue(
            any(
                "/find/71663"
                in call[0]
                for call in session.calls
            )
        )

    def test_imdb_fallback_after_tvdb_miss(
        self,
    ) -> None:
        provider, _ = (
            self.make_provider(
                shows={
                    200: show_record(
                        tmdb_id=200
                    )
                },
                external={
                    (
                        "imdb_id",
                        "tt1234567",
                    ): [
                        {"id": 200}
                    ]
                },
            )
        )

        result = provider.get_metadata(
            identity(
                tmdb_id=None,
                tvdb_id=99999,
                imdb_id="tt1234567",
            )
        )

        self.assertTrue(
            result.matched
        )

        self.assertEqual(
            result.provider_show_id,
            "200",
        )

    def test_no_supported_id_makes_no_request(
        self,
    ) -> None:
        provider, session = (
            self.make_provider()
        )

        result = provider.get_metadata(
            identity(
                tmdb_id=None,
                tvdb_id=None,
                imdb_id=None,
            )
        )

        self.assertFalse(
            result.matched
        )

        self.assertEqual(
            result.reason,
            "no_supported_id",
        )

        self.assertEqual(
            session.calls,
            [],
        )

    def test_external_lookup_failure(
        self,
    ) -> None:
        provider, _ = (
            self.make_provider()
        )

        result = provider.get_metadata(
            identity(
                tmdb_id=None,
                tvdb_id=99999,
                imdb_id="tt9999999",
            )
        )

        self.assertFalse(
            result.matched
        )

        self.assertEqual(
            result.reason,
            "external_id_lookup_failed",
        )

    def test_identity_differences_are_warnings(
        self,
    ) -> None:
        provider, _ = (
            self.make_provider(
                shows={
                    100: show_record(
                        name="Different Name",
                        first_air_date=(
                            "2026-01-01"
                        ),
                    )
                }
            )
        )

        result = provider.get_metadata(
            identity(
                title="Example Show",
                year=2025,
            )
        )

        self.assertTrue(
            result.matched
        )

        self.assertIn(
            "title_differs",
            result.warnings,
        )

        self.assertIn(
            "year_differs:2025->2026",
            result.warnings,
        )

    def test_episode_state_normalization(
        self,
    ) -> None:
        cases = [
            (
                "finale",
                10,
                EpisodeState.SEASON_FINALE,
            ),
            (
                "mid_season",
                10,
                EpisodeState.MID_SEASON_FINALE,
            ),
            (
                "series_finale",
                10,
                EpisodeState.SERIES_FINALE,
            ),
            (
                "standard",
                1,
                EpisodeState.SEASON_PREMIERE,
            ),
            (
                "standard",
                5,
                EpisodeState.AIRING,
            ),
        ]

        for (
            episode_type,
            episode_number,
            expected,
        ) in cases:
            with self.subTest(
                episode_type=episode_type,
                episode=episode_number,
            ):
                provider, _ = (
                    self.make_provider(
                        shows={
                            100: show_record(
                                next_episode=(
                                    episode_record(
                                        episode=(
                                            episode_number
                                        ),
                                        episode_type=(
                                            episode_type
                                        ),
                                    )
                                )
                            )
                        }
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
                    "tmdb",
                )

                self.assertEqual(
                    result.next_episode.air_date.isoformat(),
                    "2026-09-01",
                )

                self.assertIsNone(
                    result.next_episode.air_datetime
                )

                self.assertEqual(
                    result.next_episode.provider_episode_id,
                    "999",
                )

                self.assertEqual(
                    result.next_episode.raw_episode_type,
                    episode_type,
                )

    def test_direct_tmdb_not_found(
        self,
    ) -> None:
        provider, _ = (
            self.make_provider()
        )

        result = provider.get_metadata(
            identity(
                tmdb_id=999999
            )
        )

        self.assertFalse(
            result.matched
        )

        self.assertEqual(
            result.reason,
            "not_found",
        )


if __name__ == "__main__":
    unittest.main()
