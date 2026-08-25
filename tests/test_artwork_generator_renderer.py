from pathlib import Path

import pytest
from PIL import Image

from artwork.generator_renderer import (
    BUNDLED_FONT_DIR,
    FONT_FILES,
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


def test_render_episode_title_card_truncates_extreme_title_to_longest_prefix(
    tmp_path: Path,
) -> None:
    source_path = _make_source_image(
        tmp_path / "source.jpg"
    )

    title = (
        "Let Your Eyes Behold the Glory and Mystery of the Brothel "
        "with a Perfect Score! Take a Newlywed or a Horny Tutor or "
        "a Little Piggie as Your Lover! They'll Squeeze, Squeeze, "
        "Squeeze It Outta Ya! Infinite Pleasure Over a Satisfying "
        "Three-Day Excursion! True Happiness Awaits!!!"
    )

    result = render_episode_title_card(
        source_image_path=source_path,
        output_path=(
            tmp_path
            / "extreme-title.jpg"
        ),
        episode_title=title,
        font_key="marcellus",
    )

    rendered_title = " ".join(
        result.title_lines
    )

    assert rendered_title
    assert len(rendered_title) < len(title)
    assert title.startswith(
        rendered_title
    )

    assert result.font_size == 34

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
        tmp_path
        / "extreme-title.jpg"
    ).is_file()


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


def test_render_episode_title_card_defaults_to_marcellus(
    tmp_path: Path,
) -> None:
    source_path = _make_source_image(
        tmp_path
        / "source.jpg"
    )

    result = (
        render_episode_title_card(
            source_image_path=(
                source_path
            ),
            output_path=(
                tmp_path
                / "default-font.jpg"
            ),
            episode_title="Pilot",
        )
    )

    assert (
        result.requested_font_key
        == "marcellus"
    )

    assert (
        result.actual_font_key
        == "marcellus"
    )


def test_render_episode_title_card_wraps_long_cjk_title(
    tmp_path: Path,
) -> None:
    source_path = _make_source_image(
        tmp_path
        / "source.jpg"
    )

    title = (
        "これは非常に長い日本語の"
        "エピソードタイトルであり"
        "二行に折り返される必要があります"
    )

    result = (
        render_episode_title_card(
            source_image_path=(
                source_path
            ),
            output_path=(
                tmp_path
                / "long-japanese.jpg"
            ),
            episode_title=title,
            font_key="marcellus",
        )
    )

    assert (
        result.requested_font_key
        == "marcellus"
    )

    assert (
        result.actual_font_key
        == "noto_sans_jp"
    )

    assert len(
        result.title_lines
    ) == 2

    assert (
        "".join(
            result.title_lines
        )
        == title
    )

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


def test_long_cjk_wrapping_is_deterministic(
    tmp_path: Path,
) -> None:
    source_path = _make_source_image(
        tmp_path
        / "source.jpg"
    )

    title = (
        "世界の果てで始まる新しい"
        "冒険と別れそして再会の物語"
    )

    first = (
        render_episode_title_card(
            source_image_path=(
                source_path
            ),
            output_path=(
                tmp_path
                / "first.jpg"
            ),
            episode_title=title,
            font_key="prata",
        )
    )

    second = (
        render_episode_title_card(
            source_image_path=(
                source_path
            ),
            output_path=(
                tmp_path
                / "second.jpg"
            ),
            episode_title=title,
            font_key="prata",
        )
    )

    assert (
        first.actual_font_key
        == "noto_sans_jp"
    )

    assert (
        second.actual_font_key
        == "noto_sans_jp"
    )

    assert (
        first.title_lines
        == second.title_lines
    )

    assert (
        first.font_size
        == second.font_size
    )


def test_all_bundled_generator_fonts_exist() -> None:
    assert BUNDLED_FONT_DIR.is_absolute()

    missing = [
        filename
        for filename
        in FONT_FILES.values()
        if not (
            BUNDLED_FONT_DIR
            / filename
        ).is_file()
    ]

    assert missing == []


def test_default_font_resolution_does_not_depend_on_cwd(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source_dir = (
        tmp_path
        / "images"
    )

    source_dir.mkdir()

    source_path = _make_source_image(
        source_dir
        / "source.jpg"
    )

    output_path = (
        source_dir
        / "rendered.jpg"
    )

    unrelated_cwd = (
        tmp_path
        / "unrelated"
    )

    unrelated_cwd.mkdir()

    monkeypatch.chdir(
        unrelated_cwd
    )

    result = (
        render_episode_title_card(
            source_image_path=(
                source_path
            ),
            output_path=(
                output_path
            ),
            episode_title="Pilot",
        )
    )

    assert (
        result.requested_font_key
        == "marcellus"
    )

    assert (
        result.actual_font_key
        == "marcellus"
    )

    assert output_path.is_file()
