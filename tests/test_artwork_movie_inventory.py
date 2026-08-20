from types import SimpleNamespace

import pytest

from artwork.movie_inventory import (
    build_movie_identity,
    build_movie_inventory,
)


def _guid(value):
    return SimpleNamespace(
        id=value
    )


def test_build_movie_identity_from_plex():
    movie = SimpleNamespace(
        title="Blade Runner",
        year=1982,
        ratingKey="1234",
        guids=[
            _guid(
                "tmdb://78"
            ),
            _guid(
                "imdb://tt0083658"
            ),
        ],
    )

    identity = (
        build_movie_identity(
            movie,
            "Movies",
        )
    )

    assert identity.title == (
        "Blade Runner"
    )

    assert identity.year == 1982

    assert (
        identity.library
        == "Movies"
    )

    assert (
        identity.plex_rating_key
        == "1234"
    )

    assert identity.tmdb_id == 78

    assert (
        identity.imdb_id
        == "tt0083658"
    )

    assert (
        identity.tmdb_id_candidates
        == (78,)
    )

    assert (
        identity.imdb_id_candidates
        == ("tt0083658",)
    )


def test_movie_identity_preserves_candidates():
    movie = SimpleNamespace(
        title="Example",
        year="2025",
        ratingKey=10,
        guids=[
            _guid(
                "tmdb://100"
            ),
            _guid(
                "tmdb://101"
            ),
            _guid(
                "tmdb://100"
            ),
            _guid(
                "imdb://tt123"
            ),
        ],
    )

    identity = (
        build_movie_identity(
            movie,
            "Films",
        )
    )

    assert identity.tmdb_id == 100

    assert (
        identity.tmdb_id_candidates
        == (
            100,
            101,
        )
    )

    assert (
        identity.imdb_id_candidates
        == ("tt123",)
    )


def test_movie_identity_ignores_invalid_guids():
    movie = SimpleNamespace(
        title="Example",
        year=None,
        ratingKey="1",
        guids=[
            _guid(
                "tmdb://invalid"
            ),
            _guid(
                "tvdb://123"
            ),
            _guid(
                "garbage"
            ),
        ],
    )

    identity = (
        build_movie_identity(
            movie,
            "Movies",
        )
    )

    assert identity.tmdb_id is None
    assert identity.imdb_id is None
    assert identity.year is None


def test_movie_inventory_wraps_identity():
    movie = SimpleNamespace(
        title="Alien",
        year=1979,
        ratingKey="42",
        guids=[
            _guid(
                "tmdb://348"
            ),
        ],
    )

    inventory = (
        build_movie_inventory(
            movie,
            "Movies",
        )
    )

    assert (
        inventory.identity.title
        == "Alien"
    )

    assert (
        inventory.identity.tmdb_id
        == 348
    )


def test_movie_identity_requires_title():
    movie = SimpleNamespace(
        title=None,
        ratingKey="1",
        guids=[],
    )

    with pytest.raises(
        ValueError,
        match="missing a title",
    ):
        build_movie_identity(
            movie,
            "Movies",
        )


def test_movie_identity_requires_rating_key():
    movie = SimpleNamespace(
        title="Alien",
        ratingKey=None,
        rating_key=None,
        guids=[],
    )

    with pytest.raises(
        ValueError,
        match="missing a rating key",
    ):
        build_movie_identity(
            movie,
            "Movies",
        )
