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


def identity():
    return ShowIdentity(
        title="Example Show",
        year=2025,
        library="TV",
        plex_rating_key="123",
        tmdb_id=100,
        tvdb_id=200,
        imdb_id="tt1234567",
    )


def episode(source):
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
        name,
        *,
        matched=True,
        lifecycle=ShowLifecycle.UNKNOWN,
        next_episode=None,
        warnings=(),
    ):
        self.name = name
        self.calls = 0

        self.result = ProviderResult(
            source=name,
            matched=matched,
            lifecycle=lifecycle,
            next_episode=next_episode,
            warnings=warnings,
        )

    def get_metadata(
        self,
        show,
    ):
        del show
        self.calls += 1
        return self.result


class TVMetadataResolverTests(
    unittest.TestCase
):
    def test_tmdb_wins_lifecycle_conflict(
        self,
    ):
        sonarr = StubProvider(
            "sonarr",
            lifecycle=(
                ShowLifecycle.RETURNING
            ),
        )

        tmdb = StubProvider(
            "tmdb",
            lifecycle=(
                ShowLifecycle.ENDED
            ),
        )

        resolver = TVMetadataResolver(
            [sonarr, tmdb]
        )

        result = resolver.resolve(
            identity()
        )

        self.assertEqual(
            result.lifecycle,
            ShowLifecycle.ENDED,
        )

        self.assertEqual(
            result.lifecycle_source,
            "tmdb",
        )

    def test_sonarr_wins_next_episode(
        self,
    ):
        sonarr = StubProvider(
            "sonarr",
            lifecycle=(
                ShowLifecycle.RETURNING
            ),
            next_episode=episode(
                "sonarr"
            ),
        )

        tmdb = StubProvider(
            "tmdb",
            lifecycle=(
                ShowLifecycle.RETURNING
            ),
            next_episode=episode(
                "tmdb"
            ),
        )

        resolver = TVMetadataResolver(
            [sonarr, tmdb]
        )

        result = resolver.resolve(
            identity()
        )

        self.assertEqual(
            result.lifecycle_source,
            "tmdb",
        )

        self.assertEqual(
            result.next_episode.source,
            "sonarr",
        )

    def test_tmdb_supplies_next_when_sonarr_has_none(
        self,
    ):
        sonarr = StubProvider(
            "sonarr",
            lifecycle=(
                ShowLifecycle.RETURNING
            ),
        )

        tmdb = StubProvider(
            "tmdb",
            lifecycle=(
                ShowLifecycle.RETURNING
            ),
            next_episode=episode(
                "tmdb"
            ),
        )

        resolver = TVMetadataResolver(
            [sonarr, tmdb]
        )

        result = resolver.resolve(
            identity()
        )

        self.assertEqual(
            result.lifecycle_source,
            "tmdb",
        )

        self.assertEqual(
            result.next_episode.source,
            "tmdb",
        )

    def test_sonarr_lifecycle_fallback_when_tmdb_unmatched(
        self,
    ):
        tmdb = StubProvider(
            "tmdb",
            matched=False,
        )

        sonarr = StubProvider(
            "sonarr",
            lifecycle=(
                ShowLifecycle.RETURNING
            ),
        )

        resolver = TVMetadataResolver(
            [sonarr, tmdb]
        )

        result = resolver.resolve(
            identity()
        )

        self.assertEqual(
            result.lifecycle_source,
            "sonarr",
        )

    def test_tvmaze_final_lifecycle_fallback(
        self,
    ):
        tmdb = StubProvider(
            "tmdb",
            matched=False,
        )

        sonarr = StubProvider(
            "sonarr",
            matched=False,
        )

        tvmaze = StubProvider(
            "tvmaze",
            lifecycle=(
                ShowLifecycle.ENDED
            ),
        )

        resolver = TVMetadataResolver(
            [
                sonarr,
                tmdb,
                tvmaze,
            ]
        )

        result = resolver.resolve(
            identity()
        )

        self.assertEqual(
            result.lifecycle_source,
            "tvmaze",
        )

    def test_ended_lifecycle_can_have_future_episode(
        self,
    ):
        tmdb = StubProvider(
            "tmdb",
            lifecycle=(
                ShowLifecycle.ENDED
            ),
        )

        sonarr = StubProvider(
            "sonarr",
            lifecycle=(
                ShowLifecycle.RETURNING
            ),
            next_episode=episode(
                "sonarr"
            ),
        )

        resolver = TVMetadataResolver(
            [sonarr, tmdb]
        )

        result = resolver.resolve(
            identity()
        )

        self.assertEqual(
            result.lifecycle,
            ShowLifecycle.ENDED,
        )

        self.assertEqual(
            result.lifecycle_source,
            "tmdb",
        )

        self.assertIsNotNone(
            result.next_episode
        )

        self.assertEqual(
            result.next_episode.source,
            "sonarr",
        )

        self.assertIn(
            "resolver:ended_with_next_episode",
            result.warnings,
        )

    def test_uncorroborated_ended_provider_next_is_rejected(
        self,
    ):
        sonarr = StubProvider(
            "sonarr",
            lifecycle=ShowLifecycle.ENDED,
        )

        tmdb = StubProvider(
            "tmdb",
            lifecycle=ShowLifecycle.ENDED,
            next_episode=episode(
                "tmdb"
            ),
        )

        tvmaze = StubProvider(
            "tvmaze",
            lifecycle=ShowLifecycle.ENDED,
        )

        result = TVMetadataResolver(
            [
                sonarr,
                tmdb,
                tvmaze,
            ]
        ).resolve(
            identity()
        )

        self.assertEqual(
            result.lifecycle,
            ShowLifecycle.ENDED,
        )

        self.assertIsNone(
            result.next_episode
        )

        self.assertIn(
            "resolver:"
            "rejected_unconfirmed_ended_next:"
            "tmdb",
            result.warnings,
        )

    def test_corroborated_ended_provider_next_is_kept(
        self,
    ):
        sonarr = StubProvider(
            "sonarr",
            lifecycle=ShowLifecycle.ENDED,
        )

        tmdb = StubProvider(
            "tmdb",
            lifecycle=ShowLifecycle.ENDED,
            next_episode=episode(
                "tmdb"
            ),
        )

        tvmaze = StubProvider(
            "tvmaze",
            lifecycle=ShowLifecycle.ENDED,
            next_episode=episode(
                "tvmaze"
            ),
        )

        result = TVMetadataResolver(
            [
                sonarr,
                tmdb,
                tvmaze,
            ]
        ).resolve(
            identity()
        )

        self.assertIsNotNone(
            result.next_episode
        )

        self.assertEqual(
            result.next_episode.source,
            "tmdb",
        )

        self.assertIn(
            "resolver:ended_with_next_episode",
            result.warnings,
        )

    def test_provider_called_at_most_once(
        self,
    ):
        tmdb = StubProvider(
            "tmdb",
            lifecycle=(
                ShowLifecycle.RETURNING
            ),
            next_episode=episode(
                "tmdb"
            ),
        )

        sonarr = StubProvider(
            "sonarr",
            lifecycle=(
                ShowLifecycle.RETURNING
            ),
        )

        resolver = TVMetadataResolver(
            [sonarr, tmdb]
        )

        resolver.resolve(
            identity()
        )

        self.assertEqual(
            tmdb.calls,
            1,
        )

        self.assertEqual(
            sonarr.calls,
            1,
        )

    def test_warnings_are_preserved(
        self,
    ):
        tmdb = StubProvider(
            "tmdb",
            lifecycle=(
                ShowLifecycle.RETURNING
            ),
            warnings=(
                "title_differs",
            ),
        )

        sonarr = StubProvider(
            "sonarr",
            next_episode=episode(
                "sonarr"
            ),
        )

        resolver = TVMetadataResolver(
            [sonarr, tmdb]
        )

        result = resolver.resolve(
            identity()
        )

        self.assertIn(
            "tmdb:title_differs",
            result.warnings,
        )

    def test_all_unmatched_returns_unknown(
        self,
    ):
        providers = [
            StubProvider(
                "sonarr",
                matched=False,
            ),
            StubProvider(
                "tmdb",
                matched=False,
            ),
            StubProvider(
                "tvmaze",
                matched=False,
            ),
        ]

        result = TVMetadataResolver(
            providers
        ).resolve(
            identity()
        )

        self.assertEqual(
            result.lifecycle,
            ShowLifecycle.UNKNOWN,
        )

        self.assertIsNone(
            result.lifecycle_source
        )

        self.assertIsNone(
            result.next_episode
        )


if __name__ == "__main__":
    unittest.main()
