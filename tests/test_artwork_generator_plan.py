from pathlib import Path

import pytest

from artwork.generator_inputs import (
    EpisodeGenerationInput,
    EpisodeGenerationPath,
)
from artwork.generator_plan import (
    plan_generated_episode_card,
)
from artwork.models import (
    ArtworkKind,
    ArtworkQuality,
    ArtworkSource,
)


def _generation_input(
    *,
    title="Pilot",
    image_ref=(
        "https://image.tmdb.org/"
        "t/p/original/source.jpg"
    ),
    provider_asset_id=(
        "/source.jpg"
    ),
):
    return EpisodeGenerationInput(
        episode_number=1,
        path=(
            EpisodeGenerationPath
            .GENERATE_MISSING
        ),
        title=title,
        title_source=(
            ArtworkSource.PLEX
        ),
        image_ref=image_ref,
        image_source=(
            ArtworkSource.TMDB
        ),
        image_provider_asset_id=(
            provider_asset_id
        ),
    )


def test_plans_generated_asset_without_writing(
    tmp_path: Path,
):
    local_root = (
        tmp_path
        / "generated"
    )

    result = (
        plan_generated_episode_card(
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

    assert not local_root.exists()

    assert not result.cached
    assert (
        result.needs_materialization
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

    assert result.local_path == (
        local_root
        / "tv"
        / "tmdb-1398"
        / "season-01"
        / (
            "S01E01-"
            f"{result.fingerprint[:16]}"
            ".jpg"
        )
    )

    assert result.kometa_path == (
        "/config/assets/generated/"
        "tv/tmdb-1398/"
        "season-01/"
        f"S01E01-{result.fingerprint[:16]}.jpg"
    )


def test_existing_nonempty_cache_is_reused(
    tmp_path: Path,
):
    local_root = (
        tmp_path
        / "generated"
    )

    first = (
        plan_generated_episode_card(
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

    first.local_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    first.local_path.write_bytes(
        b"cached-jpeg"
    )

    second = (
        plan_generated_episode_card(
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

    assert second.cached
    assert not (
        second.needs_materialization
    )

    assert (
        second.fingerprint
        == first.fingerprint
    )

    assert (
        second.local_path
        == first.local_path
    )

    assert (
        second.asset
        == first.asset
    )


def test_zero_length_cache_is_not_reusable(
    tmp_path: Path,
):
    local_root = (
        tmp_path
        / "generated"
    )

    first = (
        plan_generated_episode_card(
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

    first.local_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    first.local_path.write_bytes(
        b""
    )

    second = (
        plan_generated_episode_card(
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

    assert not second.cached
    assert (
        second.needs_materialization
    )


def test_font_change_produces_new_generation_plan(
    tmp_path: Path,
):
    common = {
        "generation_input":
            _generation_input(),
        "show_key":
            "tmdb:1398",
        "season_number":
            1,
        "local_root":
            tmp_path
            / "generated",
        "kometa_root":
            "/config/assets/generated",
    }

    marcellus = (
        plan_generated_episode_card(
            font_key="marcellus",
            **common,
        )
    )

    prata = (
        plan_generated_episode_card(
            font_key="prata",
            **common,
        )
    )

    assert (
        marcellus.fingerprint
        != prata.fingerprint
    )

    assert (
        marcellus.local_path
        != prata.local_path
    )


def test_title_change_produces_new_generation_plan(
    tmp_path: Path,
):
    first = (
        plan_generated_episode_card(
            generation_input=(
                _generation_input(
                    title="Pilot"
                )
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
    )

    second = (
        plan_generated_episode_card(
            generation_input=(
                _generation_input(
                    title=(
                        "A Different Title"
                    )
                )
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
    )

    assert (
        first.fingerprint
        != second.fingerprint
    )


def test_ineligible_generation_input_is_rejected_without_writes(
    tmp_path: Path,
):
    local_root = (
        tmp_path
        / "generated"
    )

    generation_input = (
        EpisodeGenerationInput(
            episode_number=1,
            path=(
                EpisodeGenerationPath
                .KEEP_PRIMARY
            ),
        )
    )

    with pytest.raises(
        ValueError,
        match="not eligible",
    ):
        plan_generated_episode_card(
            generation_input=(
                generation_input
            ),
            show_key="tmdb:1398",
            season_number=1,
            font_key="marcellus",
            local_root=local_root,
            kometa_root=(
                "/config/assets/generated"
            ),
        )

    assert not local_root.exists()
