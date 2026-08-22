from pathlib import Path
from types import SimpleNamespace

from artwork.generator_enrichment import (
    GeneratorEnrichmentPath,
    enrich_show_with_generated_episode_cards,
)
from artwork.inventory import (
    EpisodeInventory,
    SeasonInventory,
    ShowInventory,
)
from artwork.models import (
    ArtworkAsset,
    ArtworkKind,
    ArtworkQuality,
    ArtworkSetSelection,
    ArtworkSource,
    EpisodeArtwork,
    SeasonArtwork,
    SelectionMode,
    ShowArtworkState,
)
from artwork.providers.tmdb import (
    TMDBEpisodeArtwork,
)


def _inventory(
    *,
    episodes=(1, 2),
):
    episode_metadata = tuple(
        EpisodeInventory(
            episode_number=number,
            title=f"Episode {number}",
            plex_thumb=(
                f"/library/metadata/"
                f"{number}/thumb"
            ),
        )
        for number in episodes
    )

    return ShowInventory(
        identity=SimpleNamespace(
            library="TV",
            plex_rating_key="123",
            title="Example Show",
            tvdb_id=100,
            tmdb_id=200,
            imdb_id="tt1234567",
        ),
        seasons=(
            SeasonInventory(
                season_number=1,
                episode_numbers=(
                    frozenset(
                        episodes
                    )
                ),
                episodes=(
                    episode_metadata
                ),
            ),
        ),
    )


def _asset(
    *,
    source,
    quality,
    identifier,
):
    if (
        source
        is ArtworkSource.GENERATED
    ):
        return ArtworkAsset(
            kind=(
                ArtworkKind
                .EPISODE_CARD
            ),
            source=source,
            provider_asset_id=(
                identifier
            ),
            quality=quality,
            file_path=(
                "/config/assets/"
                f"{identifier}.jpg"
            ),
        )

    return ArtworkAsset(
        kind=(
            ArtworkKind
            .EPISODE_CARD
        ),
        source=source,
        provider_asset_id=(
            identifier
        ),
        quality=quality,
        url=(
            "https://example.test/"
            f"{identifier}.jpg"
        ),
    )


def _state(
    *,
    cards=None,
    mode=SelectionMode.AUTO,
):
    cards = cards or {}

    episodes = {
        number: EpisodeArtwork(
            episode_number=number,
            card=card,
        )
        for number, card
        in cards.items()
    }

    return ShowArtworkState(
        title="Example Show",
        tvdb_id=100,
        tmdb_id=200,
        imdb_id="tt1234567",
        seasons={
            1: SeasonArtwork(
                season_number=1,
                episodes=episodes,
            ),
        },
        selection_mode=mode,
    )


class FakeTMDB:
    def __init__(
        self,
        *,
        episodes=None,
        fail=False,
    ):
        self.episodes = (
            episodes or {}
        )
        self.fail = fail
        self.requests = []

    def resolve_tmdb_id(
        self,
        identity,
    ):
        return (
            identity.tmdb_id,
            "tmdb",
        )

    def get_season_episode_artwork(
        self,
        *,
        tmdb_id,
        season_number,
    ):
        self.requests.append(
            (
                tmdb_id,
                season_number,
            )
        )

        if self.fail:
            raise RuntimeError(
                "TMDB unavailable"
            )

        return self.episodes


def _tmdb_episode(
    number,
    *,
    title=None,
    still=True,
):
    card = None

    if still:
        card = _asset(
            source=ArtworkSource.TMDB,
            quality=(
                ArtworkQuality.RAW_STILL
            ),
            identifier=(
                f"tmdb-{number}"
            ),
        )

    return TMDBEpisodeArtwork(
        episode_number=number,
        title=(
            title
            or f"TMDB Episode {number}"
        ),
        card=card,
    )


