from pathlib import Path
from types import SimpleNamespace

from artwork.managed_state import (
    ManagedStateBaselineSource,
)
from artwork.models import (
    ArtworkAsset,
    ArtworkKind,
    ArtworkSet,
    ArtworkSource,
)
from artwork.serialization import (
    serialize_artwork_library,
)
from artwork.targets import (
    ArtworkTarget,
    MediaType,
)
from artwork.workflow import (
    apply_artwork_library_workflow,
    build_artwork_target_workflow,
)


class Section:
    def __init__(
        self,
        items,
    ):
        self._items = list(
            items
        )

    def all(self):
        return list(
            self._items
        )


class Library:
    def __init__(
        self,
        section,
    ):
        self._section = section

    def section(
        self,
        name,
    ):
        return self._section


class Plex:
    def __init__(
        self,
        items,
    ):
        self.library = Library(
            Section(
                items
            )
        )


class Provider:
    name = "fake"

    def __init__(
        self,
        artwork_sets,
    ):
        self.artwork_sets = list(
            artwork_sets
        )
        self.requests = []

    def find_sets(
        self,
        request,
    ):
        self.requests.append(
            request
        )

        return list(
            self.artwork_sets
        )


def _movie():
    return SimpleNamespace(
        title="Blade Runner",
        year=1982,
        ratingKey="123",
        guids=[
            "tmdb://78",
            "imdb://tt0083658",
        ],
    )


def _provider():
    return Provider(
        [
            ArtworkSet(
                provider=(
                    ArtworkSource.MEDIUX
                ),
                set_id="set-1",
                creator="creator",
                poster=ArtworkAsset(
                    kind=(
                        ArtworkKind
                        .MOVIE_POSTER
                    ),
                    source=(
                        ArtworkSource.MEDIUX
                    ),
                    url=(
                        "https://example/"
                        "poster.jpg"
                    ),
                    provider_asset_id=(
                        "poster-1"
                    ),
                ),
                background=ArtworkAsset(
                    kind=(
                        ArtworkKind
                        .MOVIE_BACKGROUND
                    ),
                    source=(
                        ArtworkSource.MEDIUX
                    ),
                    url=(
                        "https://example/"
                        "background.jpg"
                    ),
                    provider_asset_id=(
                        "background-1"
                    ),
                ),
            )
        ]
    )


def _target(
    directory,
):
    return ArtworkTarget(
        name="Movies",
        library="Movies",
        media_type=MediaType.MOVIE,
        output_path=Path(
            directory
        ),
    )


def test_movie_workflow_builds_real_safe_plan(
    tmp_path,
):
    directory = (
        tmp_path
        / "artwork-movies"
    )

    provider = _provider()

    run = (
        build_artwork_target_workflow(
            plex=Plex(
                [
                    _movie()
                ]
            ),
            target=_target(
                directory
            ),
            provider=provider,
        )
    )

    assert (
        run.baseline.source
        is ManagedStateBaselineSource
        .NEW_LIBRARY
    )

    assert (
        run.target.media_type
        is MediaType.MOVIE
    )

    assert (
        run.execution.discovered_count
        == 1
    )

    assert run.safe_to_apply
    assert run.plan is not None
    assert run.plan.desired_count == 1
    assert run.plan.added_count == 1
    assert run.needs_apply

    assert not directory.exists()

    assert (
        provider.requests[0]
        .media_type
        is MediaType.MOVIE
    )

    payload = (
        serialize_artwork_library(
            run
        )
    )

    assert (
        payload["media_type"]
        == "movie"
    )

    assert (
        payload["inventory"][
            "plex_shows"
        ]
        == 1
    )


def test_movie_workflow_applies_transactionally(
    tmp_path,
):
    directory = (
        tmp_path
        / "artwork-movies"
    )

    plex = Plex(
        [
            _movie()
        ]
    )

    provider = _provider()

    first = (
        build_artwork_target_workflow(
            plex=plex,
            target=_target(
                directory
            ),
            provider=provider,
        )
    )

    result = (
        apply_artwork_library_workflow(
            first
        )
    )

    assert result.changed

    assert (
        directory
        / ".dakosys-manifest.json"
    ).is_file()

    assert (
        directory
        / ".dakosys-state.json"
    ).is_file()

    assert (
        directory
        / (
            "blade-runner"
            "--tmdb-78.yaml"
        )
    ).is_file()

    second = (
        build_artwork_target_workflow(
            plex=plex,
            target=_target(
                directory
            ),
            provider=_provider(),
        )
    )

    assert (
        second.baseline.source
        is ManagedStateBaselineSource
        .DURABLE_STATE
    )

    assert second.safe_to_apply
    assert second.plan is not None
    assert second.plan.unchanged_count == 1
    assert not second.needs_apply
