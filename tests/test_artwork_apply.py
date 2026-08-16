from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from artwork.apply import (
    ArtworkApplyError,
    StaleArtworkPreviewError,
    UnsafeArtworkPreviewError,
    apply_show_target,
)
from artwork.preview import (
    ArtworkTargetPreview,
    PreviewIssue,
    PreviewIssueCode,
)


def _preview(
    *,
    output_path=Path(
        "/tmp/artwork-tv.yaml"
    ),
    proposed_state_count=2,
    issues=(),
):
    return ArtworkTargetPreview(
        library="TV",
        output_path=output_path,
        plex_show_count=2,
        existing_managed_count=1,
        proposed_state_count=(
            proposed_state_count
        ),
        newly_managed_count=1,
        lost_managed_count=0,
        expected_episode_count=3,
        episode_cards_before=1,
        episode_cards_after=3,
        episode_gaps_before=2,
        episode_gaps_after=0,
        sources=(),
        set_refresh_count=0,
        set_migration_count=0,
        tmdb_created_count=1,
        tmdb_changed_count=1,
        show_poster_count=1,
        background_count=1,
        shows_with_season_posters=1,
        no_state_titles=(),
        rendered_yaml_bytes=1234,
        issues=tuple(
            issues
        ),
    )


def _execution(
    states=("one", "two"),
):
    return SimpleNamespace(
        resolved_states=tuple(
            states
        ),
    )


def test_safe_reviewed_preview_is_atomically_written(
    monkeypatch,
):
    from artwork import apply

    execution = _execution()
    preview = _preview()

    monkeypatch.setattr(
        apply,
        "build_show_target_preview",
        lambda value: preview,
    )

    calls = []

    def fake_write(
        states,
        path,
    ):
        calls.append(
            (
                tuple(states),
                Path(path),
            )
        )

        return Path(
            path
        )

    monkeypatch.setattr(
        apply,
        "write_kometa_metadata",
        fake_write,
    )

    result = apply_show_target(
        execution=execution,
        preview=preview,
    )

    assert calls == [
        (
            ("one", "two"),
            Path(
                "/tmp/artwork-tv.yaml"
            ),
        ),
    ]

    assert (
        result.path
        == Path(
            "/tmp/artwork-tv.yaml"
        )
    )

    assert result.state_count == 2
    assert result.preview == preview
    assert (
        result.rendered_yaml_bytes
        == 1234
    )


def test_stale_preview_is_rejected_before_write(
    monkeypatch,
):
    from artwork import apply

    execution = _execution()

    reviewed = _preview()

    current = replace(
        reviewed,
        episode_gaps_after=1,
        episode_cards_after=2,
    )

    monkeypatch.setattr(
        apply,
        "build_show_target_preview",
        lambda value: current,
    )

    called = False

    def forbidden_write(
        states,
        path,
    ):
        nonlocal called
        called = True

        raise AssertionError(
            "writer must not run"
        )

    monkeypatch.setattr(
        apply,
        "write_kometa_metadata",
        forbidden_write,
    )

    with pytest.raises(
        StaleArtworkPreviewError,
        match="does not match",
    ):
        apply_show_target(
            execution=execution,
            preview=reviewed,
        )

    assert called is False


def test_unsafe_preview_is_rejected_before_write(
    monkeypatch,
):
    from artwork import apply

    issue = PreviewIssue(
        code=(
            PreviewIssueCode
            .PRIMARY_PROVIDER_ERROR
        ),
        message=(
            "provider failed"
        ),
    )

    preview = _preview(
        issues=(
            issue,
        )
    )

    execution = _execution()

    monkeypatch.setattr(
        apply,
        "build_show_target_preview",
        lambda value: preview,
    )

    called = False

    def forbidden_write(
        states,
        path,
    ):
        nonlocal called
        called = True

        raise AssertionError(
            "writer must not run"
        )

    monkeypatch.setattr(
        apply,
        "write_kometa_metadata",
        forbidden_write,
    )

    with pytest.raises(
        UnsafeArtworkPreviewError,
        match="primary_provider_error",
    ):
        apply_show_target(
            execution=execution,
            preview=preview,
        )

    assert called is False


def test_resolved_state_count_must_match_preview(
    monkeypatch,
):
    from artwork import apply

    preview = _preview(
        proposed_state_count=2,
    )

    execution = _execution(
        states=("only-one",)
    )

    monkeypatch.setattr(
        apply,
        "build_show_target_preview",
        lambda value: preview,
    )

    called = False

    def forbidden_write(
        states,
        path,
    ):
        nonlocal called
        called = True

        raise AssertionError(
            "writer must not run"
        )

    monkeypatch.setattr(
        apply,
        "write_kometa_metadata",
        forbidden_write,
    )

    with pytest.raises(
        ArtworkApplyError,
        match="state count",
    ):
        apply_show_target(
            execution=execution,
            preview=preview,
        )

    assert called is False


def test_writer_failure_propagates_without_false_success(
    monkeypatch,
):
    from artwork import apply

    execution = _execution()
    preview = _preview()

    monkeypatch.setattr(
        apply,
        "build_show_target_preview",
        lambda value: preview,
    )

    def failing_write(
        states,
        path,
    ):
        raise OSError(
            "simulated filesystem failure"
        )

    monkeypatch.setattr(
        apply,
        "write_kometa_metadata",
        failing_write,
    )

    with pytest.raises(
        OSError,
        match="simulated filesystem failure",
    ):
        apply_show_target(
            execution=execution,
            preview=preview,
        )
