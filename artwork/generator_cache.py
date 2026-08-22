"""Deterministic identity and cache paths for generated episode artwork."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from artwork.generator_inputs import (
    EpisodeGenerationInput,
)
from artwork.generator_renderer import (
    RENDERER_VERSION,
    STYLE_VERSION,
)
from artwork.models import (
    ArtworkSource,
)


@dataclass(frozen=True)
class GeneratedArtworkIdentity:
    """Stable identity for one generated episode title card."""

    show_key: str

    season_number: int
    episode_number: int

    image_source: ArtworkSource
    image_identity: str

    title: str
    title_source: ArtworkSource

    font_key: str

    renderer_version: int = (
        RENDERER_VERSION
    )
    style_version: int = (
        STYLE_VERSION
    )

    def fingerprint(
        self,
    ) -> str:
        """Return deterministic SHA-256 identity for rendered output."""

        payload = {
            "show_key":
                self.show_key,

            "season_number":
                self.season_number,

            "episode_number":
                self.episode_number,

            "image_source":
                self.image_source.value,

            "image_identity":
                self.image_identity,

            "title":
                self.title,

            "title_source":
                self.title_source.value,

            "font_key":
                self.font_key,

            "renderer_version":
                self.renderer_version,

            "style_version":
                self.style_version,
        }

        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(
                ",",
                ":",
            ),
            sort_keys=True,
        ).encode(
            "utf-8"
        )

        return hashlib.sha256(
            encoded
        ).hexdigest()


def build_generated_artwork_identity(
    *,
    show_key: str,
    season_number: int,
    generation_input: EpisodeGenerationInput,
    font_key: str,
    renderer_version: int = (
        RENDERER_VERSION
    ),
    style_version: int = (
        STYLE_VERSION
    ),
) -> GeneratedArtworkIdentity:
    """Build a deterministic cache identity from resolved inputs."""

    normalized_show_key = (
        _normalize_required_text(
            show_key,
            label="show key",
        )
    )

    _validate_nonnegative_integer(
        season_number,
        label="season number",
    )

    if (
        not generation_input
        .should_generate
    ):
        raise ValueError(
            "generation input is not "
            "eligible for rendering"
        )

    title = (
        generation_input.title
    )

    if title is None:
        raise ValueError(
            "generation input has no title"
        )

    title_source = (
        generation_input.title_source
    )

    if title_source is None:
        raise ValueError(
            "generation input has no title source"
        )

    image_source = (
        generation_input.image_source
    )

    if image_source is None:
        raise ValueError(
            "generation input has no image source"
        )

    image_identity = (
        generation_input
        .image_provider_asset_id
        or generation_input.image_ref
    )

    if image_identity is None:
        raise ValueError(
            "generation input has no image identity"
        )

    image_identity = (
        _normalize_required_text(
            image_identity,
            label="image identity",
        )
    )

    normalized_font_key = (
        _normalize_required_text(
            font_key,
            label="font key",
        )
    )

    _validate_positive_integer(
        renderer_version,
        label="renderer version",
    )

    _validate_positive_integer(
        style_version,
        label="style version",
    )

    return GeneratedArtworkIdentity(
        show_key=normalized_show_key,
        season_number=season_number,
        episode_number=(
            generation_input
            .episode_number
        ),
        image_source=image_source,
        image_identity=image_identity,
        title=title,
        title_source=title_source,
        font_key=normalized_font_key,
        renderer_version=(
            renderer_version
        ),
        style_version=(
            style_version
        ),
    )


def generated_artwork_path(
    *,
    root: str | Path,
    identity: GeneratedArtworkIdentity,
) -> Path:
    """Return deterministic local JPEG path for one generation."""

    root = Path(
        root
    )

    show_directory = (
        _filesystem_show_key(
            identity.show_key
        )
    )

    fingerprint = (
        identity.fingerprint()
    )

    filename = (
        f"S{identity.season_number:02d}"
        f"E{identity.episode_number:02d}"
        f"-{fingerprint[:16]}"
        ".jpg"
    )

    return (
        root
        / "tv"
        / show_directory
        / (
            f"season-"
            f"{identity.season_number:02d}"
        )
        / filename
    )


def _filesystem_show_key(
    show_key: str,
) -> str:
    normalized = (
        show_key.strip().lower()
    )

    normalized = re.sub(
        r"[^a-z0-9]+",
        "-",
        normalized,
    ).strip(
        "-"
    )

    if not normalized:
        raise ValueError(
            "show key cannot produce "
            "an empty cache directory"
        )

    return normalized


def _normalize_required_text(
    value,
    *,
    label: str,
) -> str:
    if not isinstance(
        value,
        str,
    ):
        raise ValueError(
            f"{label} must be a string"
        )

    normalized = value.strip()

    if not normalized:
        raise ValueError(
            f"{label} cannot be empty"
        )

    return normalized


def _validate_positive_integer(
    value,
    *,
    label: str,
) -> None:
    if (
        not isinstance(
            value,
            int,
        )
        or isinstance(
            value,
            bool,
        )
        or value <= 0
    ):
        raise ValueError(
            f"{label} must be a "
            "positive integer"
        )


def _validate_nonnegative_integer(
    value,
    *,
    label: str,
) -> None:
    if (
        not isinstance(
            value,
            int,
        )
        or isinstance(
            value,
            bool,
        )
        or value < 0
    ):
        raise ValueError(
            f"{label} must be a "
            "non-negative integer"
        )
