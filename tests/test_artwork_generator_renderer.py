from pathlib import Path

import pytest
from PIL import Image

from artwork.generator_renderer import (
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    MAX_TEXT_HEIGHT_RATIO,
    MAX_TEXT_WIDTH_RATIO,
    ArtworkGeneratorRenderError,
    render_episode_title_card,
)


def _make_source_image(
    path: Path,
    *,
    size: tuple[int, int] = (
        1280,
        720,
    ),
    color: tuple[int, int, int] = (
        32,
        64,
        128,
    ),
) -> Path:
    image = Image.new(
        "RGB",
        size,
        color,
    )
    image.save(
        path,
        format="JPEG",
        quality=95,
    )
    return path


def test_render_episode_title_card_creates_1920x1080_jpeg(
    tmp_path: Path,
) -> None:
    source_path = _make_source_image(
        tmp_path / "source.jpg"
    )
    output_path = (
        tmp_path
        / "rendered.jpg"
    )

    result = render_episode_title_card(
        source_image_path=source_path,
        output_path=output_path,
        episode_title="Pilot",
        font_key="prata",
    )

    assert (
        result.output_path
        == output_path
    )
    assert result.width == 1920
    assert result.height == 1080
    assert (
        result.requested_font_key
        == "prata"
    )
    assert (
        result.actual_font_key
        == "prata"
    )
    assert (
        result.title_lines
        == ("Pilot",)
    )

    assert output_path.exists()

    with Image.open(output_path) as rendered:
        assert rendered.size == (
            1920,
            1080,
        )
        assert (
            rendered.format
            == "JPEG"
        )


def test_render_episode_title_card_shrinks_long_title_to_fit_constraints(
    tmp_path: Path,
) -> None:
    source_path = _make_source_image(
        tmp_path / "source.jpg"
    )
    output_path = (
        tmp_path
        / "long-title.jpg"
    )

    result = render_episode_title_card(
        source_image_path=source_path,
        output_path=output_path,
        episode_title=(
            "The Eminence in Shadow Begins "
            "His Grand Performance at the "
            "Edge of Destiny"
        ),
        font_key="cormorant_garamond",
    )

    assert 1 <= len(
        result.title_lines
    ) <= 2

    assert (
        result.text_box_width
        <= int(
            CANVAS_WIDTH
            * MAX_TEXT_WIDTH_RATIO
        )
    )
    assert (
        result.text_box_height
        <= int(
            CANVAS_HEIGHT
            * MAX_TEXT_HEIGHT_RATIO
        )
    )

    assert (
        result.font_size
        < 150
    )


def test_render_episode_title_card_uses_noto_for_cjk_text(
    tmp_path: Path,
) -> None:
    source_path = _make_source_image(
        tmp_path / "source.jpg"
    )
    output_path = (
        tmp_path
        / "japanese.jpg"
    )

    result = render_episode_title_card(
        source_image_path=source_path,
        output_path=output_path,
        episode_title="旅立ちと別れ",
        font_key="marcellus",
    )

    assert (
        result.requested_font_key
        == "marcellus"
    )
    assert (
        result.actual_font_key
        == "noto_sans_jp"
    )
    assert output_path.exists()


def test_render_episode_title_card_rejects_unknown_font_key(
    tmp_path: Path,
) -> None:
    source_path = _make_source_image(
        tmp_path / "source.jpg"
    )

    with pytest.raises(
        ValueError,
        match=(
            "unknown artwork generator font"
        ),
    ):
        render_episode_title_card(
            source_image_path=source_path,
            output_path=(
                tmp_path
                / "bad.jpg"
            ),
            episode_title="Pilot",
            font_key="does_not_exist",
        )


def test_render_episode_title_card_rejects_missing_source_image(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ArtworkGeneratorRenderError,
        match=(
            "source image does not exist"
        ),
    ):
        render_episode_title_card(
            source_image_path=(
                tmp_path
                / "missing.jpg"
            ),
            output_path=(
                tmp_path
                / "bad.jpg"
            ),
            episode_title="Pilot",
            font_key="prata",
        )