def _planner(
    calls,
    *,
    fail_episode=None,
    cached=False,
):
    def materialize(
        **kwargs,
    ):
        generation_input = (
            kwargs[
                "generation_input"
            ]
        )

        episode_number = (
            generation_input
            .episode_number
        )

        calls.append(
            {
                "episode":
                    episode_number,
                "show_key":
                    kwargs[
                        "show_key"
                    ],
                "font_key":
                    kwargs[
                        "font_key"
                    ],
                "image_source":
                    generation_input
                    .image_source,
            }
        )

        if (
            episode_number
            == fail_episode
        ):
            raise RuntimeError(
                "render failed"
            )

        asset = _asset(
            source=(
                ArtworkSource
                .GENERATED
            ),
            quality=(
                ArtworkQuality
                .GENERATED
            ),
            identifier=(
                f"generated-{episode_number}"
            ),
        )

        return SimpleNamespace(
            asset=asset,
            cached=cached,
        )

    return materialize


def test_disabled_generator_makes_no_changes_or_requests(
    tmp_path: Path,
):
    state = _state()

    tmdb = FakeTMDB(
        episodes={
            1: _tmdb_episode(1),
        }
    )

    calls = []

    result = (
        enrich_show_with_generated_episode_cards(
            inventory=_inventory(),
            state=state,
            enabled=False,
            font_key="marcellus",
            local_root=tmp_path,
            kometa_root="/config/assets",
            tmdb_client=tmdb,
            plan_card=(
                _planner(
                    calls
                )
            ),
        )
    )

    assert (
        result.path
        is GeneratorEnrichmentPath.DISABLED
    )
    assert result.state is state
    assert not tmdb.requests
    assert not calls


def test_partial_mediux_keeps_curated_and_generates_gap(
    tmp_path: Path,
):
    mediux = _asset(
        source=ArtworkSource.MEDIUX,
        quality=ArtworkQuality.CURATED,
        identifier="mediux-1",
    )

    state = _state(
        cards={
            1: mediux,
        }
    )

    tmdb = FakeTMDB(
        episodes={
            1: _tmdb_episode(1),
            2: _tmdb_episode(2),
        }
    )

    calls = []

    result = (
        enrich_show_with_generated_episode_cards(
            inventory=_inventory(),
            state=state,
            enabled=True,
            font_key="marcellus",
            local_root=tmp_path,
            kometa_root="/config/assets",
            tmdb_client=tmdb,
            plan_card=(
                _planner(
                    calls
                )
            ),
        )
    )

    assert result.changed
    assert (
        result.kept_primary_count
        == 1
    )
    assert (
        result.changed_episode_count
        == 1
    )

    assert (
        result.state
        .seasons[1]
        .episodes[1]
        .card
        == mediux
    )

    assert (
        result.state
        .seasons[1]
        .episodes[2]
        .card
        .source
        is ArtworkSource.GENERATED
    )

    assert [
        call["episode"]
        for call in calls
    ] == [2]


def test_raw_tmdb_fallback_upgrades_to_generated(
    tmp_path: Path,
):
    raw = _asset(
        source=ArtworkSource.TMDB,
        quality=(
            ArtworkQuality.RAW_STILL
        ),
        identifier="raw-1",
    )

    state = _state(
        cards={
            1: raw,
        }
    )

    calls = []

    result = (
        enrich_show_with_generated_episode_cards(
            inventory=_inventory(
                episodes=(1,)
            ),
            state=state,
            enabled=True,
            font_key="prata",
            local_root=tmp_path,
            kometa_root="/config/assets",
            tmdb_client=None,
            plan_card=(
                _planner(
                    calls
                )
            ),
        )
    )

    assert result.changed

    card = (
        result.state
        .seasons[1]
        .episodes[1]
        .card
    )

    assert (
        card.source
        is ArtworkSource.GENERATED
    )

    assert calls[0][
        "image_source"
    ] is ArtworkSource.TMDB


