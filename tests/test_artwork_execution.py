from types import SimpleNamespace

from artwork.execution import (
    ManagedExecutionPath,
    execute_managed_library,
    execute_managed_show,
)
from artwork.inventory import (
    SeasonInventory,
    ShowInventory,
)
from artwork.models import (
    ArtworkAsset,
    ArtworkKind,
    ArtworkSet,
    ArtworkSource,
    EpisodeArtwork,
    SeasonArtwork,
    ShowArtworkState,
)
from artwork.policy import SetAction
from artwork.search import (
    ArtworkSearchKind,
)


class FakeProvider:
    name = "fake"

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


def _inventory(
    *,
    rating_key="1",
    tvdb_id=12345,
    episodes=4,
    title="Example Show",
):
    identity = SimpleNamespace(
        library="TV",
        plex_rating_key=(
            rating_key
        ),
        title=title,
        year=2024,
        tvdb_id=tvdb_id,
        tmdb_id=67890,
        imdb_id="tt1234567",
    )

    return ShowInventory(
        identity=identity,
        seasons=(
            SeasonInventory(
                season_number=1,
                episode_numbers=(
                    frozenset(
                        range(
                            1,
                            episodes + 1,
                        )
                    )
                ),
            ),
        ),
    )


def _card(
    asset_id,
):
    return ArtworkAsset(
        kind=(
            ArtworkKind
            .EPISODE_CARD
        ),
        source=(
            ArtworkSource
            .MEDIUX
        ),
        provider_asset_id=(
            asset_id
        ),
        url=(
            "https://api.mediux.pro/assets/"
            f"{asset_id}"
        ),
    )


def _set(
    set_id,
    episodes,
):
    return ArtworkSet(
        provider=(
            ArtworkSource
            .MEDIUX
        ),
        set_id=set_id,
        creator=(
            f"creator-{set_id}"
        ),
        seasons={
            1: SeasonArtwork(
                season_number=1,
                episodes={
                    number: EpisodeArtwork(
                        episode_number=(
                            number
                        ),
                        card=_card(
                            f"{set_id}-"
                            f"{number}"
                        ),
                    )
                    for number in range(
                        1,
                        episodes + 1,
                    )
                },
            ),
        },
    )


def _state(
    *,
    set_id="A",
    episodes=2,
    tvdb_id=12345,
):
    artwork_set = _set(
        set_id,
        episodes,
    )

    return ShowArtworkState(
        title="Example Show",
        tvdb_id=tvdb_id,
        tmdb_id=67890,
        imdb_id="tt1234567",
        poster=artwork_set.poster,
        background=(
            artwork_set.background
        ),
        seasons=artwork_set.seasons,
        selected_set_id=set_id,
        selected_set_source=(
            ArtworkSource
            .MEDIUX
        ),
        selected_creator=(
            artwork_set.creator
        ),
    )


def test_complete_show_skips_provider():
    inventory = _inventory(
        episodes=4,
    )

    state = _state(
        episodes=4,
    )

    provider = FakeProvider(
        {
            "1": [
                _set(
                    "B",
                    4,
                ),
            ],
        }
    )

    result = execute_managed_show(
        inventory=inventory,
        current_state=state,
        provider=provider,
    )

    assert (
        result.path
        is
        ManagedExecutionPath
        .COMPLETE_NO_PROVIDER
    )

    assert (
        result.action
        is SetAction.KEEP_CURRENT
    )

    assert (
        result.provider_requested
        is False
    )

    assert provider.requests == []

    assert result.state is state


def test_incomplete_show_refreshes_same_set():
    inventory = _inventory(
        episodes=4,
    )

    state = _state(
        set_id="A",
        episodes=2,
    )

    provider = FakeProvider(
        {
            "1": [
                _set(
                    "A",
                    4,
                ),
            ],
        }
    )

    result = execute_managed_show(
        inventory=inventory,
        current_state=state,
        provider=provider,
    )

    assert (
        result.path
        is
        ManagedExecutionPath
        .REEVALUATED
    )

    assert (
        result.action
        is SetAction.SET_REFRESH
    )

    assert (
        result.state
        .selected_set_id
        == "A"
    )

    assert (
        len(
            result.state
            .seasons[1]
            .episodes
        )
        == 4
    )

    assert len(
        provider.requests
    ) == 1

    request = (
        provider.requests[0]
    )

    assert (
        request.kind
        is ArtworkSearchKind.REEVALUATION
    )

    assert (
        request.current_set_id
        == "A"
    )


