from __future__ import annotations

import unittest
from typing import Any

from tv_metadata import (
    EpisodeState,
    ShowIdentity,
    ShowLifecycle,
)
from tv_metadata.providers import (
    TVmazeProvider,
)


class FakeResponse:
    def __init__(
        self,
        data: Any = None,
        *,
        status_code: int = 200,
        headers: dict[
            str,
            str,
        ] | None = None,
    ) -> None:
        self._data = (
            {}
            if data is None
            else data
        )

        self.status_code = status_code
        self.headers = headers or {}

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
        lookups: dict[
            tuple[str, str],
            int,
        ] | None = None,
        shows: dict[
            int,
            dict[str, Any],
        ] | None = None,
    ) -> None:
        self.headers: dict[str, str] = {}
        self.lookups = lookups or {}
        self.shows = shows or {}

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
        allow_redirects: bool = True,
    ) -> FakeResponse:
        del timeout
        del allow_redirects

        self.calls.append(
            (url, params)
        )

        if url.endswith(
            "/lookup/shows"
        ):
            assert params is not None

            if "thetvdb" in params:
                key = (
                    "tvdb",
                    str(params["thetvdb"]),
                )
            elif "imdb" in params:
                key = (
                    "imdb",
                    str(params["imdb"]),
                )
            else:
                raise AssertionError(
                    "Unexpected lookup params"
                )

            tvmaze_id = (
                self.lookups.get(key)
            )

            if tvmaze_id is None:
                return FakeResponse(
                    status_code=404
                )

            return FakeResponse(
                status_code=302,
                headers={
                    "Location": (
                        "https://"
                        "www.tvmaze.com/"
                        f"shows/{tvmaze_id}/"
                        "example-show"
                    )
                },
            )

        if "/shows/" in url:
            tvmaze_id = int(
                url.rsplit(
                    "/",
                    1,
                )[1]
            )

            show = self.shows.get(
                tvmaze_id
            )

            if show is None:
                return FakeResponse(
                    status_code=404
                )

            return FakeResponse(show)

        raise AssertionError(
            f"Unexpected URL: {url}"
        )


def identity(
    *,
    title: str = "Example Show",
    year: int | None = 2025,
    tvdb_id: int | None = 12345,
    imdb_id: str | None = None,
) -> ShowIdentity:
    return ShowIdentity(
        title=title,
        year=year,
        library="TV",
        plex_rating_key="1",
        tvdb_id=tvdb_id,
        imdb_id=imdb_id,
    )


def show_record(
    *,
    tvmaze_id: int = 50,
    name: str = "Example Show",
    premiered: str = "2025-01-01",
    status: str = "Running",
    next_episode: (
        dict[str, Any] | None
    ) = None,
) -> dict[str, Any]:
    embedded = {}

    if next_episode is not None:
        embedded[
            "nextepisode"
        ] = next_episode

    return {
        "id": tvmaze_id,
        "name": name,
        "premiered": premiered,
        "status": status,
        "_embedded": embedded,
    }


def episode_record(
    *,
    season: int = 2,
    episode: int | None = 5,
    airdate: str = "2026-09-01",
    airstamp: str = (
        "2026-09-01T20:00:00+00:00"
    ),
    episode_type: str = "regular",
) -> dict[str, Any]:
    return {
        "id": 99,
        "name": "Example Episode",
        "season": season,
        "number": episode,
        "airdate": airdate,
        "airstamp": airstamp,
        "type": episode_type,
    }


