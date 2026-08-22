"""Configured end-to-end Artwork Generator workflow tests."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import yaml
from PIL import Image

from artwork.models import (
    ArtworkSource,
)
from artwork.runtime import (
    build_configured_artwork_manager_workflow,
)
from artwork.state_store import (
    load_show_state_store,
)
from artwork.workflow import (
    apply_artwork_library_workflow,
)


class FakeGuid:
    def __init__(
        self,
        value,
    ):
        self.id = value


class FakeEpisode:
    def __init__(
        self,
        index,
        *,
        title,
        thumb,
    ):
        self.index = index
        self.title = title
        self.thumb = thumb


class FakeSeason:
    def __init__(
        self,
        index,
        episodes,
    ):
        self.index = index
        self._episodes = list(
            episodes
        )

    def episodes(
        self,
    ):
        return list(
            self._episodes
        )


class FakeShow:
    def __init__(
        self,
    ):
        self.title = "Generator Test Show"
        self.year = 2026
        self.ratingKey = "900"

        self.guids = [
            FakeGuid(
                "tvdb://200"
            ),
        ]

        self._seasons = [
            FakeSeason(
                1,
                (
                    FakeEpisode(
                        1,
                        title="Pilot",
                        thumb=(
                            "/library/metadata/"
                            "900/season/1/"
                            "episode/1/thumb"
                        ),
                    ),
                ),
            ),
        ]

    def seasons(
        self,
    ):
        return list(
            self._seasons
        )


class FakeSection:
    def __init__(
        self,
        show,
    ):
        self.title = "TV"
        self.type = "show"
        self._show = show

    def all(
        self,
    ):
        return [
            self._show,
        ]


class FakeLibrary:
    def __init__(
        self,
        section,
    ):
        self._section = section

    def sections(
        self,
    ):
        return [
            self._section,
        ]

    def section(
        self,
        name,
    ):
        if (
            name
            != self._section.title
        ):
            raise KeyError(
                name
            )

        return self._section


class FakePlex:
    def __init__(
        self,
        show,
    ):
        self.library = (
            FakeLibrary(
                FakeSection(
                    show
                )
            )
        )


class FakeImageResponse:
    def __init__(
        self,
        payload,
    ):
        self._payload = payload

        self.headers = {
            "Content-Type":
                "image/jpeg",
            "Content-Length":
                str(
                    len(
                        payload
                    )
                ),
        }

    def raise_for_status(
        self,
    ):
        return None

    def iter_content(
        self,
        chunk_size=65536,
    ):
        del chunk_size

        yield self._payload


class FakeImageSession:
    def __init__(
        self,
        payload,
    ):
        self.payload = payload
        self.requests = []

    def get(
        self,
        url,
        *,
        headers=None,
        stream=False,
        timeout=None,
    ):
        self.requests.append(
            {
                "url": url,
                "headers": headers,
                "stream": stream,
                "timeout": timeout,
            }
        )

        return FakeImageResponse(
            self.payload
        )


def _source_jpeg() -> bytes:
    buffer = BytesIO()

    image = Image.new(
        "RGB",
        (
            1280,
            720,
        ),
        (
            32,
            32,
            32,
        ),
    )

    image.save(
        buffer,
        format="JPEG",
        quality=90,
    )

    return buffer.getvalue()


def test_configured_generator_preview_then_apply(
    tmp_path: Path,
    monkeypatch,
):
    creative_config = (
        tmp_path
        / "artwork-generator.yaml"
    )

    creative_config.write_text(
        """
version: 1

defaults:
  font: marcellus

libraries:
  TV:
    font: cinzel

shows:
  "tvdb:200":
    font: prata
