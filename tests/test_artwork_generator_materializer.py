from pathlib import Path

import pytest

import artwork.generator_materializer as materializer_module

from artwork.generator_inputs import (
    EpisodeGenerationInput,
    EpisodeGenerationPath,
)
from artwork.generator_materializer import (
    ArtworkGeneratorMaterializationError,
    materialize_generated_episode_card,
)
from artwork.models import (
    ArtworkKind,
    ArtworkQuality,
    ArtworkSource,
)


def _generation_input():
    return EpisodeGenerationInput(
        episode_number=1,
        path=(
            EpisodeGenerationPath
            .GENERATE_MISSING
        ),
        title="Pilot",
        title_source=(
            ArtworkSource.PLEX
        ),
        image_ref=(
            "https://image.tmdb.org/"
            "t/p/original/source.jpg"
        ),
        image_source=(
            ArtworkSource.TMDB
        ),
        image_provider_asset_id=(
            "/source.jpg"
        ),
    )


def _install_successful_fakes(
    monkeypatch,
    *,
    calls,
    rendered_bytes=(
        b"rendered-jpeg"
    ),
):
    def fake_source(
        **kwargs,
    ):
        calls.append(
            (
                "source",
                kwargs,
            )
        )

        destination = Path(
            kwargs["destination"]
        )

        destination.write_bytes(
            b"source-image"
        )

    def fake_renderer(
        **kwargs,
    ):
        calls.append(
            (
                "renderer",
                kwargs,
            )
        )

        output_path = Path(
            kwargs["output_path"]
        )

        output_path.write_bytes(
            rendered_bytes
        )

    monkeypatch.setattr(
        materializer_module,
        "materialize_generation_source",
        fake_source,
    )

    monkeypatch.setattr(
        materializer_module,
        "render_episode_title_card",
        fake_renderer,
    )


def test_materializes_generated_episode_asset(
    tmp_path: Path,
    monkeypatch,
):
    calls = []

    _install_successful_fakes(
        monkeypatch,
        calls=calls,
    )

    local_root = (
        tmp_path
        / "generated"
    )

    result = (
        materialize_generated_episode_card(
            generation_input=(
                _generation_input()
            ),
            show_key="tmdb:1398",
            season_number=1,
            font_key="marcellus",
            local_root=local_root,
            kometa_root=(
                "/config/assets/generated"
            ),
        )
    )

    assert not result.reused

    assert result.local_path.exists()

    assert (
        result.local_path.read_bytes()
        == b"rendered-jpeg"
    )

    assert (
        result.asset.kind
        is ArtworkKind.EPISODE_CARD
    )

    assert (
        result.asset.source
        is ArtworkSource.GENERATED
    )

    assert (
        result.asset.quality
        is ArtworkQuality.GENERATED
    )

    assert (
        result.asset.provider_asset_id
        == result.fingerprint
    )

    assert (
        result.asset.file_path
        == result.kometa_path
    )

    assert result.asset.available

    assert result.kometa_path.startswith(
        "/config/assets/generated/"
    )

    assert (
        "/tv/tmdb-1398/"
        "season-01/"
        in result.kometa_path
    )

    assert [
        name
        for name, _kwargs
        in calls
    ] == [
        "source",
        "renderer",
    ]


def test_renderer_receives_resolved_title_and_font(
    tmp_path: Path,
    monkeypatch,
):
    calls = []

    _install_successful_fakes(
        monkeypatch,
        calls=calls,
    )

    materialize_generated_episode_card(
        generation_input=(
            _generation_input()
        ),
        show_key="tmdb:1398",
        season_number=1,
        font_key="prata",
        local_root=(
            tmp_path
            / "generated"
        ),
        kometa_root=(
            "/config/assets/generated"
        ),
    )

    renderer_call = next(
        kwargs
        for name, kwargs
        in calls
        if name == "renderer"
    )

    assert (
        renderer_call[
            "episode_title"
        ]
        == "Pilot"
    )

    assert (
        renderer_call[
            "font_key"
        ]
        == "prata"
    )


