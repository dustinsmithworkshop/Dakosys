from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from artwork.item_store import (
    MANIFEST_NAME,
    build_show_item_store_plan,
)
from artwork.item_store_apply import (
    ItemStoreApplyError,
    StaleItemStorePlanError,
    UnsafeItemStorePreviewError,
    apply_show_item_store,
)
from artwork.inventory import (
    SeasonInventory,
    ShowInventory,
)
from artwork.models import (
    ArtworkAsset,
    ArtworkKind,
    ArtworkQuality,
    ArtworkSource,
    EpisodeArtwork,
    SeasonArtwork,
    ShowArtworkState,
)
from artwork.preview import (
    ArtworkTargetPreview,
    PreviewIssue,
    PreviewIssueCode,
)
from artwork.state_store import (
    STATE_NAME,
    load_show_state_store,
)
from artwork.targets import (
    ArtworkTarget,
    MediaType,
)


def _card(
    asset_id,
):
    return ArtworkAsset(
        kind=ArtworkKind.EPISODE_CARD,
        source=ArtworkSource.MEDIUX,
        url=(
            "https://example/"
            f"{asset_id}.jpg"
        ),
        provider_asset_id=asset_id,
        quality=ArtworkQuality.CURATED,
    )


def _inventory(
    rating_key,
    tvdb_id,
):
    return ShowInventory(
        identity=SimpleNamespace(
            library="TV",
            plex_rating_key=rating_key,
            title=f"Show {rating_key}",
            tvdb_id=tvdb_id,
        ),
        seasons=(
            SeasonInventory(
                season_number=1,
                episode_numbers=frozenset(
                    {
                        1,
                    }
                ),
            ),
        ),
    )


def _state(
    tvdb_id,
    asset_id,
):
    return ShowArtworkState(
        title=f"TVDB {tvdb_id}",
        tvdb_id=tvdb_id,
        seasons={
            1: SeasonArtwork(
                season_number=1,
                episodes={
                    1: EpisodeArtwork(
                        episode_number=1,
                        card=_card(
                            asset_id
                        ),
                    ),
                },
            ),
        },
    )


def _execution(
    tmp_path,
    items,
):
    target = ArtworkTarget(
        name="TV",
        library="TV",
        media_type=MediaType.SHOW,
        output_path=(
            tmp_path
            / "artwork-tv"
        ),
    )

    results = tuple(
        SimpleNamespace(
            inventory=inventory,
            state=state,
        )
        for (
            inventory,
            state,
        ) in items
    )

    return SimpleNamespace(
        reconciliation=(
            SimpleNamespace(
                target=target,
            )
        ),
        coverage_enabled=True,
        managed_coverage=results,
        discovery_coverage=(),
    )


def _two_show_execution(
    tmp_path,
    *,
    first_asset="one",
):
    return _execution(
        tmp_path,
        (
            (
                _inventory(
                    "1",
                    100,
                ),
                _state(
                    100,
                    first_asset,
                ),
            ),
            (
                _inventory(
                    "2",
                    200,
                ),
                _state(
                    200,
                    "two",
                ),
            ),
        ),
    )


def _safe_preview(
    execution,
    *,
    proposed_state_count=2,
    issues=(),
):
    return ArtworkTargetPreview(
        library="TV",
        output_path=(
            execution
            .reconciliation
            .target
            .output_path
        ),
        plex_show_count=(
            proposed_state_count
        ),
        existing_managed_count=0,
        proposed_state_count=(
            proposed_state_count
        ),
        newly_managed_count=(
            proposed_state_count
        ),
        lost_managed_count=0,
        expected_episode_count=(
            proposed_state_count
        ),
        episode_cards_before=0,
        episode_cards_after=(
            proposed_state_count
        ),
        episode_gaps_before=(
            proposed_state_count
        ),
        episode_gaps_after=0,
        sources=(),
        set_refresh_count=0,
        set_migration_count=0,
        tmdb_created_count=0,
        tmdb_changed_count=0,
        show_poster_count=0,
        background_count=0,
        shows_with_season_posters=0,
        no_state_titles=(),
        rendered_yaml_bytes=100,
        issues=tuple(
            issues
        ),
    )


def _patch_preview(
    monkeypatch,
    preview,
):
    from artwork import item_store_apply

    monkeypatch.setattr(
        item_store_apply,
        "build_show_target_preview",
        lambda execution: preview,
    )


