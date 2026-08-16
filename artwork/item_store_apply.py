"""Transactional persistence for Artwork Manager per-item stores.

A complete replacement snapshot is built and validated in a sibling
staging directory before the live item-store directory is touched.

If an existing live directory must be replaced, it is first renamed to
a temporary rollback directory. If activation of the staged snapshot
fails, the original directory is restored.

Unknown/unowned entries are preserved in the staged snapshot.

This module does not contact Plex, artwork providers, or Kometa.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
from uuid import uuid4

import yaml

from artwork.item_store import (
    MANIFEST_NAME,
    ItemStorePlan,
    build_show_item_store_plan,
    item_store_directory_for_target,
)
from artwork.preview import (
    ArtworkTargetPreview,
    build_show_target_preview,
)
from artwork.target_execution import (
    ShowTargetExecution,
)


class ItemStoreApplyError(RuntimeError):
    """Base class for item-store persistence failures."""


class UnsafeItemStorePreviewError(
    ItemStoreApplyError
):
    """The semantic target preview blocks persistence."""


class StaleItemStorePreviewError(
    ItemStoreApplyError
):
    """The reviewed semantic preview no longer matches execution."""


class StaleItemStorePlanError(
    ItemStoreApplyError
):
    """The reviewed filesystem plan no longer matches current state."""


@dataclass(frozen=True)
class ItemStoreApplyResult:
    """Result of one item-store apply operation."""

    directory: Path
    manifest_path: Path

    changed: bool

    desired_count: int
    added_count: int
    updated_count: int
    unchanged_count: int
    removed_count: int

    retained_rollback_path: Path | None = None


def _write_text_fsync(
    path: Path,
    contents: str,
) -> None:
    """Write one staging file completely and flush it to disk."""

    with path.open(
        "w",
        encoding="utf-8",
    ) as handle:
        handle.write(
            contents
        )

        handle.flush()

        os.fsync(
            handle.fileno()
        )


def _copy_preserved_entry(
    source: Path,
    destination: Path,
) -> None:
    """Copy one unowned filesystem entry without adopting it."""

    if source.is_symlink():
        os.symlink(
            os.readlink(
                source
            ),
            destination,
        )

        return

    if source.is_dir():
        shutil.copytree(
            source,
            destination,
            symlinks=True,
        )

        return

    if source.is_file():
        shutil.copy2(
            source,
            destination,
            follow_symlinks=False,
        )

        return

    raise ItemStoreApplyError(
        "cannot preserve unsupported "
        "unowned filesystem entry: "
        f"{source}"
    )


def _validate_rendered_item_file(
    path: Path,
    *,
    tvdb_id: int,
) -> None:
    """Verify a staged per-show YAML contains exactly its TVDB item."""

    try:
        document = yaml.safe_load(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        yaml.YAMLError,
    ) as exc:
        raise ItemStoreApplyError(
            "could not validate staged "
            f"artwork file {path.name!r}"
        ) from exc

    if not isinstance(
        document,
        dict,
    ):
        raise ItemStoreApplyError(
            "staged artwork file is not "
            f"a YAML mapping: {path.name!r}"
        )

    metadata = document.get(
        "metadata"
    )

    if (
        not isinstance(
            metadata,
            dict,
        )
        or set(
            metadata
        )
        != {
            tvdb_id,
        }
    ):
        raise ItemStoreApplyError(
            "staged artwork file does not "
            "contain exactly its expected "
            f"TVDB identity {tvdb_id}: "
            f"{path.name!r}"
        )


def _write_staged_snapshot(
    *,
    execution: ShowTargetExecution,
    plan: ItemStorePlan,
    staging: Path,
) -> None:
    """Build and validate a complete replacement item-store snapshot."""

    live = plan.directory

    staging.mkdir(
        parents=False,
        exist_ok=False,
    )

    # --------------------------------------------------------------
    # Preserve entries Dakosys explicitly does not own.
    # --------------------------------------------------------------

    if live.exists():
        for name in (
            plan.preserved_unowned
        ):
            source = (
                live
                / name
            )

            destination = (
                staging
                / name
            )

            if not source.exists() and not source.is_symlink():
                raise StaleItemStorePlanError(
                    "unowned item-store entry "
                    "disappeared after planning: "
                    f"{source}"
                )

            _copy_preserved_entry(
                source,
                destination,
            )

    # --------------------------------------------------------------
    # Materialize the complete desired generated snapshot.
    # --------------------------------------------------------------

    for item in plan.files:
        path = (
            staging
            / item.filename
        )

        _write_text_fsync(
            path,
            item.contents,
        )

        _validate_rendered_item_file(
            path,
            tvdb_id=item.tvdb_id,
        )

    manifest_contents = (
        plan.manifest.to_json()
    )

    manifest_path = (
        staging
        / MANIFEST_NAME
    )

    _write_text_fsync(
        manifest_path,
        manifest_contents,
    )

    # --------------------------------------------------------------
    # Re-plan against staging itself.
    #
    # A valid finished snapshot must classify every generated file as
    # unchanged and have no adds, updates, or removals remaining.
    # --------------------------------------------------------------

    staged_plan = (
        build_show_item_store_plan(
            execution,
            directory=staging,
        )
    )

    desired_names = {
        item.filename
        for item
        in plan.files
    }

    if staged_plan.added:
        raise ItemStoreApplyError(
            "staged item-store validation "
            "still reports added files"
        )

    if staged_plan.updated:
        raise ItemStoreApplyError(
            "staged item-store validation "
            "still reports updated files"
        )

    if staged_plan.removed:
        raise ItemStoreApplyError(
            "staged item-store validation "
            "still reports removed files"
        )

    if (
        set(
            staged_plan.unchanged
        )
        != desired_names
    ):
        raise ItemStoreApplyError(
            "staged item-store validation "
            "does not contain the complete "
            "desired generated file set"
        )

    if (
        set(
            staged_plan.preserved_unowned
        )
        != set(
            plan.preserved_unowned
        )
    ):
        raise ItemStoreApplyError(
            "staged item-store validation "
            "did not preserve the expected "
            "unowned entries"
        )

    if (
        staged_plan.manifest
        != plan.manifest
    ):
        raise ItemStoreApplyError(
            "staged item-store manifest "
            "does not match reviewed plan"
        )


def _manifest_needs_write(
    plan: ItemStorePlan,
) -> bool:
    path = (
        plan.manifest_path
    )

    if not path.exists():
        return True

    try:
        current = path.read_text(
            encoding="utf-8"
        )
    except OSError:
        return True

    return (
        current
        != plan.manifest.to_json()
    )


def apply_show_item_store(
    *,
    execution: ShowTargetExecution,
    preview: ArtworkTargetPreview,
    plan: ItemStorePlan,
) -> ItemStoreApplyResult:
    """Transactionally persist one reviewed per-show item-store plan."""

    # --------------------------------------------------------------
    # Semantic target preview gate.
    # --------------------------------------------------------------

    current_preview = (
        build_show_target_preview(
            execution
        )
    )

    if preview != current_preview:
        raise StaleItemStorePreviewError(
            "reviewed Artwork Manager preview "
            "does not match current execution"
        )

    if not current_preview.safe_to_apply:
        codes = ", ".join(
            issue.code.value
            for issue
            in current_preview.issues
        )

        raise UnsafeItemStorePreviewError(
            "Artwork Manager target is "
            "not safe to apply"
            + (
                f": {codes}"
                if codes
                else ""
            )
        )

    # --------------------------------------------------------------
    # Filesystem-plan gate.
    # --------------------------------------------------------------

    expected_directory = (
        item_store_directory_for_target(
            execution
            .reconciliation
            .target
        )
    )

    if (
        plan.directory
        != expected_directory
    ):
        raise StaleItemStorePlanError(
            "reviewed item-store plan "
            "targets the wrong directory"
        )

    current_plan = (
        build_show_item_store_plan(
            execution
        )
    )

    if plan != current_plan:
        raise StaleItemStorePlanError(
            "reviewed Artwork Manager "
            "item-store plan is stale"
        )

    needs_apply = (
        bool(
            current_plan.write_count
        )
        or bool(
            current_plan.removed_count
        )
        or _manifest_needs_write(
            current_plan
        )
    )

    if not needs_apply:
        return ItemStoreApplyResult(
            directory=(
                current_plan.directory
            ),
            manifest_path=(
                current_plan.manifest_path
            ),
            changed=False,
            desired_count=(
                current_plan.desired_count
            ),
            added_count=(
                current_plan.added_count
            ),
            updated_count=(
                current_plan.updated_count
            ),
            unchanged_count=(
                current_plan.unchanged_count
            ),
            removed_count=(
                current_plan.removed_count
            ),
        )

    live = (
        current_plan.directory
    )

    parent = live.parent

    parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    transaction_id = (
        uuid4().hex
    )

    staging = (
        parent
        / (
            f".{live.name}."
            f"staging-{transaction_id}"
        )
    )

    rollback = (
        parent
        / (
            f".{live.name}."
            f"rollback-{transaction_id}"
        )
    )

    live_moved = False

    try:
        _write_staged_snapshot(
            execution=execution,
            plan=current_plan,
            staging=staging,
        )

        # ----------------------------------------------------------
        # Commit.
        #
        # Both staging and live are siblings, so the renames stay on
        # the same filesystem.
        # ----------------------------------------------------------

        if live.exists():
            os.replace(
                live,
                rollback,
            )

            live_moved = True

        try:
            os.replace(
                staging,
                live,
            )

        except Exception:
            # If activation fails after moving the old live snapshot,
            # restore it before propagating the failure.
            if (
                live_moved
                and rollback.exists()
                and not live.exists()
            ):
                os.replace(
                    rollback,
                    live,
                )

                live_moved = False

            raise

        retained_rollback = None

        if rollback.exists():
            try:
                shutil.rmtree(
                    rollback
                )
            except OSError:
                # The new snapshot is already active. Keep the old
                # directory rather than pretending cleanup succeeded.
                retained_rollback = (
                    rollback
                )

        return ItemStoreApplyResult(
            directory=live,
            manifest_path=(
                live
                / MANIFEST_NAME
            ),
            changed=True,
            desired_count=(
                current_plan.desired_count
            ),
            added_count=(
                current_plan.added_count
            ),
            updated_count=(
                current_plan.updated_count
            ),
            unchanged_count=(
                current_plan.unchanged_count
            ),
            removed_count=(
                current_plan.removed_count
            ),
            retained_rollback_path=(
                retained_rollback
            ),
        )

    finally:
        # A staging directory can remain only when activation did not
        # successfully rename it into the live location.
        if staging.exists():
            shutil.rmtree(
                staging,
                ignore_errors=True,
            )
