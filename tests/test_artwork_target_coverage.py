from pathlib import Path
from types import SimpleNamespace

from artwork.inventory import (
    SeasonInventory,
    ShowInventory,
)
from artwork.models import (
    ArtworkAsset,
    ArtworkKind,
    ArtworkQuality,
    ArtworkSet,
    ArtworkSource,
    EpisodeArtwork,
    SeasonArtwork,
    ShowArtworkState,
)
from artwork.target_execution import (
    execute_show_target,
)
from artwork.targets import (
    ArtworkTarget,
    MediaType,
)


def _asset(
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
    return _asset(
        ArtworkSource.MEDIUX,
        asset_id,
        ArtworkQuality.CURATED,
    )


def _tmdb(
    asset_id,
):
    return _asset(
        ArtworkSource.TMDB,
        asset_id,
        ArtworkQuality.RAW_STILL,
    )


def _inventory(
    *,
    rating_key="1",
    tvdb_id=100,
    tmdb_id=200,
    title="Example",
    episodes=(1, 2),
):
    return ShowInventory(
        identity=SimpleNamespace(
            library="TV",
            plex_rating_key=rating_key,
            title=title,
            year=2026,
            tvdb_id=tvdb_id,
            tmdb_id=tmdb_id,
            imdb_id=(
                f"tt{tvdb_id:07d}"
            ),
        ),
        seasons=(
            SeasonInventory(
                season_number=1,
                episode_numbers=(
                    frozenset(
                        episodes
                    )
                ),
            ),
        ),
    )


def _set(
    set_id,
    episodes,
):
    return ArtworkSet(
        provider=ArtworkSource.MEDIUX,
        set_id=set_id,
        creator="creator",
        seasons={
            1: SeasonArtwork(
                season_number=1,
                episodes={
                    number: EpisodeArtwork(
                        episode_number=number,
                        card=_mediux(
                            f"{set_id}-{number}"
                        ),
                    )
                    for number in episodes
                },
            ),
        },
    )


def _managed_state(
    *,
    tvdb_id=100,
    tmdb_id=200,
    episodes=(1,),
    selected=True,
):
    return ShowArtworkState(
        title="Example",
        tvdb_id=tvdb_id,
        tmdb_id=tmdb_id,
        imdb_id=(
            f"tt{tvdb_id:07d}"
        ),
        seasons={
            1: SeasonArtwork(
                season_number=1,
                episodes={
                    number: EpisodeArtwork(
                        episode_number=number,
                        card=_mediux(
                            f"current-{number}"
                        ),
                    )
                    for number in episodes
                },
            ),
        },
        selected_set_id=(
            "CURRENT"
            if selected
            else None
        ),
        selected_set_source=(
            ArtworkSource.MEDIUX
            if selected
            else None
        ),
        selected_creator=(
            "creator"
            if selected
            else None
        ),
    )


def _target():
    return ArtworkTarget(
        name="TV",
        library="TV",
        media_type=MediaType.SHOW,
        output_path=Path(
            "/tmp/artwork-tv"
        ),
    )


class FakeProvider:
    name = "mediux"

    def __init__(
        self,
        responses=None,
    ):
        self.responses = (
            responses or {}
        )

        self.requests = []

    def find_sets(
        self,
        request,
    ):
        self.requests.append(
            request
        )

        response = (
            self.responses.get(
                request.plex_rating_key,
                [],
            )
        )

        if isinstance(
            response,
            Exception,
        ):
            raise response

        return list(
            response
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
                (
                    tmdb_id,
                    season_number,
                ),
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


def test_unmanaged_mediux_state_gets_tmdb_gap_fill():
    inventory = _inventory(
        rating_key="new",
    )

    provider = FakeProvider(
        {
            "new": [
                _set(
                    "CARDS",
                    episodes=(1,),
                ),
            ],
        }
    )

    tmdb = FakeTMDBClient(
        {
            (200, 1): {
                2: _tmdb(
                    "tmdb-2"
                ),
            },
        }
    )

    result = execute_show_target(
        target=_target(),
        inventories=(
            inventory,
        ),
        managed_shows=(),
        provider=provider,
        tmdb_client=tmdb,
    )

    assert result.coverage_enabled is True

    assert (
        result.discovery.selected_count
        == 1
    )

    assert result.resolved_count == 1

    state = result.resolved_states[0]

    assert (
        state
        .seasons[1]
        .episodes[1]
        .card
        .source
        is ArtworkSource.MEDIUX
    )

    assert (
        state
        .seasons[1]
        .episodes[2]
        .card
        .source
        is ArtworkSource.TMDB
    )

    assert result.tmdb_changed_count == 1
    assert result.tmdb_gap_fill_count == 1
    assert result.tmdb_request_count == 1
    assert result.tmdb_created_count == 0


def test_unmanaged_show_without_mediux_can_be_created_from_tmdb():
    inventory = _inventory(
        rating_key="tmdb-only",
    )

    provider = FakeProvider(
        {
            "tmdb-only": [],
        }
    )

    tmdb = FakeTMDBClient(
        {
            (200, 1): {
                1: _tmdb(
                    "tmdb-1"
                ),
                2: _tmdb(
                    "tmdb-2"
                ),
            },
        }
    )

    result = execute_show_target(
        target=_target(),
        inventories=(
            inventory,
        ),
        managed_shows=(),
        provider=provider,
        tmdb_client=tmdb,
    )

    # Primary-provider discovery found nothing.
    assert (
        result.discovery.selected_count
        == 0
    )

    # TMDB still produced useful durable state.
    assert result.tmdb_created_count == 1
    assert result.resolved_count == 1

    state = result.resolved_states[0]

    assert state.selected_set_id is None
    assert state.episode_selection is None

    assert (
        state
        .seasons[1]
        .episodes[1]
        .card
        .source
        is ArtworkSource.TMDB
    )


def test_managed_incomplete_state_gets_tmdb_gap_fill():
    inventory = _inventory(
        rating_key="managed",
    )

    state = _managed_state(
        episodes=(1,),
    )

    provider = FakeProvider(
        {
            "managed": [
                _set(
                    "CURRENT",
                    episodes=(1,),
                ),
            ],
        }
    )

    tmdb = FakeTMDBClient(
        {
            (200, 1): {
                2: _tmdb(
                    "tmdb-2"
                ),
            },
        }
    )

    result = execute_show_target(
        target=_target(),
        inventories=(
            inventory,
        ),
        managed_shows=(
            state,
        ),
        provider=provider,
        tmdb_client=tmdb,
    )

    assert result.matched_count == 1
    assert result.resolved_count == 1

    resolved = (
        result.resolved_states[0]
    )

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

    assert result.tmdb_gap_fill_count == 1


def test_complete_managed_state_does_not_query_tmdb():
    inventory = _inventory(
        rating_key="complete",
    )

    state = _managed_state(
        episodes=(1, 2),
    )

    provider = FakeProvider()
    tmdb = FakeTMDBClient()

    result = execute_show_target(
        target=_target(),
        inventories=(
            inventory,
        ),
        managed_shows=(
            state,
        ),
        provider=provider,
        tmdb_client=tmdb,
    )

    assert result.resolved_count == 1

    # Complete managed state skipped both provider layers.
    assert provider.requests == []
    assert tmdb.calls == []

    assert result.tmdb_request_count == 0
    assert result.tmdb_gap_fill_count == 0


def test_missing_managed_set_context_is_not_bypassed_by_tmdb():
    inventory = _inventory(
        rating_key="unsafe",
    )

    state = _managed_state(
        episodes=(1,),
        selected=False,
    )

    provider = FakeProvider()

    tmdb = FakeTMDBClient(
        {
            (200, 1): {
                2: _tmdb(
                    "should-not-run"
                ),
            },
        }
    )

    result = execute_show_target(
        target=_target(),
        inventories=(
            inventory,
        ),
        managed_shows=(
            state,
        ),
        provider=provider,
        tmdb_client=tmdb,
    )

    assert (
        result.managed
        .missing_set_context_count
        == 1
    )

    assert result.resolved_count == 0

    # TMDB cannot silently bypass managed-state safety.
    assert tmdb.calls == []


def test_no_tmdb_client_preserves_original_target_behavior():
    inventory = _inventory(
        rating_key="none",
    )

    provider = FakeProvider(
        {
            "none": [],
        }
    )

    result = execute_show_target(
        target=_target(),
        inventories=(
            inventory,
        ),
        managed_shows=(),
        provider=provider,
    )

    assert result.coverage_enabled is False

    assert (
        result.discovery.selected_count
        == 0
    )

    assert result.resolved_count == 0
    assert result.tmdb_request_count == 0