def _transaction_artifacts(
    tmp_path,
):
    return tuple(
        path
        for path
        in tmp_path.iterdir()
        if (
            ".staging-"
            in path.name
            or ".rollback-"
            in path.name
        )
    )


def test_applies_new_complete_item_store_snapshot(
    tmp_path,
    monkeypatch,
):
    execution = (
        _two_show_execution(
            tmp_path
        )
    )

    preview = _safe_preview(
        execution
    )

    _patch_preview(
        monkeypatch,
        preview,
    )

    plan = (
        build_show_item_store_plan(
            execution
        )
    )

    result = apply_show_item_store(
        execution=execution,
        preview=preview,
        plan=plan,
    )

    directory = (
        tmp_path
        / "artwork-tv"
    )

    assert result.changed

    assert set(
        path.name
        for path
        in directory.iterdir()
    ) == {
        "show-1--tvdb-100.yaml",
        "show-2--tvdb-200.yaml",
        MANIFEST_NAME,
        STATE_NAME,
    }

    assert (
        result.desired_count
        == 2
    )

    assert (
        _transaction_artifacts(
            tmp_path
        )
        == ()
    )


def test_second_identical_apply_is_noop(
    tmp_path,
    monkeypatch,
):
    execution = (
        _two_show_execution(
            tmp_path
        )
    )

    preview = _safe_preview(
        execution
    )

    _patch_preview(
        monkeypatch,
        preview,
    )

    first_plan = (
        build_show_item_store_plan(
            execution
        )
    )

    apply_show_item_store(
        execution=execution,
        preview=preview,
        plan=first_plan,
    )

    second_plan = (
        build_show_item_store_plan(
            execution
        )
    )

    from artwork import item_store_apply

    def forbidden_stage(
        **kwargs,
    ):
        raise AssertionError(
            "no-op apply must not stage"
        )

    monkeypatch.setattr(
        item_store_apply,
        "_write_staged_snapshot",
        forbidden_stage,
    )

    result = apply_show_item_store(
        execution=execution,
        preview=preview,
        plan=second_plan,
    )

    assert not result.changed

    assert result.added_count == 0
    assert result.updated_count == 0
    assert result.removed_count == 0
    assert result.unchanged_count == 2


def test_unowned_file_is_preserved(
    tmp_path,
    monkeypatch,
):
    directory = (
        tmp_path
        / "artwork-tv"
    )

    directory.mkdir()

    manual = (
        directory
        / "manual-notes.yaml"
    )

    manual.write_text(
        "manual: true\n",
        encoding="utf-8",
    )

    execution = (
        _two_show_execution(
            tmp_path
        )
    )

    preview = _safe_preview(
        execution
    )

    _patch_preview(
        monkeypatch,
        preview,
    )

    plan = (
        build_show_item_store_plan(
            execution
        )
    )

    apply_show_item_store(
        execution=execution,
        preview=preview,
        plan=plan,
    )

    assert manual.read_text(
        encoding="utf-8"
    ) == "manual: true\n"


def test_removes_only_previous_manifest_owned_file(
    tmp_path,
    monkeypatch,
):
    execution = (
        _two_show_execution(
            tmp_path
        )
    )

    preview = _safe_preview(
        execution
    )

    _patch_preview(
        monkeypatch,
        preview,
    )

    apply_show_item_store(
        execution=execution,
        preview=preview,
        plan=(
            build_show_item_store_plan(
                execution
            )
        ),
    )

    directory = (
        tmp_path
        / "artwork-tv"
    )

    manual = (
        directory
        / "manual-notes.yaml"
    )

    manual.write_text(
        "manual: true\n",
        encoding="utf-8",
    )

    one_show = _execution(
        tmp_path,
        (
            (
                _inventory(
                    "1",
                    100,
                ),
                _state(
                    100,
                    "one",
                ),
            ),
        ),
    )

    one_preview = _safe_preview(
        one_show,
        proposed_state_count=1,
    )

    _patch_preview(
        monkeypatch,
        one_preview,
    )

    plan = (
        build_show_item_store_plan(
            one_show
        )
    )

    assert plan.removed == (
        "show-2--tvdb-200.yaml",
    )

    apply_show_item_store(
        execution=one_show,
        preview=one_preview,
        plan=plan,
    )

    assert (
        directory
        / "show-1--tvdb-100.yaml"
    ).exists()

    assert not (
        directory
        / "show-2--tvdb-200.yaml"
    ).exists()

    assert manual.read_text(
        encoding="utf-8"
    ) == "manual: true\n"


