from types import SimpleNamespace

from artwork.inventory import (
    SeasonInventory,
    ShowInventory,
)
from artwork.models import (
    ArtworkAsset,
    ArtworkKind,
    ArtworkQuality,
    ArtworkSource,
    EpisodeArtwork,
    SeasonArtwork,
    ShowArtworkState,
)
from artwork.tmdb_fallback import (
    TMDBFallbackPath,
    fill_tmdb_episode_gaps,
)


def _asset(
    *,
    source,
    asset_id,
    quality,
):
    return ArtworkAsset(
        kind=ArtworkKind.EPISODE_CARD,
        source=source,
        provider_asset_id=asset_id,
        url=f"https://example/{asset_id}",
        quality=quality,
    )


def _mediux(asset_id):
    return _asset(
        source=ArtworkSource.MEDIUX,
        asset_id=asset_id,
        quality=ArtworkQuality.CURATED,
    )


def _tmdb(asset_id):
    return _asset(
        source=ArtworkSource.TMDB,
        asset_id=asset_id,
        quality=ArtworkQuality.RAW_STILL,
    )


def _inventory(
    *,
    tmdb_id=100,
    seasons=None,
):
    seasons = (
        seasons
        if seasons is not None
        else {
            1: {1, 2, 3},
        }
    )

    return ShowInventory(
        identity=SimpleNamespace(
            library="TV",
            plex_rating_key="1",
            title="Example",
            year=2026,
            tvdb_id=200,
            tmdb_id=tmdb_id,
            imdb_id="tt0000001",
        ),
        seasons=tuple(
            SeasonInventory(
                season_number=number,
                episode_numbers=(
                    frozenset(episodes)
                ),
            )
            for number, episodes
            in seasons.items()
        ),
    )


def _state(
    *,
    tmdb_id=100,
    cards=None,
):
    cards = cards or {}

    seasons = {}

    for (
        season_number,
        episode_cards,
    ) in cards.items():
        seasons[
            season_number
        ] = SeasonArtwork(
            season_number=(
                season_number
            ),
            episodes={
                number: EpisodeArtwork(
                    episode_number=number,
                    card=card,
                )
                for number, card
                in episode_cards.items()
            },
        )

    return ShowArtworkState(
        title="Example",
        tvdb_id=200,
        tmdb_id=tmdb_id,
        seasons=seasons,
    )


class FakeClient:
    def __init__(
        self,
        responses=None,
    ):
        self.responses = (
            responses or {}
        )

        self.calls = []

    def get_season_episode_cards(
        self,
        *,
        tmdb_id,
        season_number,
    ):
        self.calls.append(
            (
                tmdb_id,
                season_number,
            )
        )

        response = (
            self.responses.get(
                season_number,
                {},
            )
        )

        if isinstance(
            response,
            Exception,
        ):
            raise response

        return dict(
            response
        )


def test_tmdb_fallback_fills_only_missing_cards():
    mediux_card = _mediux(
        "mediux-1"
    )

    state = _state(
        cards={
            1: {
                1: mediux_card,
            },
        }
    )

    client = FakeClient(
        {
            1: {
                1: _tmdb(
                    "tmdb-1"
                ),
                2: _tmdb(
                    "tmdb-2"
                ),
                3: _tmdb(
                    "tmdb-3"
                ),
                4: _tmdb(
                    "tmdb-extra"
                ),
            },
        }
    )

    result = fill_tmdb_episode_gaps(
        inventory=_inventory(),
        state=state,
        client=client,
    )

    assert (
        result.path
        is TMDBFallbackPath.FILLED_ALL
    )

    assert result.gaps_before == 2
    assert result.gaps_filled == 2
    assert result.gaps_remaining == 0

    # Existing curated artwork is untouched.
    assert (
        result.state
        .seasons[1]
        .episodes[1]
        .card
        is not mediux_card
    )

    preserved = (
        result.state
        .seasons[1]
        .episodes[1]
        .card
    )

    assert (
        preserved.source
        is ArtworkSource.MEDIUX
    )

    assert (
        preserved.provider_asset_id
        == "mediux-1"
    )

    assert (
        result.state
        .seasons[1]
        .episodes[2]
        .card
        .source
        is ArtworkSource.TMDB
    )

    # Provider extras not present in Plex are ignored.
    assert (
        4
        not in result.state
        .seasons[1]
        .episodes
    )

    # Input durable state was not mutated.
    assert (
        2
        not in state.seasons[1].episodes
    )


