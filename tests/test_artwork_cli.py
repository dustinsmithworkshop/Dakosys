from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner

import artwork.cli as artwork_cli
from artwork.targets import MediaType


def _config():
    return {
        "services": {
            "artwork_manager": {
                "enabled": True,
                "apply_mode": "auto",
                "providers": {
                    "mediux": {
                        "api_token":
                            "test-mediux-token",
                    },
                },
            },
        },
        "scheduler": {
            "artwork_manager": {
                "type": "daily",
                "times": ["04:00"],
            },
        },
    }


def _run_record(
    *,
    applied=0,
    no_changes=0,
    pending_review=0,
    blocked=0,
    failed=0,
    skipped=0,
):
    return {
        "apply_mode": "auto",
        "generated_at": (
            "2026-08-20T04:00:00+00:00"
        ),
        "summary": {
            "library_count": (
                applied
                + no_changes
                + pending_review
                + blocked
                + failed
            ),
            "skipped_count": skipped,
            "applied": applied,
            "no_changes": no_changes,
            "pending_review": pending_review,
            "blocked": blocked,
            "failed": failed,
        },
        "libraries": [],
        "skipped": [],
    }


def test_cli_help_lists_artwork_commands():
    runner = CliRunner()

    result = runner.invoke(
        artwork_cli.cli,
        ["--help"],
    )

    assert result.exit_code == 0

    for command in (
        "status",
        "scan",
        "run",
        "history",
    ):
        assert command in result.output


def test_status_reports_dynamic_plex_targets(
    monkeypatch,
):
    runner = CliRunner()

    monkeypatch.setattr(
        artwork_cli,
        "_config_from_context",
        lambda ctx: _config(),
    )

    monkeypatch.setattr(
        artwork_cli,
        "_connect_plex",
        lambda config: object(),
    )

    targets = (
        SimpleNamespace(
            library="Anime",
            media_type=MediaType.SHOW,
            output_path=Path(
                "/kometa/metadata/artwork-anime"
            ),
        ),
        SimpleNamespace(
            library="Movies",
            media_type=MediaType.MOVIE,
            output_path=Path(
                "/kometa/metadata/artwork-movies"
            ),
        ),
    )

    monkeypatch.setattr(
        "artwork.status.discover_artwork_targets",
        lambda plex, config: targets,
    )

    result = runner.invoke(
        artwork_cli.cli,
        ["status"],
    )

    assert result.exit_code == 0
    assert "Apply mode: auto" in result.output
    assert "Anime: show - supported" in (
        result.output
    )
    assert (
        "Movies: movie - supported"
        in result.output
    )