def test_stale_plan_is_rejected_before_generated_write(
    tmp_path,
    monkeypatch,
):
    execution = (
        _two_show_execution(
            tmp_path
        )
    )

    preview = _safe_preview(
        execution
    )

    _patch_preview(
        monkeypatch,
        preview,
    )

    plan = (
        build_show_item_store_plan(
            execution
        )
    )

    directory = (
        tmp_path
        / "artwork-tv"
    )

    directory.mkdir()

    (
        directory
        / "manual-notes.yaml"
    ).write_text(
        "appeared later\n",
        encoding="utf-8",
    )

    with pytest.raises(
        StaleItemStorePlanError,
        match="stale",
    ):
        apply_show_item_store(
            execution=execution,
            preview=preview,
            plan=plan,
        )

    assert not (
        directory
        / "show-1--tvdb-100.yaml"
    ).exists()


def test_unsafe_preview_is_rejected_before_filesystem_change(
    tmp_path,
    monkeypatch,
):
    execution = (
        _two_show_execution(
            tmp_path
        )
    )

    issue = PreviewIssue(
        code=(
            PreviewIssueCode
            .PRIMARY_PROVIDER_ERROR
        ),
        message="provider failed",
    )

    preview = _safe_preview(
        execution,
        issues=(
            issue,
        ),
    )

    _patch_preview(
        monkeypatch,
        preview,
    )

    plan = (
        build_show_item_store_plan(
            execution
        )
    )

    with pytest.raises(
        UnsafeItemStorePreviewError,
        match="primary_provider_error",
    ):
        apply_show_item_store(
            execution=execution,
            preview=preview,
            plan=plan,
        )

    assert not (
        tmp_path
        / "artwork-tv"
    ).exists()


def test_staging_failure_preserves_existing_live_snapshot(
    tmp_path,
    monkeypatch,
):
    initial = (
        _two_show_execution(
            tmp_path
        )
    )

    preview = _safe_preview(
        initial
    )

    _patch_preview(
        monkeypatch,
        preview,
    )

    apply_show_item_store(
        execution=initial,
        preview=preview,
        plan=(
            build_show_item_store_plan(
                initial
            )
        ),
    )

    live_file = (
        tmp_path
        / "artwork-tv"
        / "show-1--tvdb-100.yaml"
    )

    before = live_file.read_bytes()

    updated = (
        _two_show_execution(
            tmp_path,
            first_asset="changed",
        )
    )

    updated_preview = (
        _safe_preview(
            updated
        )
    )

    _patch_preview(
        monkeypatch,
        updated_preview,
    )

    plan = (
        build_show_item_store_plan(
            updated
        )
    )

    from artwork import item_store_apply

    def fail_stage(
        **kwargs,
    ):
        raise ItemStoreApplyError(
            "simulated staging failure"
        )

    monkeypatch.setattr(
        item_store_apply,
        "_write_staged_snapshot",
        fail_stage,
    )

    with pytest.raises(
        ItemStoreApplyError,
        match="simulated staging failure",
    ):
        apply_show_item_store(
            execution=updated,
            preview=updated_preview,
            plan=plan,
        )

    assert (
        live_file.read_bytes()
        == before
    )

    assert (
        _transaction_artifacts(
            tmp_path
        )
        == ()
    )


