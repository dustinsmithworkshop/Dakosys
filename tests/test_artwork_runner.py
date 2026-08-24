from types import SimpleNamespace

from artwork.apply_policy import (
    ArtworkApplyMode,
)
from artwork.runner import (
    ArtworkRunOutcome,
    execute_artwork_manager_workflow,
)


def _run(
    library,
    *,
    safe=True,
    needs_apply=True,
):
    return SimpleNamespace(
        library=library,
        safe_to_apply=safe,
        needs_apply=needs_apply,
        plan=object(),
    )


def _workflow(
    *runs,
):
    return SimpleNamespace(
        libraries=tuple(runs),
        skipped=(),
    )


def test_auto_mode_applies_safe_changes(
    monkeypatch,
):
    run = _run(
        "Series"
    )

    applied = []

    def fake_apply(
        value,
    ):
        applied.append(
            value.library
        )

        return SimpleNamespace(
            changed=True
        )

    monkeypatch.setattr(
        "artwork.runner."
        "apply_artwork_library_workflow",
        fake_apply,
    )

    result = (
        execute_artwork_manager_workflow(
            _workflow(run),
            apply_mode=(
                ArtworkApplyMode.AUTO
            ),
        )
    )

    assert applied == [
        "Series"
    ]

    assert (
        result.libraries[0].outcome
        is ArtworkRunOutcome.APPLIED
    )

    assert result.applied_count == 1


def test_manual_mode_leaves_safe_changes_pending(
    monkeypatch,
):
    run = _run(
        "Series"
    )

    monkeypatch.setattr(
        "artwork.runner."
        "build_artwork_review_fingerprint",
        lambda value:
            "review-fingerprint",
    )

    monkeypatch.setattr(
        "artwork.runner."
        "apply_artwork_library_workflow",
        lambda value: (
            (_ for _ in ())
            .throw(
                AssertionError(
                    "manual mode must not apply"
                )
            )
        ),
    )

    result = (
        execute_artwork_manager_workflow(
            _workflow(run),
            apply_mode=(
                ArtworkApplyMode.MANUAL
            ),
        )
    )

    assert (
        result.libraries[0].outcome
        is (
            ArtworkRunOutcome
            .PENDING_REVIEW
        )
    )

    assert (
        result.pending_review_count
        == 1
    )

    assert (
        result.libraries[0]
        .review_fingerprint
        == "review-fingerprint"
    )


def test_unsafe_change_is_blocked_in_auto_mode(
    monkeypatch,
):
    run = _run(
        "Series",
        safe=False,
    )

    monkeypatch.setattr(
        "artwork.runner."
        "apply_artwork_library_workflow",
        lambda value: (
            (_ for _ in ())
            .throw(
                AssertionError(
                    "blocked plan must not apply"
                )
            )
        ),
    )

    result = (
        execute_artwork_manager_workflow(
            _workflow(run),
            apply_mode=(
                ArtworkApplyMode.AUTO
            ),
        )
    )

    assert (
        result.libraries[0].outcome
        is ArtworkRunOutcome.BLOCKED
    )

    assert result.blocked_count == 1


def test_no_changes_do_not_apply_in_either_mode(
    monkeypatch,
):
    runs = (
        _run(
            "TV",
            needs_apply=False,
        ),
        _run(
            "Cartoons",
            needs_apply=False,
        ),
    )

    monkeypatch.setattr(
        "artwork.runner."
        "apply_artwork_library_workflow",
        lambda value: (
            (_ for _ in ())
            .throw(
                AssertionError(
                    "no-op plan must not apply"
                )
            )
        ),
    )

    result = (
        execute_artwork_manager_workflow(
            _workflow(
                *runs
            ),
            apply_mode=(
                ArtworkApplyMode.AUTO
            ),
        )
    )

    assert [
        item.outcome
        for item
        in result.libraries
    ] == [
        ArtworkRunOutcome.NO_CHANGES,
        ArtworkRunOutcome.NO_CHANGES,
    ]

    assert result.no_changes_count == 2


