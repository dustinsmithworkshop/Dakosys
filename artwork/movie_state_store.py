"""Durable semantic state for Artwork Manager movie libraries."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from artwork.models import (
    ArtworkAsset,
    ArtworkKind,
    ArtworkQuality,
    ArtworkSource,
    MovieArtworkState,
    SelectionMode,
)
from artwork.state_store import (
    STATE_NAME,
    STATE_SCHEMA_VERSION,
    ArtworkStateStoreError,
    InvalidArtworkStateStoreError,
)


@dataclass(frozen=True)
class StoredMovieArtworkState:
    """One Plex movie and its normalized durable artwork state."""

    plex_rating_key: str
    state: MovieArtworkState


@dataclass(frozen=True)
class MovieArtworkStateStore:
    """Complete durable semantic state for one Plex movie library."""

    library: str
    items: tuple[
        StoredMovieArtworkState,
        ...,
    ]

    @property
    def states(
        self,
    ) -> tuple[
        MovieArtworkState,
        ...,
    ]:
        return tuple(
            item.state
            for item in self.items
        )

    def to_dict(
        self,
    ) -> dict:
        return {
            "schema_version":
                STATE_SCHEMA_VERSION,
            "media_type":
                "movie",
            "library":
                self.library,
            "items": {
                item.plex_rating_key:
                    _state_to_dict(
                        item.state
                    )
                for item
                in self.items
            },
        }

    def to_json(
        self,
    ) -> str:
        return (
            json.dumps(
                self.to_dict(),
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
            + "\n"
        )


def _optional_string(
    value,
    *,
    field: str,
) -> str | None:
    if value is None:
        return None

    if not isinstance(
        value,
        str,
    ):
        raise InvalidArtworkStateStoreError(
            f"{field} must be a string or null"
        )

    return value


def _positive_int_or_none(
    value,
    *,
    field: str,
) -> int | None:
    if value is None:
        return None

    if (
        not isinstance(
            value,
            int,
        )
        or isinstance(
            value,
            bool,
        )
        or value <= 0
    ):
        raise InvalidArtworkStateStoreError(
            f"{field} must be a positive integer or null"
        )

    return value


def _enum_value(
    enum_type,
    value,
    *,
    field: str,
):
    try:
        return enum_type(
            value
        )

    except (
        TypeError,
        ValueError,
    ) as exc:
        raise InvalidArtworkStateStoreError(
            f"invalid {field}: {value!r}"
        ) from exc


def _optional_enum_value(
    enum_type,
    value,
    *,
    field: str,
):
    if value is None:
        return None

    return _enum_value(
        enum_type,
        value,
        field=field,
    )


def _asset_to_dict(
    asset: ArtworkAsset | None,
) -> dict | None:
    if asset is None:
        return None

    return {
        "kind":
            asset.kind.value,
        "source":
            asset.source.value,
        "url":
            asset.url,
        "provider_asset_id":
            asset.provider_asset_id,
        "quality": (
            asset.quality.value
            if asset.quality is not None
            else None
        ),
    }


def _asset_from_dict(
    raw,
    *,
    expected_kind: ArtworkKind,
    field: str,
) -> ArtworkAsset | None:
    if raw is None:
        return None

    if not isinstance(
        raw,
        dict,
    ):
        raise InvalidArtworkStateStoreError(
            f"{field} must be an object or null"
        )

    kind = _enum_value(
        ArtworkKind,
        raw.get(
            "kind"
        ),
        field=f"{field}.kind",
    )

    if kind is not expected_kind:
        raise InvalidArtworkStateStoreError(
            f"{field} has wrong artwork kind "
            f"{kind.value!r}"
        )

    return ArtworkAsset(
        kind=kind,
        source=_enum_value(
            ArtworkSource,
            raw.get(
                "source"
            ),
            field=f"{field}.source",
        ),
        url=_optional_string(
            raw.get(
                "url"
            ),
            field=f"{field}.url",
        ),
        provider_asset_id=(
            _optional_string(
                raw.get(
                    "provider_asset_id"
                ),
                field=(
                    f"{field}."
                    "provider_asset_id"
                ),
            )
        ),
        quality=(
            _optional_enum_value(
                ArtworkQuality,
                raw.get(
                    "quality"
                ),
                field=f"{field}.quality",
            )
        ),
    )


def _state_to_dict(
    state: MovieArtworkState,
) -> dict:
    return {
        "title":
            state.title,
        "tmdb_id":
            state.tmdb_id,
        "imdb_id":
            state.imdb_id,
        "poster":
            _asset_to_dict(
                state.poster
            ),
        "background":
            _asset_to_dict(
                state.background
            ),
        "selected_set_id":
            state.selected_set_id,
        "selected_set_source": (
            state.selected_set_source.value
            if (
                state.selected_set_source
                is not None
            )
            else None
        ),
        "selected_creator":
            state.selected_creator,
        "selection_mode":
            state.selection_mode.value,
    }


def _state_from_dict(
    raw,
    *,
    field: str,
) -> MovieArtworkState:
    if not isinstance(
        raw,
        dict,
    ):
        raise InvalidArtworkStateStoreError(
            f"{field} must be an object"
        )

    return MovieArtworkState(
        title=_optional_string(
            raw.get(
                "title"
            ),
            field=f"{field}.title",
        ),
        tmdb_id=_positive_int_or_none(
            raw.get(
                "tmdb_id"
            ),
            field=f"{field}.tmdb_id",
        ),
        imdb_id=_optional_string(
            raw.get(
                "imdb_id"
            ),
            field=f"{field}.imdb_id",
        ),
        poster=_asset_from_dict(
            raw.get(
                "poster"
            ),
            expected_kind=(
                ArtworkKind.MOVIE_POSTER
            ),
            field=f"{field}.poster",
        ),
        background=_asset_from_dict(
            raw.get(
                "background"
            ),
            expected_kind=(
                ArtworkKind.MOVIE_BACKGROUND
            ),
            field=f"{field}.background",
        ),
        selected_set_id=(
            _optional_string(
                raw.get(
                    "selected_set_id"
                ),
                field=(
                    f"{field}."
                    "selected_set_id"
                ),
            )
        ),
        selected_set_source=(
            _optional_enum_value(
                ArtworkSource,
                raw.get(
                    "selected_set_source"
                ),
                field=(
                    f"{field}."
                    "selected_set_source"
                ),
            )
        ),
        selected_creator=(
            _optional_string(
                raw.get(
                    "selected_creator"
                ),
                field=(
                    f"{field}."
                    "selected_creator"
                ),
            )
        ),
        selection_mode=_enum_value(
            SelectionMode,
            raw.get(
                "selection_mode",
                SelectionMode.AUTO.value,
            ),
            field=(
                f"{field}."
                "selection_mode"
            ),
        ),
    )


def build_movie_state_store(
    *,
    library: str,
    items,
) -> MovieArtworkStateStore:
    """Build normalized movie state from Plex-key/state pairs."""

    normalized = []

    seen_rating_keys = set()

    for (
        raw_rating_key,
        state,
    ) in items:
        rating_key = str(
            raw_rating_key
        ).strip()

        if not rating_key:
            raise ArtworkStateStoreError(
                "movie artwork state has "
                "an empty Plex rating key"
            )

        if rating_key in seen_rating_keys:
            raise ArtworkStateStoreError(
                "duplicate movie artwork "
                f"Plex rating key {rating_key!r}"
            )

        if not isinstance(
            state,
            MovieArtworkState,
        ):
            raise ArtworkStateStoreError(
                "movie artwork state contains "
                "an invalid state object"
            )

        seen_rating_keys.add(
            rating_key
        )

        normalized.append(
            StoredMovieArtworkState(
                plex_rating_key=rating_key,
                state=state,
            )
        )

    normalized.sort(
        key=lambda item:
            item.plex_rating_key
    )

    return MovieArtworkStateStore(
        library=str(
            library
        ),
        items=tuple(
            normalized
        ),
    )


def load_movie_state_store(
    directory: str | Path,
    *,
    expected_library: str,
) -> MovieArtworkStateStore | None:
    """Read and validate one existing movie semantic state sidecar."""

    path = (
        Path(
            directory
        )
        / STATE_NAME
    )

    if not path.exists():
        return None

    try:
        raw = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise InvalidArtworkStateStoreError(
            "could not read Artwork Manager "
            "movie durable state"
        ) from exc

    if not isinstance(
        raw,
        dict,
    ):
        raise InvalidArtworkStateStoreError(
            "Artwork Manager movie durable "
            "state must contain an object"
        )

    if (
        raw.get(
            "schema_version"
        )
        != STATE_SCHEMA_VERSION
    ):
        raise InvalidArtworkStateStoreError(
            "unsupported Artwork Manager "
            "movie state schema version"
        )

    if (
        raw.get(
            "media_type"
        )
        != "movie"
    ):
        raise InvalidArtworkStateStoreError(
            "Artwork Manager durable state "
            "is not a movie state store"
        )

    library = raw.get(
        "library"
    )

    if library != expected_library:
        raise InvalidArtworkStateStoreError(
            "Artwork Manager movie durable "
            "state belongs to a different "
            f"library: {library!r}"
        )

    raw_items = raw.get(
        "items"
    )

    if not isinstance(
        raw_items,
        dict,
    ):
        raise InvalidArtworkStateStoreError(
            "Artwork Manager movie durable "
            "state items must be a mapping"
        )

    items = []

    for (
        raw_rating_key,
        raw_state,
    ) in raw_items.items():
        rating_key = str(
            raw_rating_key
        ).strip()

        if not rating_key:
            raise InvalidArtworkStateStoreError(
                "movie durable state contains "
                "an empty Plex rating key"
            )

        items.append(
            StoredMovieArtworkState(
                plex_rating_key=rating_key,
                state=_state_from_dict(
                    raw_state,
                    field=(
                        f"items[{rating_key!r}]"
                    ),
                ),
            )
        )

    items.sort(
        key=lambda item:
            item.plex_rating_key
    )

    return MovieArtworkStateStore(
        library=expected_library,
        items=tuple(
            items
        ),
    )
