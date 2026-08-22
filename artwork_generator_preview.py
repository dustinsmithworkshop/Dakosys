#!/usr/bin/env python3
"""Render Artwork Generator font previews from one source still."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont

from artwork.generator_renderer import (
    BUNDLED_FONT_DIR,
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    render_episode_title_card,
)


FONT_PREVIEWS = (
    (
        "cormorant_garamond",
        "Cormorant Garamond",
    ),
    (
        "marcellus",
        "Marcellus",
    ),
    (
        "prata",
        "Prata",
    ),
    (
        "libre_baskerville",
        "Libre Baskerville",
    ),
    (
        "syne",
        "Syne",
    ),
    (
        "cinzel",
        "Cinzel",
    ),
)

CONTACT_COLUMNS = 3
CONTACT_ROWS = 2

THUMBNAIL_WIDTH = 640
THUMBNAIL_HEIGHT = 360
LABEL_HEIGHT = 56

CONTACT_WIDTH = (
    CONTACT_COLUMNS
    * THUMBNAIL_WIDTH
)

CONTACT_HEIGHT = (
    CONTACT_ROWS
    * (
        THUMBNAIL_HEIGHT
        + LABEL_HEIGHT
    )
)


def render_font_previews(
    *,
    source_image_path: str | Path,
    episode_title: str,
    output_dir: str | Path,
) -> tuple[
    tuple[Path, ...],
    Path,
]:
    """Render all selectable 3.1 fonts and one comparison sheet."""

    source_path = Path(
        source_image_path
    )

    if not source_path.is_file():
        raise FileNotFoundError(
            "source image does not exist: "
            f"{source_path}"
        )

    output_dir = Path(
        output_dir
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    rendered_paths: list[
        Path
    ] = []

    for (
        font_key,
        _display_name,
    ) in FONT_PREVIEWS:
        output_path = (
            output_dir
            / f"{font_key}.jpg"
        )

        render_episode_title_card(
            source_image_path=(
                source_path
            ),
            output_path=(
                output_path
            ),
            episode_title=(
                episode_title
            ),
            font_key=font_key,
        )

        rendered_paths.append(
            output_path
        )

    comparison_path = (
        output_dir
        / "comparison.jpg"
    )

    _build_comparison_sheet(
        rendered_paths=(
            tuple(
                rendered_paths
            )
        ),
        output_path=(
            comparison_path
        ),
    )

    return (
        tuple(
            rendered_paths
        ),
        comparison_path,
    )


def _build_comparison_sheet(
    *,
    rendered_paths: tuple[
        Path,
        ...,
    ],
    output_path: Path,
) -> None:
    if len(
        rendered_paths
    ) != len(
        FONT_PREVIEWS
    ):
        raise ValueError(
            "comparison sheet requires "
            "all six font previews"
        )

    sheet = Image.new(
        "RGB",
        (
            CONTACT_WIDTH,
            CONTACT_HEIGHT,
        ),
        (
            18,
            18,
            18,
        ),
    )

    draw = ImageDraw.Draw(
        sheet
    )

    label_font = (
        ImageFont.truetype(
            str(
                BUNDLED_FONT_DIR
                / "Marcellus-Regular.ttf"
            ),
            size=28,
        )
    )

    for index, (
        (
            _font_key,
            display_name,
        ),
        rendered_path,
    ) in enumerate(
        zip(
            FONT_PREVIEWS,
            rendered_paths,
            strict=True,
        )
    ):
        column = (
            index
            % CONTACT_COLUMNS
        )

        row = (
            index
            // CONTACT_COLUMNS
        )

        x = (
            column
            * THUMBNAIL_WIDTH
        )

        y = (
            row
            * (
                THUMBNAIL_HEIGHT
                + LABEL_HEIGHT
            )
        )

        with Image.open(
            rendered_path
        ) as rendered:
            thumbnail = (
                rendered
                .convert("RGB")
                .resize(
                    (
                        THUMBNAIL_WIDTH,
                        THUMBNAIL_HEIGHT,
                    ),
                    Image.Resampling.LANCZOS,
                )
            )

        sheet.paste(
            thumbnail,
            (
                x,
                y,
            ),
        )

        draw.text(
            (
                x + 18,
                y
                + THUMBNAIL_HEIGHT
                + 10,
            ),
            display_name,
            font=label_font,
            fill=(
                245,
                245,
                245,
            ),
        )

    sheet.save(
        output_path,
        format="JPEG",
        quality=95,
        optimize=True,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Render the same episode title card "
            "with all six Dakosys 3.1 fonts."
        )
    )

    parser.add_argument(
        "--source",
        required=True,
        help=(
            "Local source still or Plex/TMDB "
            "image already downloaded to disk."
        ),
    )

    parser.add_argument(
        "--title",
        required=True,
        help="Episode title to render.",
    )

    parser.add_argument(
        "--output-dir",
        default=(
            "data/"
            "artwork_generator_preview"
        ),
        help=(
            "Preview output directory "
            "(default: "
            "data/artwork_generator_preview)."
        ),
    )

    return parser


def main() -> int:
    args = (
        _parser()
        .parse_args()
    )

    rendered, comparison = (
        render_font_previews(
            source_image_path=(
                args.source
            ),
            episode_title=(
                args.title
            ),
            output_dir=(
                args.output_dir
            ),
        )
    )

    print(
        "Artwork Generator previews:"
    )

    for (
        (
            _font_key,
            display_name,
        ),
        path,
    ) in zip(
        FONT_PREVIEWS,
        rendered,
        strict=True,
    ):
        print(
            f"  {display_name}: "
            f"{path}"
        )

    print(
        "  Comparison: "
        f"{comparison}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
