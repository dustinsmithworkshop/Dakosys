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