def test_tmdb_fallback_requests_only_seasons_with_gaps():
    state = _state(
        cards={
            1: {
                1: _mediux("1-1"),
                2: _mediux("1-2"),
            },
            2: {
                1: _mediux("2-1"),
            },
        }
    )

    inventory = _inventory(
        seasons={
            1: {1, 2},
            2: {1, 2},
        }
    )

    client = FakeClient(
        {
            2: {
                2: _tmdb("2-2"),
            },
        }
    )

    result = fill_tmdb_episode_gaps(
        inventory=inventory,
        state=state,
        client=client,
    )

    assert client.calls == [
        (100, 2),
    ]

    assert (
        result.season_request_count
        == 1
    )

    assert result.gaps_filled == 1


def test_tmdb_fallback_skips_provider_when_no_gaps():
    state = _state(
        cards={
            1: {
                1: _mediux("1"),
                2: _mediux("2"),
                3: _mediux("3"),
            },
        }
    )

    client = FakeClient()

    result = fill_tmdb_episode_gaps(
        inventory=_inventory(),
        state=state,
        client=client,
    )

    assert (
        result.path
        is TMDBFallbackPath.NO_GAPS
    )

    assert client.calls == []
    assert result.state is state


def test_tmdb_fallback_requires_tmdb_identity():
    inventory = _inventory(
        tmdb_id=None
    )

    state = _state(
        tmdb_id=None
    )

    client = FakeClient()

    result = fill_tmdb_episode_gaps(
        inventory=inventory,
        state=state,
        client=client,
    )

    assert (
        result.path
        is TMDBFallbackPath.NO_TMDB_ID
    )

    assert client.calls == []


def test_tmdb_fallback_rejects_identity_mismatch():
    inventory = _inventory(
        tmdb_id=100
    )

    state = _state(
        tmdb_id=999
    )

    client = FakeClient()

    result = fill_tmdb_episode_gaps(
        inventory=inventory,
        state=state,
        client=client,
    )

    assert (
        result.path
        is (
            TMDBFallbackPath
            .IDENTITY_MISMATCH
        )
    )

    assert client.calls == []


def test_tmdb_fallback_leaves_unavailable_stills_missing():
    client = FakeClient(
        {
            1: {
                2: _tmdb(
                    "tmdb-2"
                ),
            },
        }
    )

    result = fill_tmdb_episode_gaps(
        inventory=_inventory(),
        state=_state(),
        client=client,
    )

    assert (
        result.path
        is TMDBFallbackPath.FILLED_PARTIAL
    )

    assert result.gaps_before == 3
    assert result.gaps_filled == 1
    assert result.gaps_remaining == 2


def test_tmdb_fallback_reports_no_stills_as_normal_outcome():
    client = FakeClient(
        {
            1: {},
        }
    )

    result = fill_tmdb_episode_gaps(
        inventory=_inventory(),
        state=_state(),
        client=client,
    )

    assert (
        result.path
        is TMDBFallbackPath.NO_STILLS
    )

    assert result.provider_error_count == 0
    assert result.gaps_remaining == 3


def test_tmdb_fallback_preserves_state_on_provider_failure():
    state = _state(
        cards={
            1: {
                1: _mediux(
                    "existing"
                ),
            },
        }
    )

    client = FakeClient(
        {
            1: RuntimeError(
                "TMDB unavailable"
            ),
        }
    )

    result = fill_tmdb_episode_gaps(
        inventory=_inventory(),
        state=state,
        client=client,
    )

    assert (
        result.path
        is TMDBFallbackPath.PROVIDER_ERROR
    )

    assert result.gaps_filled == 0
    assert result.provider_error_count == 1

    assert (
        result.state
        .seasons[1]
        .episodes[1]
        .card
        .provider_asset_id
        == "existing"
    )
