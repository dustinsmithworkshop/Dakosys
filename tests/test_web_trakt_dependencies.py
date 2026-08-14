from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

import trakt_auth
import web_server


class TraktDependencyTests(unittest.TestCase):
    def test_tv_status_does_not_require_trakt(
        self,
    ):
        config = {
            "services": {
                "tv_status_tracker": {
                    "enabled": True,
                },
            },
            "scheduler": {
                "auto_schedule": {
                    "enabled": False,
                },
            },
            "trakt": {
                "episode_list_publishing": {
                    "enabled": False,
                },
            },
        }

        summary = (
            web_server
            ._get_local_trakt_summary(
                config
            )
        )

        self.assertFalse(
            summary["required"]
        )

        self.assertEqual(
            set(summary["features"]),
            {
                "auto_schedule",
                "legacy_episode_publishing",
            },
        )

    def test_auto_schedule_requires_trakt(
        self,
    ):
        config = {
            "scheduler": {
                "auto_schedule": {
                    "enabled": True,
                },
            },
            "trakt": {
                "episode_list_publishing": {
                    "enabled": False,
                },
            },
        }

        summary = (
            web_server
            ._get_local_trakt_summary(
                config
            )
        )

        self.assertTrue(
            summary["required"]
        )

        self.assertTrue(
            summary["features"][
                "auto_schedule"
            ]
        )

    def test_overview_does_not_require_trakt_for_tv_status(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = (
                Path(tmp)
                / "config.yaml"
            )

            config_path.write_text(
                yaml.safe_dump(
                    {
                        "services": {
                            "tv_status_tracker": {
                                "enabled": True,
                            },
                        },
                        "scheduler": {
                            "auto_schedule": {
                                "enabled": False,
                            },
                        },
                        "trakt": {
                            "episode_list_publishing": {
                                "enabled": False,
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(
                web_server,
                "CONFIG_FILE",
                str(config_path),
            ):
                result = (
                    web_server
                    .get_trakt_overview()
                )

        self.assertFalse(
            result["required"]
        )

        self.assertEqual(
            set(result["requirements"]),
            {
                "auto_schedule",
                "legacy_episode_publishing",
            },
        )

        self.assertIsNone(
            result["error"]
        )

    def test_generic_list_usage_does_not_query_tracked_list(
        self,
    ):
        capabilities = {
            "username": "example",
            "vip": False,
            "vip_ep": False,
            "max_lists": 10,
            "max_items_per_list": 500,
            "limits_known": True,
        }

        lists = [
            {
                "name": "Example",
                "ids": {
                    "trakt": 1,
                    "slug": "example",
                },
            },
        ]

        with (
            patch.object(
                trakt_auth,
                "get_trakt_list_capabilities",
                return_value=capabilities,
            ),
            patch.object(
                trakt_auth,
                "_get_all_trakt_pages",
                return_value=lists,
            ) as pages,
        ):
            usage = (
                trakt_auth
                .get_trakt_list_usage(
                    tracked_list_name=None,
                )
            )

        pages.assert_called_once_with(
            "users/me/lists"
        )

        self.assertNotIn(
            "tracked_list",
            usage,
        )

        self.assertEqual(
            usage["lists"]["current"],
            1,
        )


if __name__ == "__main__":
    unittest.main()