def test_generation_failure_preserves_existing_fallback_and_continues(
    tmp_path: Path,
):
    raw = _asset(
        source=ArtworkSource.TMDB,
        quality=(
            ArtworkQuality.RAW_STILL
        ),
        identifier="raw-1",
    )

    state = _state(
        cards={
            1: raw,
        }
    )

    calls = []

    result = (
        enrich_show_with_generated_episode_cards(
            inventory=_inventory(),
            state=state,
            enabled=True,
            font_key="marcellus",
            local_root=tmp_path,
            kometa_root="/config/assets",
            tmdb_client=None,
            plan_card=(
                _planner(
                    calls,
                    fail_episode=1,
                )
            ),
        )
    )

    assert (
        result.failure_count
        == 1
    )

    assert (
        result.state
        .seasons[1]
        .episodes[1]
        .card
        == raw
    )

    assert (
        result.state
        .seasons[1]
        .episodes[2]
        .card
        .source
        is ArtworkSource.GENERATED
    )


def test_tmdb_failure_still_allows_plex_thumbnail_generation(
    tmp_path: Path,
):
    tmdb = FakeTMDB(
        fail=True
    )

    calls = []

    result = (
        enrich_show_with_generated_episode_cards(
            inventory=_inventory(
                episodes=(1,)
            ),
            state=_state(),
            enabled=True,
            font_key="marcellus",
            local_root=tmp_path,
            kometa_root="/config/assets",
            tmdb_client=tmdb,
            plan_card=(
                _planner(
                    calls
                )
            ),
        )
    )

    assert result.changed

    assert len(
        result.season_failures
    ) == 1

    assert calls[0][
        "image_source"
    ] is ArtworkSource.PLEX


def test_generator_can_create_state_from_plex_only(
    tmp_path: Path,
):
    calls = []

    result = (
        enrich_show_with_generated_episode_cards(
            inventory=_inventory(
                episodes=(1,)
            ),
            state=None,
            enabled=True,
            font_key="marcellus",
            local_root=tmp_path,
            kometa_root="/config/assets",
            tmdb_client=None,
            plan_card=(
                _planner(
                    calls
                )
            ),
        )
    )

    assert result.changed
    assert result.state is not None

    assert (
        result.state.tvdb_id
        == 100
    )

    assert (
        result.state.tmdb_id
        == 200
    )

    assert (
        result.state
        .seasons[1]
        .episodes[1]
        .card
        .source
        is ArtworkSource.GENERATED
    )


def test_locked_episode_selection_never_generates(
    tmp_path: Path,
):
    state = _state()

    state.episode_selection = (
        ArtworkSetSelection(
            provider=(
                ArtworkSource.MEDIUX
            ),
            set_id="set-1",
            mode=(
                SelectionMode.LOCKED
            ),
        )
    )

    calls = []

    result = (
        enrich_show_with_generated_episode_cards(
            inventory=_inventory(),
            state=state,
            enabled=True,
            font_key="marcellus",
            local_root=tmp_path,
            kometa_root="/config/assets",
            tmdb_client=FakeTMDB(),
            plan_card=(
                _planner(
                    calls
                )
            ),
        )
    )

    assert (
        result.path
        is GeneratorEnrichmentPath.LOCKED
    )

    assert not calls


def test_tmdb_metadata_is_requested_once_per_season(
    tmp_path: Path,
):
    tmdb = FakeTMDB(
        episodes={
            1: _tmdb_episode(1),
            2: _tmdb_episode(2),
        }
    )

    calls = []

    result = (
        enrich_show_with_generated_episode_cards(
            inventory=_inventory(),
            state=_state(),
            enabled=True,
            font_key="marcellus",
            local_root=tmp_path,
            kometa_root="/config/assets",
            tmdb_client=tmdb,
            plan_card=(
                _planner(
                    calls
                )
            ),
        )
    )

    assert result.tmdb_request_count == 1

    assert tmdb.requests == [
        (
            200,
            1,
        )
    ]


def test_cached_plan_is_reported_separately_from_state_change(
    tmp_path: Path,
):
    calls = []

    result = (
        enrich_show_with_generated_episode_cards(
            inventory=_inventory(
                episodes=(1,)
            ),
            state=_state(),
            enabled=True,
            font_key="marcellus",
            local_root=tmp_path,
            kometa_root="/config/assets",
            tmdb_client=None,
            plan_card=(
                _planner(
                    calls,
                    cached=True,
                )
            ),
        )
    )

    assert result.changed
    assert (
        result.cached_plan_count
        == 1
    )
    assert result.materialization_needed_count == 0


