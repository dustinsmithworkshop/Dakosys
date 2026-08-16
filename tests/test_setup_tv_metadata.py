from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import yaml

import setup as dakosys_setup


class TVMetadataSetupTests(unittest.TestCase):
    def test_provider_setup_uses_environment_credentials(
        self,
    ):
        config = {
            "services": {
                "tv_status_tracker": {
                    "metadata": {},
                },
            },
        }

        with (
            patch.dict(
                os.environ,
                {
                    "SONARR_URL": (
                        "http://env-sonarr:8989"
                    ),
                    "SONARR_API_KEY": (
                        "env-sonarr-key"
                    ),
                    "TMDB_TOKEN": (
                        "env-tmdb-token"
                    ),
                },
                clear=True,
            ),
            patch.object(
                dakosys_setup.click,
                "confirm",
                side_effect=[
                    True,
                    True,
                    True,
                ],
            ),
            patch.object(
                dakosys_setup.click,
                "prompt",
            ) as prompt,
        ):
            dakosys_setup.setup_tv_metadata_providers(
                config
            )

        prompt.assert_not_called()

        metadata = (
            config["services"]
            ["tv_status_tracker"]
            ["metadata"]
        )

        self.assertTrue(
            metadata["sonarr"]["enabled"]
        )
        self.assertTrue(
            metadata["tmdb"]["enabled"]
        )
        self.assertTrue(
            metadata["tvmaze"]["enabled"]
        )

        # Environment credentials remain environment
        # credentials; they are not copied into YAML.
        self.assertNotIn(
            "url",
            metadata["sonarr"],
        )
        self.assertNotIn(
            "api_key",
            metadata["sonarr"],
        )
        self.assertNotIn(
            "tmdb_api_key",
            config,
        )

    def test_provider_setup_persists_yaml_credentials(
        self,
    ):
        config = {
            "services": {
                "tv_status_tracker": {
                    "metadata": {},
                },
            },
        }

        with (
            patch.dict(
                os.environ,
                {},
                clear=True,
            ),
            patch.object(
                dakosys_setup.click,
                "confirm",
                side_effect=[
                    True,
                    True,
                    True,
                ],
            ),
            patch.object(
                dakosys_setup.click,
                "prompt",
                side_effect=[
                    "http://yaml-sonarr:8989",
                    "yaml-sonarr-key",
                    "yaml-tmdb-key",
                ],
            ),
        ):
            dakosys_setup.setup_tv_metadata_providers(
                config
            )

        metadata = (
            config["services"]
            ["tv_status_tracker"]
            ["metadata"]
        )

        self.assertEqual(
            metadata["sonarr"]["url"],
            "http://yaml-sonarr:8989",
        )
        self.assertEqual(
            metadata["sonarr"]["api_key"],
            "yaml-sonarr-key",
        )
        self.assertEqual(
            config["tmdb_api_key"],
            "yaml-tmdb-key",
        )
        self.assertTrue(
            metadata["tmdb"]["enabled"]
        )
        self.assertTrue(
            metadata["tvmaze"]["enabled"]
        )

    def test_tv_status_only_full_setup_skips_trakt(
        self,
    ):
        def fake_confirm(
            message,
            default=False,
            **kwargs,
        ):
            if (
                "Enable Anime Episode Type service?"
                in message
            ):
                return False

            if (
                "Enable TV/Anime Status Tracker service?"
                in message
            ):
                return True

            if (
                "Enable Sonarr metadata provider?"
                in message
            ):
                return False

            if (
                "Enable TMDB metadata provider?"
                in message
            ):
                return True

            if (
                "Enable TVmaze fallback provider?"
                in message
            ):
                return True

            if (
                "Enable Size Overlay service?"
                in message
            ):
                return False

            if (
                "Do you have anime libraries"
                in message
            ):
                return False

            if (
                "Do you have TV show libraries"
                in message
            ):
                return True

            if (
                "Do you want to add another TV show library?"
                in message
            ):
                return False

            if (
                "Do you have movie libraries"
                in message
            ):
                return False

            if (
                "Include TV show libraries for "
                "TV/Anime Status Tracker?"
                in message
            ):
                return True

            if (
                "Enable notifications?"
                in message
            ):
                return False

            raise AssertionError(
                f"Unexpected confirmation: {message}"
            )

        def fake_prompt(
            message,
            default=None,
            **kwargs,
        ):
            if (
                "Trakt"
                in message
                or "Default privacy for created lists"
                in message
            ):
                raise AssertionError(
                    "TV Status-only setup must not "
                    f"prompt for Trakt: {message}"
                )

            if (
                "Plex authentication token"
                in message
            ):
                return "plex-token"

            if (
                "TMDB v3 API key"
                in message
            ):
                return "tmdb-key"

            if (
                "first TV show library"
                in message
            ):
                return "TV"

            if default is not None:
                return default

            raise AssertionError(
                f"Unexpected prompt: {message}"
            )

        fake_trakt = SimpleNamespace(
            ensure_auth_during_setup=MagicMock(
                side_effect=AssertionError(
                    "Trakt authentication must not "
                    "run for TV Status-only setup"
                )
            )
        )

        old_cwd = os.getcwd()

        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)

                with (
                    patch.dict(
                        os.environ,
                        {},
                        clear=True,
                    ),
                    patch.dict(
                        sys.modules,
                        {
                            "trakt_auth": fake_trakt,
                        },
                    ),
                    patch.object(
                        dakosys_setup.click,
                        "confirm",
                        side_effect=fake_confirm,
                    ),
                    patch.object(
                        dakosys_setup.click,
                        "prompt",
                        side_effect=fake_prompt,
                    ),
                ):
                    dakosys_setup.run_setup()

                config_path = (
                    Path(tmp)
                    / "config"
                    / "config.yaml"
                )

                config = yaml.safe_load(
                    config_path.read_text(
                        encoding="utf-8"
                    )
                )
            finally:
                os.chdir(old_cwd)

        fake_trakt.ensure_auth_during_setup.assert_not_called()

        self.assertTrue(
            config["services"]
            ["tv_status_tracker"]
            ["enabled"]
        )

        self.assertEqual(
            config["tmdb_api_key"],
            "tmdb-key",
        )

        self.assertFalse(
            config["trakt"]
            ["episode_list_publishing"]
            ["enabled"]
        )

        self.assertNotIn(
            "client_id",
            config["trakt"],
        )

        self.assertNotIn(
            "default_privacy",
            config.get(
                "lists",
                {},
            ),
        )


if __name__ == "__main__":
    unittest.main()