def test_existing_cached_jpeg_is_reused_without_download_or_render(
    tmp_path: Path,
    monkeypatch,
):
    calls = []

    _install_successful_fakes(
        monkeypatch,
        calls=calls,
    )

    kwargs = {
        "generation_input":
            _generation_input(),
        "show_key":
            "tmdb:1398",
        "season_number":
            1,
        "font_key":
            "marcellus",
        "local_root":
            tmp_path
            / "generated",
        "kometa_root":
            "/config/assets/generated",
    }

    first = (
        materialize_generated_episode_card(
            **kwargs
        )
    )

    assert not first.reused

    calls.clear()

    def unexpected_call(
        **_kwargs,
    ):
        raise AssertionError(
            "cache reuse must not "
            "download or render"
        )

    monkeypatch.setattr(
        materializer_module,
        "materialize_generation_source",
        unexpected_call,
    )

    monkeypatch.setattr(
        materializer_module,
        "render_episode_title_card",
        unexpected_call,
    )

    second = (
        materialize_generated_episode_card(
            **kwargs
        )
    )

    assert second.reused
    assert (
        second.local_path
        == first.local_path
    )
    assert (
        second.fingerprint
        == first.fingerprint
    )


def test_zero_length_cache_entry_is_regenerated(
    tmp_path: Path,
    monkeypatch,
):
    calls = []

    _install_successful_fakes(
        monkeypatch,
        calls=calls,
    )

    kwargs = {
        "generation_input":
            _generation_input(),
        "show_key":
            "tmdb:1398",
        "season_number":
            1,
        "font_key":
            "marcellus",
        "local_root":
            tmp_path
            / "generated",
        "kometa_root":
            "/config/assets/generated",
    }

    first = (
        materialize_generated_episode_card(
            **kwargs
        )
    )

    first.local_path.write_bytes(
        b""
    )

    calls.clear()

    second = (
        materialize_generated_episode_card(
            **kwargs
        )
    )

    assert not second.reused

    assert (
        second.local_path.read_bytes()
        == b"rendered-jpeg"
    )

    assert [
        name
        for name, _kwargs
        in calls
    ] == [
        "source",
        "renderer",
    ]


def test_source_failure_does_not_leave_cached_output(
    tmp_path: Path,
    monkeypatch,
):
    local_root = (
        tmp_path
        / "generated"
    )

    def fail_source(
        **_kwargs,
    ):
        raise RuntimeError(
            "download failed"
        )

    monkeypatch.setattr(
        materializer_module,
        "materialize_generation_source",
        fail_source,
    )

    with pytest.raises(
        ArtworkGeneratorMaterializationError,
        match="could not materialize",
    ):
        materialize_generated_episode_card(
            generation_input=(
                _generation_input()
            ),
            show_key="tmdb:1398",
            season_number=1,
            font_key="marcellus",
            local_root=local_root,
            kometa_root=(
                "/config/assets/generated"
            ),
        )

    assert not list(
        local_root.rglob(
            "*.jpg"
        )
    )


def test_renderer_failure_does_not_leave_cached_output(
    tmp_path: Path,
    monkeypatch,
):
    local_root = (
        tmp_path
        / "generated"
    )

    calls = []

    _install_successful_fakes(
        monkeypatch,
        calls=calls,
    )

    def fail_renderer(
        **_kwargs,
    ):
        raise RuntimeError(
            "renderer failed"
        )

    monkeypatch.setattr(
        materializer_module,
        "render_episode_title_card",
        fail_renderer,
    )

    with pytest.raises(
        ArtworkGeneratorMaterializationError,
        match="could not materialize",
    ):
        materialize_generated_episode_card(
            generation_input=(
                _generation_input()
            ),
            show_key="tmdb:1398",
            season_number=1,
            font_key="marcellus",
            local_root=local_root,
            kometa_root=(
                "/config/assets/generated"
            ),
        )

    assert not list(
        local_root.rglob(
            "*.jpg"
        )
    )

    assert not [
        path
        for path in local_root.rglob(
            "*"
        )
        if path.name.startswith(
            ".dakosys-generator-"
        )
    ]


def test_non_generation_input_is_rejected_before_io(
    tmp_path: Path,
    monkeypatch,
):
    generation_input = (
        EpisodeGenerationInput(
            episode_number=1,
            path=(
                EpisodeGenerationPath
                .KEEP_PRIMARY
            ),
        )
    )

    def unexpected_call(
        **_kwargs,
    ):
        raise AssertionError(
            "ineligible input must not "
            "perform I/O"
        )

    monkeypatch.setattr(
        materializer_module,
        "materialize_generation_source",
        unexpected_call,
    )

    monkeypatch.setattr(
        materializer_module,
        "render_episode_title_card",
        unexpected_call,
    )

    with pytest.raises(
        ValueError,
        match="not eligible",
    ):
        materialize_generated_episode_card(
            generation_input=(
                generation_input
            ),
            show_key="tmdb:1398",
            season_number=1,
            font_key="marcellus",
            local_root=(
                tmp_path
                / "generated"
            ),
            kometa_root=(
                "/config/assets/generated"
            ),
        )
