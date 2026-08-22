"""Materialize cacheable generated episode artwork."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from artwork.generator_cache import (
    GeneratedArtworkIdentity,
    build_generated_artwork_identity,
    generated_artwork_path,
)
from artwork.generator_inputs import (
    EpisodeGenerationInput,
)
from artwork.generator_paths import (
    translate_generated_artwork_path,
)
from artwork.generator_renderer import (
    render_episode_title_card,
)
from artwork.generator_source import (
    DEFAULT_DOWNLOAD_TIMEOUT,
    DEFAULT_MAX_IMAGE_BYTES,
    DEFAULT_TMDB_IMAGE_ROOT,
    materialize_generation_source,
)
from artwork.models import (
    ArtworkAsset,
    ArtworkKind,
    ArtworkQuality,
    ArtworkSource,
)


class ArtworkGeneratorMaterializationError(
    RuntimeError
):
    """A generated episode card could not be materialized."""


@dataclass(frozen=True)
class GeneratedEpisodeCardResult:
    """Result of materializing one generated episode card."""

    asset: ArtworkAsset
    identity: GeneratedArtworkIdentity

    local_path: Path
    kometa_path: str

    fingerprint: str
    reused: bool


def materialize_generated_episode_card(
    *,
    generation_input: EpisodeGenerationInput,
    show_key: str,
    season_number: int,
    font_key: str,
    local_root: str | Path,
    kometa_root: str,
    font_dir: str | Path = (
        "fonts/artwork-generator"
    ),
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
) -> GeneratedEpisodeCardResult:
    """Render or reuse one deterministic generated episode card.

    The final JPEG is written atomically. Source downloads and
    intermediate renders live only in a temporary directory and are
    removed after success or failure.
    """

    identity = (
        build_generated_artwork_identity(
            show_key=show_key,
            season_number=season_number,
            generation_input=(
                generation_input
            ),
            font_key=font_key,
        )
    )

    local_root = Path(
        local_root
    )

    output_path = (
        generated_artwork_path(
            root=local_root,
            identity=identity,
        )
    )

    fingerprint = (
        identity.fingerprint()
    )

    kometa_path = (
        translate_generated_artwork_path(
            local_path=str(
                output_path
            ),
            local_root=str(
                local_root
            ),
            kometa_root=kometa_root,
        )
    )

    if _usable_cached_file(
        output_path
    ):
        return _result(
            identity=identity,
            local_path=output_path,
            kometa_path=kometa_path,
            fingerprint=fingerprint,
            reused=True,
        )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:
        with TemporaryDirectory(
            prefix=".dakosys-generator-",
            dir=output_path.parent,
        ) as temporary_directory:
            temporary_directory = Path(
                temporary_directory
            )

            source_path = (
                temporary_directory
                / "source-image"
            )

            rendered_path = (
                temporary_directory
                / "rendered.jpg"
            )

            materialize_generation_source(
                generation_input=(
                    generation_input
                ),
                destination=source_path,
                plex_base_url=(
                    plex_base_url
                ),
                plex_token=plex_token,
                tmdb_image_root=(
                    tmdb_image_root
                ),
                session=session,
                timeout=timeout,
                max_bytes=max_bytes,
            )

            render_episode_title_card(
                source_image_path=(
                    source_path
                ),
                output_path=(
                    rendered_path
                ),
                episode_title=(
                    identity.title
                ),
                font_key=(
                    identity.font_key
                ),
                font_dir=font_dir,
            )

            if not _usable_cached_file(
                rendered_path
            ):
                raise (
                    ArtworkGeneratorMaterializationError(
                        "Artwork Generator renderer "
                        "did not produce a usable JPEG"
                    )
                )

            # os.replace is atomic when source and destination are on
            # the same filesystem. The temporary directory deliberately
            # lives underneath output_path.parent for that reason.
            os.replace(
                rendered_path,
                output_path,
            )

    except ArtworkGeneratorMaterializationError:
        raise

    except Exception as exc:
        raise ArtworkGeneratorMaterializationError(
            "could not materialize generated "
            "episode artwork"
        ) from exc

    return _result(
        identity=identity,
        local_path=output_path,
        kometa_path=kometa_path,
        fingerprint=fingerprint,
        reused=False,
    )


def _usable_cached_file(
    path: Path,
) -> bool:
    try:
        return (
            path.is_file()
            and path.stat().st_size > 0
        )

    except OSError:
        return False


def _result(
    *,
    identity: GeneratedArtworkIdentity,
    local_path: Path,
    kometa_path: str,
    fingerprint: str,
    reused: bool,
) -> GeneratedEpisodeCardResult:
    asset = ArtworkAsset(
        kind=(
            ArtworkKind.EPISODE_CARD
        ),
        source=(
            ArtworkSource.GENERATED
        ),
        provider_asset_id=(
            fingerprint
        ),
        quality=(
            ArtworkQuality.GENERATED
        ),
        file_path=kometa_path,
    )

    return GeneratedEpisodeCardResult(
        asset=asset,
        identity=identity,
        local_path=local_path,
        kometa_path=kometa_path,
        fingerprint=fingerprint,
        reused=reused,
    )
