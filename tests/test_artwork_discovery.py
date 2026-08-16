from types import SimpleNamespace

from artwork.discovery import (
    DiscoveryPath,
    discover_unmanaged_library,
    discover_unmanaged_show,
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
)
from artwork.search import (
    ArtworkSearchKind,
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

        return list(
            response
        )


def _inventory(
    *,
    rating_key="1",
    tvdb_id=12345,
    title="Example Show",
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
        tmdb_id=67890,
        imdb_id="tt1234567",
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


def _asset(
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


def _set(
    set_id,
    episodes=0,
    *,
    poster=False,
    background=False,
    season_poster=False,
):
    return ArtworkSet(
        provider=ArtworkSource.MEDIUX,
        set_id=set_id,
        creator=f"creator-{set_id}",
        poster=(
            _asset(
                ArtworkKind.SHOW_POSTER,
                f"{set_id}-poster",
            )
            if poster
            else None
        ),
        background=(
            _asset(
                ArtworkKind.SHOW_BACKGROUND,
                f"{set_id}-background",
            )
            if background
            else None
        ),
        seasons={
            1: SeasonArtwork(
                season_number=1,
                poster=(
                    _asset(
                        ArtworkKind.SEASON_POSTER,
                        f"{set_id}-season",
                    )
                    if season_poster
                    else None
                ),
                episodes={
                    number: EpisodeArtwork(
                        episode_number=number,
                        card=_asset(
                            ArtworkKind.EPISODE_CARD,
                            f"{set_id}-e{number}",
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


def test_discovery_selects_best_candidate():
    inventory = _inventory(
        episodes=4,
    )

    provider = FakeProvider(
        {
            "1": [
                _set(
                    "A",
                    episodes=2,
                    poster=True,
                ),
                _set(
                    "B",
                    episodes=4,
                    poster=True,
                ),
            ],
        }
    )

    result = discover_unmanaged_show(
        inventory=inventory,
        provider=provider,
    )

    assert (
        result.path
        is DiscoveryPath.SELECTED
    )

    assert result.resolved is True

    assert (
        result.state.selected_set_id
        == "B"
    )

    assert (
        result.state.selected_creator
        == "creator-B"
    )

    assert (
        result.provider_candidate_count
        == 2
    )

    assert (
        result.usable_candidate_count
        == 2
    )

    assert len(provider.requests) == 1

    request = provider.requests[0]

    assert (
        request.kind
        is ArtworkSearchKind.DISCOVERY
    )

    assert (
        request.plex_rating_key
        == "1"
    )

    assert (
        request.current_set_id
        is None
    )

    assert (
        request.current_set_source
        is None
    )


def test_discovery_state_uses_plex_identity():
    inventory = _inventory(
        tvdb_id=54321,
        title="Plex Canonical Title",
    )

    provider = FakeProvider(
        {
            "1": [
                _set(
                    "B",
                    episodes=4,
                ),
            ],
        }
    )

    result = discover_unmanaged_show(
        inventory=inventory,
        provider=provider,
    )

    state = result.state

    assert (
        state.title
        == "Plex Canonical Title"
    )

    assert state.tvdb_id == 54321
    assert state.tmdb_id == 67890
    assert state.imdb_id == "tt1234567"


def test_discovery_returns_no_candidates():
    inventory = _inventory()

    provider = FakeProvider(
        {
            "1": [],
        }
    )

    result = discover_unmanaged_show(
        inventory=inventory,
        provider=provider,
    )

    assert (
        result.path
        is DiscoveryPath.NO_CANDIDATES
    )

    assert result.state is None
    assert result.resolved is False

    assert (
        result.provider_candidate_count
        == 0
    )


def test_discovery_ignores_sets_with_no_usable_artwork():
    inventory = _inventory()

    provider = FakeProvider(
        {
            "1": [
                _set(
                    "EMPTY",
                    episodes=0,
                ),
            ],
        }
    )

    result = discover_unmanaged_show(
        inventory=inventory,
        provider=provider,
    )

    assert (
        result.path
        is
        DiscoveryPath
        .NO_USABLE_CANDIDATE
    )

    assert result.state is None

    assert (
        result.provider_candidate_count
        == 1
    )

    assert (
        result.usable_candidate_count
        == 0
    )


def test_discovery_accepts_non_episode_artwork():
    inventory = _inventory()

    provider = FakeProvider(
        {
            "1": [
                _set(
                    "POSTERS",
                    episodes=0,
                    poster=True,
                    season_poster=True,
                ),
            ],
        }
    )

    result = discover_unmanaged_show(
        inventory=inventory,
        provider=provider,
    )

    assert (
        result.path
        is DiscoveryPath.SELECTED
    )

    assert (
        result.state.selected_set_id
        == "POSTERS"
    )


def test_discovery_provider_error_is_reported():
    inventory = _inventory()

    provider = FakeProvider(
        {
            "1": RuntimeError(
                "provider unavailable"
            ),
        }
    )

    result = discover_unmanaged_show(
        inventory=inventory,
        provider=provider,
    )

    assert (
        result.path
        is DiscoveryPath.PROVIDER_ERROR
    )

    assert result.state is None

    assert (
        result.error_type
        == "RuntimeError"
    )

    assert (
        result.error_message
        == "provider unavailable"
    )


def test_library_discovery_reports_all_outcomes():
    inventories = (
        _inventory(
            rating_key="selected",
            tvdb_id=1,
        ),
        _inventory(
            rating_key="none",
            tvdb_id=2,
        ),
        _inventory(
            rating_key="empty",
            tvdb_id=3,
        ),
        _inventory(
            rating_key="error",
            tvdb_id=4,
        ),
    )

    provider = FakeProvider(
        {
            "selected": [
                _set(
                    "B",
                    episodes=4,
                ),
            ],
            "none": [],
            "empty": [
                _set(
                    "EMPTY",
                    episodes=0,
                ),
            ],
            "error": RuntimeError(
                "boom"
            ),
        }
    )

    result = discover_unmanaged_library(
        inventories=inventories,
        provider=provider,
    )

    assert result.unmanaged_count == 4
    assert result.selected_count == 1
    assert result.provider_request_count == 4
    assert result.no_candidates_count == 1

    assert (
        result.no_usable_candidate_count
        == 1
    )

    assert result.provider_error_count == 1

    assert (
        result.selected_states[0]
        .selected_set_id
        == "B"
    )
