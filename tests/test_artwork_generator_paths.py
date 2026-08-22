import pytest

from artwork.generator_paths import (
    GeneratedArtworkPathError,
    translate_generated_artwork_path,
)


def test_translates_generated_path_between_container_views():
    translated = (
        translate_generated_artwork_path(
            local_path=(
                "/kometa/assets/generated/"
                "tv/tmdb-1398/"
                "season-01/"
                "S01E01-test.jpg"
            ),
            local_root=(
                "/kometa/assets/generated"
            ),
            kometa_root=(
                "/config/assets/generated"
            ),
        )
    )

    assert translated == (
        "/config/assets/generated/"
        "tv/tmdb-1398/"
        "season-01/"
        "S01E01-test.jpg"
    )


def test_translation_preserves_specials_path():
    translated = (
        translate_generated_artwork_path(
            local_path=(
                "/kometa/assets/generated/"
                "tv/tmdb-1398/"
                "season-00/"
                "S00E01-test.jpg"
            ),
            local_root=(
                "/kometa/assets/generated"
            ),
            kometa_root=(
                "/config/assets/generated"
            ),
        )
    )

    assert translated.endswith(
        "/tv/tmdb-1398/"
        "season-00/"
        "S00E01-test.jpg"
    )


def test_local_root_itself_maps_to_kometa_root():
    translated = (
        translate_generated_artwork_path(
            local_path=(
                "/kometa/assets/generated"
            ),
            local_root=(
                "/kometa/assets/generated"
            ),
            kometa_root=(
                "/config/assets/generated"
            ),
        )
    )

    assert translated == (
        "/config/assets/generated"
    )


def test_path_outside_local_root_is_rejected():
    with pytest.raises(
        GeneratedArtworkPathError,
        match="outside",
    ):
        translate_generated_artwork_path(
            local_path=(
                "/other/assets/card.jpg"
            ),
            local_root=(
                "/kometa/assets/generated"
            ),
            kometa_root=(
                "/config/assets/generated"
            ),
        )


def test_relative_local_path_is_rejected():
    with pytest.raises(
        GeneratedArtworkPathError,
        match="absolute",
    ):
        translate_generated_artwork_path(
            local_path=(
                "generated/card.jpg"
            ),
            local_root=(
                "/kometa/assets/generated"
            ),
            kometa_root=(
                "/config/assets/generated"
            ),
        )


def test_relative_local_root_is_rejected():
    with pytest.raises(
        GeneratedArtworkPathError,
        match="absolute",
    ):
        translate_generated_artwork_path(
            local_path=(
                "/kometa/assets/generated/"
                "card.jpg"
            ),
            local_root=(
                "generated"
            ),
            kometa_root=(
                "/config/assets/generated"
            ),
        )


def test_relative_kometa_root_is_rejected():
    with pytest.raises(
        GeneratedArtworkPathError,
        match="absolute",
    ):
        translate_generated_artwork_path(
            local_path=(
                "/kometa/assets/generated/"
                "card.jpg"
            ),
            local_root=(
                "/kometa/assets/generated"
            ),
            kometa_root=(
                "assets/generated"
            ),
        )


def test_normalizes_redundant_path_components():
    translated = (
        translate_generated_artwork_path(
            local_path=(
                "/kometa/assets/generated/"
                "tv/tmdb-1398/"
                "season-01/../season-02/"
                "S02E03-test.jpg"
            ),
            local_root=(
                "/kometa/assets/generated"
            ),
            kometa_root=(
                "/config/assets/generated"
            ),
        )
    )

    assert translated == (
        "/config/assets/generated/"
        "tv/tmdb-1398/"
        "season-02/"
        "S02E03-test.jpg"
    )
