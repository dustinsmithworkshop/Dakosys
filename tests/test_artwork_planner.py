from artwork.coverage import analyze_set_coverage
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
from artwork.planner import (
    PlanAction,
    PlanReason,
    build_target_plan,
)
from artwork.reconciliation import (
    AmbiguousManagedMatch,
    ReconciledShow,
    TargetReconciliation,
)
from artwork.targets import (
    ArtworkTarget,
    MediaType,
)
from tv_metadata.models import ShowIdentity


def _target():
    return ArtworkTarget(
        name="Series Collection",
        library="Series Collection",
        media_type=MediaType.SHOW,
        output_path="artwork-series-collection.yaml",
    )


def _inventory(
    *,
    title="Example",
    rating_key="100",
    tvdb_id=100,
    episodes=(1, 2, 3),
):
    return ShowInventory(
        identity=ShowIdentity(
            title=title,
            year=2026,
            library="Series Collection",
            plex_rating_key=rating_key,
            tvdb_id=tvdb_id,
            tmdb_id=200,
            imdb_id="tt0000200",
        ),
        seasons=(
            SeasonInventory(
                season_number=1,
                episode_numbers=frozenset(
                    episodes
                ),
            ),
        ),
    )


def _managed(
    *,
    title="Example",
    tvdb_id=100,
    episodes=(1, 2, 3),
):
    season = SeasonArtwork(
        season_number=1,
    )

    for number in episodes:
        season.episodes[number] = (
            EpisodeArtwork(
                episode_number=number,
                card=ArtworkAsset(
                    kind=ArtworkKind.EPISODE_CARD,
                    source=ArtworkSource.MEDIUX,
                    url=(
                        "https://example.test/"
                        f"e{number}.jpg"
                    ),
                    quality=ArtworkQuality.CURATED,
                ),
            )
        )

    return ShowArtworkState(
        title=title,
        tvdb_id=tvdb_id,
        tmdb_id=200,
        imdb_id="tt0000200",
        seasons={
            1: season,
        },
        selected_set_id="500",
        selected_set_source=ArtworkSource.MEDIUX,
        selected_creator="ExampleArtist",
    )


def _reconciled(
    inventory,
    artwork,
):
    artwork_set = ArtworkSet(
        provider=ArtworkSource.MEDIUX,
        set_id=artwork.selected_set_id,
        creator=artwork.selected_creator,
        seasons=artwork.seasons,
    )

    coverage = analyze_set_coverage(
        artwork_set,
        inventory.expected_episodes(),
    )

    return ReconciledShow(
        inventory=inventory,
        artwork=artwork,
        coverage=coverage,
    )


def _result(
    *,
    matched=(),
    unmanaged=(),
    missing_identity=(),
    ambiguous=(),
    orphaned=(),
):
    return TargetReconciliation(
        target=_target(),
        matched=tuple(matched),
        unmanaged=tuple(unmanaged),
        missing_identity=tuple(
            missing_identity
        ),
        ambiguous=tuple(ambiguous),
        orphaned=tuple(orphaned),
    )


def test_complete_managed_show_needs_no_immediate_work():
    inventory = _inventory()
    artwork = _managed()

    plan = build_target_plan(
        _result(
            matched=[
                _reconciled(
                    inventory,
                    artwork,
                )
            ],
        )
    )

    item = plan.items[0]

    assert item.action is PlanAction.NONE
    assert item.reason is PlanReason.COMPLETE
    assert item.expected_episode_count == 3
    assert item.managed_card_count == 3
    assert item.missing_managed_card_count == 0


def test_incomplete_managed_show_needs_provider_search():
    inventory = _inventory(
        episodes=(1, 2, 3, 4),
    )

    artwork = _managed(
        episodes=(1, 2),
    )

    plan = build_target_plan(
        _result(
            matched=[
                _reconciled(
                    inventory,
                    artwork,
                )
            ],
        )
    )

    item = plan.items[0]

    assert item.action is PlanAction.PROVIDER_SEARCH
    assert (
        item.reason
        is PlanReason.INCOMPLETE_COVERAGE
    )
    assert item.expected_episode_count == 4
    assert item.managed_card_count == 2
    assert item.missing_managed_card_count == 2
    assert item.selected_set_id == "500"


