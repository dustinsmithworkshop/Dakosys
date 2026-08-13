from __future__ import annotations

import unittest
from datetime import date

from tv_metadata import (
    EpisodeState,
    NextEpisode,
    ProviderResult,
    ShowIdentity,
    ShowLifecycle,
)
from tv_metadata.resolver import (
    TVMetadataResolver,
)


def identity() -> ShowIdentity:
    return ShowIdentity(
        title="Example Show",
        year=2025,
        library="TV",
        plex_rating_key="123",
        tmdb_id=100,
        tvdb_id=200,
        imdb_id="tt1234567",
    )


def next_episode(
    source: str,
) -> NextEpisode:
    return NextEpisode(
        source=source,
        season=2,
        episode=1,
        air_date=date(
            2026,
            9,
            1,
        ),
        state=(
            EpisodeState.SEASON_PREMIERE
        ),
    )


class StubProvider:
    def __init__(
        self,
        name: str,
        result: ProviderResult,
    ) -> None:
        self.name = name
        self.result = result
        self.calls = 0

    def get_metadata(
        self,
        show: ShowIdentity,
    ) -> ProviderResult:
        del show

        self.calls += 1

        return self.result


def result(
    source: str,
    *,
    matched: bool = True,
    lifecycle: ShowLifecycle = (
        ShowLifecycle.UNKNOWN
    ),
    episode: NextEpisode | None = None,
    warnings: tuple[str, ...] = (),
) -> ProviderResult:
    return ProviderResult(
        source=source,
        matched=matched,
        lifecycle=lifecycle,
        next_episode=episode,
        warnings=warnings,
    )


