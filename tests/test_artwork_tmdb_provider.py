from artwork.models import (
    ArtworkKind,
    ArtworkQuality,
    ArtworkSource,
)
from artwork.providers.tmdb import (
    TMDBArtworkClient,
)


class FakeResponse:
    def __init__(
        self,
        *,
        status_code=200,
        payload=None,
    ):
        self.status_code = status_code
        self._payload = (
            payload
            if payload is not None
            else {}
        )

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(
                f"HTTP {self.status_code}"
            )


class FakeSession:
    def __init__(
        self,
        responses,
    ):
        self.headers = {}
        self.responses = list(
            responses
        )
        self.calls = []

    def get(
        self,
        url,
        *,
        params=None,
        timeout=None,
    ):
        self.calls.append(
            {
                "url": url,
                "params": params,
                "timeout": timeout,
            }
        )

        return self.responses.pop(0)


def test_tmdb_artwork_client_builds_episode_cards():
    session = FakeSession(
        [
            FakeResponse(
                payload={
                    "episodes": [
                        {
                            "episode_number": 1,
                            "still_path": (
                                "/one.jpg"
                            ),
                        },
                        {
                            "episode_number": 2,
                            "still_path": None,
                        },
                        {
                            "episode_number": 3,
                            "still_path": (
                                "/three.jpg"
                            ),
                        },
                    ],
                }
            ),
        ]
    )

    client = TMDBArtworkClient(
        api_key="test-key",
        base_url=(
            "https://tmdb.example/3"
        ),
        session=session,
        timeout=12.0,
    )

    cards = (
        client
        .get_season_episode_cards(
            tmdb_id=100,
            season_number=2,
        )
    )

    assert set(cards) == {
        1,
        3,
    }

    card = cards[1]

    assert (
        card.kind
        is ArtworkKind.EPISODE_CARD
    )

    assert (
        card.source
        is ArtworkSource.TMDB
    )

    assert (
        card.quality
        is ArtworkQuality.RAW_STILL
    )

    assert (
        card.provider_asset_id
        == "/one.jpg"
    )

    assert (
        card.url
        == (
            "https://image.tmdb.org/"
            "t/p/original/one.jpg"
        )
    )

    assert session.calls == [
        {
            "url": (
                "https://tmdb.example/3"
                "/tv/100/season/2"
            ),
            "params": {
                "api_key": "test-key",
            },
            "timeout": 12.0,
        }
    ]


def test_tmdb_artwork_client_returns_empty_for_missing_season():
    session = FakeSession(
        [
            FakeResponse(
                status_code=404,
            ),
        ]
    )

    client = TMDBArtworkClient(
        api_key="test-key",
        session=session,
    )

    cards = (
        client
        .get_season_episode_cards(
            tmdb_id=100,
            season_number=99,
        )
    )

    assert cards == {}


def test_tmdb_artwork_client_publicly_resolves_tvdb_identity():
    from types import SimpleNamespace

    session = FakeSession(
        [
            FakeResponse(
                payload={
                    "tv_results": [
                        {
                            "id": 456,
                        },
                    ],
                }
            ),
        ]
    )

    client = TMDBArtworkClient(
        api_key="test-key",
        base_url=(
            "https://tmdb.example/3"
        ),
        session=session,
    )

    identity = SimpleNamespace(
        tmdb_id=None,
        tvdb_id=71663,
        imdb_id=None,
    )

    tmdb_id, source = (
        client.resolve_tmdb_id(
            identity
        )
    )

    assert tmdb_id == 456
    assert source == "tvdb"

    assert session.calls == [
        {
            "url": (
                "https://tmdb.example/3"
                "/find/71663"
            ),
            "params": {
                "external_source": (
                    "tvdb_id"
                ),
                "api_key": "test-key",
            },
            "timeout": 30.0,
        }
    ]
