from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

import web_server


class NextAiringWebTests(unittest.TestCase):
    def _write_fixture(
        self,
        root: Path,
        *,
        tmdb_api_key="",
    ):
        config_path = root / "config.yaml"
        snapshot_path = root / "next_airing.json"

        config_path.write_text(
            yaml.safe_dump(
                {
                    "date_format": "MM/DD",
                    "tmdb_api_key": tmdb_api_key,
                }
            ),
            encoding="utf-8",
        )

        snapshot_path.write_text(
            json.dumps(
                {
                    "generated_at": (
                        "2026-08-14T08:00:00+00:00"
                    ),
                    "timezone": "America/Chicago",
                    "count": 1,
                    "shows": [
                        {
                            "rank": 1,
                            "title": "Example Show",
                            "year": 2025,
                            "library": "TV",
                            "plex_rating_key": "123",
                            "ids": {
                                "tmdb": 100,
                                "tvdb": 200,
                                "imdb": "tt1234567",
                            },
                            "next_episode": {
                                "source": "sonarr",
                                "season": 2,
                                "episode": 1,
                                "title": "Premiere",
                                "state": (
                                    "season_premiere"
                                ),
                                "air_date": (
                                    "2026-09-27"
                                ),
                                "air_datetime": None,
                                "display_date": (
                                    "2026-09-27"
                                ),
                            },
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        return config_path, snapshot_path

    def test_reads_local_snapshot_without_trakt_or_tmdb(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            config_path, snapshot_path = (
                self._write_fixture(root)
            )

            with (
                patch.object(
                    web_server,
                    "CONFIG_FILE",
                    str(config_path),
                ),
                patch.object(
                    web_server,
                    "NEXT_AIRING_SNAPSHOT",
                    str(snapshot_path),
                ),
            ):
                result = (
                    web_server.get_next_airing()
                )

        self.assertEqual(
            result["count"],
            1,
        )

        self.assertNotIn(
            "error",
            result,
        )

        show = result["shows"][0]

        self.assertEqual(
            show["title"],
            "Example Show",
        )

        self.assertEqual(
            show["plex_rating_key"],
            "123",
        )

        self.assertEqual(
            show["status"],
            "SEASON_PREMIERE",
        )

        self.assertEqual(
            show["date"],
            "09/27",
        )

        self.assertEqual(
            show["source"],
            "sonarr",
        )

        self.assertEqual(
            show["tmdb_id"],
            100,
        )

        self.assertEqual(
            show["external_url"],
            "https://www.themoviedb.org/tv/100",
        )

        self.assertIsNone(
            show["poster_url"]
        )

    def test_tmdb_poster_is_optional_enrichment(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            config_path, snapshot_path = (
                self._write_fixture(
                    root,
                    tmdb_api_key="test-key",
                )
            )

            web_server._tmdb_poster_cache.clear()

            with (
                patch.object(
                    web_server,
                    "CONFIG_FILE",
                    str(config_path),
                ),
                patch.object(
                    web_server,
                    "NEXT_AIRING_SNAPSHOT",
                    str(snapshot_path),
                ),
                patch.object(
                    web_server,
                    "_fetch_tmdb_poster",
                    return_value=(
                        "https://example/poster.jpg"
                    ),
                ) as poster,
            ):
                # Mimic the helper's normal cache effect.
                def cache_poster(
                    tmdb_id,
                    api_key,
                ):
                    web_server._tmdb_poster_cache[
                        tmdb_id
                    ] = (
                        "https://example/poster.jpg"
                    )
                    return (
                        "https://example/poster.jpg"
                    )

                poster.side_effect = cache_poster

                result = (
                    web_server.get_next_airing()
                )

            poster.assert_called_once_with(
                100,
                "test-key",
            )

        self.assertEqual(
            result["shows"][0]["poster_url"],
            "https://example/poster.jpg",
        )

    def test_missing_snapshot_is_reported(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            config_path = root / "config.yaml"

            config_path.write_text(
                yaml.safe_dump(
                    {
                        "date_format": "DD/MM",
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch.object(
                    web_server,
                    "CONFIG_FILE",
                    str(config_path),
                ),
                patch.object(
                    web_server,
                    "NEXT_AIRING_SNAPSHOT",
                    str(
                        root
                        / "missing.json"
                    ),
                ),
            ):
                result = (
                    web_server.get_next_airing()
                )

        self.assertEqual(
            result["count"],
            0,
        )

        self.assertIn(
            "run the TV Status Tracker",
            result["error"],
        )


if __name__ == "__main__":
    unittest.main()
