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
            "/tmp/artwork-tv"
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

    assert len(provider.requests) == 2

    assert (
        provider.requests[0]
        .plex_rating_key
        == "managed"
    )

    assert (
        provider.requests[1]
        .plex_rating_key
        == "unmanaged"
    )

    assert (
        result.discovery.selected_count
        == 0
    )

    assert (
        result.discovery.no_candidates_count
        == 1
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

    assert (
        result.discovery.unmanaged_count
        == 1
    )

    assert (
        result.discovery.no_candidates_count
        == 1
    )

    assert len(provider.requests) == 1

    assert (
        provider.requests[0]
        .plex_rating_key
        == "other"
    )


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



def test_unmanaged_show_is_discovered_into_prospective_state():
    inventory = _inventory(
        rating_key="new",
        tvdb_id=99,
        title="New Plex Show",
    )

    provider = FakeProvider(
        {
            "new": [
                _set(
                    "NEW",
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
        managed_shows=(),
        provider=provider,
    )

    assert result.matched_count == 0
    assert result.unmanaged_count == 1

    assert (
        result.discovery.selected_count
        == 1
    )

    assert (
        result.discovered_count
        == 1
    )

    assert (
        result.resolved_count
        == 1
    )

    assert (
        result.resolved_states[0]
        .title
        == "New Plex Show"
    )

    assert (
        result.resolved_states[0]
        .selected_set_id
        == "NEW"
    )

    assert (
        result.provider_request_count
        == 1
    )


def test_missing_identity_is_not_sent_to_discovery():
    inventory = _inventory(
        rating_key="missing",
        tvdb_id=None,
        title="Missing Identity",
    )

    provider = FakeProvider()

    result = execute_show_target(
        target=_target(),
        inventories=(
            inventory,
        ),
        managed_shows=(),
        provider=provider,
    )

    assert (
        result.missing_identity_count
        == 1
    )

    assert (
        result.unmanaged_count
        == 0
    )

    assert (
        result.discovery.unmanaged_count
        == 0
    )

    assert (
        result.provider_request_count
        == 0
    )

    assert provider.requests == []


def test_target_reports_managed_and_discovery_provider_errors():
    managed_inventory = _inventory(
        rating_key="managed-error",
        tvdb_id=1,
        title="Managed Error",
    )

    unmanaged_inventory = _inventory(
        rating_key="discovery-error",
        tvdb_id=2,
        title="Discovery Error",
    )

    state = _state(
        tvdb_id=1,
        episodes=2,
    )

    provider = FakeProvider(
        {
            "managed-error": RuntimeError(
                "managed provider error"
            ),
            "discovery-error": RuntimeError(
                "discovery provider error"
            ),
        }
    )

    result = execute_show_target(
        target=_target(),
        inventories=(
            managed_inventory,
            unmanaged_inventory,
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
        result.discovery.provider_error_count
        == 1
    )

    assert (
        result.provider_error_count
        == 2
    )

    # Managed provider failure preserves durable state.
    assert (
        result.managed.resolved_count
        == 1
    )

    # Discovery failure cannot create new state.
    assert (
        result.discovery.selected_count
        == 0
    )

    assert (
        result.resolved_count
        == 1
    )

    assert (
        result.resolved_states[0]
        is state
    )

    assert (
        result.provider_request_count
        == 2
    )


def test_missing_tvdb_is_enriched_before_reconciliation():
    from artwork.providers.tmdb import (
        TMDBTVExternalIds,
    )

    identity = SimpleNamespace(
        library="TV",
        plex_rating_key="digimon",
        title="Digimon Data Squad",
        year=2006,
        tvdb_id=None,
        tmdb_id=39980,
        imdb_id="tt1138300",
        library_roles=(),
    )

    inventory = ShowInventory(
        identity=identity,
        seasons=(
            SeasonInventory(
                season_number=1,
                episode_numbers=frozenset(
                    {
                        1,
                        2,
                        3,
                        4,
                    }
                ),
            ),
        ),
    )

    class FakeTMDBIdentityClient:
        def __init__(self):
            self.external_requests = []
            self.season_requests = []

        def get_tv_external_ids(
            self,
            *,
            tmdb_id,
        ):
            self.external_requests.append(
                tmdb_id
            )

            return TMDBTVExternalIds(
                tvdb_id=339733,
                imdb_id="tt1138300",
            )

        def get_season_episode_cards(
            self,
            *,
            tmdb_id,
            season_number,
        ):
            self.season_requests.append(
                (
                    tmdb_id,
                    season_number,
                )
            )

            return {}

    tmdb_client = FakeTMDBIdentityClient()

    provider = FakeProvider(
        {
            "digimon": [
                _set(
                    "DIGIMON",
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
        managed_shows=(),
        provider=provider,
        tmdb_client=tmdb_client,
    )

    # Exact TMDB bridge happened before reconciliation.
    assert (
        result.identity_enriched_count
        == 1
    )

    assert (
        result.identity_enrichment_request_count
        == 1
    )

    assert (
        result.identity_enrichment_error_count
        == 0
    )

    assert (
        tmdb_client.external_requests
        == [
            39980,
        ]
    )

    # The original missing-TVDB condition no longer blocks execution.
    assert (
        result.missing_identity_count
        == 0
    )

    assert (
        result.unmanaged_count
        == 1
    )

    assert (
        result.discovery.selected_count
        == 1
    )

    assert (
        result.resolved_count
        == 1
    )

    # The recovered TVDB identity propagates all the way into durable
    # prospective artwork state.
    state = result.resolved_states[0]

    assert state.title == "Digimon Data Squad"
    assert state.tmdb_id == 39980
    assert state.tvdb_id == 339733
    assert state.imdb_id == "tt1138300"

    # Primary artwork was already complete, so TMDB did not need to
    # fetch episode stills after identity enrichment.
    assert (
        tmdb_client.season_requests
        == []
    )


def _split_test_asset(
    kind,
    asset_id,
):
    return ArtworkAsset(
        kind=kind,
        source=ArtworkSource.MEDIUX,
        provider_asset_id=asset_id,
        url=(
            "https://api.mediux.pro/assets/"
            f"{asset_id}"
        ),
    )


def _split_managed_state():
    from artwork.models import (
        ArtworkSetSelection,
    )

    episode_set = _set(
        "EPISODES",
        2,
    )

    poster = _split_test_asset(
        ArtworkKind.SHOW_POSTER,
        "presentation-poster",
    )

    season_poster = _split_test_asset(
        ArtworkKind.SEASON_POSTER,
        "presentation-season-1",
    )

    state = ShowArtworkState(
        title="Split Show",
        tvdb_id=1,
        tmdb_id=10001,
        imdb_id="tt0000001",
        poster=poster,
        background=None,
        seasons={
            1: SeasonArtwork(
                season_number=1,
                poster=season_poster,
                episodes=dict(
                    episode_set
                    .seasons[1]
                    .episodes
                ),
            ),
        },
        selected_set_id="EPISODES",
        selected_set_source=(
            ArtworkSource.MEDIUX
        ),
        selected_creator=(
            "creator-EPISODES"
        ),
        episode_selection=(
            ArtworkSetSelection(
                provider=(
                    ArtworkSource.MEDIUX
                ),
                set_id="EPISODES",
                creator=(
                    "creator-EPISODES"
                ),
            )
        ),
        presentation_selection=(
            ArtworkSetSelection(
                provider=(
                    ArtworkSource.MEDIUX
                ),
                set_id="PRESENTATION",
                creator=(
                    "presentation-creator"
                ),
            )
        ),
    )

    return state


def _split_presentation_set():
    return ArtworkSet(
        provider=ArtworkSource.MEDIUX,
        set_id="PRESENTATION",
        creator="presentation-creator",
        poster=_split_test_asset(
            ArtworkKind.SHOW_POSTER,
            "presentation-poster",
        ),
        seasons={
            1: SeasonArtwork(
                season_number=1,
                poster=_split_test_asset(
                    ArtworkKind.SEASON_POSTER,
                    "presentation-season-1",
                ),
            ),
        },
    )


def test_split_episode_reevaluation_does_not_absorb_presentation_artwork():
    from artwork.execution import (
        execute_managed_show,
    )

    inventory = _inventory(
        rating_key="split",
        tvdb_id=1,
        title="Split Show",
        episodes=4,
    )

    current_state = (
        _split_managed_state()
    )

    live_episode_set = _set(
        "EPISODES",
        2,
    )

    # This belongs to the episode set and must never be silently mixed
    # into the independently selected presentation family.
    live_episode_set.background = (
        _split_test_asset(
            ArtworkKind.SHOW_BACKGROUND,
            "episode-set-background",
        )
    )

    result = execute_managed_show(
        inventory=inventory,
        current_state=current_state,
        provider=FakeProvider(
            {
                "split": [
                    live_episode_set,
                    _split_presentation_set(),
                ],
            }
        ),
    )

    assert (
        result.action
        is SetAction.KEEP_CURRENT
    )

    assert result.state.background is None

    assert (
        result.state.poster.provider_asset_id
        == "presentation-poster"
    )

    assert (
        result.state
        .presentation_selection
        .set_id
        == "PRESENTATION"
    )

    assert (
        result.state
        .episode_selection
        .set_id
        == "EPISODES"
    )


def test_split_episode_migration_preserves_presentation_family():
    from artwork.execution import (
        execute_managed_show,
    )

    inventory = _inventory(
        rating_key="split-migration",
        tvdb_id=1,
        title="Split Show",
        episodes=4,
    )

    current_state = (
        _split_managed_state()
    )

    current_episode = _set(
        "EPISODES",
        2,
    )

    challenger = _set(
        "BETTER-EPISODES",
        4,
    )

    # Even a migrating episode set must not take presentation ownership.
    challenger.background = (
        _split_test_asset(
            ArtworkKind.SHOW_BACKGROUND,
            "challenger-background",
        )
    )

    result = execute_managed_show(
        inventory=inventory,
        current_state=current_state,
        provider=FakeProvider(
            {
                "split-migration": [
                    current_episode,
                    challenger,
                    _split_presentation_set(),
                ],
            }
        ),
    )

    assert (
        result.action
        is SetAction.SET_MIGRATION
    )

    assert (
        result.state
        .episode_selection
        .set_id
        == "BETTER-EPISODES"
    )

    assert (
        result.state
        .presentation_selection
        .set_id
        == "PRESENTATION"
    )

    assert (
        result.state.selected_set_id
        == "BETTER-EPISODES"
    )

    assert (
        result.state.poster.provider_asset_id
        == "presentation-poster"
    )

    assert result.state.background is None

    assert (
        result.state
        .seasons[1]
        .poster
        .provider_asset_id
        == "presentation-season-1"
    )

    assert len(
        result.state
        .seasons[1]
        .episodes
    ) == 4


def test_unique_tvdb_candidate_collision_is_resolved_before_reconciliation():
    from tv_metadata.models import (
        ShowIdentity,
    )

    def candidate_inventory(
        *,
        rating_key,
        candidates,
    ):
        return ShowInventory(
            identity=ShowIdentity(
                title=(
                    f"Candidate {rating_key}"
                ),
                year=2024,
                library="TV",
                plex_rating_key=(
                    rating_key
                ),
                tvdb_id=188551,
                tmdb_id=246862,
                imdb_id="tt1727444",
                tvdb_id_candidates=tuple(
                    candidates
                ),
            ),
            seasons=(
                SeasonInventory(
                    season_number=1,
                    episode_numbers=frozenset(
                        {
                            1,
                        }
                    ),
                ),
            ),
        )

    result = execute_show_target(
        target=_target(),
        inventories=(
            candidate_inventory(
                rating_key="first",
                candidates=(
                    188551,
                    436780,
                ),
            ),
            candidate_inventory(
                rating_key="second",
                candidates=(
                    188551,
                ),
            ),
        ),
        managed_shows=(),
        provider=FakeProvider(),
    )

    resolved = {
        item.identity.plex_rating_key:
            item.identity.tvdb_id
        for item
        in result.reconciliation.unmanaged
    }

    assert resolved == {
        "first": 436780,
        "second": 188551,
    }