def test_apply_failure_does_not_stop_other_libraries(
    monkeypatch,
):
    first = _run(
        "Broken Library"
    )

    second = _run(
        "Healthy Library"
    )

    calls = []

    def fake_apply(
        run,
    ):
        calls.append(
            run.library
        )

        if (
            run.library
            == "Broken Library"
        ):
            raise RuntimeError(
                "disk problem"
            )

        return SimpleNamespace(
            changed=True
        )

    monkeypatch.setattr(
        "artwork.runner."
        "apply_artwork_library_workflow",
        fake_apply,
    )

    result = (
        execute_artwork_manager_workflow(
            _workflow(
                first,
                second,
            ),
            apply_mode=(
                ArtworkApplyMode.AUTO
            ),
        )
    )

    assert calls == [
        "Broken Library",
        "Healthy Library",
    ]

    assert [
        item.outcome
        for item
        in result.libraries
    ] == [
        ArtworkRunOutcome.FAILED,
        ArtworkRunOutcome.APPLIED,
    ]

    assert result.failed_count == 1
    assert result.applied_count == 1

    failure = result.libraries[0]

    assert (
        failure.error_type
        == "RuntimeError"
    )

    assert (
        failure.error_message
        == "disk problem"
    )


def test_auto_result_keeps_pre_apply_needs_apply_snapshot(
    monkeypatch,
):
    class MutableRun:
        library = "Series"
        safe_to_apply = True

        def __init__(
            self,
        ):
            self.applied = False

        @property
        def needs_apply(
            self,
        ):
            return not self.applied

    run = MutableRun()

    def fake_apply(
        value,
    ):
        value.applied = True

        return SimpleNamespace(
            changed=True
        )

    monkeypatch.setattr(
        "artwork.runner."
        "apply_artwork_library_workflow",
        fake_apply,
    )

    result = (
        execute_artwork_manager_workflow(
            _workflow(run),
            apply_mode=(
                ArtworkApplyMode.AUTO
            ),
        )
    )

    # The live workflow now sees an up-to-date filesystem.
    assert (
        run.needs_apply
        is False
    )

    # The operational record preserves why this run acted.
    assert (
        result.libraries[0]
        .needs_apply
        is True
    )

    assert (
        result.libraries[0]
        .outcome
        is ArtworkRunOutcome.APPLIED
    )


def test_reviewed_apply_accepts_exact_fingerprint(
    monkeypatch,
):
    from artwork.runner import (
        execute_reviewed_artwork_library_workflow,
    )

    run = _run(
        "Anime"
    )

    applied = []

    monkeypatch.setattr(
        "artwork.runner."
        "build_artwork_review_fingerprint",
        lambda value:
            "reviewed-plan",
    )

    def fake_apply(
        value,
    ):
        applied.append(
            value.library
        )

        return SimpleNamespace(
            changed=True
        )

    monkeypatch.setattr(
        "artwork.runner."
        "apply_artwork_library_workflow",
        fake_apply,
    )

    result = (
        execute_reviewed_artwork_library_workflow(
            run,
            review_fingerprint=(
                "reviewed-plan"
            ),
        )
    )

    assert applied == [
        "Anime"
    ]

    assert (
        result.apply_mode
        is ArtworkApplyMode.MANUAL
    )

    assert (
        result.outcome
        is ArtworkRunOutcome.APPLIED
    )

    assert (
        result.review_fingerprint
        == "reviewed-plan"
    )

    assert (
        result.needs_apply
        is True
    )


def test_reviewed_apply_rejects_changed_plan(
    monkeypatch,
):
    import pytest

    from artwork.runner import (
        ArtworkReviewMismatchError,
        execute_reviewed_artwork_library_workflow,
    )

    run = _run(
        "Anime"
    )

    monkeypatch.setattr(
        "artwork.runner."
        "build_artwork_review_fingerprint",
        lambda value:
            "current-plan",
    )

    monkeypatch.setattr(
        "artwork.runner."
        "apply_artwork_library_workflow",
        lambda value: (
            (_ for _ in ())
            .throw(
                AssertionError(
                    "stale review must not apply"
                )
            )
        ),
    )

    with pytest.raises(
        ArtworkReviewMismatchError,
        match="changed after review",
    ):
        execute_reviewed_artwork_library_workflow(
            run,
            review_fingerprint=(
                "old-reviewed-plan"
            ),
        )


