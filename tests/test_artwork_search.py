import pytest

from artwork.inventory import SeasonInventory
from artwork.models import (
    ArtworkSource,
    SelectionMode,
)
from artwork.planner import (
    ArtworkPlanItem,
    PlanAction,
    PlanReason,
    TargetPlan,
)
from artwork.search import (
    ArtworkSearchKind,
    build_provider_search_requests,
)
from artwork.targets import (
    ArtworkTarget,
    MediaType,
)


def _target():
    return ArtworkTarget(
        name="Series Vault",
        library="Series Vault",
        media_type=MediaType.SHOW,
        output_path=(
            "/metadata/"
            "artwork-series-vault"
        ),
    )


def _item(
    *,
    title="Example",
    rating_keys=("100",),
    action=PlanAction.PROVIDER_SEARCH,
    reason=PlanReason.UNMANAGED,
    selected_set_id=None,
    selected_set_source=None,
    selected_creator=None,
    selection_mode=SelectionMode.AUTO,
):
    return ArtworkPlanItem(
        library="Series Vault",
        title=title,
        action=action,
        reason=reason,
        plex_rating_keys=rating_keys,
        year=2026,
        tvdb_id=100,
        tmdb_id=200,
        imdb_id="tt0000200",
        seasons=(
            SeasonInventory(
                season_number=1,
                episode_numbers=frozenset(
                    {
                        1,
                        2,
                        3,
                    }
                ),
            ),
            SeasonInventory(
                season_number=2,
                episode_numbers=frozenset(
                    {
                        1,
                        2,
                    }
                ),
            ),
        ),
        selected_set_id=selected_set_id,
        selected_set_source=(
            selected_set_source
        ),
        selected_creator=(
            selected_creator
        ),
        selection_mode=selection_mode,
    )


def _plan(
    *items,
):
    return TargetPlan(
        target=_target(),
        items=tuple(items),
    )


def test_unmanaged_item_becomes_discovery_request():
    requests = build_provider_search_requests(
        _plan(
            _item()
        )
    )

    assert len(requests) == 1

    request = requests[0]

    assert (
        request.kind
        is ArtworkSearchKind.DISCOVERY
    )

    assert request.plex_identity == (
        "Series Vault",
        "100",
    )

    assert request.title == "Example"
    assert request.year == 2026
    assert request.tvdb_id == 100
    assert request.tmdb_id == 200
    assert request.imdb_id == "tt0000200"

    assert request.current_set_id is None


def test_request_preserves_actual_plex_episode_inventory():
    request = build_provider_search_requests(
        _plan(
            _item()
        )
    )[0]

    assert request.expected_episode_count == 5

    assert request.expected_episodes() == {
        1: frozenset(
            {
                1,
                2,
                3,
            }
        ),
        2: frozenset(
            {
                1,
                2,
            }
        ),
    }


def test_incomplete_managed_item_becomes_reevaluation():
    request = build_provider_search_requests(
        _plan(
            _item(
                reason=(
                    PlanReason
                    .INCOMPLETE_COVERAGE
                ),
                selected_set_id="500",
                selected_set_source=(
                    ArtworkSource.MEDIUX
                ),
                selected_creator="Artist",
                selection_mode=(
                    SelectionMode.PREFERRED
                ),
            )
        )
    )[0]

    assert (
        request.kind
        is ArtworkSearchKind.REEVALUATION
    )

    assert request.current_set_id == "500"

    assert (
        request.current_set_source
        is ArtworkSource.MEDIUX
    )

    assert request.current_creator == "Artist"

    assert (
        request.selection_mode
        is SelectionMode.PREFERRED
    )


def test_non_provider_work_does_not_create_request():
    requests = build_provider_search_requests(
        _plan(
            _item(
                action=PlanAction.NONE,
                reason=PlanReason.COMPLETE,
            )
        )
    )

    assert requests == ()


def test_provider_search_requires_one_plex_item():
    with pytest.raises(
        ValueError,
        match="exactly one Plex rating key",
    ):
        build_provider_search_requests(
            _plan(
                _item(
                    rating_keys=(
                        "100",
                        "101",
                    ),
                )
            )
        )


def test_duplicate_plex_search_identity_is_rejected():
    with pytest.raises(
        ValueError,
        match="duplicate provider search request",
    ):
        build_provider_search_requests(
            _plan(
                _item(
                    title="First"
                ),
                _item(
                    title="Second"
                ),
            )
        )