def test_status_json_output(
    monkeypatch,
):
    runner = CliRunner()

    monkeypatch.setattr(
        artwork_cli,
        "_config_from_context",
        lambda ctx: _config(),
    )

    monkeypatch.setattr(
        artwork_cli,
        "_connect_plex",
        lambda config: object(),
    )

    monkeypatch.setattr(
        "artwork.status.discover_artwork_targets",
        lambda plex, config: (
            SimpleNamespace(
                library="TV",
                media_type=MediaType.SHOW,
                output_path=Path(
                    "/kometa/metadata/artwork-tv"
                ),
            ),
        ),
    )

    result = runner.invoke(
        artwork_cli.cli,
        [
            "status",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert '"apply_mode": "auto"' in (
        result.output
    )
    assert '"library": "TV"' in result.output
    assert '"supported": true' in (
        result.output
    )


def test_scan_is_read_only_and_forwards_library(
    monkeypatch,
):
    runner = CliRunner()

    captured = {}

    monkeypatch.setattr(
        artwork_cli,
        "_config_from_context",
        lambda ctx: _config(),
    )

    monkeypatch.setattr(
        artwork_cli,
        "_connect_plex",
        lambda config: object(),
    )

    workflow = object()

    def build_workflow(
        *,
        plex,
        config,
        selected_libraries,
        legacy_metadata_by_library=None,
        progress_callback=None,
    ):
        captured[
            "selected_libraries"
        ] = selected_libraries

        return workflow

    monkeypatch.setattr(
        artwork_cli,
        (
            "build_configured_"
            "artwork_manager_workflow"
        ),
        build_workflow,
    )

    def forbidden_run(*args, **kwargs):
        raise AssertionError(
            "scan must never execute "
            "run_configured_artwork_manager"
        )

    monkeypatch.setattr(
        artwork_cli,
        "run_configured_artwork_manager",
        forbidden_run,
    )

    monkeypatch.setattr(
        artwork_cli,
        "serialize_artwork_workflow",
        lambda value: {
            "summary": {
                "library_count": 1,
                "skipped_count": 0,
                "safe_to_apply": True,
                "changed_files": 0,
            },
            "libraries": [
                {
                    "library": "TV",
                    "safety": {
                        "safe_to_apply": True,
                    },
                    "output": {
                        "needs_apply": False,
                        "changed_files": 0,
                    },
                },
            ],
            "skipped": [],
        },
    )

    result = runner.invoke(
        artwork_cli.cli,
        [
            "scan",
            "--library",
            "TV",
        ],
    )

    assert result.exit_code == 0

    assert captured[
        "selected_libraries"
    ] == (
        "TV",
    )

    assert (
        "TV: SAFE, "
        "needs_apply=False, "
        "changed_files=0"
        in result.output
    )


def test_scan_forwards_multiple_exact_library_names(
    monkeypatch,
):
    runner = CliRunner()

    captured = {}

    monkeypatch.setattr(
        artwork_cli,
        "_config_from_context",
        lambda ctx: _config(),
    )

    monkeypatch.setattr(
        artwork_cli,
        "_connect_plex",
        lambda config: object(),
    )

    def build_workflow(
        *,
        plex,
        config,
        selected_libraries,
        legacy_metadata_by_library=None,
        progress_callback=None,
    ):
        captured[
            "selected_libraries"
        ] = selected_libraries

        return object()

    monkeypatch.setattr(
        artwork_cli,
        (
            "build_configured_"
            "artwork_manager_workflow"
        ),
        build_workflow,
    )

    monkeypatch.setattr(
        artwork_cli,
        "serialize_artwork_workflow",
        lambda workflow: {
            "summary": {
                "library_count": 0,
                "skipped_count": 0,
                "safe_to_apply": True,
                "changed_files": 0,
            },
            "libraries": [],
            "skipped": [],
        },
    )

    result = runner.invoke(
        artwork_cli.cli,
        [
            "scan",
            "--library",
            "Anime",
            "--library",
            "Cartoons",
        ],
    )

    assert result.exit_code == 0

    assert captured[
        "selected_libraries"
    ] == (
        "Anime",
        "Cartoons",
    )


def test_run_delegates_to_runtime_and_history(
    monkeypatch,
):
    runner = CliRunner()

    captured = {}

    monkeypatch.setattr(
        artwork_cli,
        "_config_from_context",
        lambda ctx: _config(),
    )

    monkeypatch.setattr(
        artwork_cli,
        "_connect_plex",
        lambda config: object(),
    )

    def run_manager(
        *,
        plex,
        config,
        selected_libraries,
        history_directory,
        legacy_metadata_by_library=None,
        progress_callback=None,
    ):
        captured[
            "selected_libraries"
        ] = selected_libraries

        captured[
            "history_directory"
        ] = history_directory

        captured[
            "progress_callback"
        ] = progress_callback

        return object()

    monkeypatch.setattr(
        artwork_cli,
        "run_configured_artwork_manager",
        run_manager,
    )

    record = _run_record(
        no_changes=1,
    )

    monkeypatch.setattr(
        artwork_cli,
        "load_latest_artwork_run",
        lambda directory: record,
    )

    result = runner.invoke(
        artwork_cli.cli,
        [
            "--history-directory",
            "/tmp/artwork-history",
            "run",
            "--library",
            "TV",
        ],
    )

    assert result.exit_code == 0

    assert captured[
        "selected_libraries"
    ] == (
        "TV",
    )

    assert captured[
        "history_directory"
    ] == Path(
        "/tmp/artwork-history"
    )

    assert callable(
        captured[
            "progress_callback"
        ]
    )

    assert (
        "1 no changes"
        in result.output
    )


def test_run_does_not_fail_for_blocked_or_pending(
    monkeypatch,
):
    runner = CliRunner()

    monkeypatch.setattr(
        artwork_cli,
        "_config_from_context",
        lambda ctx: _config(),
    )

    monkeypatch.setattr(
        artwork_cli,
        "_connect_plex",
        lambda config: object(),
    )

    monkeypatch.setattr(
        artwork_cli,
        "run_configured_artwork_manager",
        lambda **kwargs: object(),
    )

    record = _run_record(
        pending_review=1,
        blocked=1,
    )

    monkeypatch.setattr(
        artwork_cli,
        "load_latest_artwork_run",
        lambda directory: record,
    )

    result = runner.invoke(
        artwork_cli.cli,
        ["run"],
    )

    assert result.exit_code == 0
    assert "1 pending review" in (
        result.output
    )
    assert "1 blocked" in result.output


def test_run_returns_nonzero_for_failed_library(
    monkeypatch,
):
    runner = CliRunner()

    monkeypatch.setattr(
        artwork_cli,
        "_config_from_context",
        lambda ctx: _config(),
    )

    monkeypatch.setattr(
        artwork_cli,
        "_connect_plex",
        lambda config: object(),
    )

    monkeypatch.setattr(
        artwork_cli,
        "run_configured_artwork_manager",
        lambda **kwargs: object(),
    )

    record = _run_record(
        failed=1,
    )

    monkeypatch.setattr(
        artwork_cli,
        "load_latest_artwork_run",
        lambda directory: record,
    )

    result = runner.invoke(
        artwork_cli.cli,
        ["run"],
    )

    assert result.exit_code == 1
    assert "1 failed" in result.output


def test_history_reads_recent_records(
    monkeypatch,
):
    runner = CliRunner()

    records = (
        _run_record(
            no_changes=3,
            skipped=1,
        ),
    )

    captured = {}

    def list_history(
        directory,
        *,
        limit,
    ):
        captured[
            "directory"
        ] = directory
        captured[
            "limit"
        ] = limit

        return records

    monkeypatch.setattr(
        artwork_cli,
        "list_artwork_run_history",
        list_history,
    )

    result = runner.invoke(
        artwork_cli.cli,
        [
            "--history-directory",
            "/tmp/history",
            "history",
            "--limit",
            "5",
        ],
    )

    assert result.exit_code == 0
    assert captured["limit"] == 5
    assert captured[
        "directory"
    ] == Path(
        "/tmp/history"
    )
    assert "3 no changes" in (
        result.output
    )


def test_scan_forwards_explicit_legacy_metadata(
    monkeypatch,
):
    runner = CliRunner()

    captured = {}

    monkeypatch.setattr(
        artwork_cli,
        "_config_from_context",
        lambda ctx: _config(),
    )

    monkeypatch.setattr(
        artwork_cli,
        "_connect_plex",
        lambda config: object(),
    )

    def build_workflow(
        *,
        plex,
        config,
        selected_libraries,
        legacy_metadata_by_library=None,
        progress_callback=None,
    ):
        captured[
            "legacy_metadata_by_library"
        ] = legacy_metadata_by_library

        return object()

    monkeypatch.setattr(
        artwork_cli,
        (
            "build_configured_"
            "artwork_manager_workflow"
        ),
        build_workflow,
    )

    monkeypatch.setattr(
        artwork_cli,
        "serialize_artwork_workflow",
        lambda workflow: {
            "summary": {
                "library_count": 0,
                "skipped_count": 0,
                "safe_to_apply": True,
                "changed_files": 0,
            },
            "libraries": [],
            "skipped": [],
        },
    )

    result = runner.invoke(
        artwork_cli.cli,
        [
            "scan",
            "--library",
            "TV",
            "--legacy-metadata",
            "TV=/tmp/mediux-tv.yml",
        ],
    )

    assert result.exit_code == 0

    assert captured[
        "legacy_metadata_by_library"
    ] == {
        "TV": Path(
            "/tmp/mediux-tv.yml"
        ),
    }


def test_run_forwards_explicit_legacy_metadata(
    monkeypatch,
):
    runner = CliRunner()

    captured = {}

    monkeypatch.setattr(
        artwork_cli,
        "_config_from_context",
        lambda ctx: _config(),
    )

    monkeypatch.setattr(
        artwork_cli,
        "_connect_plex",
        lambda config: object(),
    )

    def run_manager(
        *,
        plex,
        config,
        selected_libraries,
        history_directory,
        legacy_metadata_by_library=None,
        progress_callback=None,
    ):
        captured[
            "legacy_metadata_by_library"
        ] = legacy_metadata_by_library

        return object()

    monkeypatch.setattr(
        artwork_cli,
        "run_configured_artwork_manager",
        run_manager,
    )

    record = _run_record(
        no_changes=1,
    )

    monkeypatch.setattr(
        artwork_cli,
        "load_latest_artwork_run",
        lambda directory: record,
    )

    result = runner.invoke(
        artwork_cli.cli,
        [
            "run",
            "--legacy-metadata",
            "TV=/tmp/mediux-tv.yml",
        ],
    )

    assert result.exit_code == 0

    assert captured[
        "legacy_metadata_by_library"
    ] == {
        "TV": Path(
            "/tmp/mediux-tv.yml"
        ),
    }


def test_legacy_metadata_rejects_malformed_mapping():
    runner = CliRunner()

    result = runner.invoke(
        artwork_cli.cli,
        [
            "scan",
            "--legacy-metadata",
            "TV",
        ],
    )

    assert result.exit_code != 0
    assert "LIBRARY=PATH" in result.output


def test_legacy_metadata_rejects_duplicate_library():
    runner = CliRunner()

    result = runner.invoke(
        artwork_cli.cli,
        [
            "scan",
            "--legacy-metadata",
            "TV=/tmp/first.yml",
            "--legacy-metadata",
            "TV=/tmp/second.yml",
        ],
    )

    assert result.exit_code != 0
    assert "duplicate" in result.output
    assert "TV" in result.output
