from types import SimpleNamespace

import pytest

from artwork.episode_coverage import (
    resolve_episode_coverage,
)
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
)


def _inventory(
    *,
    tvdb_id=200,
    tmdb_id=100,
    seasons=None,
):
    if seasons is None:
        seasons = {
            1: {1, 2, 3},
        }

    return ShowInventory(
        identity=SimpleNamespace(
            library="TV",
            plex_rating_key="1",
            title="Example Show",
            year=2026,
            tvdb_id=tvdb_id,
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


def _card(
    *,
    source,
    asset_id,
    quality,
):
    return ArtworkAsset(
        kind=ArtworkKind.EPISODE_CARD,
        source=source,
        provider_asset_id=asset_id,
        url=(
            f"https://example/"
            f"{asset_id}.jpg"
        ),
        quality=quality,
    )


def _mediux(
    asset_id,
):
    return _card(
        source=ArtworkSource.MEDIUX,
        asset_id=asset_id,
        quality=ArtworkQuality.CURATED,
    )


def _tmdb(
    asset_id,
):
    return _card(
        source=ArtworkSource.TMDB,
        asset_id=asset_id,
        quality=ArtworkQuality.RAW_STILL,
    )


def _state(
    *,
    tvdb_id=200,
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
                episode_number: (
                    EpisodeArtwork(
                        episode_number=(
                            episode_number
                        ),
                        card=card,
                    )
                )
                for (
                    episode_number,
                    card,
                ) in episode_cards.items()
            },
        )

    return ShowArtworkState(
        title="Example Show",
        tvdb_id=tvdb_id,
        tmdb_id=tmdb_id,
        imdb_id="tt0000001",
        seasons=seasons,
    )


class FakeTMDBClient:
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


def test_coverage_enriches_existing_mediux_state():
    mediux = _mediux(
        "mediux-1"
    )

    state = _state(
        cards={
            1: {
                1: mediux,
            },
        }
    )

    client = FakeTMDBClient(
        {
            1: {
                2: _tmdb("tmdb-2"),
                3: _tmdb("tmdb-3"),
            },
        }
    )

    result = resolve_episode_coverage(
        inventory=_inventory(),
        state=state,
        tmdb_client=client,
    )

    assert result.resolved is True
    assert result.created is False
    assert result.changed is True

    assert result.gaps_before == 2
    assert result.gaps_filled == 2
    assert result.gaps_remaining == 0

    resolved = result.state

    assert (
        resolved
        .seasons[1]
        .episodes[1]
        .card
        .source
        is ArtworkSource.MEDIUX
    )

    assert (
        resolved
        .seasons[1]
        .episodes[2]
        .card
        .source
        is ArtworkSource.TMDB
    )

    # Original durable state was not mutated.
    assert (
        2
        not in state.seasons[1].episodes
    )


def test_coverage_can_create_state_from_tmdb_only():
    client = FakeTMDBClient(
        {
            1: {
                1: _tmdb("tmdb-1"),
                2: _tmdb("tmdb-2"),
            },
        }
    )

    inventory = _inventory()

    result = resolve_episode_coverage(
        inventory=inventory,
        state=None,
        tmdb_client=client,
    )

    assert result.resolved is True
    assert result.created is True
    assert result.changed is True

    assert result.gaps_before == 3
    assert result.gaps_filled == 2
    assert result.gaps_remaining == 1

    state = result.state

    assert state.title == "Example Show"
    assert state.tvdb_id == 200
    assert state.tmdb_id == 100
    assert state.imdb_id == "tt0000001"

    assert state.selected_set_id is None
    assert state.episode_selection is None
    assert state.presentation_selection is None

    assert (
        state
        .seasons[1]
        .episodes[1]
        .card
        .source
        is ArtworkSource.TMDB
    )


def test_coverage_does_not_create_empty_state_when_tmdb_has_no_stills():
    client = FakeTMDBClient(
        {
            1: {},
        }
    )

    result = resolve_episode_coverage(
        inventory=_inventory(),
        state=None,
        tmdb_client=client,
    )

    assert result.resolved is False
    assert result.created is False
    assert result.changed is False

    assert result.state is None

    assert (
        result.tmdb_path
        is TMDBFallbackPath.NO_STILLS
    )


def test_coverage_does_not_create_state_on_tmdb_failure():
    client = FakeTMDBClient(
        {
            1: RuntimeError(
                "TMDB unavailable"
            ),
        }
    )

    result = resolve_episode_coverage(
        inventory=_inventory(),
        state=None,
        tmdb_client=client,
    )

    assert result.state is None
    assert result.resolved is False
    assert result.provider_error_count == 1

    assert (
        result.tmdb_path
        is TMDBFallbackPath.PROVIDER_ERROR
    )


def test_coverage_preserves_existing_state_when_tmdb_has_nothing():
    state = _state(
        cards={
            1: {
                1: _mediux("existing"),
            },
        }
    )

    client = FakeTMDBClient(
        {
            1: {},
        }
    )

    result = resolve_episode_coverage(
        inventory=_inventory(),
        state=state,
        tmdb_client=client,
    )

    assert result.resolved is True
    assert result.created is False
    assert result.changed is False

    assert (
        result.state
        .seasons[1]
        .episodes[1]
        .card
        .provider_asset_id
        == "existing"
    )


def test_coverage_skips_tmdb_when_existing_state_is_complete():
    state = _state(
        cards={
            1: {
                1: _mediux("1"),
                2: _mediux("2"),
                3: _mediux("3"),
            },
        }
    )

    client = FakeTMDBClient()

    result = resolve_episode_coverage(
        inventory=_inventory(),
        state=state,
        tmdb_client=client,
    )

    assert result.state is state
    assert result.changed is False

    assert (
        result.tmdb_path
        is TMDBFallbackPath.NO_GAPS
    )

    assert client.calls == []


def test_coverage_rejects_tvdb_identity_mismatch():
    state = _state(
        tvdb_id=999,
    )

    client = FakeTMDBClient()

    with pytest.raises(
        ValueError,
        match="TVDB ID",
    ):
        resolve_episode_coverage(
            inventory=_inventory(
                tvdb_id=200,
            ),
            state=state,
            tmdb_client=client,
        )

    assert client.calls == []
