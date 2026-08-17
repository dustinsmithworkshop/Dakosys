"""Durable semantic state for Artwork Manager item stores.

The Kometa YAML files are delivery documents, not Artwork Manager's
complete internal state.

This module persists the normalized artwork state required for future
provider reevaluation so subsequent runs do not depend on legacy
migration YAML.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import TYPE_CHECKING

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
from artwork.projection import (
    project_show_target_items,
)

if TYPE_CHECKING:
    from artwork.target_execution import (
        ShowTargetExecution,
    )


STATE_NAME = ".dakosys-state.json"
STATE_SCHEMA_VERSION = 1


class ArtworkStateStoreError(RuntimeError):
    """Base class for durable Artwork Manager state errors."""


class InvalidArtworkStateStoreError(
    ArtworkStateStoreError
):
    """Existing durable state is malformed or incompatible."""


@dataclass(frozen=True)
class StoredShowArtworkState:
    """One Plex item and its normalized durable artwork state."""

    plex_rating_key: str
    state: ShowArtworkState


@dataclass(frozen=True)
class ArtworkStateStore:
    """Complete durable semantic state for one Plex library."""

    library: str

    items: tuple[
        StoredShowArtworkState,
        ...,
    ]

    @property
    def states(
        self,
    ) -> tuple[
        ShowArtworkState,
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


def _nonnegative_int(
    value,
    *,
    field: str,
) -> int:
    try:
        result = int(value)
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise InvalidArtworkStateStoreError(
            f"{field} must be an integer"
        ) from exc

    if result < 0:
        raise InvalidArtworkStateStoreError(
            f"{field} cannot be negative"
        )

    return result


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

    source = _enum_value(
        ArtworkSource,
        raw.get(
            "source"
        ),
        field=f"{field}.source",
    )

    quality = _optional_enum_value(
        ArtworkQuality,
        raw.get(
            "quality"
        ),
        field=f"{field}.quality",
    )

    return ArtworkAsset(
        kind=kind,
        source=source,
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
        quality=quality,
    )


def _selection_to_dict(
    selection:
        ArtworkSetSelection | None,
) -> dict | None:
    if selection is None:
        return None

    return {
        "provider":
            selection.provider.value,
        "set_id":
            selection.set_id,
        "creator":
            selection.creator,
        "mode":
            selection.mode.value,
    }


def _selection_from_dict(
    raw,
    *,
    field: str,
) -> ArtworkSetSelection | None:
    if raw is None:
        return None

    if not isinstance(
        raw,
        dict,
    ):
        raise InvalidArtworkStateStoreError(
            f"{field} must be an object or null"
        )

    set_id = raw.get(
        "set_id"
    )

    if (
        not isinstance(
            set_id,
            str,
        )
        or not set_id.strip()
    ):
        raise InvalidArtworkStateStoreError(
            f"{field}.set_id must be a "
            "non-empty string"
        )

    return ArtworkSetSelection(
        provider=_enum_value(
            ArtworkSource,
            raw.get(
                "provider"
            ),
            field=f"{field}.provider",
        ),
        set_id=set_id,
        creator=_optional_string(
            raw.get(
                "creator"
            ),
            field=f"{field}.creator",
        ),
        mode=_enum_value(
            SelectionMode,
            raw.get(
                "mode",
                SelectionMode.AUTO.value,
            ),
            field=f"{field}.mode",
        ),
    )


def _state_to_dict(
    state: ShowArtworkState,
) -> dict:
    seasons = {}

    for (
        season_number,
        season,
    ) in sorted(
        state.seasons.items()
    ):
        episodes = {}

        for (
            episode_number,
            episode,
        ) in sorted(
            season.episodes.items()
        ):
            episodes[
                str(
                    episode_number
                )
            ] = {
                "card":
                    _asset_to_dict(
                        episode.card
                    ),
            }

        seasons[
            str(
                season_number
            )
        ] = {
            "poster":
                _asset_to_dict(
                    season.poster
                ),
            "episodes":
                episodes,
        }

    return {
        "title":
            state.title,
        "tvdb_id":
            state.tvdb_id,
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
        "seasons":
            seasons,
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
        "episode_selection":
            _selection_to_dict(
                state.episode_selection
            ),
        "presentation_selection":
            _selection_to_dict(
                state.presentation_selection
            ),
    }


def _state_from_dict(
    raw,
    *,
    field: str,
) -> ShowArtworkState:
    if not isinstance(
        raw,
        dict,
    ):
        raise InvalidArtworkStateStoreError(
            f"{field} must be an object"
        )

    tvdb_id = _positive_int_or_none(
        raw.get(
            "tvdb_id"
        ),
        field=f"{field}.tvdb_id",
    )

    if tvdb_id is None:
        raise InvalidArtworkStateStoreError(
            f"{field}.tvdb_id is required"
        )

    raw_seasons = (
        raw.get(
            "seasons"
        )
        or {}
    )

    if not isinstance(
        raw_seasons,
        dict,
    ):
        raise InvalidArtworkStateStoreError(
            f"{field}.seasons must be an object"
        )

    seasons = {}

    for (
        raw_season_number,
        raw_season,
    ) in raw_seasons.items():
        season_number = (
            _nonnegative_int(
                raw_season_number,
                field=(
                    f"{field}."
                    "season_number"
                ),
            )
        )

        if not isinstance(
            raw_season,
            dict,
        ):
            raise InvalidArtworkStateStoreError(
                f"{field}.seasons."
                f"{season_number} must be an object"
            )

        raw_episodes = (
            raw_season.get(
                "episodes"
            )
            or {}
        )

        if not isinstance(
            raw_episodes,
            dict,
        ):
            raise InvalidArtworkStateStoreError(
                f"{field}.seasons."
                f"{season_number}.episodes "
                "must be an object"
            )

        episodes = {}

        for (
            raw_episode_number,
            raw_episode,
        ) in raw_episodes.items():
            episode_number = (
                _nonnegative_int(
                    raw_episode_number,
                    field=(
                        f"{field}.seasons."
                        f"{season_number}."
                        "episode_number"
                    ),
                )
            )

            if not isinstance(
                raw_episode,
                dict,
            ):
                raise InvalidArtworkStateStoreError(
                    f"{field}.seasons."
                    f"{season_number}.episodes."
                    f"{episode_number} "
                    "must be an object"
                )

            episodes[
                episode_number
            ] = EpisodeArtwork(
                episode_number=(
                    episode_number
                ),
                card=_asset_from_dict(
                    raw_episode.get(
                        "card"
                    ),
                    expected_kind=(
                        ArtworkKind
                        .EPISODE_CARD
                    ),
                    field=(
                        f"{field}.seasons."
                        f"{season_number}."
                        f"episodes."
                        f"{episode_number}.card"
                    ),
                ),
            )

        seasons[
            season_number
        ] = SeasonArtwork(
            season_number=(
                season_number
            ),
            poster=_asset_from_dict(
                raw_season.get(
                    "poster"
                ),
                expected_kind=(
                    ArtworkKind
                    .SEASON_POSTER
                ),
                field=(
                    f"{field}.seasons."
                    f"{season_number}.poster"
                ),
            ),
            episodes=episodes,
        )

    return ShowArtworkState(
        title=_optional_string(
            raw.get(
                "title"
            ),
            field=f"{field}.title",
        ),
        tvdb_id=tvdb_id,
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
                ArtworkKind
                .SHOW_POSTER
            ),
            field=f"{field}.poster",
        ),
        background=_asset_from_dict(
            raw.get(
                "background"
            ),
            expected_kind=(
                ArtworkKind
                .SHOW_BACKGROUND
            ),
            field=f"{field}.background",
        ),
        seasons=seasons,
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
                f"{field}.selection_mode"
            ),
        ),
        episode_selection=(
            _selection_from_dict(
                raw.get(
                    "episode_selection"
                ),
                field=(
                    f"{field}."
                    "episode_selection"
                ),
            )
        ),
        presentation_selection=(
            _selection_from_dict(
                raw.get(
                    "presentation_selection"
                ),
                field=(
                    f"{field}."
                    "presentation_selection"
                ),
            )
        ),
    )


def build_show_state_store(
    execution: ShowTargetExecution,
) -> ArtworkStateStore:
    """Build durable semantic state from projected target output."""

    library = (
        execution
        .reconciliation
        .target
        .library
    )

    items = []

    for (
        inventory,
        state,
    ) in project_show_target_items(
        execution
    ):
        rating_key = str(
            inventory
            .identity
            .plex_rating_key
        ).strip()

        if not rating_key:
            raise ArtworkStateStoreError(
                "projected artwork state has "
                "an empty Plex rating key"
            )

        if state.tvdb_id is None:
            raise ArtworkStateStoreError(
                "projected artwork state lacks "
                f"TVDB identity: {state.title!r}"
            )

        items.append(
            StoredShowArtworkState(
                plex_rating_key=(
                    rating_key
                ),
                state=state,
            )
        )

    items.sort(
        key=lambda item: (
            item.plex_rating_key
        )
    )

    return ArtworkStateStore(
        library=library,
        items=tuple(
            items
        ),
    )


def load_show_state_store(
    directory: str | Path,
    *,
    expected_library: str,
) -> ArtworkStateStore | None:
    """Read and validate one existing semantic state sidecar."""

    directory = Path(
        directory
    )

    path = (
        directory
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
            "durable state"
        ) from exc

    if not isinstance(
        raw,
        dict,
    ):
        raise InvalidArtworkStateStoreError(
            "Artwork Manager durable state "
            "must contain an object"
        )

    if (
        raw.get(
            "schema_version"
        )
        != STATE_SCHEMA_VERSION
    ):
        raise InvalidArtworkStateStoreError(
            "unsupported Artwork Manager "
            "state schema version"
        )

    library = raw.get(
        "library"
    )

    if library != expected_library:
        raise InvalidArtworkStateStoreError(
            "Artwork Manager durable state "
            "belongs to a different library: "
            f"{library!r}"
        )

    raw_items = raw.get(
        "items"
    )

    if not isinstance(
        raw_items,
        dict,
    ):
        raise InvalidArtworkStateStoreError(
            "Artwork Manager durable state "
            "items must be a mapping"
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
                "durable state contains an "
                "empty Plex rating key"
            )

        items.append(
            StoredShowArtworkState(
                plex_rating_key=(
                    rating_key
                ),
                state=_state_from_dict(
                    raw_state,
                    field=(
                        f"items[{rating_key!r}]"
                    ),
                ),
            )
        )

    items.sort(
        key=lambda item: (
            item.plex_rating_key
        )
    )

    return ArtworkStateStore(
        library=expected_library,
        items=tuple(
            items
        ),
    )