def test_real_enrichment_plans_without_writing_files(
    tmp_path: Path,
):
    local_root = (
        tmp_path
        / "generated"
    )

    result = (
        enrich_show_with_generated_episode_cards(
            inventory=_inventory(
                episodes=(1,)
            ),
            state=_state(),
            enabled=True,
            font_key="marcellus",
            local_root=local_root,
            kometa_root=(
                "/config/assets/generated"
            ),
            tmdb_client=None,
        )
    )

    assert result.changed
    assert result.planned_count == 1

    assert (
        result.materialization_needed_count
        == 1
    )

    assert result.cached_plan_count == 0

    assert (
        result.generation_plans[0]
        .needs_materialization
    )

    assert (
        result.state
        .seasons[1]
        .episodes[1]
        .card
        .source
        is ArtworkSource.GENERATED
    )

    # Preview/planning must not create the cache root, let alone a JPEG.
    assert not local_root.exists()


def test_library_font_override_is_used_for_generation_plan(
    tmp_path: Path,
):
    from artwork.generator_config import (
        parse_artwork_generator_config,
    )

    creative = (
        parse_artwork_generator_config(
            {
                "defaults": {
                    "font": "marcellus",
                },
                "libraries": {
                    "TV": {
                        "font": (
                            "cormorant_garamond"
                        ),
                    },
                },
            }
        )
    )

    calls = []

    result = (
        enrich_show_with_generated_episode_cards(
            inventory=_inventory(
                episodes=(1,)
            ),
            state=_state(),
            enabled=True,
            local_root=(
                tmp_path
                / "generated"
            ),
            kometa_root=(
                "/config/assets/generated"
            ),
            creative_config=creative,
            tmdb_client=None,
            plan_card=(
                _planner(
                    calls
                )
            ),
        )
    )

    assert result.changed

    assert (
        calls[0]["font_key"]
        == "cormorant_garamond"
    )


def test_show_font_override_beats_library_override(
    tmp_path: Path,
):
    from artwork.generator_config import (
        parse_artwork_generator_config,
    )

    creative = (
        parse_artwork_generator_config(
            {
                "defaults": {
                    "font": "marcellus",
                },
                "libraries": {
                    "TV": {
                        "font": "cinzel",
                    },
                },
                "shows": {
                    "tmdb:200": {
                        "font": "prata",
                    },
                },
            }
        )
    )

    calls = []

    result = (
        enrich_show_with_generated_episode_cards(
            inventory=_inventory(
                episodes=(1,)
            ),
            state=_state(),
            enabled=True,
            local_root=(
                tmp_path
                / "generated"
            ),
            kometa_root=(
                "/config/assets/generated"
            ),
            creative_config=creative,
            tmdb_client=None,
            plan_card=(
                _planner(
                    calls
                )
            ),
        )
    )

    assert result.changed

    assert (
        calls[0]["show_key"]
        == "tmdb:200"
    )

    assert (
        calls[0]["font_key"]
        == "prata"
    )


def test_global_font_is_used_when_no_override_matches(
    tmp_path: Path,
):
    from artwork.generator_config import (
        parse_artwork_generator_config,
    )

    creative = (
        parse_artwork_generator_config(
            {
                "defaults": {
                    "font": (
                        "libre_baskerville"
                    ),
                },
                "libraries": {
                    "Anime": {
                        "font": "cinzel",
                    },
                },
            }
        )
    )

    calls = []

    enrich_show_with_generated_episode_cards(
        inventory=_inventory(
            episodes=(1,)
        ),
        state=_state(),
        enabled=True,
        local_root=(
            tmp_path
            / "generated"
        ),
        kometa_root=(
            "/config/assets/generated"
        ),
        creative_config=creative,
        tmdb_client=None,
        plan_card=(
            _planner(
                calls
            )
        ),
    )

    assert (
        calls[0]["font_key"]
        == "libre_baskerville"
    )
