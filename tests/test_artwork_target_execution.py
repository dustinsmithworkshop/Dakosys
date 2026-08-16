from pathlib import Path
from types import SimpleNamespace

from artwork.execution import (
    ManagedExecutionPath,
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
from artwork.target_execution import (
    execute_show_target,
)
from artwork.targets import (
    ArtworkTarget,
    MediaType,
)


class FakeProvider:
    name = "fake"

    def __init__(
        self,
        responses=None,
    ):
        self.responses = responses or {}
        self.requests = []

    def find_sets(
        self,
        request,
    ):
        self.requests.append(
            request
        )

        response = self.responses.get(
            request.plex_rating_key,
            [],
        )

        if isinstance(
            response,
            Exception,
        ):
            raise response

        return list(response)


def _target():
    return ArtworkTarget(
        name="TV",
        library="TV",
        media_type=MediaType.SHOW,
        output_path=Path(
            "/tmp/artwork-tv.yaml"
        ),
    )


def _inventory(
    *,
    rating_key,
    tvdb_id,
    title,
    episodes=4,
):
    identity = SimpleNamespace(
        library="TV",
        plex_rating_key=str(
            rating_key
        ),
        title=title,
        year=2024,
        tvdb_id=tvdb_id,
        tmdb_id=(
            None
            if tvdb_id is None
            else tvdb_id + 10000
        ),
        imdb_id=(
            None
            if tvdb_id is None
            else f"tt{tvdb_id:07d}"
        ),
    )

    return ShowInventory(
        identity=identity,
        seasons=(
            SeasonInventory(
                season_number=1,
                episode_numbers=frozenset(
                    range(
                        1,
                        episodes + 1,
                    )
                ),
            ),
        ),
    )


def _card(
    asset_id,
):
    return ArtworkAsset(
        kind=ArtworkKind.EPISODE_CARD,
        source=ArtworkSource.MEDIUX,
        provider_asset_id=asset_id,
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
        provider=ArtworkSource.MEDIUX,
        set_id=set_id,
        creator=f"creator-{set_id}",
        seasons={
            1: SeasonArtwork(
                season_number=1,
                episodes={
                    number: EpisodeArtwork(
                        episode_number=number,
                        card=_card(
                            f"{set_id}-{number}"
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
    tvdb_id,
    set_id="A",
    episodes=2,
    title="Managed Show",
):
    artwork_set = _set(
        set_id,
        episodes,
    )

    return ShowArtworkState(
        title=title,
        tvdb_id=tvdb_id,
        tmdb_id=tvdb_id + 10000,
        imdb_id=f"tt{tvdb_id:07d}",
        seasons=artwork_set.seasons,
        selected_set_id=set_id,
        selected_set_source=(
            ArtworkSource.MEDIUX
        ),
        selected_creator=(
            artwork_set.creator
        ),
    )


def test_executes_only_unambiguous_managed_matches():
    managed_inventory = _inventory(
        rating_key="managed",
        tvdb_id=1,
        title="Managed Plex Title",
    )

    unmanaged_inventory = _inventory(
        rating_key="unmanaged",
        tvdb_id=2,
        title="Unmanaged Show",
    )

    missing_identity = _inventory(
        rating_key="missing",
        tvdb_id=None,
        title="Missing Identity",
    )

    state = _state(
        tvdb_id=1,
        episodes=2,
        title="Legacy Managed Title",
    )

    provider = FakeProvider(
        {
            "managed": [
                _set(
                    "B",
                    4,
                ),
            ],
        }
    )

    result = execute_show_target(
        target=_target(),
        inventories=(
            managed_inventory,
            unmanaged_inventory,
            missing_identity,
        ),
        managed_shows=(
            state,
        ),
        provider=provider,
    )

    assert result.matched_count == 1
    assert result.unmanaged_count == 1
    assert result.missing_identity_count == 1
    assert result.ambiguous_count == 0
    assert result.orphaned_count == 0

    assert (
        result.managed.managed_count
        == 1
    )

    assert (
        result.managed.set_migration_count
        == 1
    )

    assert (
        result.resolved_states[0]
        .selected_set_id
        == "B"
    )

    assert len(provider.requests) == 1

    assert (
        provider.requests[0]
        .plex_rating_key
        == "managed"
    )


def test_ambiguous_managed_match_is_not_executed():
    first = _inventory(
        rating_key="one",
        tvdb_id=1,
        title="Duplicate One",
    )

    second = _inventory(
        rating_key="two",
        tvdb_id=1,
        title="Duplicate Two",
    )

    state = _state(
        tvdb_id=1,
    )

    provider = FakeProvider()

    result = execute_show_target(
        target=_target(),
        inventories=(
            first,
            second,
        ),
        managed_shows=(
            state,
        ),
        provider=provider,
    )

    assert result.matched_count == 0
    assert result.ambiguous_count == 1

    assert (
        result.managed.managed_count
        == 0
    )

    assert result.resolved_states == ()
    assert provider.requests == []


def test_orphaned_state_is_not_executed():
    inventory = _inventory(
        rating_key="other",
        tvdb_id=2,
        title="Other Show",
    )

    state = _state(
        tvdb_id=1,
    )

    provider = FakeProvider()

    result = execute_show_target(
        target=_target(),
        inventories=(
            inventory,
        ),
        managed_shows=(
            state,
        ),
        provider=provider,
    )

    assert result.matched_count == 0
    assert result.unmanaged_count == 1
    assert result.orphaned_count == 1

    assert (
        result.managed.managed_count
        == 0
    )

    assert provider.requests == []


def test_complete_managed_match_skips_provider():
    inventory = _inventory(
        rating_key="complete",
        tvdb_id=1,
        title="Complete Show",
        episodes=4,
    )

    state = _state(
        tvdb_id=1,
        episodes=4,
    )

    provider = FakeProvider(
        {
            "complete": [
                _set(
                    "B",
                    4,
                ),
            ],
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
    )

    execution = (
        result.managed.results[0]
    )

    assert (
        execution.path
        is
        ManagedExecutionPath
        .COMPLETE_NO_PROVIDER
    )

    assert (
        execution.action
        is SetAction.KEEP_CURRENT
    )

    assert (
        result.managed
        .complete_no_provider_count
        == 1
    )

    assert provider.requests == []


def test_provider_error_remains_resolved_from_durable_state():
    inventory = _inventory(
        rating_key="error",
        tvdb_id=1,
        title="Provider Error Show",
    )

    state = _state(
        tvdb_id=1,
        episodes=2,
    )

    provider = FakeProvider(
        {
            "error": RuntimeError(
                "provider unavailable"
            ),
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
    )

    assert (
        result.managed.provider_error_count
        == 1
    )

    assert (
        result.managed.resolved_count
        == 1
    )

    assert (
        result.resolved_states[0]
        is state
    )

    assert len(provider.requests) == 1