class TVMetadataResolverTests(
    unittest.TestCase
):
    def test_complete_primary_result_short_circuits(
        self,
    ) -> None:
        sonarr = StubProvider(
            "sonarr",
            result(
                "sonarr",
                lifecycle=(
                    ShowLifecycle.RETURNING
                ),
                episode=next_episode(
                    "sonarr"
                ),
            ),
        )

        tmdb = StubProvider(
            "tmdb",
            result(
                "tmdb",
                lifecycle=(
                    ShowLifecycle.RETURNING
                ),
                episode=next_episode(
                    "tmdb"
                ),
            ),
        )

        resolver = TVMetadataResolver(
            [sonarr, tmdb]
        )

        resolved = resolver.resolve(
            identity()
        )

        self.assertEqual(
            resolved.lifecycle,
            ShowLifecycle.RETURNING,
        )

        self.assertEqual(
            resolved.lifecycle_source,
            "sonarr",
        )

        assert (
            resolved.next_episode
            is not None
        )

        self.assertEqual(
            resolved.next_episode.source,
            "sonarr",
        )

        self.assertEqual(
            sonarr.calls,
            1,
        )

        self.assertEqual(
            tmdb.calls,
            0,
        )

    def test_fallback_can_supply_next_episode(
        self,
    ) -> None:
        sonarr = StubProvider(
            "sonarr",
            result(
                "sonarr",
                lifecycle=(
                    ShowLifecycle.RETURNING
                ),
            ),
        )

        tmdb = StubProvider(
            "tmdb",
            result(
                "tmdb",
                lifecycle=(
                    ShowLifecycle.RETURNING
                ),
                episode=next_episode(
                    "tmdb"
                ),
            ),
        )

        resolver = TVMetadataResolver(
            [sonarr, tmdb]
        )

        resolved = resolver.resolve(
            identity()
        )

        self.assertEqual(
            resolved.lifecycle_source,
            "sonarr",
        )

        assert (
            resolved.next_episode
            is not None
        )

        self.assertEqual(
            resolved.next_episode.source,
            "tmdb",
        )

        self.assertEqual(
            sonarr.calls,
            1,
        )

        self.assertEqual(
            tmdb.calls,
            1,
        )

    def test_unmatched_provider_falls_through(
        self,
    ) -> None:
        sonarr = StubProvider(
            "sonarr",
            result(
                "sonarr",
                matched=False,
            ),
        )

        tmdb = StubProvider(
            "tmdb",
            result(
                "tmdb",
                lifecycle=(
                    ShowLifecycle.RETURNING
                ),
                episode=next_episode(
                    "tmdb"
                ),
            ),
        )

        resolver = TVMetadataResolver(
            [sonarr, tmdb]
        )

        resolved = resolver.resolve(
            identity()
        )

        self.assertEqual(
            resolved.lifecycle_source,
            "tmdb",
        )

        assert (
            resolved.next_episode
            is not None
        )

        self.assertEqual(
            resolved.next_episode.source,
            "tmdb",
        )

    def test_ended_primary_stops_fallback(
        self,
    ) -> None:
        sonarr = StubProvider(
            "sonarr",
            result(
                "sonarr",
                lifecycle=(
                    ShowLifecycle.ENDED
                ),
            ),
        )

        tmdb = StubProvider(
            "tmdb",
            result(
                "tmdb",
                lifecycle=(
                    ShowLifecycle.RETURNING
                ),
                episode=next_episode(
                    "tmdb"
                ),
            ),
        )

        resolver = TVMetadataResolver(
            [sonarr, tmdb]
        )

        resolved = resolver.resolve(
            identity()
        )

        self.assertEqual(
            resolved.lifecycle,
            ShowLifecycle.ENDED,
        )

        self.assertEqual(
            resolved.lifecycle_source,
            "sonarr",
        )

        self.assertIsNone(
            resolved.next_episode
        )

        self.assertEqual(
            tmdb.calls,
            0,
        )

    def test_unknown_lifecycle_falls_through(
        self,
    ) -> None:
        sonarr = StubProvider(
            "sonarr",
            result(
                "sonarr",
                lifecycle=(
                    ShowLifecycle.UNKNOWN
                ),
            ),
        )

        tmdb = StubProvider(
            "tmdb",
            result(
                "tmdb",
                lifecycle=(
                    ShowLifecycle.RETURNING
                ),
                episode=next_episode(
                    "tmdb"
                ),
            ),
        )

        resolver = TVMetadataResolver(
            [sonarr, tmdb]
        )

        resolved = resolver.resolve(
            identity()
        )

        self.assertEqual(
            resolved.lifecycle,
            ShowLifecycle.RETURNING,
        )

        self.assertEqual(
            resolved.lifecycle_source,
            "tmdb",
        )

    def test_primary_episode_survives_lifecycle_fallback(
        self,
    ) -> None:
        first = StubProvider(
            "first",
            result(
                "first",
                lifecycle=(
                    ShowLifecycle.UNKNOWN
                ),
                episode=next_episode(
                    "first"
                ),
            ),
        )

        second = StubProvider(
            "second",
            result(
                "second",
                lifecycle=(
                    ShowLifecycle.RETURNING
                ),
            ),
        )

        resolver = TVMetadataResolver(
            [first, second]
        )

        resolved = resolver.resolve(
            identity()
        )

        self.assertEqual(
            resolved.lifecycle_source,
            "second",
        )

        assert (
            resolved.next_episode
            is not None
        )

        self.assertEqual(
            resolved.next_episode.source,
            "first",
        )

    def test_warnings_are_prefixed_and_aggregated(
        self,
    ) -> None:
        sonarr = StubProvider(
            "sonarr",
            result(
                "sonarr",
                lifecycle=(
                    ShowLifecycle.RETURNING
                ),
                warnings=(
                    "first_warning",
                ),
            ),
        )

        tmdb = StubProvider(
            "tmdb",
            result(
                "tmdb",
                lifecycle=(
                    ShowLifecycle.RETURNING
                ),
                episode=next_episode(
                    "tmdb"
                ),
                warnings=(
                    "title_differs",
                ),
            ),
        )

        resolver = TVMetadataResolver(
            [sonarr, tmdb]
        )

        resolved = resolver.resolve(
            identity()
        )

        self.assertEqual(
            resolved.warnings,
            (
                "sonarr:first_warning",
                "tmdb:title_differs",
            ),
        )

    def test_all_unmatched_returns_unknown(
        self,
    ) -> None:
        sonarr = StubProvider(
            "sonarr",
            result(
                "sonarr",
                matched=False,
            ),
        )

        tmdb = StubProvider(
            "tmdb",
            result(
                "tmdb",
                matched=False,
            ),
        )

        tvmaze = StubProvider(
            "tvmaze",
            result(
                "tvmaze",
                matched=False,
            ),
        )

        resolver = TVMetadataResolver(
            [
                sonarr,
                tmdb,
                tvmaze,
            ]
        )

        resolved = resolver.resolve(
            identity()
        )

        self.assertEqual(
            resolved.lifecycle,
            ShowLifecycle.UNKNOWN,
        )

        self.assertIsNone(
            resolved.lifecycle_source
        )

        self.assertIsNone(
            resolved.next_episode
        )

        self.assertEqual(
            sonarr.calls,
            1,
        )

        self.assertEqual(
            tmdb.calls,
            1,
        )

        self.assertEqual(
            tvmaze.calls,
            1,
        )


if __name__ == "__main__":
    unittest.main()
