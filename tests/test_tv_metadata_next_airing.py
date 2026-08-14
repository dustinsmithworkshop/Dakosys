from __future__ import annotations

import tempfile
import unittest
from datetime import (
    date,
    datetime,
    timezone,
)
from pathlib import Path

import yaml

from tv_metadata import (
    EpisodeState,
    NextEpisode,
    ShowIdentity,
    ShowLifecycle,
    ShowStatus,
)
from tv_metadata.next_airing import (
    build_kometa_collection,
    build_next_airing_entry,
    build_text_file_lines,
    next_airing_date,
    sort_next_airing,
    text_file_identifier,
    write_next_airing_files,
)


def identity(
    *,
    title="Example Show",
    year=2025,
    library="TV",
    rating_key="123",
    tmdb_id=100,
    tvdb_id=200,
    imdb_id="tt1234567",
):
    return ShowIdentity(
        title=title,
        year=year,
        library=library,
        plex_rating_key=rating_key,
        tmdb_id=tmdb_id,
        tvdb_id=tvdb_id,
        imdb_id=imdb_id,
    )


def status(
    *,
    air_date=None,
    air_datetime=None,
    source="sonarr",
):
    return ShowStatus(
        lifecycle=ShowLifecycle.RETURNING,
        lifecycle_source="tmdb",
        next_episode=NextEpisode(
            source=source,
            season=2,
            episode=1,
            air_date=air_date,
            air_datetime=air_datetime,
            state=EpisodeState.SEASON_PREMIERE,
        ),
    )


class NextAiringTests(
    unittest.TestCase
):
    def test_builds_entry_with_external_ids(
        self,
    ):
        result = build_next_airing_entry(
            identity(),
            status(
                air_date=date(
                    2026,
                    9,
                    1,
                )
            ),
        )

        self.assertIsNotNone(result)
        self.assertEqual(
            result.tvdb_id,
            200,
        )
        self.assertEqual(
            result.tmdb_id,
            100,
        )
        self.assertEqual(
            result.imdb_id,
            "tt1234567",
        )

    def test_no_next_episode_returns_none(
        self,
    ):
        result = build_next_airing_entry(
            identity(),
            ShowStatus(
                lifecycle=ShowLifecycle.RETURNING,
                lifecycle_source="tmdb",
            ),
        )

        self.assertIsNone(result)

    def test_undated_episode_returns_none(
        self,
    ):
        self.assertIsNone(
            build_next_airing_entry(
                identity(),
                status(),
            )
        )

    def test_display_date_uses_configured_timezone(
        self,
    ):
        entry = build_next_airing_entry(
            identity(),
            status(
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
            ),
        )

        self.assertEqual(
            next_airing_date(
                entry,
                "America/Chicago",
            ),
            date(
                2026,
                9,
                2,
            ),
        )

    def test_sort_uses_display_air_date(
        self,
    ):
        later = build_next_airing_entry(
            identity(
                title="Later",
                rating_key="2",
            ),
            status(
                air_date=date(
                    2026,
                    9,
                    4,
                ),
            ),
        )

        earlier = build_next_airing_entry(
            identity(
                title="Earlier",
                rating_key="1",
            ),
            status(
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
            ),
        )

        ordered = sort_next_airing(
            [later, earlier],
            "America/Chicago",
        )

        self.assertEqual(
            [
                entry.title
                for entry in ordered
            ],
            [
                "Earlier",
                "Later",
            ],
        )

    def test_identifier_prefers_tvdb(
        self,
    ):
        entry = build_next_airing_entry(
            identity(),
            status(
                air_date=date(
                    2026,
                    9,
                    1,
                )
            ),
        )

        self.assertEqual(
            text_file_identifier(entry),
            "tvdb:200",
        )

    def test_identifier_falls_back_to_tmdb(
        self,
    ):
        entry = build_next_airing_entry(
            identity(
                tvdb_id=None,
            ),
            status(
                air_date=date(
                    2026,
                    9,
                    1,
                )
            ),
        )

        self.assertEqual(
            text_file_identifier(entry),
            "tmdb:100",
        )

    def test_identifier_falls_back_to_imdb(
        self,
    ):
        entry = build_next_airing_entry(
            identity(
                tvdb_id=None,
                tmdb_id=None,
            ),
            status(
                air_date=date(
                    2026,
                    9,
                    1,
                )
            ),
        )

        self.assertEqual(
            text_file_identifier(entry),
            "imdb:tt1234567",
        )

    def test_collection_uses_text_file(
        self,
    ):
        data = build_kometa_collection(
            "TV",
            "config/collections/"
            "tv-next-airing.txt",
        )

        collection = data[
            "collections"
        ]["Next Airing TV"]

        self.assertEqual(
            collection["text_file"],
            "config/collections/"
            "tv-next-airing.txt",
        )

        self.assertEqual(
            collection[
                "collection_order"
            ],
            "custom",
        )

        self.assertNotIn(
            "trakt_list",
            collection,
        )

        self.assertNotIn(
            "plex_search",
            collection,
        )

    def test_written_text_file_preserves_date_order(
        self,
    ):
        late = build_next_airing_entry(
            identity(
                title="Late",
                rating_key="2",
                tvdb_id=202,
            ),
            status(
                air_date=date(
                    2026,
                    9,
                    10,
                )
            ),
        )

        early = build_next_airing_entry(
            identity(
                title="Early",
                rating_key="1",
                tvdb_id=201,
            ),
            status(
                air_date=date(
                    2026,
                    9,
                    1,
                )
            ),
        )

        with tempfile.TemporaryDirectory() as tmp:
            yaml_path, text_path = (
                write_next_airing_files(
                    tmp,
                    "TV",
                    [late, early],
                    "America/Chicago",
                )
            )

            lines = (
                text_path
                .read_text(
                    encoding="utf-8"
                )
                .splitlines()
            )

            data = yaml.safe_load(
                yaml_path.read_text(
                    encoding="utf-8"
                )
            )

        self.assertTrue(
            lines[0].startswith(
                "tvdb:201"
            )
        )

        self.assertTrue(
            lines[1].startswith(
                "tvdb:202"
            )
        )

        self.assertEqual(
            data["collections"][
                "Next Airing TV"
            ]["text_file"],
            "config/collections/"
            "tv-next-airing.txt",
        )


if __name__ == "__main__":
    unittest.main()
