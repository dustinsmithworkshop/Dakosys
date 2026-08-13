from __future__ import annotations

import unittest

from tv_metadata import (
    ShowIdentity,
    build_show_identity,
)


class FakeGuid:
    def __init__(
        self,
        value: str,
    ) -> None:
        self.id = value


class FakeShow:
    def __init__(
        self,
        *,
        title="Example Show",
        year=2025,
        rating_key="123",
        guids=None,
    ) -> None:
        self.title = title
        self.year = year
        self.ratingKey = rating_key
        self.guids = (
            guids
            if guids is not None
            else []
        )


class PlexIdentityTests(
    unittest.TestCase
):
    def test_collects_all_external_ids(
        self,
    ) -> None:
        show = FakeShow(
            guids=[
                FakeGuid("tmdb://100"),
                FakeGuid("tvdb://200"),
                FakeGuid(
                    "imdb://tt1234567"
                ),
            ]
        )

        result = build_show_identity(
            show,
            "TV",
            library_roles=(
                "tv",
            ),
        )

        self.assertIsInstance(
            result,
            ShowIdentity,
        )

        self.assertEqual(
            result.title,
            "Example Show",
        )

        self.assertEqual(
            result.year,
            2025,
        )

        self.assertEqual(
            result.plex_rating_key,
            "123",
        )

        self.assertEqual(
            result.tmdb_id,
            100,
        )

        self.assertEqual(
            result.tvdb_id,
            200,
        )

        self.assertEqual(
            result.imdb_id,
            "tt1234567",
        )

        self.assertEqual(
            result.library_roles,
            ("tv",),
        )

    def test_external_ids_are_individually_optional(
        self,
    ) -> None:
        show = FakeShow(
            guids=[
                FakeGuid("tvdb://200"),
            ]
        )

        result = build_show_identity(
            show,
            "Anime",
        )

        self.assertIsNone(
            result.tmdb_id
        )

        self.assertEqual(
            result.tvdb_id,
            200,
        )

        self.assertIsNone(
            result.imdb_id
        )

    def test_ignores_unrecognized_and_malformed_guids(
        self,
    ) -> None:
        show = FakeShow(
            guids=[
                FakeGuid(
                    "plex://show/abcdef"
                ),
                FakeGuid("tmdb://bad"),
                FakeGuid("tvdb://"),
                FakeGuid("not-a-guid"),
                FakeGuid(
                    "imdb://tt7654321"
                ),
            ]
        )

        result = build_show_identity(
            show,
            "TV",
        )

        self.assertIsNone(
            result.tmdb_id
        )

        self.assertIsNone(
            result.tvdb_id
        )

        self.assertEqual(
            result.imdb_id,
            "tt7654321",
        )

    def test_guid_query_suffix_is_ignored(
        self,
    ) -> None:
        show = FakeShow(
            guids=[
                FakeGuid(
                    "tmdb://456?lang=en"
                ),
                FakeGuid(
                    "tvdb://71663/"
                ),
            ]
        )

        result = build_show_identity(
            show,
            "TV",
        )

        self.assertEqual(
            result.tmdb_id,
            456,
        )

        self.assertEqual(
            result.tvdb_id,
            71663,
        )

    def test_library_roles_are_deduplicated(
        self,
    ) -> None:
        show = FakeShow()

        result = build_show_identity(
            show,
            "Cartoons",
            library_roles=(
                "anime",
                "tv",
                "anime",
            ),
        )

        self.assertEqual(
            result.library_roles,
            (
                "anime",
                "tv",
            ),
        )

    def test_missing_rating_key_is_rejected(
        self,
    ) -> None:
        show = FakeShow(
            rating_key=None
        )

        with self.assertRaisesRegex(
            ValueError,
            "rating key",
        ):
            build_show_identity(
                show,
                "TV",
            )

    def test_missing_title_is_rejected(
        self,
    ) -> None:
        show = FakeShow(
            title=None
        )

        with self.assertRaisesRegex(
            ValueError,
            "title",
        ):
            build_show_identity(
                show,
                "TV",
            )


if __name__ == "__main__":
    unittest.main()
