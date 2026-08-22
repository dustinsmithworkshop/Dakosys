"""Render generated episode title cards from TMDB/Plex raw stills."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
from PIL import ImageOps


RENDERER_VERSION = 1
STYLE_VERSION = 1


CANVAS_WIDTH = 1920
CANVAS_HEIGHT = 1080
CANVAS_SIZE = (
    CANVAS_WIDTH,
    CANVAS_HEIGHT,
)

MAX_TEXT_WIDTH_RATIO = 0.80
MAX_TEXT_HEIGHT_RATIO = 0.25

LEFT_MARGIN = 96
RIGHT_MARGIN = 96
BOTTOM_MARGIN = 72

DEFAULT_MAX_FONT_SIZE = 150
DEFAULT_MIN_FONT_SIZE = 34
DEFAULT_LINE_SPACING = 8
DEFAULT_SHADOW_OFFSET = 3
DEFAULT_STROKE_WIDTH = 2

GRADIENT_HEIGHT_RATIO = 0.45
GRADIENT_MAX_ALPHA = 185

TITLE_FILL = (
    245,
    245,
    245,
    255,
)
TITLE_STROKE_FILL = (
    0,
    0,
    0,
    200,
)
TITLE_SHADOW_FILL = (
    0,
    0,
    0,
    180,
)

FONT_FILES = {
    "cormorant_garamond":
        "CormorantGaramond[wght].ttf",
    "prata":
        "Prata-Regular.ttf",
    "marcellus":
        "Marcellus-Regular.ttf",
    "syne":
        "Syne[wght].ttf",
    "libre_baskerville":
        "LibreBaskerville[wght].ttf",
    "cinzel":
        "Cinzel[wght].ttf",
    "noto_sans_jp":
        "NotoSansJP[wght].ttf",
}


class ArtworkGeneratorRenderError(
    RuntimeError
):
    """Raised when Dakosys cannot render one title card."""


@dataclass(frozen=True)
class TitleCardRenderResult:
    """Structured render output for one generated title card."""

    output_path: Path
    width: int
    height: int
    requested_font_key: str
    actual_font_key: str
    font_size: int
    title_lines: tuple[str, ...]
    text_box_width: int
    text_box_height: int


def render_episode_title_card(
    *,
    source_image_path: str | Path,
    output_path: str | Path,
    episode_title: str,
    font_key: str = (
        "cormorant_garamond"
    ),
    font_dir: str | Path = (
        "fonts/artwork-generator"
    ),
    jpeg_quality: int = 95,
) -> TitleCardRenderResult:
    """Render one generated episode title card.

    This is the MVP renderer for Dakosys 3.1:

    - source still from TMDB or Plex
    - 1920x1080 output
    - subtle lower gradient
    - lower-left title only
    - adaptive font sizing
    - 2-line maximum
    """

    normalized_title = _normalize_title(
        episode_title
    )

    source_path = Path(
        source_image_path
    )
    if not source_path.exists():
        raise ArtworkGeneratorRenderError(
            "source image does not exist: "
            f"{source_path}"
        )

    output_path = Path(
        output_path
    )
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    actual_font_key = _resolve_font_key(
        requested_font_key=font_key,
        text=normalized_title,
    )

    font_path = _resolve_font_path(
        font_key=actual_font_key,
        font_dir=font_dir,
    )

    with Image.open(source_path) as raw_image:
        base = ImageOps.fit(
            raw_image.convert("RGB"),
            CANVAS_SIZE,
            method=Image.Resampling.LANCZOS,
        )

    composed = _apply_bottom_gradient(
        base
    )

    layout = _fit_title_text(
        text=normalized_title,
        font_path=font_path,
    )

    draw = ImageDraw.Draw(
        composed,
        "RGBA",
    )

    text_x = LEFT_MARGIN
    text_y = (
        CANVAS_HEIGHT
        - BOTTOM_MARGIN
        - layout["text_box_height"]
    )

    rendered_text = "\n".join(
        layout["lines"]
    )

    shadow_x = (
        text_x
        + DEFAULT_SHADOW_OFFSET
    )
    shadow_y = (
        text_y
        + DEFAULT_SHADOW_OFFSET
    )

    draw.multiline_text(
        (
            shadow_x,
            shadow_y,
        ),
        rendered_text,
        font=layout["font"],
        fill=TITLE_SHADOW_FILL,
        spacing=DEFAULT_LINE_SPACING,
        stroke_width=0,
        align="left",
    )

    draw.multiline_text(
        (
            text_x,
            text_y,
        ),
        rendered_text,
        font=layout["font"],
        fill=TITLE_FILL,
        spacing=DEFAULT_LINE_SPACING,
        stroke_width=DEFAULT_STROKE_WIDTH,
        stroke_fill=TITLE_STROKE_FILL,
        align="left",
    )

    composed.convert("RGB").save(
        output_path,
        format="JPEG",
        quality=jpeg_quality,
        optimize=True,
    )

    return TitleCardRenderResult(
        output_path=output_path,
        width=CANVAS_WIDTH,
        height=CANVAS_HEIGHT,
        requested_font_key=font_key,
        actual_font_key=actual_font_key,
        font_size=layout["font_size"],
        title_lines=layout["lines"],
        text_box_width=layout["text_box_width"],
        text_box_height=layout["text_box_height"],
    )


def _normalize_title(
    episode_title: str,
) -> str:
    if not isinstance(
        episode_title,
        str,
    ):
        raise TypeError(
            "episode title must be a string"
        )

    normalized = " ".join(
        episode_title.split()
    ).strip()

    if not normalized:
        raise ValueError(
            "episode title cannot be empty"
        )

    return normalized


def _resolve_font_key(
    *,
    requested_font_key: str,
    text: str,
) -> str:
    if (
        requested_font_key
        not in FONT_FILES
    ):
        raise ValueError(
            "unknown artwork generator font: "
            f"{requested_font_key}"
        )

    if _contains_cjk(text):
        return "noto_sans_jp"

    return requested_font_key


def _resolve_font_path(
    *,
    font_key: str,
    font_dir: str | Path,
) -> Path:
    filename = FONT_FILES.get(
        font_key
    )
    if filename is None:
        raise ValueError(
            "unknown artwork generator font: "
            f"{font_key}"
        )

    path = (
        Path(font_dir)
        / filename
    )

    if not path.exists():
        raise ArtworkGeneratorRenderError(
            "font file does not exist: "
            f"{path}"
        )

    return path


def _contains_cjk(
    text: str,
) -> bool:
    for character in text:
        codepoint = ord(
            character
        )

        if (
            0x3040 <= codepoint <= 0x309F
            or 0x30A0 <= codepoint <= 0x30FF
            or 0x3400 <= codepoint <= 0x4DBF
            or 0x4E00 <= codepoint <= 0x9FFF
            or 0xF900 <= codepoint <= 0xFAFF
            or 0xFF66 <= codepoint <= 0xFF9D
        ):
            return True

    return False


def _apply_bottom_gradient(
    image: Image.Image,
) -> Image.Image:
    base = image.convert(
        "RGBA"
    )

    gradient_height = max(
        1,
        int(
            CANVAS_HEIGHT
            * GRADIENT_HEIGHT_RATIO
        ),
    )

    mask = Image.new(
        "L",
        (1, gradient_height),
    )

    denominator = max(
        gradient_height - 1,
        1,
    )

    for y in range(
        gradient_height
    ):
        ratio = y / denominator
        alpha = int(
            GRADIENT_MAX_ALPHA
            * ratio
        )
        mask.putpixel(
            (0, y),
            alpha,
        )

    alpha_mask = mask.resize(
        (
            CANVAS_WIDTH,
            gradient_height,
        )
    )

    overlay = Image.new(
        "RGBA",
        (
            CANVAS_WIDTH,
            gradient_height,
        ),
        (
            0,
            0,
            0,
            0,
        ),
    )
    overlay.putalpha(
        alpha_mask
    )

    base.alpha_composite(
        overlay,
        dest=(
            0,
            CANVAS_HEIGHT
            - gradient_height,
        ),
    )

    return base


def _fit_title_text(
    *,
    text: str,
    font_path: Path,
) -> dict[str, object]:
    max_width = int(
        CANVAS_WIDTH
        * MAX_TEXT_WIDTH_RATIO
    )
    max_height = int(
        CANVAS_HEIGHT
        * MAX_TEXT_HEIGHT_RATIO
    )

    scratch_image = Image.new(
        "RGBA",
        (8, 8),
    )
    draw = ImageDraw.Draw(
        scratch_image
    )

    for font_size in range(
        DEFAULT_MAX_FONT_SIZE,
        DEFAULT_MIN_FONT_SIZE - 1,
        -2,
    ):
        font = ImageFont.truetype(
            str(font_path),
            size=font_size,
        )

        lines = _wrap_text_to_two_lines(
            draw=draw,
            text=text,
            font=font,
            max_width=max_width,
        )

        if lines is None:
            continue

        bbox = draw.multiline_textbbox(
            (
                0,
                0,
            ),
            "\n".join(lines),
            font=font,
            spacing=DEFAULT_LINE_SPACING,
            stroke_width=DEFAULT_STROKE_WIDTH,
            align="left",
        )

        text_box_width = (
            bbox[2] - bbox[0]
        )
        text_box_height = (
            bbox[3] - bbox[1]
        )

        if (
            text_box_width
            <= max_width
            and text_box_height
            <= max_height
        ):
            return {
                "font": font,
                "font_size":
                    font_size,
                "lines":
                    tuple(lines),
                "text_box_width":
                    text_box_width,
                "text_box_height":
                    text_box_height,
            }

    raise ArtworkGeneratorRenderError(
        "unable to fit episode title within "
        "Artwork Generator layout constraints"
    )


def _wrap_text_to_two_lines(
    *,
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> tuple[str, ...] | None:
    if _text_width(
        draw=draw,
        text=text,
        font=font,
    ) <= max_width:
        return (text,)

    words = text.split()

    if len(words) <= 1:
        return None

    lines: list[str] = []
    current = ""

    for word in words:
        proposal = (
            word
            if not current
            else f"{current} {word}"
        )

        if _text_width(
            draw=draw,
            text=proposal,
            font=font,
        ) <= max_width:
            current = proposal
            continue

        if current:
            lines.append(current)
            current = word
        else:
            return None

        if len(lines) > 1:
            return None

    if current:
        lines.append(current)

    if not lines or len(lines) > 2:
        return None

    if any(
        _text_width(
            draw=draw,
            text=line,
            font=font,
        ) > max_width
        for line in lines
    ):
        return None

    return tuple(lines)


def _text_width(
    *,
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
) -> int:
    bbox = draw.textbbox(
        (
            0,
            0,
        ),
        text,
        font=font,
        stroke_width=DEFAULT_STROKE_WIDTH,
    )

    return bbox[2] - bbox[0]
