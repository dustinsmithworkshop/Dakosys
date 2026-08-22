from artwork.inventory import build_show_inventory


class FakeGuid:
    def __init__(self, value):
        self.id = value


class FakeEpisode:
    def __init__(
        self,
        index,
        *,
        title=None,
        thumb=None,
    ):
        self.index = index
        self.title = title
        self.thumb = thumb


class FakeSeason:
    def __init__(self, index, episodes):
        self.index = index
        self._episodes = [
            (
                episode
                if isinstance(
                    episode,
                    FakeEpisode,
                )
                else FakeEpisode(
                    episode
                )
            )
            for episode in episodes
        ]

    def episodes(self):
        return list(self._episodes)


class FakeShow:
    def __init__(
        self,
        *,
        title="Example Show",
        year=2026,
        rating_key="123",
        guids=None,
        seasons=None,
    ):
        self.title = title
        self.year = year
        self.ratingKey = rating_key
        self.guids = guids or []
        self._seasons = seasons or []

    def seasons(self):
        return list(self._seasons)


def test_builds_show_identity_from_existing_tv_metadata_helper():
    show = FakeShow(
        guids=[
            FakeGuid("tmdb://100"),
            FakeGuid("tvdb://200"),
            FakeGuid("imdb://tt1234567"),
        ],
        seasons=[
            FakeSeason(1, [1, 2]),
        ],
    )

    inventory = build_show_inventory(
        show,
        "TV",
        library_roles=("tv",),
    )

    identity = inventory.identity

    assert identity.title == "Example Show"
    assert identity.year == 2026
    assert identity.library == "TV"
    assert identity.plex_rating_key == "123"
    assert identity.tmdb_id == 100
    assert identity.tvdb_id == 200
    assert identity.imdb_id == "tt1234567"
    assert identity.library_roles == ("tv",)


def test_collects_episode_inventory_by_season():
    show = FakeShow(
        seasons=[
            FakeSeason(1, [1, 2, 3]),
            FakeSeason(2, [1, 2]),
        ],
    )

    inventory = build_show_inventory(
        show,
        "TV",
    )

    assert inventory.expected_episodes() == {
        1: frozenset({1, 2, 3}),
        2: frozenset({1, 2}),
    }


def test_preserves_specials_as_season_zero():
    show = FakeShow(
        seasons=[
            FakeSeason(0, [1, 2]),
            FakeSeason(1, [1]),
        ],
    )

    inventory = build_show_inventory(
        show,
        "TV",
    )

    assert inventory.expected_episodes() == {
        0: frozenset({1, 2}),
        1: frozenset({1}),
    }


def test_sorts_seasons():
    show = FakeShow(
        seasons=[
            FakeSeason(3, [1]),
            FakeSeason(1, [1]),
            FakeSeason(2, [1]),
        ],
    )

    inventory = build_show_inventory(
        show,
        "TV",
    )

    assert [
        season.season_number
        for season in inventory.seasons
    ] == [1, 2, 3]


def test_duplicate_episode_numbers_are_normalized():
    show = FakeShow(
        seasons=[
            FakeSeason(1, [1, 1, 2]),
        ],
    )

    inventory = build_show_inventory(
        show,
        "TV",
    )

    assert inventory.season(
        1
    ).episode_numbers == frozenset(
        {1, 2}
    )


def test_invalid_episode_numbers_are_ignored():
    show = FakeShow(
        seasons=[
            FakeSeason(
                1,
                [
                    1,
                    None,
                    "bad",
                    0,
                    -1,
                    2,
                ],
            ),
        ],
    )

    inventory = build_show_inventory(
        show,
        "TV",
    )

    assert inventory.expected_episodes() == {
        1: frozenset({1, 2}),
    }


def test_empty_seasons_are_not_included():
    show = FakeShow(
        seasons=[
            FakeSeason(1, []),
            FakeSeason(2, [1]),
        ],
    )

    inventory = build_show_inventory(
        show,
        "TV",
    )

    assert inventory.expected_episodes() == {
        2: frozenset({1}),
    }


def test_inventory_feeds_coverage_shape_directly():
    show = FakeShow(
        seasons=[
            FakeSeason(1, [1, 2, 3]),
            FakeSeason(2, [1, 2]),
        ],
    )

    inventory = build_show_inventory(
        show,
        "TV",
    )

    expected = inventory.expected_episodes()

    assert expected[1] == frozenset(
        {1, 2, 3}
    )
    assert expected[2] == frozenset(
        {1, 2}
    )


def test_collects_episode_generation_metadata():
    show = FakeShow(
        seasons=[
            FakeSeason(
                1,
                [
                    FakeEpisode(
                        1,
                        title=(
                            "The Journey's End"
                        ),
                        thumb=(
                            "/library/metadata/"
                            "123/thumb/456"
                        ),
                    ),
                    FakeEpisode(
                        2,
                        title=(
                            "It Didn't Have "
                            "to Be Magic..."
                        ),
                        thumb=(
                            "/library/metadata/"
                            "124/thumb/457"
                        ),
                    ),
                ],
            ),
        ],
    )

    inventory = build_show_inventory(
        show,
        "TV",
    )

    season = inventory.season(1)

    assert season is not None

    episode = season.episode(1)

    assert episode is not None
    assert episode.episode_number == 1
    assert (
        episode.title
        == "The Journey's End"
    )
    assert episode.plex_thumb == (
        "/library/metadata/123/thumb/456"
    )

    second_episode = season.episode(2)

    assert second_episode is not None
    assert second_episode.title == (
        "It Didn't Have to Be Magic..."
    )


def test_normalizes_blank_episode_generation_metadata():
    show = FakeShow(
        seasons=[
            FakeSeason(
                1,
                [
                    FakeEpisode(
                        1,
                        title="   ",
                        thumb="   ",
                    ),
                ],
            ),
        ],
    )

    inventory = build_show_inventory(
        show,
        "TV",
    )

    season = inventory.season(1)

    assert season is not None

    episode = season.episode(1)

    assert episode is not None
    assert episode.title is None
    assert episode.plex_thumb is None


def test_episode_metadata_preserves_existing_coverage_shape():
    show = FakeShow(
        seasons=[
            FakeSeason(
                1,
                [
                    FakeEpisode(
                        1,
                        title="Episode One",
                    ),
                    FakeEpisode(
                        2,
                        title="Episode Two",
                    ),
                ],
            ),
        ],
    )

    inventory = build_show_inventory(
        show,
        "TV",
    )

    assert inventory.expected_episodes() == {
        1: frozenset({1, 2}),
    }