class TVmazeProviderTests(
    unittest.TestCase
):
    def make_provider(
        self,
        *,
        lookups: dict[
            tuple[str, str],
            int,
        ] | None = None,
        shows: dict[
            int,
            dict[str, Any],
        ] | None = None,
    ) -> tuple[
        TVmazeProvider,
        FakeSession,
    ]:
        session = FakeSession(
            lookups=lookups,
            shows=shows,
        )

        provider = TVmazeProvider(
            base_url=(
                "https://tvmaze.example"
            ),
            session=session,
        )

        return provider, session

    def test_no_supported_id_makes_no_request(
        self,
    ) -> None:
        provider, session = (
            self.make_provider()
        )

        result = provider.get_metadata(
            identity(
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

    def test_exact_tvdb_lookup(
        self,
    ) -> None:
        provider, _ = (
            self.make_provider(
                lookups={
                    (
                        "tvdb",
                        "12345",
                    ): 50,
                },
                shows={
                    50: show_record(),
                },
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
            "50",
        )

        self.assertEqual(
            result.lifecycle,
            ShowLifecycle.RETURNING,
        )

    def test_imdb_fallback_after_tvdb_miss(
        self,
    ) -> None:
        provider, session = (
            self.make_provider(
                lookups={
                    (
                        "imdb",
                        "tt1234567",
                    ): 75,
                },
                shows={
                    75: show_record(
                        tvmaze_id=75
                    ),
                },
            )
        )

        result = provider.get_metadata(
            identity(
                tvdb_id=99999,
                imdb_id="tt1234567",
            )
        )

        self.assertTrue(
            result.matched
        )

        self.assertEqual(
            result.provider_show_id,
            "75",
        )

        lookup_calls = [
            call
            for call in session.calls
            if call[0].endswith(
                "/lookup/shows"
            )
        ]

        self.assertEqual(
            len(lookup_calls),
            2,
        )

    def test_not_found(
        self,
    ) -> None:
        provider, _ = (
            self.make_provider()
        )

        result = provider.get_metadata(
            identity(
                imdb_id="tt1234567"
            )
        )

        self.assertFalse(
            result.matched
        )

        self.assertEqual(
            result.reason,
            "not_found",
        )

    def test_lifecycle_normalization(
        self,
    ) -> None:
        cases = [
            (
                "Running",
                ShowLifecycle.RETURNING,
            ),
            (
                "Ended",
                ShowLifecycle.ENDED,
            ),
            (
                "To Be Determined",
                ShowLifecycle.UNKNOWN,
            ),
        ]

        for status, expected in cases:
            with self.subTest(
                status=status
            ):
                provider, _ = (
                    self.make_provider(
                        lookups={
                            (
                                "tvdb",
                                "12345",
                            ): 50,
                        },
                        shows={
                            50: show_record(
                                status=status
                            )
                        },
                    )
                )

                result = (
                    provider.get_metadata(
                        identity()
                    )
                )

                self.assertEqual(
                    result.lifecycle,
                    expected,
                )

    def test_episode_normalization(
        self,
    ) -> None:
        provider, _ = (
            self.make_provider(
                lookups={
                    (
                        "tvdb",
                        "12345",
                    ): 50,
                },
                shows={
                    50: show_record(
                        next_episode=(
                            episode_record()
                        )
                    )
                },
            )
        )

        result = provider.get_metadata(
            identity()
        )

        self.assertIsNotNone(
            result.next_episode
        )

        assert (
            result.next_episode
            is not None
        )

        self.assertEqual(
            result.next_episode.source,
            "tvmaze",
        )

        self.assertEqual(
            result.next_episode.season,
            2,
        )

        self.assertEqual(
            result.next_episode.episode,
            5,
        )

        self.assertEqual(
            result.next_episode.air_date.isoformat(),
            "2026-09-01",
        )

        self.assertEqual(
            result.next_episode.air_datetime.isoformat(),
            "2026-09-01T20:00:00+00:00",
        )

        self.assertEqual(
            result.next_episode.state,
            EpisodeState.AIRING,
        )

        self.assertEqual(
            result.next_episode.provider_episode_id,
            "99",
        )

        self.assertEqual(
            result.next_episode.raw_episode_type,
            "regular",
        )

    def test_episode_one_is_season_premiere(
        self,
    ) -> None:
        provider, _ = (
            self.make_provider(
                lookups={
                    (
                        "tvdb",
                        "12345",
                    ): 50,
                },
                shows={
                    50: show_record(
                        next_episode=(
                            episode_record(
                                episode=1
                            )
                        )
                    )
                },
            )
        )

        result = provider.get_metadata(
            identity()
        )

        assert (
            result.next_episode
            is not None
        )

        self.assertEqual(
            result.next_episode.state,
            EpisodeState.SEASON_PREMIERE,
        )

    def test_null_episode_number_is_allowed(
        self,
    ) -> None:
        provider, _ = (
            self.make_provider(
                lookups={
                    (
                        "tvdb",
                        "12345",
                    ): 50,
                },
                shows={
                    50: show_record(
                        next_episode=(
                            episode_record(
                                episode=None
                            )
                        )
                    )
                },
            )
        )

        result = provider.get_metadata(
            identity()
        )

        assert (
            result.next_episode
            is not None
        )

        self.assertIsNone(
            result.next_episode.episode
        )

        self.assertEqual(
            result.next_episode.state,
            EpisodeState.AIRING,
        )

    def test_identity_differences_are_warnings(
        self,
    ) -> None:
        provider, _ = (
            self.make_provider(
                lookups={
                    (
                        "tvdb",
                        "12345",
                    ): 50,
                },
                shows={
                    50: show_record(
                        name="Different Show",
                        premiered=(
                            "2026-01-01"
                        ),
                    )
                },
            )
        )

        result = provider.get_metadata(
            identity(
                title="Example Show",
                year=2025,
            )
        )

        self.assertIn(
            "title_differs",
            result.warnings,
        )

        self.assertIn(
            "year_differs:2025->2026",
            result.warnings,
        )

    def test_suspicious_tvdb_match_crosschecks_imdb(
        self,
    ) -> None:
        provider, session = (
            self.make_provider(
                lookups={
                    (
                        "tvdb",
                        "12345",
                    ): 50,
                    (
                        "imdb",
                        "tt1234567",
                    ): 50,
                },
                shows={
                    50: show_record(
                        name="Different Show",
                    )
                },
            )
        )

        result = provider.get_metadata(
            identity(
                imdb_id="tt1234567"
            )
        )

        self.assertTrue(
            result.matched
        )

        self.assertIn(
            "title_differs",
            result.warnings,
        )

        self.assertFalse(
            any(
                warning.startswith(
                    "identity_conflict:"
                )
                for warning
                in result.warnings
            )
        )

        imdb_calls = [
            call
            for call in session.calls
            if (
                call[1]
                and call[1].get(
                    "imdb"
                )
                == "tt1234567"
            )
        ]

        self.assertEqual(
            len(imdb_calls),
            1,
        )

    def test_cross_id_conflict_is_reported(
        self,
    ) -> None:
        provider, _ = (
            self.make_provider(
                lookups={
                    (
                        "tvdb",
                        "436780",
                    ): 85212,
                    (
                        "imdb",
                        "tt1234567",
                    ): 17194,
                },
                shows={
                    85212: show_record(
                        tvmaze_id=85212,
                        name=(
                            "New Panty & "
                            "Stocking with "
                            "Garterbelt"
                        ),
                        premiered=(
                            "2025-07-10"
                        ),
                    )
                },
            )
        )

        result = provider.get_metadata(
            identity(
                title=(
                    "Panty & Stocking "
                    "with Garterbelt"
                ),
                year=2010,
                tvdb_id=436780,
                imdb_id="tt1234567",
            )
        )

        self.assertTrue(
            result.matched
        )

        self.assertEqual(
            result.provider_show_id,
            "85212",
        )

        self.assertIn(
            (
                "identity_conflict:"
                "tvdb=85212,"
                "imdb=17194"
            ),
            result.warnings,
        )


if __name__ == "__main__":
    unittest.main()
