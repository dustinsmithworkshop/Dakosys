from pathlib import Path

from artwork.models import (
    ArtworkAsset,
    ArtworkKind,
    ArtworkSource,
    MovieArtworkState,
)
from artwork.movie_execution import (
    execute_movie_target,
)
from artwork.movie_inventory import (
    MovieIdentity,
    MovieInventory,
)
from artwork.movie_tmdb_fallback import (
    MovieTMDBFallbackPath,
    resolve_movie_tmdb_coverage,
)
from artwork.providers.tmdb import (
    TMDBMovieArtwork,
)
from artwork.targets import (
    ArtworkTarget,
    MediaType,
)


def _inventory(
    *,
    tmdb_id=78,
    imdb_id="tt0083658",
):
    return MovieInventory(
        identity=MovieIdentity(
            title="Blade Runner",
            year=1982,
            library="Movies",
            plex_rating_key="123",
            tmdb_id=tmdb_id,
            imdb_id=imdb_id,
        )
    )


def _asset(
    kind,
    source,
    value,
):
    return ArtworkAsset(
        kind=kind,
        source=source,
        provider_asset_id=value,
    )


class TMDB:
    def __init__(
        self,
        *,
        poster=True,
        background=True,
        resolved_tmdb_id=78,
        error=None,
    ):
        self.poster = poster
        self.background = background
        self.resolved_tmdb_id = (
            resolved_tmdb_id
        )
        self.error = error
        self.resolutions = []
        self.requests = []

    def resolve_movie_tmdb_id(
        self,
        identity,
    ):
        self.resolutions.append(
            identity
        )

        return (
            self.resolved_tmdb_id,
            "imdb",
        )

    def get_movie_artwork(
        self,
        *,
        tmdb_id,
    ):
        self.requests.append(
            tmdb_id
        )

        if self.error is not None:
            raise self.error

        return TMDBMovieArtwork(
            tmdb_id=tmdb_id,
            poster=(
                _asset(
                    ArtworkKind.MOVIE_POSTER,
                    ArtworkSource.TMDB,
                    "tmdb-poster",
                )
                if self.poster
                else None
            ),
            background=(
                _asset(
                    ArtworkKind.MOVIE_BACKGROUND,
                    ArtworkSource.TMDB,
                    "tmdb-background",
                )
                if self.background
                else None
            ),
        )


class Primary:
    name = "fake"

    def find_sets(
        self,
        request,
    ):
        return []


def _target():
    return ArtworkTarget(
        name="Movies",
        library="Movies",
        media_type=MediaType.MOVIE,
        output_path=Path(
            "/tmp/movies"
        ),
    )


def test_tmdb_creates_fallback_movie_state():
    client = TMDB()

    result = (
        resolve_movie_tmdb_coverage(
            inventory=_inventory(),
            state=None,
            client=client,
        )
    )

    assert (
        result.path
        is MovieTMDBFallbackPath
        .FILLED_ALL
    )

    assert result.created
    assert result.gaps_filled == 2

    assert (
        result.state.poster.source
        is ArtworkSource.TMDB
    )

    assert (
        result.state.background.source
        is ArtworkSource.TMDB
    )

    assert (
        result.state.selected_set_id
        is None
    )

    assert (
        result.state.selected_set_source
        is None
    )


def test_tmdb_only_fills_missing_movie_slots():
    state = MovieArtworkState(
        title="Blade Runner",
        tmdb_id=78,
        imdb_id="tt0083658",
        poster=_asset(
            ArtworkKind.MOVIE_POSTER,
            ArtworkSource.MEDIUX,
            "mediux-poster",
        ),
        selected_set_id="set-1",
        selected_set_source=(
            ArtworkSource.MEDIUX
        ),
    )

    result = (
        resolve_movie_tmdb_coverage(
            inventory=_inventory(),
            state=state,
            client=TMDB(),
        )
    )

    assert result.gaps_before == 1
    assert result.gaps_filled == 1

    assert (
        result.state.poster
        .provider_asset_id
        == "mediux-poster"
    )

    assert (
        result.state.background.source
        is ArtworkSource.TMDB
    )

    assert (
        result.state.selected_set_id
        == "set-1"
    )


def test_tmdb_no_artwork_does_not_create_identity_shell():
    result = (
        resolve_movie_tmdb_coverage(
            inventory=_inventory(),
            state=None,
            client=TMDB(
                poster=False,
                background=False,
            ),
        )
    )

    assert (
        result.path
        is MovieTMDBFallbackPath
        .NO_ARTWORK
    )

    assert result.state is None
    assert not result.created


def test_tmdb_resolves_movie_through_imdb_when_needed():
    client = TMDB(
        resolved_tmdb_id=78
    )

    result = (
        resolve_movie_tmdb_coverage(
            inventory=_inventory(
                tmdb_id=None,
            ),
            state=None,
            client=client,
        )
    )

    assert result.state is not None
    assert result.state.tmdb_id == 78

    assert len(
        client.resolutions
    ) == 1

    assert result.request_count == 2


def test_tmdb_provider_error_preserves_existing_state():
    state = MovieArtworkState(
        title="Blade Runner",
        tmdb_id=78,
        poster=_asset(
            ArtworkKind.MOVIE_POSTER,
            ArtworkSource.MEDIUX,
            "mediux-poster",
        ),
    )

    result = (
        resolve_movie_tmdb_coverage(
            inventory=_inventory(),
            state=state,
            client=TMDB(
                error=RuntimeError(
                    "boom"
                )
            ),
        )
    )

    assert (
        result.path
        is MovieTMDBFallbackPath
        .PROVIDER_ERROR
    )

    assert result.state == state
    assert (
        result.provider_error_count
        == 1
    )


def test_movie_target_uses_tmdb_after_primary_miss():
    execution = (
        execute_movie_target(
            target=_target(),
            inventories=[
                _inventory()
            ],
            managed_items=[],
            provider=Primary(),
            tmdb_client=TMDB(),
        )
    )

    assert execution.coverage_enabled

    assert (
        execution.tmdb_created_count
        == 1
    )

    assert (
        execution.tmdb_changed_count
        == 1
    )

    assert (
        execution.tmdb_request_count
        == 1
    )

    assert len(
        execution.resolved_items
    ) == 1

    _, state = (
        execution.resolved_items[0]
    )

    assert (
        state.poster.source
        is ArtworkSource.TMDB
    )
