from __future__ import annotations

import unittest

from tv_metadata.shadow import (
    compare_presentations,
    normalized_status_type,
    presented_date,
)


def info(
    status_type,
    text,
):
    return {
        "status_type": status_type,
        "text_content": text,
    }


class TVMetadataShadowTests(
    unittest.TestCase
):
    def test_exact_match(self):
        self.assertEqual(
            compare_presentations(
                info(
                    "AIRING",
                    "AIRING 08/14",
                ),
                info(
                    "AIRING",
                    "AIRING 08/14",
                ),
            ),
            "MATCH",
        )

    def test_cancelled_and_ended_are_equivalent(self):
        self.assertEqual(
            compare_presentations(
                info(
                    "CANCELLED",
                    "C A N C E L L E D",
                ),
                info(
                    "ENDED",
                    "E N D E D",
                ),
            ),
            "MATCH",
        )

        self.assertEqual(
            normalized_status_type(
                info(
                    "CANCELLED",
                    "C A N C E L L E D",
                )
            ),
            "ENDED",
        )

    def test_date_difference(self):
        self.assertEqual(
            compare_presentations(
                info(
                    "AIRING",
                    "AIRING 08/14",
                ),
                info(
                    "AIRING",
                    "AIRING 08/21",
                ),
            ),
            "DATE_DIFFERS",
        )

    def test_status_difference(self):
        self.assertEqual(
            compare_presentations(
                info(
                    "AIRING",
                    "AIRING 08/14",
                ),
                info(
                    "SEASON_FINALE",
                    "SEASON FINALE 08/14",
                ),
            ),
            "STATUS_DIFFERS",
        )

    def test_status_and_date_difference(self):
        self.assertEqual(
            compare_presentations(
                info(
                    "AIRING",
                    "AIRING 08/14",
                ),
                info(
                    "SEASON_FINALE",
                    "SEASON FINALE 08/21",
                ),
            ),
            "STATUS_AND_DATE_DIFFER",
        )

    def test_provider_only(self):
        self.assertEqual(
            compare_presentations(
                None,
                info(
                    "RETURNING",
                    "R E T U R N I N G",
                ),
            ),
            "PROVIDER_ONLY",
        )

    def test_legacy_only(self):
        self.assertEqual(
            compare_presentations(
                info(
                    "RETURNING",
                    "R E T U R N I N G",
                ),
                None,
            ),
            "LEGACY_ONLY",
        )

    def test_both_none(self):
        self.assertEqual(
            compare_presentations(
                None,
                None,
            ),
            "BOTH_NONE",
        )

    def test_date_extraction(self):
        self.assertEqual(
            presented_date(
                info(
                    "SEASON_PREMIERE",
                    "SEASON PREMIERE 09/27",
                )
            ),
            "09/27",
        )

        self.assertIsNone(
            presented_date(
                info(
                    "RETURNING",
                    "R E T U R N I N G",
                )
            )
        )


if __name__ == "__main__":
    unittest.main()
