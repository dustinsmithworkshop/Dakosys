import json
from pathlib import Path

import pytest

from artwork.inventory import SeasonInventory
from artwork.models import (
    ArtworkKind,
    ArtworkQuality,
    ArtworkSource,
    SelectionMode,
)
from artwork.providers.mediux import (
    MediuxClient,
    MediuxProvider,
    MediuxResponseError,
    parse_mediux_show_sets,
)
from artwork.search import (
    ArtworkSearchKind,
    ArtworkSearchRequest,
)


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "mediux_show_sets.json"
)


def _payload():
    return json.loads(
        FIXTURE.read_text(
            encoding="utf-8"
        )
    )


def _request(
    *,
    tmdb_id=549,
    tvdb_id=72368,
):
    return ArtworkSearchRequest(
        library="Series Vault",
        plex_rating_key="100",
        title="Example Show",
        year=1990,
        tvdb_id=tvdb_id,
        tmdb_id=tmdb_id,
        imdb_id="tt0098844",
        seasons=(
            SeasonInventory(
                season_number=1,
                episode_numbers=frozenset(
                    {
                        1,
                        2,
                    }
                ),
            ),
        ),
        kind=ArtworkSearchKind.DISCOVERY,
        selection_mode=SelectionMode.AUTO,
    )


def test_parser_maps_complete_show_set():
    sets = parse_mediux_show_sets(
        _payload(),
        expected_tmdb_id=549,
    )

    assert len(sets) == 1

    artwork_set = sets[0]

    assert artwork_set.provider is ArtworkSource.MEDIUX
    assert artwork_set.set_id == "17571"
    assert artwork_set.title == "Example Complete Set"
    assert artwork_set.creator == "example_artist"

    assert artwork_set.poster is not None
    assert artwork_set.poster.kind is ArtworkKind.SHOW_POSTER
    assert artwork_set.poster.provider_asset_id == "poster-1"
    assert artwork_set.poster.quality is ArtworkQuality.CURATED

    assert artwork_set.background is not None
    assert (
        artwork_set.background.provider_asset_id
        == "backdrop-1"
    )

    season = artwork_set.seasons[1]

    assert season.poster is not None
    assert (
        season.poster.provider_asset_id
        == "season-1-poster"
    )

    assert (
        season.episodes[1]
        .card
        .provider_asset_id
        == "s1e1-card"
    )

    assert (
        season.episodes[2]
        .card
        .provider_asset_id
        == "s1e2-card"
    )


def test_parser_preserves_specials_season_zero():
    artwork_set = parse_mediux_show_sets(
        _payload(),
        expected_tmdb_id=549,
    )[0]

    specials = artwork_set.seasons[0]

    assert specials.season_number == 0
    assert (
        specials.poster.provider_asset_id
        == "season-0-poster"
    )
    assert (
        specials.episodes[1]
        .card
        .provider_asset_id
        == "special-1-card"
    )


def test_non_url_src_is_not_treated_as_kometa_url():
    artwork_set = parse_mediux_show_sets(
        _payload(),
    )[0]

    card = (
        artwork_set
        .seasons[1]
        .episodes[1]
        .card
    )

    assert card.url is None
    assert card.provider_asset_id == "s1e1-card"


def test_parser_rejects_tmdb_identity_mismatch():
    with pytest.raises(
        MediuxResponseError,
        match="TMDB ID mismatch",
    ):
        parse_mediux_show_sets(
            _payload(),
            expected_tmdb_id=999,
        )


def test_parser_returns_empty_when_show_not_found():
    payload = {
        "data": {
            "shows_by_id": None,
        },
    }

    assert (
        parse_mediux_show_sets(
            payload,
            expected_tmdb_id=549,
        )
        == []
    )


class FakeClient:
    def __init__(
        self,
        *,
        payload=None,
        resolved_tmdb=None,
    ):
        self.payload = (
            payload
            if payload is not None
            else _payload()
        )
        self.resolved_tmdb = resolved_tmdb
        self.show_calls = []
        self.tvdb_calls = []

    def get_show_sets(
        self,
        tmdb_id,
    ):
        self.show_calls.append(
            tmdb_id
        )
        return self.payload

    def resolve_show_tmdb_id(
        self,
        tvdb_id,
    ):
        self.tvdb_calls.append(
            tvdb_id
        )
        return self.resolved_tmdb


def test_provider_uses_tmdb_id_directly():
    client = FakeClient()

    provider = MediuxProvider(
        client
    )

    sets = provider.find_sets(
        _request()
    )

    assert len(sets) == 1
    assert client.show_calls == [549]
    assert client.tvdb_calls == []


def test_provider_falls_back_from_tvdb_to_tmdb():
    client = FakeClient(
        resolved_tmdb=549,
    )

    provider = MediuxProvider(
        client
    )

    sets = provider.find_sets(
        _request(
            tmdb_id=None,
        )
    )

    assert len(sets) == 1
    assert client.tvdb_calls == [72368]
    assert client.show_calls == [549]


def test_provider_returns_empty_without_usable_identity():
    client = FakeClient()

    provider = MediuxProvider(
        client
    )

    sets = provider.find_sets(
        _request(
            tmdb_id=None,
            tvdb_id=None,
        )
    )

    assert sets == []
    assert client.tvdb_calls == []
    assert client.show_calls == []


class FakeResponse:
    status = 200

    def __init__(
        self,
        payload,
    ):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        traceback,
    ):
        return False

    def read(self):
        return json.dumps(
            self.payload
        ).encode("utf-8")


class RecordingOpener:
    def __init__(
        self,
        payload,
    ):
        self.payload = payload
        self.request = None
        self.timeout = None

    def __call__(
        self,
        request,
        *,
        timeout,
    ):
        self.request = request
        self.timeout = timeout

        return FakeResponse(
            self.payload
        )


def test_client_sends_bearer_graphql_request():
    opener = RecordingOpener(
        {
            "data": {
                "shows_by_id": None,
            },
        }
    )

    client = MediuxClient(
        "secret-token",
        opener=opener,
    )

    client.get_show_sets(
        549
    )

    assert opener.request is not None

    headers = {
        key.casefold(): value
        for key, value
        in opener.request.header_items()
    }

    assert headers[
        "authorization"
    ] == "Bearer secret-token"

    body = json.loads(
        opener.request.data.decode(
            "utf-8"
        )
    )

    assert body[
        "variables"
    ] == {
        "tmdb_id": "549",
    }

    assert body[
        "query_name"
    ] == "getShowItemSetsByTMDBID"


def test_client_raises_on_graphql_errors():
    opener = RecordingOpener(
        {
            "errors": [
                {
                    "message": (
                        "invalid credentials"
                    ),
                }
            ],
        }
    )

    client = MediuxClient(
        "expired-token",
        opener=opener,
    )

    with pytest.raises(
        MediuxResponseError,
        match="invalid credentials",
    ):
        client.get_show_sets(
            549
        )
