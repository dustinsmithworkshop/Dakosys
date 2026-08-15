import pytest

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
from artwork.service import (
    TargetSkipReason,
    build_artwork_service_plan,
)
from artwork.targets import (
    ArtworkTarget,
    MediaType,
)
from tv_metadata.models import ShowIdentity


class FakeShow:
    def __init__(
        self,
        inventory,
    ):
        self.inventory = inventory


class FakeSection:
    def __init__(
        self,
        shows,
    ):
        self._shows = list(
            shows
        )

    def all(self):
        return list(
            self._shows
        )


class FakeLibrary:
    def __init__(
        self,
        sections,
    ):
        self._sections = dict(
            sections
        )
        self.requested = []

    def section(
        self,
        name,
    ):
        self.requested.append(
            name
        )
        return self._sections[
            name
        ]


class FakePlex:
    def __init__(
        self,
        sections,
    ):
        self.library = FakeLibrary(
            sections
        )


def _target(
    library,
    media_type=MediaType.SHOW,
):
    slug = (
        library
        .casefold()
        .replace(" ", "-")
    )

    return ArtworkTarget(
        name=library,
        library=library,
        media_type=media_type,
        output_path=(
            f"/metadata/artwork-{slug}.yaml"
        ),
    )


def _inventory(
    *,
    title,
    library,
    rating_key,
    tvdb_id,
    episodes=(1, 2, 3),
):
    return ShowInventory(
        identity=ShowIdentity(
            title=title,
            year=2026,
            library=library,
            plex_rating_key=rating_key,
            tvdb_id=tvdb_id,
            tmdb_id=tvdb_id + 1000,
            imdb_id=f"tt{tvdb_id:07d}",
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
    title,
    tvdb_id,
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
                        f"{number}.jpg"
                    ),
                    quality=ArtworkQuality.CURATED,
                ),
            )
        )

    return ShowArtworkState(
        title=title,
        tvdb_id=tvdb_id,
        seasons={
            1: season,
        },
        selected_set_id="500",
        selected_set_source=ArtworkSource.MEDIUX,
    )


@pytest.fixture
def fake_inventory_builder(
    monkeypatch,
):
    calls = []

    def build(
        show,
        library,
    ):
        calls.append(
            (
                show.inventory.identity.title,
                library,
            )
        )

        assert (
            show.inventory.identity.library
            == library
        )

        return show.inventory

    monkeypatch.setattr(
        "artwork.service.build_show_inventory",
        build,
    )

    return calls


def test_service_plans_arbitrary_show_library_names(
    fake_inventory_builder,
):
    first = _inventory(
        title="Example One",
        library="Series Vault",
        rating_key="1",
        tvdb_id=100,
    )

    second = _inventory(
        title="Example Two",
        library="Kids & Family",
        rating_key="2",
        tvdb_id=200,
    )

    plex = FakePlex(
        {
            "Series Vault": FakeSection(
                [FakeShow(first)]
            ),
            "Kids & Family": FakeSection(
                [FakeShow(second)]
            ),
        }
    )

    result = build_artwork_service_plan(
        plex=plex,
        targets=[
            _target(
                "Series Vault"
            ),
            _target(
                "Kids & Family"
            ),
        ],
    )

    assert result.target_count == 2
    assert result.planned_target_count == 2
    assert result.skipped_target_count == 0
    assert result.provider_search_count == 2

    assert [
        plan.target.library
        for plan in result.plans
    ] == [
        "Series Vault",
        "Kids & Family",
    ]


def test_service_uses_exact_target_library_name(
    fake_inventory_builder,
):
    inventory = _inventory(
        title="Example",
        library="My Shows",
        rating_key="1",
        tvdb_id=100,
    )

    plex = FakePlex(
        {
            "My Shows": FakeSection(
                [FakeShow(inventory)]
            ),
        }
    )

    build_artwork_service_plan(
        plex=plex,
        targets=[
            _target(
                "My Shows"
            )
        ],
    )

    assert plex.library.requested == [
        "My Shows"
    ]

    assert fake_inventory_builder == [
        (
            "Example",
            "My Shows",
        )
    ]


def test_unmanaged_show_becomes_provider_search(
    fake_inventory_builder,
):
    inventory = _inventory(
        title="Unmanaged",
        library="Series",
        rating_key="1",
        tvdb_id=100,
    )

    plex = FakePlex(
        {
            "Series": FakeSection(
                [FakeShow(inventory)]
            ),
        }
    )

    result = build_artwork_service_plan(
        plex=plex,
        targets=[
            _target("Series")
        ],
    )

    plan = result.plan_for_library(
        "Series"
    )

    assert plan is not None
    assert plan.provider_search_count == 1
    assert plan.stable_count == 0


def test_existing_complete_state_becomes_stable(
    fake_inventory_builder,
):
    inventory = _inventory(
        title="Managed",
        library="Shows",
        rating_key="1",
        tvdb_id=100,
    )

    plex = FakePlex(
        {
            "Shows": FakeSection(
                [FakeShow(inventory)]
            ),
        }
    )

    result = build_artwork_service_plan(
        plex=plex,
        targets=[
            _target("Shows")
        ],
        managed_by_library={
            "Shows": [
                _managed(
                    title="Managed",
                    tvdb_id=100,
                )
            ],
        },
    )

    assert result.stable_count == 1
    assert result.provider_search_count == 0


def test_movie_target_is_reported_as_skipped(
    fake_inventory_builder,
):
    plex = FakePlex(
        {}
    )

    result = build_artwork_service_plan(
        plex=plex,
        targets=[
            _target(
                "Feature Films",
                MediaType.MOVIE,
            )
        ],
    )

    assert result.target_count == 1
    assert result.planned_target_count == 0
    assert result.skipped_target_count == 1

    skipped = result.skipped[0]

    assert (
        skipped.reason
        is TargetSkipReason.MOVIE_SUPPORT_PENDING
    )

    assert skipped.target.library == (
        "Feature Films"
    )

    assert plex.library.requested == []
    assert fake_inventory_builder == []


def test_empty_target_list_is_valid(
    fake_inventory_builder,
):
    result = build_artwork_service_plan(
        plex=FakePlex({}),
        targets=[],
    )

    assert result.target_count == 0
    assert result.item_count == 0
    assert result.plans == ()
    assert result.skipped == ()


def test_unknown_managed_library_is_rejected(
    fake_inventory_builder,
):
    plex = FakePlex(
        {}
    )

    with pytest.raises(
        ValueError,
        match="unknown target libraries",
    ):
        build_artwork_service_plan(
            plex=plex,
            targets=[
                _target("Series")
            ],
            managed_by_library={
                "Typo Library": [],
            },
        )


def test_duplicate_target_library_is_rejected(
    fake_inventory_builder,
):
    plex = FakePlex(
        {}
    )

    with pytest.raises(
        ValueError,
        match="duplicate Artwork Manager target",
    ):
        build_artwork_service_plan(
            plex=plex,
            targets=[
                _target("Series"),
                ArtworkTarget(
                    name="Series Duplicate",
                    library="Series",
                    media_type=MediaType.SHOW,
                    output_path=(
                        "/metadata/"
                        "different.yaml"
                    ),
                ),
            ],
        )
