"""TMDB fallback coverage for movie artwork."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import Enum

from artwork.models import (
    MovieArtworkState,
)
from artwork.movie_inventory import (
    MovieInventory,
)
from artwork.providers.tmdb import (
    TMDBArtworkClient,
)


class MovieTMDBFallbackPath(
    str,
    Enum,
):
    NO_GAPS = "no_gaps"
    NO_TMDB_ID = "no_tmdb_id"
    IDENTITY_MISMATCH = "identity_mismatch"
    FILLED_ALL = "filled_all"
    FILLED_PARTIAL = "filled_partial"
    NO_ARTWORK = "no_artwork"
    PROVIDER_ERROR = "provider_error"
    SKIPPED_MISSING_SET_CONTEXT = (
        "skipped_missing_set_context"
    )


@dataclass(frozen=True)
class MovieTMDBFallbackResult:
    """Result of one movie's TMDB fallback stage."""

    inventory: MovieInventory
    initial_state: MovieArtworkState | None
    state: MovieArtworkState | None

    path: MovieTMDBFallbackPath

    gaps_before: int
    gaps_filled: int
    gaps_remaining: int

    request_count: int = 0

    error_type: str | None = None
    error_message: str | None = None

    @property
    def changed(
        self,
    ) -> bool:
        return self.gaps_filled > 0

    @property
    def created(
        self,
    ) -> bool:
        return (
            self.initial_state is None
            and self.state is not None
        )

    @property
    def provider_error_count(
        self,
    ) -> int:
        return int(
            self.error_type is not None
        )


def _available(
    asset,
) -> bool:
    return bool(
        asset is not None
        and asset.available
    )


def _missing_count(
    state: MovieArtworkState | None,
) -> int:
    if state is None:
        return 2

    return (
        int(
            not _available(
                state.poster
            )
        )
        + int(
            not _available(
                state.background
            )
        )
    )


def skip_movie_tmdb_missing_set_context(
    *,
    inventory: MovieInventory,
    state: MovieArtworkState,
) -> MovieTMDBFallbackResult:
    """Preserve unsafe managed state without trying to repair it."""

    gaps = _missing_count(
        state
    )

    return MovieTMDBFallbackResult(
        inventory=inventory,
        initial_state=state,
        state=state,
        path=(
            MovieTMDBFallbackPath
            .SKIPPED_MISSING_SET_CONTEXT
        ),
        gaps_before=gaps,
        gaps_filled=0,
        gaps_remaining=gaps,
    )


def resolve_movie_tmdb_coverage(
    *,
    inventory: MovieInventory,
    state: MovieArtworkState | None,
    client: TMDBArtworkClient,
) -> MovieTMDBFallbackResult:
    """Fill only missing movie poster/background slots with TMDB."""

    gaps_before = _missing_count(
        state
    )

    if gaps_before == 0:
        return MovieTMDBFallbackResult(
            inventory=inventory,
            initial_state=state,
            state=state,
            path=(
                MovieTMDBFallbackPath
                .NO_GAPS
            ),
            gaps_before=0,
            gaps_filled=0,
            gaps_remaining=0,
        )

    identity = inventory.identity

    state_tmdb_id = (
        state.tmdb_id
        if state is not None
        else None
    )

    plex_tmdb_id = (
        identity.tmdb_id
    )

    if (
        state_tmdb_id is not None
        and plex_tmdb_id is not None
        and state_tmdb_id
        != plex_tmdb_id
    ):
        return MovieTMDBFallbackResult(
            inventory=inventory,
            initial_state=state,
            state=state,
            path=(
                MovieTMDBFallbackPath
                .IDENTITY_MISMATCH
            ),
            gaps_before=gaps_before,
            gaps_filled=0,
            gaps_remaining=gaps_before,
        )

    tmdb_id = (
        state_tmdb_id
        if state_tmdb_id is not None
        else plex_tmdb_id
    )

    request_count = 0

    if tmdb_id is None:
        if not identity.imdb_id:
            return MovieTMDBFallbackResult(
                inventory=inventory,
                initial_state=state,
                state=state,
                path=(
                    MovieTMDBFallbackPath
                    .NO_TMDB_ID
                ),
                gaps_before=gaps_before,
                gaps_filled=0,
                gaps_remaining=gaps_before,
            )

        request_count += 1

        try:
            (
                tmdb_id,
                _resolution_source,
            ) = (
                client.resolve_movie_tmdb_id(
                    identity
                )
            )

        except Exception as exc:
            return MovieTMDBFallbackResult(
                inventory=inventory,
                initial_state=state,
                state=state,
                path=(
                    MovieTMDBFallbackPath
                    .PROVIDER_ERROR
                ),
                gaps_before=gaps_before,
                gaps_filled=0,
                gaps_remaining=gaps_before,
                request_count=request_count,
                error_type=(
                    type(exc).__name__
                ),
                error_message=str(
                    exc
                ),
            )

    if tmdb_id is None:
        return MovieTMDBFallbackResult(
            inventory=inventory,
            initial_state=state,
            state=state,
            path=(
                MovieTMDBFallbackPath
                .NO_TMDB_ID
            ),
            gaps_before=gaps_before,
            gaps_filled=0,
            gaps_remaining=gaps_before,
            request_count=request_count,
        )

    request_count += 1

    try:
        artwork = (
            client.get_movie_artwork(
                tmdb_id=tmdb_id
            )
        )

    except Exception as exc:
        return MovieTMDBFallbackResult(
            inventory=inventory,
            initial_state=state,
            state=state,
            path=(
                MovieTMDBFallbackPath
                .PROVIDER_ERROR
            ),
            gaps_before=gaps_before,
            gaps_filled=0,
            gaps_remaining=gaps_before,
            request_count=request_count,
            error_type=(
                type(exc).__name__
            ),
            error_message=str(
                exc
            ),
        )

    working = (
        deepcopy(
            state
        )
        if state is not None
        else MovieArtworkState(
            title=identity.title,
            tmdb_id=tmdb_id,
            imdb_id=identity.imdb_id,
        )
    )

    if working.tmdb_id is None:
        working.tmdb_id = tmdb_id

    if (
        working.imdb_id is None
        and identity.imdb_id
    ):
        working.imdb_id = (
            identity.imdb_id
        )

    filled = 0

    if (
        not _available(
            working.poster
        )
        and _available(
            artwork.poster
        )
    ):
        working.poster = artwork.poster
        filled += 1

    if (
        not _available(
            working.background
        )
        and _available(
            artwork.background
        )
    ):
        working.background = (
            artwork.background
        )
        filled += 1

    remaining = (
        gaps_before
        - filled
    )

    if (
        state is None
        and filled == 0
    ):
        resolved_state = None

    else:
        resolved_state = working

    if filled == gaps_before:
        path = (
            MovieTMDBFallbackPath
            .FILLED_ALL
        )

    elif filled > 0:
        path = (
            MovieTMDBFallbackPath
            .FILLED_PARTIAL
        )

    else:
        path = (
            MovieTMDBFallbackPath
            .NO_ARTWORK
        )

    return MovieTMDBFallbackResult(
        inventory=inventory,
        initial_state=state,
        state=resolved_state,
        path=path,
        gaps_before=gaps_before,
        gaps_filled=filled,
        gaps_remaining=remaining,
        request_count=request_count,
    )
