"""Read-only planning for generated episode artwork."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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
from artwork.models import (
    ArtworkAsset,
    ArtworkKind,
    ArtworkQuality,
    ArtworkSource,
)


@dataclass(frozen=True)
class GeneratedEpisodeCardPlan:
    """Read-only plan for one generated episode card."""

    generation_input: EpisodeGenerationInput

    identity: GeneratedArtworkIdentity

    local_path: Path
    kometa_path: str

    fingerprint: str

    asset: ArtworkAsset

    cached: bool

    @property
    def needs_materialization(
        self,
    ) -> bool:
        """Whether apply must create the generated JPEG."""

        return not self.cached


def plan_generated_episode_card(
    *,
    generation_input: EpisodeGenerationInput,
    show_key: str,
    season_number: int,
    font_key: str,
    local_root: str | Path,
    kometa_root: str,
) -> GeneratedEpisodeCardPlan:
    """Plan one deterministic generated card without writing files."""

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

    local_path = (
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
                local_path
            ),
            local_root=str(
                local_root
            ),
            kometa_root=kometa_root,
        )
    )

    cached = (
        _usable_cached_file(
            local_path
        )
    )

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

    return GeneratedEpisodeCardPlan(
        generation_input=(
            generation_input
        ),
        identity=identity,
        local_path=local_path,
        kometa_path=kometa_path,
        fingerprint=fingerprint,
        asset=asset,
        cached=cached,
    )


def _usable_cached_file(
    path: Path,
) -> bool:
    """Check cache state without modifying the filesystem."""

    try:
        return (
            path.is_file()
            and path.stat().st_size > 0
        )

    except OSError:
        return False