def test_activation_failure_rolls_back_original_directory(
    tmp_path,
    monkeypatch,
):
    initial = (
        _two_show_execution(
            tmp_path
        )
    )

    preview = _safe_preview(
        initial
    )

    _patch_preview(
        monkeypatch,
        preview,
    )

    apply_show_item_store(
        execution=initial,
        preview=preview,
        plan=(
            build_show_item_store_plan(
                initial
            )
        ),
    )

    live_file = (
        tmp_path
        / "artwork-tv"
        / "show-1--tvdb-100.yaml"
    )

    before = live_file.read_bytes()

    updated = (
        _two_show_execution(
            tmp_path,
            first_asset="changed",
        )
    )

    updated_preview = (
        _safe_preview(
            updated
        )
    )

    _patch_preview(
        monkeypatch,
        updated_preview,
    )

    plan = (
        build_show_item_store_plan(
            updated
        )
    )

    from artwork import item_store_apply

    real_replace = (
        item_store_apply
        .os
        .replace
    )

    calls = 0

    def fail_activation(
        source,
        destination,
    ):
        nonlocal calls

        calls += 1

        if calls == 2:
            raise OSError(
                "simulated activation failure"
            )

        return real_replace(
            source,
            destination,
        )

    monkeypatch.setattr(
        item_store_apply.os,
        "replace",
        fail_activation,
    )

    with pytest.raises(
        OSError,
        match="simulated activation failure",
    ):
        apply_show_item_store(
            execution=updated,
            preview=updated_preview,
            plan=plan,
        )

    assert (
        live_file.read_bytes()
        == before
    )

    assert (
        _transaction_artifacts(
            tmp_path
        )
        == ()
    )


def test_successful_update_replaces_snapshot_and_cleans_transaction_dirs(
    tmp_path,
    monkeypatch,
):
    initial = (
        _two_show_execution(
            tmp_path
        )
    )

    preview = _safe_preview(
        initial
    )

    _patch_preview(
        monkeypatch,
        preview,
    )

    apply_show_item_store(
        execution=initial,
        preview=preview,
        plan=(
            build_show_item_store_plan(
                initial
            )
        ),
    )

    live_file = (
        tmp_path
        / "artwork-tv"
        / "show-1--tvdb-100.yaml"
    )

    before = live_file.read_bytes()

    updated = (
        _two_show_execution(
            tmp_path,
            first_asset="changed",
        )
    )

    updated_preview = (
        _safe_preview(
            updated
        )
    )

    _patch_preview(
        monkeypatch,
        updated_preview,
    )

    plan = (
        build_show_item_store_plan(
            updated
        )
    )

    assert plan.updated == (
        "show-1--tvdb-100.yaml",
    )

    result = apply_show_item_store(
        execution=updated,
        preview=updated_preview,
        plan=plan,
    )

    after = live_file.read_bytes()

    assert result.changed
    assert before != after

    assert (
        result.retained_rollback_path
        is None
    )

    assert (
        _transaction_artifacts(
            tmp_path
        )
        == ()
    )


def test_missing_durable_state_bootstraps_transactionally(
    tmp_path,
    monkeypatch,
):
    execution = (
        _two_show_execution(
            tmp_path
        )
    )

    preview = _safe_preview(
        execution
    )

    _patch_preview(
        monkeypatch,
        preview,
    )

    first_plan = (
        build_show_item_store_plan(
            execution
        )
    )

    apply_show_item_store(
        execution=execution,
        preview=preview,
        plan=first_plan,
    )

    directory = (
        tmp_path
        / "artwork-tv"
    )

    state_path = (
        directory
        / STATE_NAME
    )

    assert state_path.is_file()

    # Simulate a pre-state-store production snapshot:
    # YAML + manifest exist, semantic state does not.
    state_path.unlink()

    second_plan = (
        build_show_item_store_plan(
            execution
        )
    )

    assert second_plan.added == ()
    assert second_plan.updated == ()
    assert second_plan.removed == ()
    assert len(
        second_plan.unchanged
    ) == 2

    result = apply_show_item_store(
        execution=execution,
        preview=preview,
        plan=second_plan,
    )

    assert result.changed
    assert state_path.is_file()

    loaded = load_show_state_store(
        directory,
        expected_library="TV",
    )

    assert loaded is not None
    assert (
        loaded
        == second_plan.state_store
    )


def test_complete_store_with_durable_state_is_true_noop(
    tmp_path,
    monkeypatch,
):
    execution = (
        _two_show_execution(
            tmp_path
        )
    )

    preview = _safe_preview(
        execution
    )

    _patch_preview(
        monkeypatch,
        preview,
    )

    apply_show_item_store(
        execution=execution,
        preview=preview,
        plan=(
            build_show_item_store_plan(
                execution
            )
        ),
    )

    plan = (
        build_show_item_store_plan(
            execution
        )
    )

    from artwork import item_store_apply

    def forbidden_stage(
        **kwargs,
    ):
        raise AssertionError(
            "complete durable store "
            "must not stage"
        )

    monkeypatch.setattr(
        item_store_apply,
        "_write_staged_snapshot",
        forbidden_stage,
    )

    result = apply_show_item_store(
        execution=execution,
        preview=preview,
        plan=plan,
    )

    assert not result.changed
    assert result.added_count == 0
    assert result.updated_count == 0
    assert result.removed_count == 0
    assert result.unchanged_count == 2


