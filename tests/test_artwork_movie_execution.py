from pathlib import Path

from artwork.models import (
    ArtworkAsset,
    ArtworkKind,
    ArtworkSet,
    ArtworkSource,
    MovieArtworkState,
    SelectionMode,
)
from artwork.movie_execution import (
    MovieExecutionPath,
    discover_movie,
    execute_managed_movie,
    execute_movie_target,
)
from artwork.movie_inventory import (
    MovieIdentity,
    MovieInventory,
)
from artwork.movie_reconciliation import (
    reconcile_movie_target,
)
from artwork.movie_state_store import (
    StoredMovieArtworkState,
)
from artwork.policy import (
    SetAction,
)
from artwork.targets import (
    ArtworkTarget,
    MediaType,
)


def _target():
    return ArtworkTarget(
        name="movies",
        library="Movies",
        media_type=MediaType.MOVIE,
        output_path=Path(
            "/tmp/movies"
        ),
    )


def _inventory(
    *,
    rating_key="123",
    title="Blade Runner",
    tmdb_id=78,
    imdb_id="tt0083658",
):
    return MovieInventory(
        identity=MovieIdentity(
            title=title,
            year=1982,
            library="Movies",
            plex_rating_key=rating_key,
            tmdb_id=tmdb_id,
            imdb_id=imdb_id,
        )
    )


def _asset(
    kind,
    asset_id,
    *,
    source=ArtworkSource.MEDIUX,
):
    return ArtworkAsset(
        kind=kind,
        source=source,
        provider_asset_id=asset_id,
    )


def _set(
    set_id,
    *,
    poster=True,
    background=False,
):
    return ArtworkSet(
        provider=ArtworkSource.MEDIUX,
        set_id=set_id,
        creator="creator",
        poster=(
            _asset(
                ArtworkKind.MOVIE_POSTER,
                f"{set_id}-poster",
            )
            if poster
            else None
        ),
        background=(
            _asset(
                ArtworkKind.MOVIE_BACKGROUND,
                f"{set_id}-background",
            )
            if background
            else None
        ),
    )


def _state(
    *,
    set_id="current",
    poster=True,
    background=False,
    source=ArtworkSource.MEDIUX,
    mode=SelectionMode.AUTO,
):
    return MovieArtworkState(
        title="Blade Runner",
        tmdb_id=78,
        imdb_id="tt0083658",
        poster=(
            _asset(
                ArtworkKind.MOVIE_POSTER,
                "stored-poster",
                source=source,
            )
            if poster
            else None
        ),
        background=(
            _asset(
                ArtworkKind.MOVIE_BACKGROUND,
                "stored-background",
                source=source,
            )
            if background
            else None
        ),
        selected_set_id=set_id,
        selected_set_source=(
            source
            if set_id is not None
            else None
        ),
        selected_creator=(
            "creator"
            if set_id is not None
            else None
        ),
        selection_mode=mode,
    )


class Provider:
    name = "fake"

    def __init__(
        self,
        sets,
    ):
        self.sets = sets
        self.requests = []

    def find_sets(
        self,
        request,
    ):
        self.requests.append(
            request
        )

        return list(
            self.sets
        )


def test_movie_reconciliation_matches_rating_key():
    inventory = _inventory()

    stored = StoredMovieArtworkState(
        plex_rating_key="123",
        state=_state(),
    )

    result = reconcile_movie_target(
        target=_target(),
        inventories=[inventory],
        managed_items=[stored],
    )

    assert result.managed_movie_count == 1
    assert result.unmanaged_movie_count == 0

    assert (
        result.matched[0]
        .inventory
        .identity
        .plex_rating_key
        == "123"
    )


def test_movie_reconciliation_reports_missing_and_orphan():
    missing = _inventory(
        rating_key="1",
        title="Unknown",
        tmdb_id=None,
        imdb_id=None,
    )

    orphan = StoredMovieArtworkState(
        plex_rating_key="999",
        state=_state(),
    )

    result = reconcile_movie_target(
        target=_target(),
        inventories=[missing],
        managed_items=[orphan],
    )

    assert result.missing_identity_count == 1
    assert result.orphaned_movie_count == 1