""".lstrip(),
        encoding="utf-8",
    )

    dakosys_assets = (
        tmp_path
        / "kometa-assets"
    )

    metadata_root = (
        tmp_path
        / "metadata"
    )

    config = {
        "plex": {
            "url":
                "http://plex:32400",
            "token":
                "plex-token",
        },
        "kometa_config": {
            "asset_directory":
                str(
                    dakosys_assets
                ),
        },
        "services": {
            "artwork_manager": {
                "enabled": True,
                "apply_mode":
                    "manual",
                "output_dir":
                    str(
                        metadata_root
                    ),
                "providers": {
                    "mediux": {
                        "api_token":
                            "fake-token",
                    },
                },
                "generated_episode_cards": {
                    "enabled": True,
                    "kometa_asset_directory":
                        "/config/assets",
                    "config_file":
                        str(
                            creative_config
                        ),
                },
            },
        },
    }

    # No curated artwork is available for this show. This keeps the
    # configured provider boundary real while avoiding network access.
    monkeypatch.setattr(
        "artwork.providers.mediux."
        "MediuxProvider.find_sets",
        lambda self, request: [],
    )

    plex = FakePlex(
        FakeShow()
    )

    # --------------------------------------------------------------
    # PREVIEW
    # --------------------------------------------------------------

    workflow = (
        build_configured_artwork_manager_workflow(
            plex=plex,
            config=config,
            environ={},
        )
    )

    assert workflow.library_count == 1

    run = workflow.libraries[0]

    assert run.library == "TV"
    assert run.safe_to_apply

    execution = run.execution

    assert execution.generator_enabled

    assert (
        execution.generator_plan_count
        == 1
    )

    assert (
        execution.generator_materialization_needed_count
        == 1
    )

    assert (
        execution.tmdb_request_count
        == 0
    )

    generation_plan = (
        execution.generation_plans[0]
    )

    # Show override beats the TV library override and global default.
    assert (
        generation_plan
        .identity
        .show_key
        == "tvdb:200"
    )

    assert (
        generation_plan
        .identity
        .font_key
        == "prata"
    )

    assert (
        generation_plan
        .generation_input
        .image_source
        is ArtworkSource.PLEX
    )

    assert (
        generation_plan
        .generation_input
        .title
        == "Pilot"
    )

    assert (
        generation_plan
        .generation_input
        .title_source
        is ArtworkSource.PLEX
    )

    generated_root = (
        dakosys_assets
        / "generated-artwork"
    )

    # Building the configured workflow is read-only.
    assert not generated_root.exists()
    assert not (
        generation_plan
        .local_path
        .exists()
    )

    # --------------------------------------------------------------
    # APPLY
    # --------------------------------------------------------------

    image_session = (
        FakeImageSession(
            _source_jpeg()
        )
    )

    # Generator source I/O happens only now, during reviewed apply.
    monkeypatch.setattr(
        "artwork.generator_source."
        "requests.Session",
        lambda: image_session,
    )

    result = (
        apply_artwork_library_workflow(
            run
        )
    )

    assert result.changed

    assert (
        result.generated_materialized_count
        == 1
    )

    assert (
        result.generated_reused_count
        == 0
    )

    assert (
        generation_plan
        .local_path
        .is_file()
    )

    assert (
        generation_plan
        .local_path
        .stat()
        .st_size
        > 0
    )

    with Image.open(
        generation_plan.local_path
    ) as generated:
        assert generated.size == (
            1920,
            1080,
        )

    # Plex token is scoped only to the Plex image request.
    assert len(
        image_session.requests
    ) == 1

    request = (
        image_session
        .requests[0]
    )

    assert request["url"] == (
        "http://plex:32400/"
        "library/metadata/"
        "900/season/1/"
        "episode/1/thumb"
    )

    assert request["headers"] == {
        "X-Plex-Token":
            "plex-token",
    }

    assert request["stream"] is True

    # --------------------------------------------------------------
    # KOMETA METADATA
    # --------------------------------------------------------------

    yaml_files = tuple(
        run.output_path.glob(
            "*.yaml"
        )
    )

    assert len(
        yaml_files
    ) == 1

    document = yaml.safe_load(
        yaml_files[0].read_text(
            encoding="utf-8"
        )
    )

    episode_metadata = (
        document[
            "metadata"
        ][
            200
        ][
            "seasons"
        ][
            1
        ][
            "episodes"
        ][
            1
        ]
    )

    assert (
        episode_metadata[
            "file_poster"
        ]
        == generation_plan
        .kometa_path
    )

    assert (
        generation_plan
        .kometa_path
        .startswith(
            "/config/assets/"
            "generated-artwork/"
        )
    )

    # --------------------------------------------------------------
    # DURABLE STATE
    # --------------------------------------------------------------

    store = (
        load_show_state_store(
            run.output_path,
            expected_library="TV",
        )
    )

    assert store is not None
    assert len(
        store.items
    ) == 1

    state = (
        store.items[0].state
    )

    card = (
        state
        .seasons[1]
        .episodes[1]
        .card
    )

    assert (
        card.source
        is ArtworkSource.GENERATED
    )

    assert (
        card.file_path
        == generation_plan
        .kometa_path
    )

    assert (
        card.provider_asset_id
        == generation_plan
        .fingerprint
    )