def test_generation_runs_after_preview_and_plan_validation(
    tmp_path,
    monkeypatch,
):
    from artwork import item_store_apply

    execution = (
        _two_show_execution(
            tmp_path
        )
    )

    execution = SimpleNamespace(
        **execution.__dict__,
        generation_plans=(
            SimpleNamespace(),
        ),
        generator_options=(
            SimpleNamespace(
                enabled=True
            )
        ),
    )

    preview = _safe_preview(
        execution
    )

    _patch_preview(
        monkeypatch,
        preview,
    )

    plan = (
        build_show_item_store_plan(
            execution
        )
    )

    calls = []

    def fake_generation(
        *,
        plans,
        options,
    ):
        calls.append(
            (
                plans,
                options,
            )
        )

        return SimpleNamespace(
            materialized_count=1,
            reused_count=0,
        )

    monkeypatch.setattr(
        item_store_apply,
        "materialize_reviewed_generation_plans",
        fake_generation,
    )

    result = apply_show_item_store(
        execution=execution,
        preview=preview,
        plan=plan,
    )

    assert len(calls) == 1

    assert (
        result.generated_materialized_count
        == 1
    )

    assert (
        result.generated_reused_count
        == 0
    )

    assert result.changed


def test_unsafe_preview_blocks_generation_before_io(
    tmp_path,
    monkeypatch,
):
    from artwork import item_store_apply

    execution = (
        _two_show_execution(
            tmp_path
        )
    )

    execution = SimpleNamespace(
        **execution.__dict__,
        generation_plans=(
            SimpleNamespace(),
        ),
        generator_options=(
            SimpleNamespace(
                enabled=True
            )
        ),
    )

    issue = PreviewIssue(
        code=(
            PreviewIssueCode
            .PRIMARY_PROVIDER_ERROR
        ),
        message="provider failed",
    )

    preview = _safe_preview(
        execution,
        issues=(
            issue,
        ),
    )

    _patch_preview(
        monkeypatch,
        preview,
    )

    plan = (
        build_show_item_store_plan(
            execution
        )
    )

    def forbidden_generation(
        **_kwargs,
    ):
        raise AssertionError(
            "unsafe preview must not "
            "materialize artwork"
        )

    monkeypatch.setattr(
        item_store_apply,
        "materialize_reviewed_generation_plans",
        forbidden_generation,
    )

    with pytest.raises(
        UnsafeItemStorePreviewError,
    ):
        apply_show_item_store(
            execution=execution,
            preview=preview,
            plan=plan,
        )


def test_stale_item_store_plan_blocks_generation_before_io(
    tmp_path,
    monkeypatch,
):
    from artwork import item_store_apply

    execution = (
        _two_show_execution(
            tmp_path
        )
    )

    execution = SimpleNamespace(
        **execution.__dict__,
        generation_plans=(
            SimpleNamespace(),
        ),
        generator_options=(
            SimpleNamespace(
                enabled=True
            )
        ),
    )

    preview = _safe_preview(
        execution
    )

    _patch_preview(
        monkeypatch,
        preview,
    )

    plan = (
        build_show_item_store_plan(
            execution
        )
    )

    directory = (
        tmp_path
        / "artwork-tv"
    )

    directory.mkdir()

    (
        directory
        / "manual-notes.yaml"
    ).write_text(
        "appeared later\n",
        encoding="utf-8",
    )

    def forbidden_generation(
        **_kwargs,
    ):
        raise AssertionError(
            "stale plan must not "
            "materialize artwork"
        )

    monkeypatch.setattr(
        item_store_apply,
        "materialize_reviewed_generation_plans",
        forbidden_generation,
    )

    with pytest.raises(
        StaleItemStorePlanError,
    ):
        apply_show_item_store(
            execution=execution,
            preview=preview,
            plan=plan,
        )