def test_incomplete_show_migrates_to_better_set():
    inventory = _inventory(
        episodes=4,
    )

    state = _state(
        set_id="A",
        episodes=2,
    )

    provider = FakeProvider(
        {
            "1": [
                _set(
                    "B",
                    4,
                ),
            ],
        }
    )

    result = execute_managed_show(
        inventory=inventory,
        current_state=state,
        provider=provider,
    )

    assert (
        result.action
        is SetAction.SET_MIGRATION
    )

    assert (
        result.state
        .selected_set_id
        == "B"
    )

    assert (
        result.state
        .selected_creator
        == "creator-B"
    )


def test_no_provider_candidates_keeps_current():
    inventory = _inventory(
        episodes=4,
    )

    state = _state(
        set_id="A",
        episodes=2,
    )

    provider = FakeProvider(
        {
            "1": [],
        }
    )

    result = execute_managed_show(
        inventory=inventory,
        current_state=state,
        provider=provider,
    )

    assert (
        result.path
        is
        ManagedExecutionPath
        .REEVALUATED
    )

    assert (
        result.action
        is SetAction.KEEP_CURRENT
    )

    assert (
        result.state
        .selected_set_id
        == "A"
    )

    assert (
        result.provider_candidate_count
        == 0
    )


def test_provider_error_preserves_durable_state():
    inventory = _inventory(
        episodes=4,
    )

    state = _state(
        set_id="A",
        episodes=2,
    )

    provider = FakeProvider(
        {
            "1": RuntimeError(
                "provider unavailable"
            ),
        }
    )

    result = execute_managed_show(
        inventory=inventory,
        current_state=state,
        provider=provider,
    )

    assert (
        result.path
        is
        ManagedExecutionPath
        .PROVIDER_ERROR
    )

    assert (
        result.action
        is SetAction.KEEP_CURRENT
    )

    assert result.state is state

    assert (
        result.provider_requested
        is True
    )

    assert (
        result.error_type
        == "RuntimeError"
    )

    assert (
        result.error_message
        == "provider unavailable"
    )


def test_missing_set_context_does_not_query_provider():
    inventory = _inventory(
        episodes=4,
    )

    state = ShowArtworkState(
        title="Example Show",
        tvdb_id=12345,
    )

    provider = FakeProvider()

    result = execute_managed_show(
        inventory=inventory,
        current_state=state,
        provider=provider,
    )

    assert (
        result.path
        is
        ManagedExecutionPath
        .MISSING_SET_CONTEXT
    )

    assert result.state is None

    assert (
        result.provider_requested
        is False
    )

    assert provider.requests == []


def test_library_execution_reports_all_outcomes():
    items = [
        (
            _inventory(
                rating_key="complete",
                tvdb_id=1,
                episodes=4,
            ),
            _state(
                tvdb_id=1,
                episodes=4,
            ),
        ),
        (
            _inventory(
                rating_key="refresh",
                tvdb_id=2,
                episodes=4,
            ),
            _state(
                tvdb_id=2,
                set_id="A",
                episodes=2,
            ),
        ),
        (
            _inventory(
                rating_key="migrate",
                tvdb_id=3,
                episodes=4,
            ),
            _state(
                tvdb_id=3,
                set_id="A",
                episodes=2,
            ),
        ),
        (
            _inventory(
                rating_key="keep",
                tvdb_id=4,
                episodes=4,
            ),
            _state(
                tvdb_id=4,
                set_id="A",
                episodes=2,
            ),
        ),
        (
            _inventory(
                rating_key="error",
                tvdb_id=5,
                episodes=4,
            ),
            _state(
                tvdb_id=5,
                set_id="A",
                episodes=2,
            ),
        ),
    ]

    provider = FakeProvider(
        {
            "refresh": [
                _set(
                    "A",
                    4,
                ),
            ],
            "migrate": [
                _set(
                    "B",
                    4,
                ),
            ],
            "keep": [],
            "error": RuntimeError(
                "boom"
            ),
        }
    )

    result = (
        execute_managed_library(
            items=items,
            provider=provider,
        )
    )

    assert (
        result.managed_count
        == 5
    )

    assert (
        result.resolved_count
        == 5
    )

    assert (
        result.provider_request_count
        == 4
    )

    assert (
        result.complete_no_provider_count
        == 1
    )

    assert (
        result.set_refresh_count
        == 1
    )

    assert (
        result.set_migration_count
        == 1
    )

    assert (
        result.keep_current_after_check_count
        == 1
    )

    assert (
        result.provider_error_count
        == 1
    )

    assert (
        result.missing_set_context_count
        == 0
    )

    assert (
        result.cohesion_blocked_count
        == 0
    )
