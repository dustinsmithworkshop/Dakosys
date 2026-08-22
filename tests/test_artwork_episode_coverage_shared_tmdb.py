"""Shared TMDB metadata across episode coverage stages."""

from pathlib import Path

from artwork.episode_coverage import (
    EpisodeGeneratorOptions,
    resolve_episode_coverage,
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
    ArtworkSource,
    ShowArtworkState,
)
from artwork.providers.tmdb import (
    TMDBEpisodeArtwork,
)
from tv_metadata.models import (
    ShowIdentity,
)


class FakeTMDBClient:
    def __init__(
        self,
    ):
        self.calls = []

    def get_season_episode_artwork(
        self,
        *,
        tmdb_id,
        season_number,
    ):
        self.calls.append(
            (
                tmdb_id,
                season_number,
            )
        )

        return {
            1: TMDBEpisodeArtwork(
                episode_number=1,
                title="TMDB Pilot",
                card=ArtworkAsset(
                    kind=(
                        ArtworkKind
                        .EPISODE_CARD
                    ),
                    source=(
                        ArtworkSource.TMDB
                    ),
                    url=(
                        "https://image.tmdb.org/"
                        "t/p/original/still.jpg"
                    ),
                    provider_asset_id=(
                        "/still.jpg"
                    ),
                    quality=(
                        ArtworkQuality
                        .RAW_STILL
                    ),
                ),
            ),
        }


def test_fallback_and_generator_share_one_tmdb_season_request(
    tmp_path: Path,
):
    inventory = ShowInventory(
        identity=ShowIdentity(
            title="Example Show",
            year=2026,
            library="TV",
            plex_rating_key="123",
            tmdb_id=200,
            tvdb_id=100,
            imdb_id="tt0000001",
        ),
        seasons=(
            SeasonInventory(
                season_number=1,
                episode_numbers=(
                    frozenset(
                        {
                            1,
                        }
                    )
                ),
                episodes=(
                    EpisodeInventory(
                        episode_number=1,
                        title="Plex Pilot",
                        plex_thumb=(
                            "/library/metadata/"
                            "123/1/thumb"
                        ),
                    ),
                ),
            ),
        ),
    )

    state = ShowArtworkState(
        title="Example Show",
        tvdb_id=100,
        tmdb_id=200,
        imdb_id="tt0000001",
    )

    client = FakeTMDBClient()

    generated_root = (
        tmp_path
        / "generated-artwork"
    )

    result = resolve_episode_coverage(
        inventory=inventory,
        state=state,
        tmdb_client=client,
        generator_options=(
            EpisodeGeneratorOptions(
                enabled=True,
                local_root=(
                    generated_root
                ),
                kometa_root=(
                    "/config/assets/"
                    "generated-artwork"
                ),
                font_key="marcellus",
            )
        ),
    )

    # Fallback and generator both needed the same TMDB season metadata,
    # but the provider was contacted only once.
    assert client.calls == [
        (
            200,
            1,
        ),
    ]

    assert (
        result.season_request_count
        == 1
    )

    assert result.generator is not None

    assert (
        result.generator
        .tmdb_request_count
        == 0
    )

    assert (
        result.generator_plan_count
        == 1
    )

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

    # Plex title still wins, while the shared TMDB still is the image.
    plan = (
        result.generator
        .generation_plans[0]
    )

    assert (
        plan.generation_input.title
        == "Plex Pilot"
    )

    assert (
        plan.generation_input
        .title_source
        is ArtworkSource.PLEX
    )

    assert (
        plan.generation_input
        .image_source
        is ArtworkSource.TMDB
    )

    # Coverage remains a read-only planning operation.
    assert not generated_root.exists()