def test_reviewed_apply_blocks_exact_unsafe_plan(
    monkeypatch,
):
    from artwork.runner import (
        execute_reviewed_artwork_library_workflow,
    )

    run = _run(
        "Anime",
        safe=False,
    )

    monkeypatch.setattr(
        "artwork.runner."
        "build_artwork_review_fingerprint",
        lambda value:
            "unsafe-plan",
    )

    monkeypatch.setattr(
        "artwork.runner."
        "apply_artwork_library_workflow",
        lambda value: (
            (_ for _ in ())
            .throw(
                AssertionError(
                    "unsafe review must not apply"
                )
            )
        ),
    )

    result = (
        execute_reviewed_artwork_library_workflow(
            run,
            review_fingerprint=(
                "unsafe-plan"
            ),
        )
    )

    assert (
        result.outcome
        is ArtworkRunOutcome.BLOCKED
    )

    assert (
        result.apply_mode
        is ArtworkApplyMode.MANUAL
    )


def test_reviewed_apply_exact_no_change_is_noop(
    monkeypatch,
):
    from artwork.runner import (
        execute_reviewed_artwork_library_workflow,
    )

    run = _run(
        "Anime",
        needs_apply=False,
    )

    monkeypatch.setattr(
        "artwork.runner."
        "build_artwork_review_fingerprint",
        lambda value:
            "no-change-plan",
    )

    monkeypatch.setattr(
        "artwork.runner."
        "apply_artwork_library_workflow",
        lambda value: (
            (_ for _ in ())
            .throw(
                AssertionError(
                    "no-change review must not apply"
                )
            )
        ),
    )

    result = (
        execute_reviewed_artwork_library_workflow(
            run,
            review_fingerprint=(
                "no-change-plan"
            ),
        )
    )

    assert (
        result.outcome
        is ArtworkRunOutcome.NO_CHANGES
    )

    assert (
        result.needs_apply
        is False
    )


def test_reviewed_apply_records_apply_failure(
    monkeypatch,
):
    from artwork.runner import (
        execute_reviewed_artwork_library_workflow,
    )

    run = _run(
        "Anime"
    )

    monkeypatch.setattr(
        "artwork.runner."
        "build_artwork_review_fingerprint",
        lambda value:
            "reviewed-plan",
    )

    def fail_apply(
        value,
    ):
        raise RuntimeError(
            "render failed"
        )

    monkeypatch.setattr(
        "artwork.runner."
        "apply_artwork_library_workflow",
        fail_apply,
    )

    result = (
        execute_reviewed_artwork_library_workflow(
            run,
            review_fingerprint=(
                "reviewed-plan"
            ),
        )
    )

    assert (
        result.outcome
        is ArtworkRunOutcome.FAILED
    )

    assert (
        result.error_type
        == "RuntimeError"
    )

    assert (
        result.error_message
        == "render failed"
    )


def test_reviewed_apply_blocks_unplannable_current_state(
    monkeypatch,
):
    from artwork.runner import (
        execute_reviewed_artwork_library_workflow,
    )

    run = SimpleNamespace(
        library="Anime",
        safe_to_apply=False,
        needs_apply=False,
        plan=None,
    )

    monkeypatch.setattr(
        "artwork.runner."
        "build_artwork_review_fingerprint",
        lambda value: (
            (_ for _ in ())
            .throw(
                AssertionError(
                    "unplannable state cannot be fingerprinted"
                )
            )
        ),
    )

    monkeypatch.setattr(
        "artwork.runner."
        "apply_artwork_library_workflow",
        lambda value: (
            (_ for _ in ())
            .throw(
                AssertionError(
                    "unplannable state must not apply"
                )
            )
        ),
    )

    result = (
        execute_reviewed_artwork_library_workflow(
            run,
            review_fingerprint=(
                "previous-reviewed-plan"
            ),
        )
    )

    assert (
        result.outcome
        is ArtworkRunOutcome.BLOCKED
    )

    assert (
        result.apply_mode
        is ArtworkApplyMode.MANUAL
    )

    assert (
        result.needs_apply
        is False
    )

    assert (
        result.review_fingerprint
        == "previous-reviewed-plan"
    )
