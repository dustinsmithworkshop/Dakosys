"""Materialize source images used by Artwork Generator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image

from artwork.generator_inputs import (
    EpisodeGenerationInput,
)
from artwork.models import (
    ArtworkSource,
)


DEFAULT_DOWNLOAD_TIMEOUT = 30.0
DEFAULT_MAX_IMAGE_BYTES = 25 * 1024 * 1024

DEFAULT_TMDB_IMAGE_ROOT = (
    "https://image.tmdb.org/t/p/original"
)


class ArtworkGeneratorSourceError(
    RuntimeError
):
    """A generation source image could not be materialized."""


class InvalidArtworkGeneratorSourceError(
    ArtworkGeneratorSourceError
):
    """A downloaded source body is not a decodable image."""


@dataclass(frozen=True)
class MaterializedSourceImage:
    """One downloaded source image ready for the renderer."""

    path: Path
    source: ArtworkSource
    source_ref: str
    byte_count: int


def materialize_generation_source(
    *,
    generation_input: EpisodeGenerationInput,
    destination: str | Path,
    plex_base_url: str | None = None,
    plex_token: str | None = None,
    tmdb_image_root: str = (
        DEFAULT_TMDB_IMAGE_ROOT
    ),
    session=None,
    timeout: float = (
        DEFAULT_DOWNLOAD_TIMEOUT
    ),
    max_bytes: int = (
        DEFAULT_MAX_IMAGE_BYTES
    ),
) -> MaterializedSourceImage:
    """Download one resolved generation source image.

    TMDB:
        Uses the resolved absolute URL when available.
        A TMDB provider path such as ``/abc.jpg`` is resolved against
        ``tmdb_image_root``.

    Plex:
        Relative Plex thumbnail paths are resolved against
        ``plex_base_url``.
        Plex authentication is sent only on the Plex request.

    The caller owns ``destination`` and may delete it after rendering.
    """

    if not generation_input.should_generate:
        raise ArtworkGeneratorSourceError(
            "generation input is not "
            "eligible for source materialization"
        )

    image_source = (
        generation_input.image_source
    )
    image_ref = (
        generation_input.image_ref
    )

    if (
        image_source is None
        or image_ref is None
        or not image_ref.strip()
    ):
        raise ArtworkGeneratorSourceError(
            "generation input has no "
            "usable source image"
        )

    if (
        not isinstance(
            timeout,
            (int, float),
        )
        or isinstance(
            timeout,
            bool,
        )
        or timeout <= 0
    ):
        raise ValueError(
            "download timeout must be positive"
        )

    if (
        not isinstance(
            max_bytes,
            int,
        )
        or isinstance(
            max_bytes,
            bool,
        )
        or max_bytes <= 0
    ):
        raise ValueError(
            "maximum image size must be "
            "a positive integer"
        )

    destination = Path(
        destination
    )

    client = (
        session
        if session is not None
        else requests.Session()
    )

    if (
        image_source
        is ArtworkSource.TMDB
    ):
        url = _tmdb_url(
            image_ref=image_ref,
            image_provider_asset_id=(
                generation_input
                .image_provider_asset_id
            ),
            tmdb_image_root=(
                tmdb_image_root
            ),
        )

        headers = None

    elif (
        image_source
        is ArtworkSource.PLEX
    ):
        url = _plex_url(
            image_ref=image_ref,
            plex_base_url=(
                plex_base_url
            ),
        )

        token = _required_text(
            plex_token,
            label="Plex token",
        )

        headers = {
            "X-Plex-Token": token,
        }

    else:
        raise ArtworkGeneratorSourceError(
            "unsupported generation image "
            f"source: {image_source.value}"
        )

    try:
        response = client.get(
            url,
            headers=headers,
            stream=True,
            timeout=timeout,
        )

        response.raise_for_status()

        content_type = (
            response.headers.get(
                "Content-Type",
                "",
            )
            or ""
        ).lower()

        if (
            content_type
            and not content_type.startswith(
                "image/"
            )
        ):
            raise ArtworkGeneratorSourceError(
                "generation source returned "
                "non-image content"
            )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        byte_count = 0

        try:
            with destination.open(
                "wb"
            ) as handle:
                for chunk in response.iter_content(
                    chunk_size=64 * 1024
                ):
                    if not chunk:
                        continue

                    byte_count += len(
                        chunk
                    )

                    if (
                        byte_count
                        > max_bytes
                    ):
                        raise ArtworkGeneratorSourceError(
                            "generation source image "
                            "exceeds configured "
                            "maximum size"
                        )

                    handle.write(
                        chunk
                    )

        except Exception:
            destination.unlink(
                missing_ok=True
            )
            raise

    except ArtworkGeneratorSourceError:
        raise

    except Exception as exc:
        destination.unlink(
            missing_ok=True
        )

        raise ArtworkGeneratorSourceError(
            "could not download generation "
            f"source image from {image_source.value}"
        ) from exc

    if byte_count == 0:
        destination.unlink(
            missing_ok=True
        )

        raise ArtworkGeneratorSourceError(
            "generation source image was empty"
        )

    # A successful HTTP response and image/* Content-Type do not prove
    # that the body contains a fully decodable image. Force Pillow to
    # decode the pixel data here so truncated/corrupt provider or Plex
    # responses are classified as source failures rather than renderer
    # failures.
    try:
        with Image.open(
            destination
        ) as image:
            image.load()

    except (
        OSError,
        ValueError,
    ) as exc:
        destination.unlink(
            missing_ok=True
        )

        raise InvalidArtworkGeneratorSourceError(
            "generation source returned "
            "invalid image data"
        ) from exc

    return MaterializedSourceImage(
        path=destination,
        source=image_source,
        source_ref=url,
        byte_count=byte_count,
    )


def _tmdb_url(
    *,
    image_ref: str,
    image_provider_asset_id: str | None,
    tmdb_image_root: str,
) -> str:
    ref = _required_text(
        image_ref,
        label="TMDB image reference",
    )

    parsed = urlparse(
        ref
    )

    if (
        parsed.scheme
        in {"http", "https"}
        and parsed.netloc
    ):
        return ref

    provider_path = (
        image_provider_asset_id
        or ref
    )

    provider_path = _required_text(
        provider_path,
        label="TMDB image path",
    )

    root = _required_text(
        tmdb_image_root,
        label="TMDB image root",
    ).rstrip(
        "/"
    )

    return (
        f"{root}/"
        f"{provider_path.lstrip('/')}"
    )


def _plex_url(
    *,
    image_ref: str,
    plex_base_url: str | None,
) -> str:
    ref = _required_text(
        image_ref,
        label="Plex image reference",
    )

    base = _required_text(
        plex_base_url,
        label="Plex base URL",
    ).rstrip(
        "/"
    )

    base_parsed = urlparse(
        base
    )

    if (
        base_parsed.scheme
        not in {"http", "https"}
        or not base_parsed.netloc
    ):
        raise ArtworkGeneratorSourceError(
            "Plex base URL must be "
            "an absolute HTTP(S) URL"
        )

    parsed = urlparse(
        ref
    )

    if (
        parsed.scheme
        in {"http", "https"}
        and parsed.netloc
    ):
        if (
            parsed.scheme
            != base_parsed.scheme
            or parsed.netloc
            != base_parsed.netloc
        ):
            raise ArtworkGeneratorSourceError(
                "absolute Plex image URL "
                "does not match configured "
                "Plex server"
            )

        return ref

    if not ref.startswith(
        "/"
    ):
        ref = (
            "/"
            + ref
        )

    return (
        base
        + ref
    )


def _required_text(
    value,
    *,
    label: str,
) -> str:
    if not isinstance(
        value,
        str,
    ):
        raise ArtworkGeneratorSourceError(
            f"{label} is required"
        )

    normalized = value.strip()

    if not normalized:
        raise ArtworkGeneratorSourceError(
            f"{label} is required"
        )

    return normalized
