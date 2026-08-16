from types import SimpleNamespace

from artwork.discovery import (
    DiscoveryPath,
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


class FakeProvider:
    name = "fake"

    def __init__(self, sets):
        self.sets = sets

    def find_sets(self, request):
        return list(self.sets)


def _asset(kind, asset_id):
    return ArtworkAsset(
        kind=kind,
        source=ArtworkSource.MEDIUX,
        provider_asset_id=asset_id,
        url=(
            "https://api.mediux.pro/assets/"
            f"{asset_id}"
        ),
    )


def _inventory():
    return ShowInventory(
        identity=SimpleNamespace(
            library="TV",
            plex_rating_key="1",
            title="Example Show",
            year=2026,
            tvdb_id=123,
            tmdb_id=456,
            imdb_id="tt0000123",
        ),
        seasons=(
            SeasonInventory(
                season_number=1,
                episode_numbers=frozenset(
                    {1, 2, 3, 4}
                ),
            ),
        ),
    )


def _cards_set(
    set_id="CARDS",
):
    return ArtworkSet(
        provider=ArtworkSource.MEDIUX,
        set_id=set_id,
        creator="card-creator",
        seasons={
            1: SeasonArtwork(
                season_number=1,
                episodes={
                    number: EpisodeArtwork(
                        episode_number=number,
                        card=_asset(
                            ArtworkKind.EPISODE_CARD,
                            f"card-{number}",
                        ),
                    )
                    for number in range(1, 5)
                },
            ),
        },
    )


def _presentation_set(
    set_id="PRESENT",
):
    return ArtworkSet(
        provider=ArtworkSource.MEDIUX,
        set_id=set_id,
        creator="presentation-creator",
        poster=_asset(
            ArtworkKind.SHOW_POSTER,
            "show-poster",
        ),
        background=_asset(
            ArtworkKind.SHOW_BACKGROUND,
            "background",
        ),
        seasons={
            1: SeasonArtwork(
                season_number=1,
                poster=_asset(
                    ArtworkKind.SEASON_POSTER,
                    "season-1",
                ),
            ),
        },
    )


def test_discovery_combines_episode_and_presentation_sets():
    result = discover_unmanaged_show(
        inventory=_inventory(),
        provider=FakeProvider(
            [
                _cards_set(),
                _presentation_set(),
            ]
        ),
    )

    assert result.path is DiscoveryPath.SELECTED

    assert (
        result.episode_selected.set_id
        == "CARDS"
    )

    assert (
        result.presentation_selected.set_id
        == "PRESENT"
    )

    state = result.state

    assert (
        state.episode_selection.set_id
        == "CARDS"
    )

    assert (
        state.presentation_selection.set_id
        == "PRESENT"
    )

    # Legacy primary provenance remains episode-oriented.
    assert state.selected_set_id == "CARDS"

    assert (
        state.poster.provider_asset_id
        == "show-poster"
    )

    assert (
        state.background.provider_asset_id
        == "background"
    )

    assert (
        state.seasons[1]
        .poster
        .provider_asset_id
        == "season-1"
    )

    assert (
        state.seasons[1]
        .episodes[4]
        .card
        .provider_asset_id
        == "card-4"
    )


def test_discovery_uses_same_set_for_both_families_when_best():
    combined = _cards_set(
        "COMBINED"
    )

    combined.poster = _asset(
        ArtworkKind.SHOW_POSTER,
        "combined-poster",
    )

    combined.background = _asset(
        ArtworkKind.SHOW_BACKGROUND,
        "combined-background",
    )

    combined.seasons[1].poster = _asset(
        ArtworkKind.SEASON_POSTER,
        "combined-season",
    )

    result = discover_unmanaged_show(
        inventory=_inventory(),
        provider=FakeProvider(
            [
                combined,
                _presentation_set(),
            ]
        ),
    )

    assert (
        result.episode_selected.set_id
        == "COMBINED"
    )

    # Presentation quality ties, so avoid an unnecessary split.
    assert (
        result.presentation_selected.set_id
        == "COMBINED"
    )


def test_presentation_only_discovery_has_no_episode_selection():
    result = discover_unmanaged_show(
        inventory=_inventory(),
        provider=FakeProvider(
            [
                _presentation_set(),
            ]
        ),
    )

    assert result.path is DiscoveryPath.SELECTED

    assert result.episode_selected is None

    assert (
        result.presentation_selected.set_id
        == "PRESENT"
    )

    assert (
        result.state.episode_selection
        is None
    )

    assert (
        result.state
        .presentation_selection
        .set_id
        == "PRESENT"
    )

    assert (
        result.state.selected_set_id
        == "PRESENT"
    )


def test_discovery_does_not_emit_provider_only_extra_seasons():
    presentation = _presentation_set()

    presentation.seasons[0] = (
        SeasonArtwork(
            season_number=0,
            poster=_asset(
                ArtworkKind.SEASON_POSTER,
                "extra-specials",
            ),
        )
    )

    result = discover_unmanaged_show(
        inventory=_inventory(),
        provider=FakeProvider(
            [
                _cards_set(),
                presentation,
            ]
        ),
    )

    assert 1 in result.state.seasons
    assert 0 not in result.state.seasons
