from artwork.models import (
    ArtworkKind,
    ArtworkSource,
)
from artwork.providers.mediux import (
    MediuxProvider,
    parse_mediux_movie_sets,
)
from artwork.search import (
    ArtworkSearchKind,
    ArtworkSearchRequest,
)
from artwork.targets import MediaType


def _payload():
    return {
        "data": {
            "movies_by_id": {
                "id": "78",
                "title": "Blade Runner",
                "imdb_id": "tt0083658",
                "movie_sets": [
                    {
                        "id": "set-1",
                        "set_title": "Blade Runner",
                        "user_created": {
                            "username": "creator",
                        },
                        "movie_poster": [
                            {
                                "id": "poster-1",
                                "src": None,
                            }
                        ],
                        "movie_backdrop": [
                            {
                                "id": "backdrop-1",
                                "src": None,
                            }
                        ],
                    }
                ],
            }
        }
    }


def _request(
    *,
    tmdb_id=78,
    media_type=MediaType.MOVIE,
):
    return ArtworkSearchRequest(
        library="Movies",
        plex_rating_key="123",
        title="Blade Runner",
        year=1982,
        tvdb_id=None,
        tmdb_id=tmdb_id,
        imdb_id="tt0083658",
        seasons=(),
        kind=ArtworkSearchKind.DISCOVERY,
        media_type=media_type,
    )


def test_parse_mediux_movie_sets():
    sets = parse_mediux_movie_sets(
        _payload(),
        expected_tmdb_id=78,
    )

    assert len(sets) == 1

    artwork_set = sets[0]

    assert (
        artwork_set.provider
        is ArtworkSource.MEDIUX
    )

    assert artwork_set.set_id == "set-1"
    assert artwork_set.creator == "creator"

    assert (
        artwork_set.poster.kind
        is ArtworkKind.MOVIE_POSTER
    )

    assert (
        artwork_set.background.kind
        is ArtworkKind.MOVIE_BACKGROUND
    )

    assert (
        artwork_set.poster.provider_asset_id
        == "poster-1"
    )

    assert (
        artwork_set.background.provider_asset_id
        == "backdrop-1"
    )


def test_parse_movie_sets_empty_movie():
    assert (
        parse_mediux_movie_sets(
            {
                "data": {
                    "movies_by_id": None,
                }
            }
        )
        == []
    )


def test_movie_provider_uses_movie_endpoint():
    class Client:
        def __init__(self):
            self.movie_calls = []
            self.show_calls = []

        def get_movie_sets(
            self,
            tmdb_id,
        ):
            self.movie_calls.append(
                tmdb_id
            )

            return _payload()

        def get_show_sets(
            self,
            tmdb_id,
        ):
            self.show_calls.append(
                tmdb_id
            )

            raise AssertionError(
                "movie request used show endpoint"
            )

        def resolve_show_tmdb_id(
            self,
            tvdb_id,
        ):
            raise AssertionError(
                "movie request used TVDB resolution"
            )

    client = Client()

    provider = MediuxProvider(
        client
    )

    sets = provider.find_sets(
        _request()
    )

    assert len(sets) == 1
    assert client.movie_calls == [78]
    assert client.show_calls == []


def test_movie_provider_requires_tmdb_id():
    class Client:
        def get_movie_sets(
            self,
            tmdb_id,
        ):
            raise AssertionError(
                "provider should not query without TMDB ID"
            )

        def resolve_show_tmdb_id(
            self,
            tvdb_id,
        ):
            raise AssertionError(
                "movie must not use TVDB fallback"
            )

    provider = MediuxProvider(
        Client()
    )

    assert (
        provider.find_sets(
            _request(
                tmdb_id=None
            )
        )
        == []
    )


def test_show_request_still_uses_show_path():
    class Client:
        def __init__(self):
            self.resolved = []

        def resolve_show_tmdb_id(
            self,
            tvdb_id,
        ):
            self.resolved.append(
                tvdb_id
            )

            return 999

        def get_show_sets(
            self,
            tmdb_id,
        ):
            assert tmdb_id == 999

            return {
                "data": {
                    "shows_by_id": None,
                }
            }

        def get_movie_sets(
            self,
            tmdb_id,
        ):
            raise AssertionError(
                "show request used movie endpoint"
            )

    request = ArtworkSearchRequest(
        library="TV",
        plex_rating_key="5",
        title="Example",
        year=2020,
        tvdb_id=1234,
        tmdb_id=None,
        imdb_id=None,
        seasons=(),
        kind=(
            ArtworkSearchKind.DISCOVERY
        ),
    )

    client = Client()

    provider = MediuxProvider(
        client
    )

    assert (
        provider.find_sets(
            request
        )
        == []
    )

    assert client.resolved == [1234]