def test_generation_failure_blocks_item_store_activation(
    tmp_path,
    monkeypatch,
):
    from artwork import item_store_apply
    from artwork.generator_apply import (
        GeneratedArtworkApplyError,
    )

    execution = (
        _two_show_execution(
            tmp_path
        )
    )

    execution = SimpleNamespace(
        **execution.__dict__,
        generation_plans=(
            SimpleNamespace(),
        ),
        generator_options=(
            SimpleNamespace(
                enabled=True
            )
        ),
    )

    preview = _safe_preview(
        execution
    )

    _patch_preview(
        monkeypatch,
        preview,
    )

    plan = (
        build_show_item_store_plan(
            execution
        )
    )

    def fail_generation(
        **_kwargs,
    ):
        raise GeneratedArtworkApplyError(
            "render failed"
        )

    monkeypatch.setattr(
        item_store_apply,
        "materialize_reviewed_generation_plans",
        fail_generation,
    )

    with pytest.raises(
        ItemStoreApplyError,
        match="Artwork Generator",
    ) as caught:
        apply_show_item_store(
            execution=execution,
            preview=preview,
            plan=plan,
        )

    assert (
        "render failed"
        in str(
            caught.value
        )
    )

    assert not (
        tmp_path
        / "artwork-tv"
    ).exists()


def test_missing_generated_file_can_be_repaired_when_item_store_is_current(
    tmp_path,
    monkeypatch,
):
    from artwork import item_store_apply

    base_execution = (
        _two_show_execution(
            tmp_path
        )
    )

    preview = _safe_preview(
        base_execution
    )

    _patch_preview(
        monkeypatch,
        preview,
    )

    # First create a fully current item-store snapshot with no
    # generator involvement.
    apply_show_item_store(
        execution=base_execution,
        preview=preview,
        plan=(
            build_show_item_store_plan(
                base_execution
            )
        ),
    )

    execution = SimpleNamespace(
        **base_execution.__dict__,
        generation_plans=(
            SimpleNamespace(),
        ),
        generator_options=(
            SimpleNamespace(
                enabled=True
            )
        ),
    )

    current_preview = (
        _safe_preview(
            execution
        )
    )

    _patch_preview(
        monkeypatch,
        current_preview,
    )

    current_plan = (
        build_show_item_store_plan(
            execution
        )
    )

    assert (
        current_plan.added_count
        == 0
    )

    assert (
        current_plan.updated_count
        == 0
    )

    calls = []

    def repair_generation(
        **_kwargs,
    ):
        calls.append(
            True
        )

        return SimpleNamespace(
            materialized_count=1,
            reused_count=0,
        )

    monkeypatch.setattr(
        item_store_apply,
        "materialize_reviewed_generation_plans",
        repair_generation,
    )

    # A truly metadata-current item store still gets its reviewed
    # missing generated artwork repaired.
    result = apply_show_item_store(
        execution=execution,
        preview=current_preview,
        plan=current_plan,
    )

    assert calls == [
        True,
    ]

    assert result.changed

    assert (
        result.generated_materialized_count
        == 1
    )

    assert result.added_count == 0
    assert result.updated_count == 0
    assert result.removed_count == 0


def test_cached_generation_with_current_item_store_is_noop(
    tmp_path,
    monkeypatch,
):
    from artwork import item_store_apply

    base_execution = (
        _two_show_execution(
            tmp_path
        )
    )

    preview = _safe_preview(
        base_execution
    )

    _patch_preview(
        monkeypatch,
        preview,
    )

    apply_show_item_store(
        execution=base_execution,
        preview=preview,
        plan=(
            build_show_item_store_plan(
                base_execution
            )
        ),
    )

    execution = SimpleNamespace(
        **base_execution.__dict__,
        generation_plans=(
            SimpleNamespace(),
        ),
        generator_options=(
            SimpleNamespace(
                enabled=True
            )
        ),
    )

    current_preview = (
        _safe_preview(
            execution
        )
    )

    _patch_preview(
        monkeypatch,
        current_preview,
    )

    current_plan = (
        build_show_item_store_plan(
            execution
        )
    )

    monkeypatch.setattr(
        item_store_apply,
        "materialize_reviewed_generation_plans",
        lambda **_kwargs: (
            SimpleNamespace(
                materialized_count=0,
                reused_count=1,
            )
        ),
    )

    result = apply_show_item_store(
        execution=execution,
        preview=current_preview,
        plan=current_plan,
    )

    assert not result.changed

    assert (
        result.generated_materialized_count
        == 0
    )

    assert (
        result.generated_reused_count
        == 1
    )
