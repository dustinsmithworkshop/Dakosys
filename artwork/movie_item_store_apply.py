"""Transactional persistence for movie Artwork Manager item stores."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
from uuid import uuid4

import yaml

from artwork.item_store import (
    MANIFEST_NAME,
)
from artwork.item_store_apply import (
    ItemStoreApplyError,
    ItemStoreApplyResult,
    StaleItemStorePlanError,
    StaleItemStorePreviewError,
    UnsafeItemStorePreviewError,
    _copy_preserved_entry,
    _write_text_fsync,
    item_store_plan_needs_apply,
)
from artwork.movie_execution import (
    MovieTargetExecution,
)
from artwork.movie_item_store import (
    MovieItemStorePlan,
    build_movie_item_store_plan,
)
from artwork.movie_preview import (
    MovieArtworkTargetPreview,
    build_movie_target_preview,
)
from artwork.movie_state_store import (
    load_movie_state_store,
)
from artwork.state_store import (
    STATE_NAME,
)


def _validate_rendered_movie_item_file(
    path: Path,
    *,
    mapping_id: int | str,
) -> None:
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
            f"movie artwork file {path.name!r}"
        ) from exc

    if not isinstance(
        document,
        dict,
    ):
        raise ItemStoreApplyError(
            "staged movie artwork file "
            "is not a YAML mapping: "
            f"{path.name!r}"
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
            mapping_id,
        }
    ):
        raise ItemStoreApplyError(
            "staged movie artwork file does "
            "not contain exactly its expected "
            f"mapping identity {mapping_id!r}: "
            f"{path.name!r}"
        )


def _write_staged_snapshot(
    *,
    execution: MovieTargetExecution,
    plan: MovieItemStorePlan,
    staging: Path,
) -> None:
    live = plan.directory

    staging.mkdir(
        parents=False,
        exist_ok=False,
    )

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

            if (
                not source.exists()
                and not source.is_symlink()
            ):
                raise StaleItemStorePlanError(
                    "unowned movie item-store "
                    "entry disappeared after "
                    f"planning: {source}"
                )

            _copy_preserved_entry(
                source,
                destination,
            )

    for item in plan.files:
        path = (
            staging
            / item.filename
        )

        _write_text_fsync(
            path,
            item.contents,
        )

        _validate_rendered_movie_item_file(
            path,
            mapping_id=(
                item.mapping_id
            ),
        )

    _write_text_fsync(
        staging
        / MANIFEST_NAME,
        plan.manifest.to_json(),
    )

    _write_text_fsync(
        staging
        / STATE_NAME,
        plan.state_store.to_json(),
    )

    try:
        staged_state = (
            load_movie_state_store(
                staging,
                expected_library=(
                    plan.library
                ),
            )
        )

    except Exception as exc:
        raise ItemStoreApplyError(
            "could not validate staged "
            "Artwork Manager movie "
            "durable state"
        ) from exc

    if (
        staged_state
        != plan.state_store
    ):
        raise ItemStoreApplyError(
            "staged Artwork Manager movie "
            "durable state does not match "
            "reviewed plan"
        )

    staged_plan = (
        build_movie_item_store_plan(
            library=plan.library,
            directory=staging,
            items=(
                execution
                .resolved_items
            ),
        )
    )

    desired_names = {
        item.filename
        for item
        in plan.files
    }

    if (
        staged_plan.added
        or staged_plan.updated
        or staged_plan.removed
    ):
        raise ItemStoreApplyError(
            "staged movie item-store "
            "validation still reports "
            "filesystem changes"
        )

    if (
        set(
            staged_plan.unchanged
        )
        != desired_names
    ):
        raise ItemStoreApplyError(
            "staged movie item-store does "
            "not contain the complete "
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
            "staged movie item-store did "
            "not preserve expected "
            "unowned entries"
        )

    if (
        staged_plan.manifest
        != plan.manifest
    ):
        raise ItemStoreApplyError(
            "staged movie item-store "
            "manifest does not match "
            "reviewed plan"
        )


def apply_movie_item_store(
    *,
    execution: MovieTargetExecution,
    preview: MovieArtworkTargetPreview,
    plan: MovieItemStorePlan,
) -> ItemStoreApplyResult:
    """Transactionally persist a reviewed movie item-store plan."""

    current_preview = (
        build_movie_target_preview(
            execution
        )
    )

    if preview != current_preview:
        raise StaleItemStorePreviewError(
            "reviewed Artwork Manager "
            "movie preview does not match "
            "current execution"
        )

    if not current_preview.safe_to_apply:
        codes = ", ".join(
            issue.code.value
            for issue
            in current_preview.issues
        )

        raise UnsafeItemStorePreviewError(
            "Artwork Manager movie target "
            "is not safe to apply"
            + (
                f": {codes}"
                if codes
                else ""
            )
        )

    expected_directory = (
        execution
        .reconciliation
        .target
        .output_path
    )

    if (
        plan.directory
        != expected_directory
    ):
        raise StaleItemStorePlanError(
            "reviewed movie item-store "
            "plan targets the wrong directory"
        )

    current_plan = (
        build_movie_item_store_plan(
            library=(
                plan.library
            ),
            directory=(
                expected_directory
            ),
            items=(
                execution
                .resolved_items
            ),
        )
    )

    if plan != current_plan:
        raise StaleItemStorePlanError(
            "reviewed Artwork Manager "
            "movie item-store plan is stale"
        )

    if not item_store_plan_needs_apply(
        current_plan
    ):
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

    live = current_plan.directory
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
        if staging.exists():
            shutil.rmtree(
                staging,
                ignore_errors=True,
            )
