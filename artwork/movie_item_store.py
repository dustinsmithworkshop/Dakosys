"""Read-only per-movie Artwork Manager item-store planning."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import unicodedata

from artwork.item_store import (
    MANIFEST_NAME,
    MANIFEST_SCHEMA_VERSION,
    ItemStoreCollisionError,
    ItemStoreError,
    InvalidItemStoreManifestError,
)
from artwork.movie_inventory import (
    MovieInventory,
)
from artwork.movie_kometa import (
    movie_mapping_id,
    render_movie_kometa_metadata,
)
from artwork.movie_state_store import (
    MovieArtworkStateStore,
    build_movie_state_store,
    load_movie_state_store,
)
from artwork.models import (
    MovieArtworkState,
)
from artwork.state_store import (
    STATE_NAME,
)


_TITLE_SLUG_MAX_BYTES = 120

_APOSTROPHES = frozenset(
    {
        "'",
        "’",
        "‘",
        "ʼ",
    }
)


def _truncate_utf8(
    value: str,
    *,
    max_bytes: int,
) -> str:
    encoded = value.encode(
        "utf-8"
    )

    if len(encoded) <= max_bytes:
        return value

    return (
        encoded[:max_bytes]
        .decode(
            "utf-8",
            errors="ignore",
        )
    )


def _movie_title_slug(
    title: str,
) -> str:
    normalized = (
        unicodedata.normalize(
            "NFKC",
            str(
                title
                or ""
            ),
        )
        .casefold()
        .strip()
    )

    normalized = normalized.replace(
        "&",
        " and ",
    )

    characters = []
    separator_pending = False

    for character in normalized:
        if character in _APOSTROPHES:
            continue

        if character.isalnum():
            if (
                separator_pending
                and characters
            ):
                characters.append(
                    "-"
                )

            characters.append(
                character
            )

            separator_pending = False

        else:
            separator_pending = True

    slug = "".join(
        characters
    ).strip(
        "-"
    )

    if not slug:
        slug = "movie"

    slug = (
        _truncate_utf8(
            slug,
            max_bytes=(
                _TITLE_SLUG_MAX_BYTES
            ),
        )
        .rstrip(
            "-"
        )
    )

    return slug or "movie"


def movie_item_filename(
    *,
    title: str,
    tmdb_id: int | None = None,
    imdb_id: str | None = None,
) -> str:
    """Return a deterministic human-readable movie item filename."""

    slug = _movie_title_slug(
        title
    )

    if (
        isinstance(
            tmdb_id,
            int,
        )
        and not isinstance(
            tmdb_id,
            bool,
        )
        and tmdb_id > 0
    ):
        return (
            f"{slug}"
            f"--tmdb-{tmdb_id}.yaml"
        )

    if isinstance(
        imdb_id,
        str,
    ):
        normalized_imdb = (
            imdb_id
            .strip()
            .casefold()
        )

        if (
            len(
                normalized_imdb
            ) > 2
            and normalized_imdb
            .startswith(
                "tt"
            )
            and normalized_imdb[
                2:
            ].isdigit()
        ):
            return (
                f"{slug}"
                f"--imdb-"
                f"{normalized_imdb}"
                ".yaml"
            )

    raise ValueError(
        "movie item filename requires "
        "a valid TMDB or IMDb identity"
    )


def _sha256_bytes(
    value: bytes,
) -> str:
    return sha256(
        value
    ).hexdigest()


def _sha256_text(
    value: str,
) -> str:
    return _sha256_bytes(
        value.encode(
            "utf-8"
        )
    )


def _valid_sha256(
    value,
) -> bool:
    if not isinstance(
        value,
        str,
    ):
        return False

    if len(value) != 64:
        return False

    return all(
        character
        in "0123456789abcdef"
        for character
        in value
    )


def _validate_filename(
    value,
) -> str:
    if not isinstance(
        value,
        str,
    ):
        raise InvalidItemStoreManifestError(
            "movie manifest item filename "
            "must be a string"
        )

    filename = value.strip()

    if (
        not filename
        or filename != Path(
            filename
        ).name
        or Path(
            filename
        ).suffix.casefold()
        not in {
            ".yaml",
            ".yml",
        }
    ):
        raise InvalidItemStoreManifestError(
            "movie manifest contains "
            "unsafe item filename "
            f"{value!r}"
        )

    return filename


def _validate_mapping_id(
    value,
) -> int | str:
    if (
        isinstance(
            value,
            int,
        )
        and not isinstance(
            value,
            bool,
        )
        and value > 0
    ):
        return value

    if isinstance(
        value,
        str,
    ):
        normalized = (
            value
            .strip()
            .casefold()
        )

        if (
            len(normalized) > 2
            and normalized.startswith(
                "tt"
            )
            and normalized[
                2:
            ].isdigit()
        ):
            return normalized

    raise InvalidItemStoreManifestError(
        "movie manifest contains "
        f"invalid mapping ID {value!r}"
    )


@dataclass(frozen=True)
class MovieItemStoreManifestEntry:
    """One Dakosys-owned movie output file."""

    plex_rating_key: str
    mapping_id: int | str
    filename: str
    sha256: str


@dataclass(frozen=True)
class MovieItemStoreManifest:
    """Ownership manifest for one movie Artwork Manager library."""

    library: str

    items: tuple[
        MovieItemStoreManifestEntry,
        ...,
    ]

    def to_dict(
        self,
    ) -> dict:
        return {
            "schema_version":
                MANIFEST_SCHEMA_VERSION,
            "media_type":
                "movie",
            "library":
                self.library,
            "items": {
                entry.plex_rating_key: {
                    "mapping_id":
                        entry.mapping_id,
                    "file":
                        entry.filename,
                    "sha256":
                        entry.sha256,
                }
                for entry
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


@dataclass(frozen=True)
class MovieItemStoreFile:
    """One fully rendered desired movie metadata file."""

    plex_rating_key: str
    mapping_id: int | str
    filename: str
    sha256: str
    contents: str


@dataclass(frozen=True)
class MovieItemStorePlan:
    """Read-only filesystem plan for a movie library."""

    library: str
    directory: Path

    files: tuple[
        MovieItemStoreFile,
        ...,
    ]

    manifest: MovieItemStoreManifest

    state_store: MovieArtworkStateStore

    added: tuple[str, ...]
    updated: tuple[str, ...]
    unchanged: tuple[str, ...]
    removed: tuple[str, ...]

    preserved_unowned: tuple[
        str,
        ...,
    ]

    @property
    def manifest_path(
        self,
    ) -> Path:
        return (
            self.directory
            / MANIFEST_NAME
        )

    @property
    def state_path(
        self,
    ) -> Path:
        return (
            self.directory
            / STATE_NAME
        )

    @property
    def desired_count(
        self,
    ) -> int:
        return len(
            self.files
        )

    @property
    def added_count(
        self,
    ) -> int:
        return len(
            self.added
        )

    @property
    def updated_count(
        self,
    ) -> int:
        return len(
            self.updated
        )

    @property
    def unchanged_count(
        self,
    ) -> int:
        return len(
            self.unchanged
        )

    @property
    def removed_count(
        self,
    ) -> int:
        return len(
            self.removed
        )

    @property
    def write_count(
        self,
    ) -> int:
        return (
            self.added_count
            + self.updated_count
        )


def load_movie_item_store_manifest(
    directory: str | Path,
    *,
    expected_library: str,
) -> MovieItemStoreManifest | None:
    """Read and validate one movie ownership manifest."""

    path = (
        Path(
            directory
        )
        / MANIFEST_NAME
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
        raise InvalidItemStoreManifestError(
            "could not read Artwork Manager "
            "movie item-store manifest"
        ) from exc

    if not isinstance(
        raw,
        dict,
    ):
        raise InvalidItemStoreManifestError(
            "Artwork Manager movie manifest "
            "must contain an object"
        )

    if (
        raw.get(
            "schema_version"
        )
        != MANIFEST_SCHEMA_VERSION
    ):
        raise InvalidItemStoreManifestError(
            "unsupported Artwork Manager "
            "movie manifest schema version"
        )

    if (
        raw.get(
            "media_type"
        )
        != "movie"
    ):
        raise InvalidItemStoreManifestError(
            "Artwork Manager manifest "
            "is not a movie manifest"
        )

    library = raw.get(
        "library"
    )

    if library != expected_library:
        raise InvalidItemStoreManifestError(
            "Artwork Manager movie manifest "
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
        raise InvalidItemStoreManifestError(
            "Artwork Manager movie manifest "
            "items must be a mapping"
        )

    entries = []
    filenames = set()
    mapping_ids = set()

    for (
        raw_rating_key,
        raw_entry,
    ) in raw_items.items():
        rating_key = str(
            raw_rating_key
        ).strip()

        if not rating_key:
            raise InvalidItemStoreManifestError(
                "movie manifest contains "
                "empty Plex rating key"
            )

        if not isinstance(
            raw_entry,
            dict,
        ):
            raise InvalidItemStoreManifestError(
                "movie manifest item must "
                "contain an object"
            )

        mapping_id = (
            _validate_mapping_id(
                raw_entry.get(
                    "mapping_id"
                )
            )
        )

        filename = (
            _validate_filename(
                raw_entry.get(
                    "file"
                )
            )
        )

        digest = raw_entry.get(
            "sha256"
        )

        if not _valid_sha256(
            digest
        ):
            raise InvalidItemStoreManifestError(
                "movie manifest contains "
                "invalid SHA256 for "
                f"{filename!r}"
            )

        if filename in filenames:
            raise InvalidItemStoreManifestError(
                "movie manifest contains "
                "duplicate filename "
                f"{filename!r}"
            )

        if mapping_id in mapping_ids:
            raise InvalidItemStoreManifestError(
                "movie manifest contains "
                "duplicate mapping ID "
                f"{mapping_id!r}"
            )

        filenames.add(
            filename
        )

        mapping_ids.add(
            mapping_id
        )

        entries.append(
            MovieItemStoreManifestEntry(
                plex_rating_key=(
                    rating_key
                ),
                mapping_id=(
                    mapping_id
                ),
                filename=filename,
                sha256=digest,
            )
        )

    entries.sort(
        key=lambda entry:
            entry.plex_rating_key
    )

    return MovieItemStoreManifest(
        library=expected_library,
        items=tuple(
            entries
        ),
    )


def build_movie_item_store_plan(
    *,
    library: str,
    directory: str | Path,
    items: Iterable[
        tuple[
            MovieInventory,
            MovieArtworkState,
        ]
    ],
) -> MovieItemStorePlan:
    """Build a read-only per-movie persistence plan."""

    directory = Path(
        directory
    )

    if (
        directory.exists()
        and not directory.is_dir()
    ):
        raise ItemStoreCollisionError(
            "Artwork Manager movie "
            "item-store destination exists "
            "but is not a directory: "
            f"{directory}"
        )

    projected_items = tuple(
        items
    )

    files = []

    desired_filenames = set()
    desired_mapping_ids = set()
    desired_rating_keys = set()

    state_items = []

    for (
        inventory,
        state,
    ) in projected_items:
        identity = (
            inventory.identity
        )

        if identity.library != library:
            raise ItemStoreError(
                "movie inventory library "
                "does not match item-store "
                f"library: {identity.library!r}"
            )

        rating_key = str(
            identity.plex_rating_key
        ).strip()

        if not rating_key:
            raise ItemStoreError(
                "movie item-store contains "
                "an empty Plex rating key"
            )

        if rating_key in desired_rating_keys:
            raise ItemStoreError(
                "duplicate Plex rating key "
                "in movie item store: "
                f"{rating_key!r}"
            )

        mapping_id = (
            movie_mapping_id(
                state
            )
        )

        if mapping_id is None:
            raise ItemStoreError(
                "projected movie artwork "
                "state lacks TMDB/IMDb identity: "
                f"{identity.title!r}"
            )

        if mapping_id in desired_mapping_ids:
            raise ItemStoreError(
                "duplicate movie mapping "
                "identity in Artwork Manager "
                f"item store: {mapping_id!r}"
            )

        filename = (
            movie_item_filename(
                title=identity.title,
                tmdb_id=(
                    mapping_id
                    if isinstance(
                        mapping_id,
                        int,
                    )
                    else None
                ),
                imdb_id=(
                    mapping_id
                    if isinstance(
                        mapping_id,
                        str,
                    )
                    else None
                ),
            )
        )

        if filename in desired_filenames:
            raise ItemStoreError(
                "duplicate Artwork Manager "
                "movie item filename "
                f"{filename!r}"
            )

        contents = (
            render_movie_kometa_metadata(
                (
                    state,
                )
            )
        )

        digest = (
            _sha256_text(
                contents
            )
        )

        files.append(
            MovieItemStoreFile(
                plex_rating_key=(
                    rating_key
                ),
                mapping_id=(
                    mapping_id
                ),
                filename=filename,
                sha256=digest,
                contents=contents,
            )
        )

        state_items.append(
            (
                rating_key,
                state,
            )
        )

        desired_rating_keys.add(
            rating_key
        )

        desired_mapping_ids.add(
            mapping_id
        )

        desired_filenames.add(
            filename
        )

    files.sort(
        key=lambda item: (
            (
                0,
                item.mapping_id,
            )
            if isinstance(
                item.mapping_id,
                int,
            )
            else (
                1,
                item.mapping_id,
            )
        )
    )

    existing_manifest = (
        load_movie_item_store_manifest(
            directory,
            expected_library=library,
        )
    )

    existing_state_store = (
        load_movie_state_store(
            directory,
            expected_library=library,
        )
    )

    if (
        existing_state_store is not None
        and existing_manifest is None
    ):
        raise ItemStoreError(
            "Artwork Manager movie durable "
            "state exists without an "
            "ownership manifest"
        )

    if (
        existing_state_store is not None
        and existing_manifest is not None
    ):
        manifest_identities = {
            entry.plex_rating_key:
                entry.mapping_id
            for entry
            in existing_manifest.items
        }

        state_identities = {
            item.plex_rating_key:
                movie_mapping_id(
                    item.state
                )
            for item
            in existing_state_store.items
        }

        if (
            manifest_identities
            != state_identities
        ):
            raise ItemStoreError(
                "Artwork Manager movie "
                "ownership manifest and "
                "durable state disagree"
            )

    old_entries = (
        existing_manifest.items
        if existing_manifest
        is not None
        else ()
    )

    old_owned = {
        entry.filename:
            entry
        for entry
        in old_entries
    }

    existing_names = set()

    if directory.exists():
        existing_names = {
            entry.name
            for entry
            in directory.iterdir()
        }

    existing_names.discard(
        MANIFEST_NAME
    )

    existing_names.discard(
        STATE_NAME
    )

    unowned_names = (
        existing_names
        - set(
            old_owned
        )
    )

    collisions = sorted(
        desired_filenames
        & unowned_names
    )

    if collisions:
        formatted = ", ".join(
            repr(
                value
            )
            for value
            in collisions
        )

        raise ItemStoreCollisionError(
            "Artwork Manager would "
            "overwrite unowned movie "
            "item-store file(s): "
            f"{formatted}"
        )

    added = []
    updated = []
    unchanged = []

    for item in files:
        path = (
            directory
            / item.filename
        )

        if not path.exists():
            added.append(
                item.filename
            )
            continue

        if not path.is_file():
            raise ItemStoreCollisionError(
                "Artwork Manager owned "
                "movie path is not a "
                "regular file: "
                f"{path}"
            )

        actual_digest = (
            _sha256_bytes(
                path.read_bytes()
            )
        )

        if (
            actual_digest
            == item.sha256
        ):
            unchanged.append(
                item.filename
            )
        else:
            updated.append(
                item.filename
            )

    removed = sorted(
        set(
            old_owned
        )
        - desired_filenames
    )

    manifest = (
        MovieItemStoreManifest(
            library=library,
            items=tuple(
                sorted(
                    (
                        MovieItemStoreManifestEntry(
                            plex_rating_key=(
                                item
                                .plex_rating_key
                            ),
                            mapping_id=(
                                item
                                .mapping_id
                            ),
                            filename=(
                                item
                                .filename
                            ),
                            sha256=(
                                item
                                .sha256
                            ),
                        )
                        for item
                        in files
                    ),
                    key=lambda entry:
                        entry.plex_rating_key,
                )
            ),
        )
    )

    state_store = (
        build_movie_state_store(
            library=library,
            items=state_items,
        )
    )

    return MovieItemStorePlan(
        library=library,
        directory=directory,
        files=tuple(
            files
        ),
        manifest=manifest,
        state_store=state_store,
        added=tuple(
            sorted(
                added
            )
        ),
        updated=tuple(
            sorted(
                updated
            )
        ),
        unchanged=tuple(
            sorted(
                unchanged
            )
        ),
        removed=tuple(
            removed
        ),
        preserved_unowned=tuple(
            sorted(
                unowned_names
            )
        ),
    )