def test_movie_discovery_selects_best_presentation():
    provider = Provider(
        [
            _set(
                "poster-only",
                poster=True,
                background=False,
            ),
            _set(
                "complete",
                poster=True,
                background=True,
            ),
        ]
    )

    result = discover_movie(
        inventory=_inventory(),
        provider=provider,
    )

    assert (
        result.path
        is MovieExecutionPath.DISCOVERED
    )

    assert (
        result.action
        is SetAction.SELECT_SET
    )

    assert (
        result.state.selected_set_id
        == "complete"
    )

    assert (
        provider.requests[0]
        .media_type
        is MediaType.MOVIE
    )


def test_movie_discovery_handles_no_candidates():
    result = discover_movie(
        inventory=_inventory(),
        provider=Provider([]),
    )

    assert (
        result.path
        is MovieExecutionPath.NO_CANDIDATES
    )

    assert result.state is None


def test_managed_movie_refreshes_same_set():
    current = _state(
        set_id="current",
        poster=True,
        background=False,
    )

    provider = Provider(
        [
            _set(
                "current",
                poster=True,
                background=True,
            )
        ]
    )

    result = execute_managed_movie(
        inventory=_inventory(),
        current_state=current,
        provider=provider,
    )

    assert (
        result.path
        is MovieExecutionPath.REFRESHED
    )

    assert (
        result.action
        is SetAction.SET_REFRESH
    )

    assert result.state.background is not None

    assert (
        result.state.poster.provider_asset_id
        == "stored-poster"
    )


def test_managed_movie_migrates_to_stronger_set():
    current = _state(
        set_id="current",
        poster=True,
        background=False,
    )

    provider = Provider(
        [
            _set(
                "current",
                poster=True,
                background=False,
            ),
            _set(
                "better",
                poster=True,
                background=True,
            ),
        ]
    )

    result = execute_managed_movie(
        inventory=_inventory(),
        current_state=current,
        provider=provider,
    )

    assert (
        result.path
        is MovieExecutionPath.MIGRATED
    )

    assert (
        result.action
        is SetAction.SET_MIGRATION
    )

    assert (
        result.state.selected_set_id
        == "better"
    )


def test_equal_challenger_keeps_current_set():
    current = _state(
        set_id="current",
        poster=True,
        background=True,
    )

    provider = Provider(
        [
            _set(
                "current",
                poster=True,
                background=True,
            ),
            _set(
                "equal",
                poster=True,
                background=True,
            ),
        ]
    )

    result = execute_managed_movie(
        inventory=_inventory(),
        current_state=current,
        provider=provider,
    )

    assert (
        result.state.selected_set_id
        == "current"
    )

    assert (
        result.action
        is not SetAction.SET_MIGRATION
    )


def test_locked_movie_never_migrates():
    current = _state(
        set_id="current",
        poster=True,
        background=False,
        mode=SelectionMode.LOCKED,
    )

    provider = Provider(
        [
            _set(
                "current",
                poster=True,
                background=False,
            ),
            _set(
                "better",
                poster=True,
                background=True,
            ),
        ]
    )

    result = execute_managed_movie(
        inventory=_inventory(),
        current_state=current,
        provider=provider,
    )

    assert (
        result.state.selected_set_id
        == "current"
    )

    assert (
        result.action
        is not SetAction.SET_MIGRATION
    )


def test_fallback_movie_upgrades_to_primary():
    current = MovieArtworkState(
        title="Blade Runner",
        tmdb_id=78,
        imdb_id="tt0083658",
        poster=_asset(
            ArtworkKind.MOVIE_POSTER,
            "tmdb-poster",
            source=ArtworkSource.TMDB,
        ),
    )

    provider = Provider(
        [
            _set(
                "mediux",
                poster=True,
                background=False,
            )
        ]
    )

    result = execute_managed_movie(
        inventory=_inventory(),
        current_state=current,
        provider=provider,
    )

    assert (
        result.path
        is MovieExecutionPath.MIGRATED
    )

    assert (
        result.state.selected_set_source
        is ArtworkSource.MEDIUX
    )


def test_movie_target_returns_resolved_items():
    provider = Provider(
        [
            _set(
                "complete",
                poster=True,
                background=True,
            )
        ]
    )

    execution = execute_movie_target(
        target=_target(),
        inventories=[
            _inventory()
        ],
        managed_items=[],
        provider=provider,
    )

    assert len(
        execution.resolved_items
    ) == 1

    inventory, state = (
        execution.resolved_items[0]
    )

    assert (
        inventory.identity.tmdb_id
        == 78
    )

    assert (
        state.selected_set_id
        == "complete"
    )
