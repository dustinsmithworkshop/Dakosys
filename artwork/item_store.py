"""Per-item Artwork Manager output planning.

Artwork Manager persists one Kometa YAML document per Plex item.

The item-store manifest records exactly which files Dakosys owns.
Unknown files in the output directory are never silently adopted,
overwritten, or considered removable.

This module plans filesystem changes but does not mutate the filesystem.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import TYPE_CHECKING
import unicodedata

from artwork.kometa import (
    render_kometa_metadata,
)
from artwork.projection import (
    project_show_target_items,
)

if TYPE_CHECKING:
    from artwork.target_execution import (
        ShowTargetExecution,
    )
    from artwork.targets import ArtworkTarget


MANIFEST_NAME = ".dakosys-manifest.json"
MANIFEST_SCHEMA_VERSION = 1

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
    """Truncate text without splitting a UTF-8 codepoint."""

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


def _show_title_slug(
    title: str,
) -> str:
    """Return a deterministic filesystem-friendly display slug.

    Unicode letters and numbers are preserved. Punctuation becomes a
    hyphen, apostrophes are removed, and ampersands are rendered as
    ``and``.

    The slug is display convenience only. It is never used as artwork
    identity.
    """

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
        slug = "show"

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

    return slug or "show"


def show_item_filename(
    *,
    title: str,
    tvdb_id: int,
) -> str:
    """Return the human-readable per-show Artwork Manager filename."""

    if (
        not isinstance(
            tvdb_id,
            int,
        )
        or isinstance(
            tvdb_id,
            bool,
        )
        or tvdb_id <= 0
    ):
        raise ValueError(
            "TVDB ID must be a "
            "positive integer"
        )

    slug = _show_title_slug(
        title
    )

    return (
        f"{slug}"
        f"--tvdb-{tvdb_id}.yaml"
    )


class ItemStoreError(RuntimeError):
    """Base class for per-item artwork store errors."""


class InvalidItemStoreManifestError(
    ItemStoreError
):
    """Existing Dakosys manifest is invalid or incompatible."""


class ItemStoreCollisionError(
    ItemStoreError
):
    """Dakosys output would collide with an unowned filesystem entry."""


@dataclass(frozen=True)
class ItemStoreManifestEntry:
    """One Dakosys-owned per-item output file."""

    plex_rating_key: str
    tvdb_id: int
    filename: str
    sha256: str


@dataclass(frozen=True)
class ItemStoreManifest:
    """Ownership manifest for one Artwork Manager library."""

    library: str
    items: tuple[
        ItemStoreManifestEntry,
        ...,
    ]

    def to_dict(self) -> dict:
        return {
            "schema_version":
                MANIFEST_SCHEMA_VERSION,
            "library":
                self.library,
            "items": {
                entry.plex_rating_key: {
                    "tvdb_id":
                        entry.tvdb_id,
                    "file":
                        entry.filename,
                    "sha256":
                        entry.sha256,
                }
                for entry
                in self.items
            },
        }

    def to_json(self) -> str:
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
class ItemStoreFile:
    """One fully rendered desired per-item file."""

    plex_rating_key: str
    tvdb_id: int
    filename: str
    sha256: str
    contents: str


@dataclass(frozen=True)
class ItemStorePlan:
    """Read-only filesystem plan for one library item store."""

    library: str
    directory: Path

    files: tuple[
        ItemStoreFile,
        ...,
    ]

    manifest: ItemStoreManifest

    added: tuple[str, ...]
    updated: tuple[str, ...]
    unchanged: tuple[str, ...]
    removed: tuple[str, ...]

    preserved_unowned: tuple[
        str,
        ...,
    ]

    @property
    def manifest_path(self) -> Path:
        return (
            self.directory
            / MANIFEST_NAME
        )

    @property
    def desired_count(self) -> int:
        return len(
            self.files
        )

    @property
    def added_count(self) -> int:
        return len(
            self.added
        )

    @property
    def updated_count(self) -> int:
        return len(
            self.updated
        )

    @property
    def unchanged_count(self) -> int:
        return len(
            self.unchanged
        )

    @property
    def removed_count(self) -> int:
        return len(
            self.removed
        )

    @property
    def write_count(self) -> int:
        return (
            self.added_count
            + self.updated_count
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
    value: object,
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
    value: object,
) -> str:
    if not isinstance(
        value,
        str,
    ):
        raise InvalidItemStoreManifestError(
            "manifest item filename "
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
            "manifest contains unsafe "
            f"item filename {value!r}"
        )

    return filename


def load_item_store_manifest(
    directory: str | Path,
    *,
    expected_library: str,
) -> ItemStoreManifest | None:
    """Read and validate an existing Dakosys ownership manifest."""

    directory = Path(
        directory
    )

    path = (
        directory
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
            "item-store manifest"
        ) from exc

    if not isinstance(
        raw,
        dict,
    ):
        raise InvalidItemStoreManifestError(
            "Artwork Manager manifest "
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
            "manifest schema version"
        )

    library = raw.get(
        "library"
    )

    if library != expected_library:
        raise InvalidItemStoreManifestError(
            "Artwork Manager manifest "
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
            "Artwork Manager manifest "
            "items must be a mapping"
        )

    entries = []
    filenames = set()
    tvdb_ids = set()

    for (
        raw_rating_key,
        raw_entry,
    ) in raw_items.items():
        rating_key = str(
            raw_rating_key
        ).strip()

        if not rating_key:
            raise InvalidItemStoreManifestError(
                "manifest contains empty "
                "Plex rating key"
            )

        if not isinstance(
            raw_entry,
            dict,
        ):
            raise InvalidItemStoreManifestError(
                "manifest item must "
                "contain an object"
            )

        tvdb_id = raw_entry.get(
            "tvdb_id"
        )

        if (
            not isinstance(
                tvdb_id,
                int,
            )
            or isinstance(
                tvdb_id,
                bool,
            )
            or tvdb_id <= 0
        ):
            raise InvalidItemStoreManifestError(
                "manifest contains invalid "
                f"TVDB ID {tvdb_id!r}"
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
                "manifest contains invalid "
                f"SHA256 for {filename!r}"
            )

        if filename in filenames:
            raise InvalidItemStoreManifestError(
                "manifest contains duplicate "
                f"filename {filename!r}"
            )

        if tvdb_id in tvdb_ids:
            raise InvalidItemStoreManifestError(
                "manifest contains duplicate "
                f"TVDB ID {tvdb_id}"
            )

        filenames.add(
            filename
        )

        tvdb_ids.add(
            tvdb_id
        )

        entries.append(
            ItemStoreManifestEntry(
                plex_rating_key=rating_key,
                tvdb_id=tvdb_id,
                filename=filename,
                sha256=digest,
            )
        )

    entries.sort(
        key=lambda entry: (
            entry.plex_rating_key
        )
    )

    return ItemStoreManifest(
        library=expected_library,
        items=tuple(
            entries
        ),
    )


def build_show_item_store_plan(
    execution: ShowTargetExecution,
    *,
    directory: str | Path | None = None,
) -> ItemStorePlan:
    """Build a read-only per-show persistence plan."""

    library = (
        execution
        .reconciliation
        .target
        .library
    )

    if directory is None:
        directory = (
            execution
            .reconciliation
            .target
            .output_path
        )

    directory = Path(
        directory
    )

    if (
        directory.exists()
        and not directory.is_dir()
    ):
        raise ItemStoreCollisionError(
            "Artwork Manager item-store "
            "destination exists but is "
            "not a directory: "
            f"{directory}"
        )

    projected_items = (
        project_show_target_items(
            execution
        )
    )

    files = []
    desired_filenames = set()
    desired_tvdb_ids = set()

    for (
        inventory,
        state,
    ) in projected_items:
        tvdb_id = state.tvdb_id

        if tvdb_id is None:
            raise ItemStoreError(
                "projected Artwork Manager "
                "state lacks TVDB identity: "
                f"{inventory.identity.title!r}"
            )

        if tvdb_id in desired_tvdb_ids:
            raise ItemStoreError(
                "duplicate TVDB identity in "
                "Artwork Manager item store: "
                f"{tvdb_id}"
            )

        filename = show_item_filename(
            title=(
                inventory
                .identity
                .title
            ),
            tvdb_id=tvdb_id,
        )

        if filename in desired_filenames:
            raise ItemStoreError(
                "duplicate Artwork Manager "
                f"item filename {filename!r}"
            )

        contents = (
            render_kometa_metadata(
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
            ItemStoreFile(
                plex_rating_key=str(
                    inventory
                    .identity
                    .plex_rating_key
                ),
                tvdb_id=tvdb_id,
                filename=filename,
                sha256=digest,
                contents=contents,
            )
        )

        desired_filenames.add(
            filename
        )

        desired_tvdb_ids.add(
            tvdb_id
        )

    files.sort(
        key=lambda item: (
            item.tvdb_id,
            item.plex_rating_key,
        )
    )

    existing_manifest = (
        load_item_store_manifest(
            directory,
            expected_library=library,
        )
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
            "Artwork Manager would overwrite "
            "unowned item-store file(s): "
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
                "Artwork Manager owned path "
                "is not a regular file: "
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

    manifest_entries = tuple(
        sorted(
            (
                ItemStoreManifestEntry(
                    plex_rating_key=(
                        item
                        .plex_rating_key
                    ),
                    tvdb_id=(
                        item.tvdb_id
                    ),
                    filename=(
                        item.filename
                    ),
                    sha256=(
                        item.sha256
                    ),
                )
                for item
                in files
            ),
            key=lambda entry: (
                entry.plex_rating_key
            ),
        )
    )

    manifest = (
        ItemStoreManifest(
            library=library,
            items=manifest_entries,
        )
    )

    return ItemStorePlan(
        library=library,
        directory=directory,
        files=tuple(
            files
        ),
        manifest=manifest,
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


def format_item_store_plan(
    plan: ItemStorePlan,
) -> str:
    """Format a human-readable per-item persistence preview."""

    lines = [
        (
            "Artwork item store: "
            f"{plan.library}"
        ),
        (
            "Directory: "
            f"{plan.directory}"
        ),
        "",
        (
            "Desired show files:     "
            f"{plan.desired_count}"
        ),
        (
            "Added:                  "
            f"{plan.added_count}"
        ),
        (
            "Updated:                "
            f"{plan.updated_count}"
        ),
        (
            "Unchanged:              "
            f"{plan.unchanged_count}"
        ),
        (
            "Removed:                "
            f"{plan.removed_count}"
        ),
        (
            "Files requiring write:  "
            f"{plan.write_count}"
        ),
        (
            "Preserved unowned:      "
            f"{len(plan.preserved_unowned)}"
        ),
        "",
        (
            "Manifest: "
            f"{plan.manifest_path}"
        ),
        "WRITE: disabled",
    ]

    return "\n".join(
        lines
    )