def test_unmanaged_show_needs_provider_search():
    plan = build_target_plan(
        _result(
            unmanaged=[
                _inventory(
                    episodes=(1, 2, 3, 4),
                )
            ],
        )
    )

    item = plan.items[0]

    assert item.action is PlanAction.PROVIDER_SEARCH
    assert item.reason is PlanReason.UNMANAGED
    assert item.expected_episode_count == 4
    assert item.managed_card_count == 0
    assert item.missing_managed_card_count == 4


def test_missing_identity_requires_resolution():
    inventory = _inventory(
        tvdb_id=None,
    )

    plan = build_target_plan(
        _result(
            missing_identity=[
                inventory
            ],
        )
    )

    item = plan.items[0]

    assert item.action is PlanAction.RESOLVE_IDENTITY
    assert (
        item.reason
        is PlanReason.MISSING_IDENTITY
    )
    assert item.plex_rating_keys == ("100",)


def test_ambiguous_managed_match_is_not_guessed():
    first = _inventory(
        rating_key="100",
    )

    second = _inventory(
        rating_key="101",
    )

    artwork = _managed()

    ambiguity = AmbiguousManagedMatch(
        tvdb_id=100,
        artwork=artwork,
        inventories=(
            first,
            second,
        ),
    )

    plan = build_target_plan(
        _result(
            ambiguous=[
                ambiguity
            ],
        )
    )

    item = plan.items[0]

    assert item.action is PlanAction.REVIEW_AMBIGUITY
    assert (
        item.reason
        is PlanReason.AMBIGUOUS_MANAGED_MATCH
    )
    assert item.plex_rating_keys == (
        "100",
        "101",
    )


def test_orphaned_managed_state_is_reported():
    plan = build_target_plan(
        _result(
            orphaned=[
                _managed()
            ],
        )
    )

    item = plan.items[0]

    assert item.action is PlanAction.REVIEW_ORPHAN
    assert (
        item.reason
        is PlanReason.ORPHANED_MANAGED_STATE
    )
    assert item.selected_set_id == "500"


def test_plan_summary_counts_work_categories():
    complete_inventory = _inventory(
        title="Complete",
        rating_key="1",
        tvdb_id=1,
    )

    complete_artwork = _managed(
        title="Complete",
        tvdb_id=1,
    )

    incomplete_inventory = _inventory(
        title="Incomplete",
        rating_key="2",
        tvdb_id=2,
        episodes=(1, 2, 3, 4),
    )

    incomplete_artwork = _managed(
        title="Incomplete",
        tvdb_id=2,
        episodes=(1,),
    )

    unmanaged = _inventory(
        title="Unmanaged",
        rating_key="3",
        tvdb_id=3,
    )

    missing = _inventory(
        title="Missing ID",
        rating_key="4",
        tvdb_id=None,
    )

    plan = build_target_plan(
        _result(
            matched=[
                _reconciled(
                    complete_inventory,
                    complete_artwork,
                ),
                _reconciled(
                    incomplete_inventory,
                    incomplete_artwork,
                ),
            ],
            unmanaged=[
                unmanaged
            ],
            missing_identity=[
                missing
            ],
        )
    )

    assert plan.item_count == 4
    assert plan.stable_count == 1
    assert plan.provider_search_count == 2
    assert plan.identity_review_count == 1
    assert plan.ambiguity_review_count == 0
    assert plan.orphan_review_count == 0


def test_plan_items_are_sorted_by_title():
    plan = build_target_plan(
        _result(
            unmanaged=[
                _inventory(
                    title="Zulu",
                    rating_key="2",
                    tvdb_id=2,
                ),
                _inventory(
                    title="Alpha",
                    rating_key="1",
                    tvdb_id=1,
                ),
            ],
        )
    )

    assert [
        item.title
        for item in plan.items
    ] == [
        "Alpha",
        "Zulu",
    ]
