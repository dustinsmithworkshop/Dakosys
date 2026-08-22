"""Developer preview utility tests."""

from pathlib import Path

from PIL import Image

import artwork_generator_preview as preview


EXPECTED_FONT_KEYS = (
    "cormorant_garamond",
    "marcellus",
    "prata",
    "libre_baskerville",
    "syne",
    "cinzel",
)


def test_preview_font_order_is_locked():
    assert tuple(
        font_key
        for (
            font_key,
            _display_name,
        )
        in preview.FONT_PREVIEWS
    ) == EXPECTED_FONT_KEYS


def test_render_font_previews_creates_all_outputs(
    tmp_path: Path,
    monkeypatch,
):
    source = (
        tmp_path
        / "source.jpg"
    )

    Image.new(
        "RGB",
        (
            1280,
            720,
        ),
        (
            32,
            64,
            96,
        ),
    ).save(
        source,
        format="JPEG",
    )

    calls = []

    def fake_render(
        *,
        source_image_path,
        output_path,
        episode_title,
        font_key,
        **_kwargs,
    ):
        calls.append(
            (
                Path(
                    source_image_path
                ),
                episode_title,
                font_key,
            )
        )

        Image.new(
            "RGB",
            (
                preview.CANVAS_WIDTH,
                preview.CANVAS_HEIGHT,
            ),
            (
                40,
                50,
                60,
            ),
        ).save(
            output_path,
            format="JPEG",
        )

    monkeypatch.setattr(
        preview,
        "render_episode_title_card",
        fake_render,
    )

    output_dir = (
        tmp_path
        / "previews"
    )

    rendered, comparison = (
        preview.render_font_previews(
            source_image_path=source,
            episode_title="Pilot",
            output_dir=output_dir,
        )
    )

    assert tuple(
        font_key
        for (
            _source,
            _title,
            font_key,
        )
        in calls
    ) == EXPECTED_FONT_KEYS

    assert all(
        title == "Pilot"
        for (
            _source,
            title,
            _font_key,
        )
        in calls
    )

    assert len(
        rendered
    ) == 6

    for path in rendered:
        assert path.is_file()

        with Image.open(
            path
        ) as image:
            assert image.size == (
                1920,
                1080,
            )

    assert comparison.is_file()

    with Image.open(
        comparison
    ) as image:
        assert image.size == (
            preview.CONTACT_WIDTH,
            preview.CONTACT_HEIGHT,
        )
