from datetime import (
    datetime,
    timedelta,
    timezone,
)
from pathlib import Path

from artwork.generator_inputs import (
    EpisodeGenerationInput,
    EpisodeGenerationPath,
)
from artwork.generator_source_failures import (
    is_generation_source_known_invalid,
    record_invalid_generation_source,
    source_failure_marker_path,
)
from artwork.models import (
    ArtworkSource,
)


NOW = datetime(
    2026,
    8,
    26,
    8,
    0,
    tzinfo=timezone.utc,
)


def _plex_input(
    image_ref=(
        "/library/metadata/"
        "114373/thumb/1786889881"
    ),
):
    return EpisodeGenerationInput(
        episode_number=7,
        path=(
            EpisodeGenerationPath
            .GENERATE_MISSING
        ),
        title="Sibling Rivalry",
        title_source=(
            ArtworkSource.PLEX
        ),
        image_ref=image_ref,
        image_source=(
            ArtworkSource.PLEX
        ),
        image_provider_asset_id=None,
    )


def test_records_and_recognizes_exact_invalid_source(
    tmp_path: Path,
):
    generation_input = (
        _plex_input()
    )

    marker = (
        record_invalid_generation_source(
            root=tmp_path,
            generation_input=(
                generation_input
            ),
            reason=(
                "generation source returned "
                "invalid image data"
            ),
            now=NOW,
        )
    )

    assert marker.is_file()

    assert (
        marker
        == source_failure_marker_path(
            root=tmp_path,
            generation_input=(
                generation_input
            ),
        )
    )

    assert is_generation_source_known_invalid(
        root=tmp_path,
        generation_input=(
            generation_input
        ),
        now=NOW,
    )


def test_changed_plex_thumb_identity_is_not_suppressed(
    tmp_path: Path,
):
    original = _plex_input()

    record_invalid_generation_source(
        root=tmp_path,
        generation_input=original,
        reason="invalid image data",
        now=NOW,
    )

    refreshed = _plex_input(
        image_ref=(
            "/library/metadata/"
            "114373/thumb/9999999999"
        )
    )

    assert not (
        is_generation_source_known_invalid(
            root=tmp_path,
            generation_input=refreshed,
            now=NOW,
        )
    )


def test_expired_invalid_source_is_reconsidered(
    tmp_path: Path,
):
    generation_input = (
        _plex_input()
    )

    record_invalid_generation_source(
        root=tmp_path,
        generation_input=(
            generation_input
        ),
        reason="invalid image data",
        now=NOW,
    )

    assert not (
        is_generation_source_known_invalid(
            root=tmp_path,
            generation_input=(
                generation_input
            ),
            now=(
                NOW
                + timedelta(
                    hours=25
                )
            ),
        )
    )


def test_malformed_marker_fails_open(
    tmp_path: Path,
):
    generation_input = (
        _plex_input()
    )

    marker = (
        source_failure_marker_path(
            root=tmp_path,
            generation_input=(
                generation_input
            ),
        )
    )

    marker.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    marker.write_text(
        "{broken",
        encoding="utf-8",
    )

    assert not (
        is_generation_source_known_invalid(
            root=tmp_path,
            generation_input=(
                generation_input
            ),
            now=NOW,
        )
    )
