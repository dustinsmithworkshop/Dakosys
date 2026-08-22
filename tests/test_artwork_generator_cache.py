from pathlib import Path

from artwork.generator_cache import (
    build_generated_artwork_identity,
    generated_artwork_path,
)
from artwork.generator_inputs import (
    EpisodeGenerationInput,
    EpisodeGenerationPath,
)
from artwork.models import (
    ArtworkSource,
)


def _generation_input(
    *,
    title="The Journey's End",
    title_source=ArtworkSource.PLEX,
    image_source=ArtworkSource.TMDB,
    image_ref=(
        "https://image.tmdb.org/"
        "t/p/original/abc123.jpg"
    ),
    image_provider_asset_id=(
        "/abc123.jpg"
    ),
):
    return EpisodeGenerationInput(
        episode_number=1,
        path=(
            EpisodeGenerationPath
            .GENERATE_MISSING
        ),
        title=title,
        title_source=title_source,
        image_ref=image_ref,
        image_source=image_source,
        image_provider_asset_id=(
            image_provider_asset_id
        ),
    )


def _identity(
    **kwargs,
):
    generation_input = (
        kwargs.pop(
            "generation_input",
            _generation_input(),
        )
    )

    return build_generated_artwork_identity(
        show_key=kwargs.pop(
            "show_key",
            "tmdb:1398",
        ),
        season_number=kwargs.pop(
            "season_number",
            1,
        ),
        generation_input=(
            generation_input
        ),
        font_key=kwargs.pop(
            "font_key",
            "marcellus",
        ),
        **kwargs,
    )


def test_same_inputs_produce_same_fingerprint():
    first = _identity()
    second = _identity()

    assert (
        first.fingerprint()
        == second.fingerprint()
    )


def test_title_change_changes_fingerprint():
    first = _identity()

    second = _identity(
        generation_input=(
            _generation_input(
                title=(
                    "A Different "
                    "Episode Title"
                )
            )
        )
    )

    assert (
        first.fingerprint()
        != second.fingerprint()
    )


def test_tmdb_still_change_changes_fingerprint():
    first = _identity()

    second = _identity(
        generation_input=(
            _generation_input(
                image_ref=(
                    "https://image.tmdb.org/"
                    "t/p/original/new.jpg"
                ),
                image_provider_asset_id=(
                    "/new.jpg"
                ),
            )
        )
    )

    assert (
        first.fingerprint()
        != second.fingerprint()
    )


def test_plex_thumbnail_change_changes_fingerprint():
    first = _identity(
        generation_input=(
            _generation_input(
                image_source=(
                    ArtworkSource.PLEX
                ),
                image_ref=(
                    "/library/metadata/"
                    "123/thumb/456"
                ),
                image_provider_asset_id=None,
            )
        )
    )

    second = _identity(
        generation_input=(
            _generation_input(
                image_source=(
                    ArtworkSource.PLEX
                ),
                image_ref=(
                    "/library/metadata/"
                    "123/thumb/999"
                ),
                image_provider_asset_id=None,
            )
        )
    )

    assert (
        first.fingerprint()
        != second.fingerprint()
    )


def test_font_change_changes_fingerprint():
    first = _identity(
        font_key="marcellus"
    )

    second = _identity(
        font_key="prata"
    )

    assert (
        first.fingerprint()
        != second.fingerprint()
    )


def test_renderer_version_change_changes_fingerprint():
    first = _identity(
        renderer_version=1
    )

    second = _identity(
        renderer_version=2
    )

    assert (
        first.fingerprint()
        != second.fingerprint()
    )


def test_style_version_change_changes_fingerprint():
    first = _identity(
        style_version=1
    )

    second = _identity(
        style_version=2
    )

    assert (
        first.fingerprint()
        != second.fingerprint()
    )


def test_title_source_is_part_of_fingerprint():
    first = _identity()

    second = _identity(
        generation_input=(
            _generation_input(
                title_source=(
                    ArtworkSource.TMDB
                )
            )
        )
    )

    assert (
        first.fingerprint()
        != second.fingerprint()
    )


def test_generated_path_is_stable_and_human_readable(
    tmp_path: Path,
):
    identity = _identity()

    first = generated_artwork_path(
        root=tmp_path,
        identity=identity,
    )

    second = generated_artwork_path(
        root=tmp_path,
        identity=identity,
    )

    assert first == second

    assert first.parent == (
        tmp_path
        / "tv"
        / "tmdb-1398"
        / "season-01"
    )

    assert (
        first.name.startswith(
            "S01E01-"
        )
    )

    assert (
        first.suffix
        == ".jpg"
    )


def test_specials_use_season_zero_path(
    tmp_path: Path,
):
    identity = _identity(
        season_number=0
    )

    path = generated_artwork_path(
        root=tmp_path,
        identity=identity,
    )

    assert (
        path.parent.name
        == "season-00"
    )

    assert (
        path.name.startswith(
            "S00E01-"
        )
    )


def test_tmdb_provider_asset_id_is_preferred_for_image_identity():
    identity = _identity(
        generation_input=(
            _generation_input(
                image_ref=(
                    "https://example.test/"
                    "temporary-url.jpg"
                ),
                image_provider_asset_id=(
                    "/stable-still.jpg"
                ),
            )
        )
    )

    assert (
        identity.image_identity
        == "/stable-still.jpg"
    )
