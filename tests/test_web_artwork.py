from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import web_server

from artwork.targets import (
    MediaType,
)


class FakeTarget:
    def __init__(
        self,
        library,
        media_type,
        output_path,
    ):
        self.library = library
        self.media_type = media_type
        self.output_path = Path(
            output_path
        )


def test_config_masks_mediux_api_token():
    config = {
        "services": {
            "artwork_manager": {
                "enabled": True,
                "providers": {
                    "mediux": {
                        "api_token":
                            "super-secret-token",
                    },
                },
            },
        },
    }

    masked = (
        web_server.mask_secrets(
            config
        )
    )

    assert (
        masked["services"]
        ["artwork_manager"]
        ["providers"]
        ["mediux"]
        ["api_token"]
        == web_server.MASKED
    )

    assert (
        config["services"]
        ["artwork_manager"]
        ["providers"]
        ["mediux"]
        ["api_token"]
        == "super-secret-token"
    )


def test_artwork_targets_are_dynamic(
    monkeypatch,
):
    config = {
        "services": {
            "artwork_manager": {
                "enabled": True,
                "output_dir":
                    "/metadata",
            },
        },
        "plex": {
            "url": "http://plex",
            "token": "token",
        },
    }

    plex = object()

    monkeypatch.setattr(
        web_server,
        "load_config",
        lambda: config,
    )

    monkeypatch.setattr(
        web_server,
        "_connect_plex",
        lambda value: plex,
    )

    def fake_discover(
        received_plex,
        received_config,
    ):
        assert (
            received_plex
            is plex
        )

        assert (
            received_config
            is config
        )

        return (
            FakeTarget(
                "Bob's Television",
                MediaType.SHOW,
                (
                    "/metadata/"
                    "artwork-bob-s-television"
                ),
            ),
            FakeTarget(
                "Cinema Vault",
                MediaType.MOVIE,
                (
                    "/metadata/"
                    "artwork-cinema-vault"
                ),
            ),
        )

    monkeypatch.setattr(
        web_server,
        "discover_artwork_targets",
        fake_discover,
    )

    result = (
        web_server.get_artwork_targets()
    )

    assert result == {
        "enabled": True,
        "targets": [
            {
                "library":
                    "Bob's Television",
                "media_type":
                    "show",
                "output_path":
                    (
                        "/metadata/"
                        "artwork-bob-s-television"
                    ),
                "supported": True,
                "status": "ready",
            },
            {
                "library":
                    "Cinema Vault",
                "media_type":
                    "movie",
                "output_path":
                    (
                        "/metadata/"
                        "artwork-cinema-vault"
                    ),
                "supported": False,
                "status":
                    "movie_support_pending",
            },
        ],
    }


def test_disabled_artwork_targets_do_not_connect_to_plex(
    monkeypatch,
):
    config = {
        "services": {
            "artwork_manager": {
                "enabled": False,
            },
        },
    }

    monkeypatch.setattr(
        web_server,
        "load_config",
        lambda: config,
    )

    def should_not_connect(
        config,
    ):
        raise AssertionError(
            "Plex should not be contacted"
        )

    monkeypatch.setattr(
        web_server,
        "_connect_plex",
        should_not_connect,
    )

    assert (
        web_server.get_artwork_targets()
        == {
            "enabled": False,
            "targets": [],
        }
    )


def test_artwork_preview_uses_exact_library(
    monkeypatch,
):
    config = {
        "services": {
            "artwork_manager": {
                "enabled": True,
            },
        },
    }

    plex = object()

    workflow = SimpleNamespace(
        libraries=(object(),),
        skipped=(),
    )

    serialized = {
        "summary": {
            "library_count": 1,
        },
    }

    seen = {}

    monkeypatch.setattr(
        web_server,
        "load_config",
        lambda: config,
    )

    monkeypatch.setattr(
        web_server,
        "_connect_plex",
        lambda value: plex,
    )

    def fake_build(
        **kwargs,
    ):
        seen.update(
            kwargs
        )

        return workflow

    monkeypatch.setattr(
        web_server,
        (
            "build_configured_"
            "artwork_manager_workflow"
        ),
        fake_build,
    )

    monkeypatch.setattr(
        web_server,
        "serialize_artwork_workflow",
        lambda value: serialized,
    )

    result = (
        web_server.get_artwork_preview(
            "Kids & Family"
        )
    )

    assert result is serialized

    assert (
        seen["plex"]
        is plex
    )

    assert (
        seen["config"]
        is config
    )

    assert (
        seen["selected_libraries"]
        == "Kids & Family"
    )


def test_artwork_preview_unknown_library_is_400(
    monkeypatch,
):
    config = {
        "services": {
            "artwork_manager": {
                "enabled": True,
            },
        },
    }

    monkeypatch.setattr(
        web_server,
        "load_config",
        lambda: config,
    )

    monkeypatch.setattr(
        web_server,
        "_connect_plex",
        lambda value: object(),
    )

    def fake_build(
        **kwargs,
    ):
        raise ValueError(
            "selected Artwork Manager "
            "libraries were not discovered "
            "in Plex: 'Missing'"
        )

    monkeypatch.setattr(
        web_server,
        (
            "build_configured_"
            "artwork_manager_workflow"
        ),
        fake_build,
    )

    with pytest.raises(
        HTTPException,
    ) as caught:
        (
            web_server
            .get_artwork_preview(
                "Missing"
            )
        )

    assert (
        caught.value.status_code
        == 400
    )


def test_artwork_preview_never_applies(
    monkeypatch,
):
    """The read-only Web endpoint must not expose persistence."""

    config = {
        "services": {
            "artwork_manager": {
                "enabled": True,
            },
        },
    }

    plex = object()

    workflow = SimpleNamespace(
        libraries=(object(),),
        skipped=(),
    )

    monkeypatch.setattr(
        web_server,
        "load_config",
        lambda: config,
    )

    monkeypatch.setattr(
        web_server,
        "_connect_plex",
        lambda value: plex,
    )

    monkeypatch.setattr(
        web_server,
        (
            "build_configured_"
            "artwork_manager_workflow"
        ),
        lambda **kwargs:
            workflow,
    )

    monkeypatch.setattr(
        web_server,
        "serialize_artwork_workflow",
        lambda value: {
            "safe": True,
        },
    )

    result = (
        web_server.get_artwork_preview(
            "Any Library"
        )
    )

    assert result == {
        "safe": True,
    }


def test_artwork_latest_history_returns_none_before_first_run(
    monkeypatch,
    tmp_path,
):
    history = (
        tmp_path
        / "artwork-manager"
    )

    monkeypatch.setattr(
        web_server,
        "ARTWORK_HISTORY_DIR",
        str(
            history
        ),
    )

    assert (
        web_server
        .get_artwork_history_latest()
        == {
            "run": None,
        }
    )


def test_artwork_latest_history_returns_persisted_record(
    monkeypatch,
    tmp_path,
):
    import json

    history = (
        tmp_path
        / "artwork-manager"
    )

    history.mkdir(
        parents=True
    )

    record = {
        "schema_version": 1,
        "run_id": "example",
        "generated_at":
            "2026-08-18T10:00:00+00:00",
        "apply_mode": "manual",
        "summary": {
            "library_count": 1,
        },
        "libraries": [],
        "skipped": [],
    }

    (
        history
        / "latest.json"
    ).write_text(
        json.dumps(
            record
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        web_server,
        "ARTWORK_HISTORY_DIR",
        str(
            history
        ),
    )

    assert (
        web_server
        .get_artwork_history_latest()
        == {
            "run": record,
        }
    )


def test_artwork_history_is_newest_first_and_limited(
    monkeypatch,
):
    seen = {}

    records = (
        {
            "run_id": "newest",
        },
        {
            "run_id": "older",
        },
    )

    def fake_history(
        directory,
        *,
        limit,
    ):
        seen[
            "directory"
        ] = directory

        seen[
            "limit"
        ] = limit

        return records

    monkeypatch.setattr(
        web_server,
        "ARTWORK_HISTORY_DIR",
        "/data/artwork-manager",
    )

    monkeypatch.setattr(
        web_server,
        "list_artwork_run_history",
        fake_history,
    )

    result = (
        web_server
        .get_artwork_history(
            limit=2
        )
    )

    assert result == {
        "runs": [
            {
                "run_id":
                    "newest",
            },
            {
                "run_id":
                    "older",
            },
        ],
        "count": 2,
    }

    assert seen == {
        "directory":
            "/data/artwork-manager",
        "limit": 2,
    }


@pytest.mark.parametrize(
    "limit",
    (
        0,
        -1,
        101,
        True,
    ),
)
def test_artwork_history_rejects_invalid_limit(
    limit,
):
    with pytest.raises(
        HTTPException,
    ) as caught:
        (
            web_server
            .get_artwork_history(
                limit=limit
            )
        )

    assert (
        caught.value.status_code
        == 400
    )


def test_artwork_history_invalid_record_is_server_error(
    monkeypatch,
    tmp_path,
):
    history = (
        tmp_path
        / "artwork-manager"
    )

    history.mkdir(
        parents=True
    )

    (
        history
        / "latest.json"
    ).write_text(
        "{ definitely not json",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        web_server,
        "ARTWORK_HISTORY_DIR",
        str(
            history
        ),
    )

    with pytest.raises(
        HTTPException,
    ) as caught:
        (
            web_server
            .get_artwork_history_latest()
        )

    assert (
        caught.value.status_code
        == 500
    )


def test_artwork_history_does_not_contact_plex_or_providers(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        web_server,
        "ARTWORK_HISTORY_DIR",
        str(
            tmp_path
            / "artwork-manager"
        ),
    )

    monkeypatch.setattr(
        web_server,
        "_connect_plex",
        lambda config:
            (_ for _ in ())
            .throw(
                AssertionError(
                    "history must not contact Plex"
                )
            ),
    )

    monkeypatch.setattr(
        web_server,
        "load_config",
        lambda:
            (_ for _ in ())
            .throw(
                AssertionError(
                    "history must not load runtime config"
                )
            ),
    )

    assert (
        web_server
        .get_artwork_history_latest()
        == {
            "run": None,
        }
    )

    assert (
        web_server
        .get_artwork_history()
        == {
            "runs": [],
            "count": 0,
        }
    )


def test_artwork_current_state_returns_none_before_first_scan(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        web_server,
        "ARTWORK_HISTORY_DIR",
        str(
            tmp_path
            / "artwork-manager"
        ),
    )

    assert (
        web_server
        .get_artwork_current_state(
            "Series"
        )
        == {
            "state": None,
        }
    )


def test_artwork_current_state_returns_cached_result(
    monkeypatch,
    tmp_path,
):
    from artwork.current_state import (
        write_artwork_current_state,
    )

    directory = (
        tmp_path
        / "artwork-manager"
    )

    record = (
        write_artwork_current_state(
            directory=directory,
            library="Series",
            preview={
                "library": "Series",
                "output": {
                    "needs_apply": False,
                },
            },
        )
    )

    monkeypatch.setattr(
        web_server,
        "ARTWORK_HISTORY_DIR",
        str(
            directory
        ),
    )

    assert (
        web_server
        .get_artwork_current_state(
            "Series"
        )
        == {
            "state": record,
        }
    )


def test_artwork_scan_start_returns_immediately_and_reuses_active_scan(
    monkeypatch,
):
    config = {
        "services": {
            "artwork_manager": {
                "enabled": True,
            },
        },
    }

    monkeypatch.setattr(
        web_server,
        "load_config",
        lambda: config,
    )

    monkeypatch.setattr(
        web_server,
        "ARTWORK_SCANS",
        {},
    )

    monkeypatch.setattr(
        web_server,
        "ARTWORK_ACTIVE_SCANS",
        {},
    )

    started = []

    class FakeThread:
        def __init__(
            self,
            *,
            target,
            args,
            name,
            daemon,
        ):
            self.target = target
            self.args = args
            self.name = name
            self.daemon = daemon

        def start(
            self,
        ):
            started.append(
                (
                    self.target,
                    self.args,
                )
            )

    monkeypatch.setattr(
        web_server.threading,
        "Thread",
        FakeThread,
    )

    first = (
        web_server
        .start_artwork_current_state_scan(
            "Series"
        )
    )

    second = (
        web_server
        .start_artwork_current_state_scan(
            "Series"
        )
    )

    assert (
        first["reused"]
        is False
    )

    assert (
        second["reused"]
        is True
    )

    assert (
        second["scan"]["scan_id"]
        == first["scan"]["scan_id"]
    )

    assert (
        first["scan"]["status"]
        == "running"
    )

    assert len(
        started
    ) == 1


def test_artwork_scan_worker_reports_progress_and_caches_success(
    monkeypatch,
):
    config = {
        "services": {
            "artwork_manager": {
                "enabled": True,
            },
        },
    }

    plex = object()

    run = SimpleNamespace(
        plan=object(),
        safe_to_apply=True,
        needs_apply=True,
    )

    class FakeWorkflow:
        skipped = ()

        def run_for_library(
            self,
            library,
        ):
            assert (
                library
                == "Series"
            )

            return run

    monkeypatch.setattr(
        web_server,
        "ARTWORK_SCANS",
        {
            "scan-1": {
                "scan_id":
                    "scan-1",

                "library":
                    "Series",

                "status":
                    "running",

                "started_at":
                    "start",

                "updated_at":
                    "start",

                "scanned_at":
                    None,

                "progress":
                    None,

                "error":
                    None,
            },
        },
    )

    monkeypatch.setattr(
        web_server,
        "ARTWORK_ACTIVE_SCANS",
        {
            "Series":
                "scan-1",
        },
    )

    monkeypatch.setattr(
        web_server,
        "load_config",
        lambda: config,
    )

    monkeypatch.setattr(
        web_server,
        "_connect_plex",
        lambda value: plex,
    )

    def fake_build(
        **kwargs,
    ):
        assert (
            kwargs["plex"]
            is plex
        )

        assert (
            kwargs["config"]
            is config
        )

        assert (
            kwargs[
                "selected_libraries"
            ]
            == "Series"
        )

        callback = (
            kwargs[
                "progress_callback"
            ]
        )

        from artwork.progress import (
            ArtworkScanPhase,
            ArtworkScanProgress,
        )

        callback(
            ArtworkScanProgress(
                library="Series",
                phase=(
                    ArtworkScanPhase
                    .PRIMARY_MANAGED
                ),
                completed=42,
                total=100,
                message=(
                    "Checking managed artwork"
                ),
                current_title=(
                    "Example Show"
                ),
            )
        )

        return FakeWorkflow()

    monkeypatch.setattr(
        web_server,
        (
            "build_configured_"
            "artwork_manager_workflow"
        ),
        fake_build,
    )

    preview = {
        "library":
            "Series",

        "output": {
            "needs_apply":
                False,
        },
    }

    monkeypatch.setattr(
        web_server,
        "serialize_artwork_library",
        lambda value:
            preview,
    )

    monkeypatch.setattr(
        web_server,
        "build_artwork_review_fingerprint",
        lambda value:
            "reviewed-series-plan",
    )

    written = {}

    def fake_write(
        *,
        directory,
        library,
        preview,
        review_fingerprint=None,
        scanned_at=None,
    ):
        written.update(
            {
                "directory":
                    directory,

                "library":
                    library,

                "preview":
                    preview,

                "review_fingerprint":
                    review_fingerprint,
            }
        )

        return {
            "schema_version": 3,
            "library": library,
            "scanned_at":
                "2026-08-18T18:00:00+00:00",
            "review_fingerprint":
                review_fingerprint,
            "preview": preview,
        }

    monkeypatch.setattr(
        web_server,
        "write_artwork_current_state",
        fake_write,
    )

    monkeypatch.setattr(
        web_server,
        "ARTWORK_HISTORY_DIR",
        "/data/artwork-manager",
    )

    web_server._run_artwork_current_state_scan(
        "scan-1",
        "Series",
    )

    scan = (
        web_server
        .ARTWORK_SCANS[
            "scan-1"
        ]
    )

    assert (
        scan["status"]
        == "complete"
    )

    assert (
        scan["progress"]["phase"]
        == "complete"
    )

    assert (
        scan["progress"]["fraction"]
        == 1.0
    )

    assert (
        scan["scanned_at"]
        == (
            "2026-08-18T18:00:00+00:00"
        )
    )

    assert written == {
        "directory":
            "/data/artwork-manager",

        "library":
            "Series",

        "preview":
            preview,

        "review_fingerprint":
            "reviewed-series-plan",
    }

    assert (
        "Series"
        not in (
            web_server
            .ARTWORK_ACTIVE_SCANS
        )
    )


def test_artwork_scan_failure_does_not_write_cache(
    monkeypatch,
):
    monkeypatch.setattr(
        web_server,
        "ARTWORK_SCANS",
        {
            "scan-1": {
                "scan_id":
                    "scan-1",

                "library":
                    "Series",

                "status":
                    "running",

                "started_at":
                    "start",

                "updated_at":
                    "start",

                "scanned_at":
                    None,

                "progress":
                    None,

                "error":
                    None,
            },
        },
    )

    monkeypatch.setattr(
        web_server,
        "ARTWORK_ACTIVE_SCANS",
        {
            "Series":
                "scan-1",
        },
    )

    monkeypatch.setattr(
        web_server,
        "load_config",
        lambda: {
            "services": {
                "artwork_manager": {
                    "enabled": True,
                },
            },
        },
    )

    monkeypatch.setattr(
        web_server,
        "_connect_plex",
        lambda value: object(),
    )

    monkeypatch.setattr(
        web_server,
        (
            "build_configured_"
            "artwork_manager_workflow"
        ),
        lambda **kwargs:
            (_ for _ in ())
            .throw(
                RuntimeError(
                    "provider unavailable"
                )
            ),
    )

    monkeypatch.setattr(
        web_server,
        "write_artwork_current_state",
        lambda **kwargs:
            (_ for _ in ())
            .throw(
                AssertionError(
                    "failed scans must not replace cache"
                )
            ),
    )

    web_server._run_artwork_current_state_scan(
        "scan-1",
        "Series",
    )

    scan = (
        web_server
        .ARTWORK_SCANS[
            "scan-1"
        ]
    )

    assert (
        scan["status"]
        == "failed"
    )

    assert (
        scan["error"]["type"]
        == "RuntimeError"
    )

    assert (
        scan["error"]["message"]
        == "provider unavailable"
    )

    assert (
        "Series"
        not in (
            web_server
            .ARTWORK_ACTIVE_SCANS
        )
    )


def test_artwork_scan_status_unknown_id_is_404(
    monkeypatch,
):
    monkeypatch.setattr(
        web_server,
        "ARTWORK_SCANS",
        {},
    )

    with pytest.raises(
        HTTPException,
    ) as caught:
        (
            web_server
            .get_artwork_current_state_scan(
                "missing"
            )
        )

    assert (
        caught.value.status_code
        == 404
    )


def _reviewed_current_state(
    fingerprint="reviewed-anime-plan",
):
    return {
        "schema_version": 3,
        "library": "Anime",
        "scanned_at":
            "2026-08-24T20:00:00+00:00",
        "review_fingerprint":
            fingerprint,
        "preview": {
            "safety": {
                "safe_to_apply": True,
                "issues": [],
            },
            "output": {
                "needs_apply": True,
            },
        },
    }


def test_artwork_reviewed_apply_starts_async_and_reuses_same_plan(
    monkeypatch,
):
    config = {
        "services": {
            "artwork_manager": {
                "enabled": True,
            },
        },
    }

    monkeypatch.setattr(
        web_server,
        "load_config",
        lambda: config,
    )

    monkeypatch.setattr(
        web_server,
        "load_artwork_current_state",
        lambda **kwargs:
            _reviewed_current_state(),
    )

    monkeypatch.setattr(
        web_server,
        "ARTWORK_APPLIES",
        {},
    )

    monkeypatch.setattr(
        web_server,
        "ARTWORK_ACTIVE_APPLIES",
        {},
    )

    monkeypatch.setattr(
        web_server,
        "ARTWORK_SCANS",
        {},
    )

    monkeypatch.setattr(
        web_server,
        "ARTWORK_ACTIVE_SCANS",
        {},
    )

    started = []

    class FakeThread:
        def __init__(
            self,
            *,
            target,
            args,
            name,
            daemon,
        ):
            self.target = target
            self.args = args
            self.name = name
            self.daemon = daemon

        def start(
            self,
        ):
            started.append(
                (
                    self.target,
                    self.args,
                )
            )

    monkeypatch.setattr(
        web_server.threading,
        "Thread",
        FakeThread,
    )

    payload = (
        web_server
        .ArtworkReviewedApplyPayload(
            review_fingerprint=(
                "reviewed-anime-plan"
            )
        )
    )

    first = (
        web_server
        .start_artwork_reviewed_apply(
            "Anime",
            payload,
        )
    )

    second = (
        web_server
        .start_artwork_reviewed_apply(
            "Anime",
            payload,
        )
    )

    assert (
        first["reused"]
        is False
    )

    assert (
        second["reused"]
        is True
    )

    assert (
        second[
            "apply"
        ][
            "apply_id"
        ]
        == first[
            "apply"
        ][
            "apply_id"
        ]
    )

    assert (
        first[
            "apply"
        ][
            "status"
        ]
        == "running"
    )

    assert len(
        started
    ) == 1


def test_artwork_reviewed_apply_rejects_active_scan(
    monkeypatch,
):
    monkeypatch.setattr(
        web_server,
        "load_config",
        lambda: {
            "services": {
                "artwork_manager": {
                    "enabled": True,
                },
            },
        },
    )

    monkeypatch.setattr(
        web_server,
        "load_artwork_current_state",
        lambda **kwargs:
            _reviewed_current_state(),
    )

    monkeypatch.setattr(
        web_server,
        "ARTWORK_APPLIES",
        {},
    )

    monkeypatch.setattr(
        web_server,
        "ARTWORK_ACTIVE_APPLIES",
        {},
    )

    monkeypatch.setattr(
        web_server,
        "ARTWORK_SCANS",
        {
            "scan-1": {
                "scan_id":
                    "scan-1",

                "library":
                    "Anime",

                "status":
                    "running",
            },
        },
    )

    monkeypatch.setattr(
        web_server,
        "ARTWORK_ACTIVE_SCANS",
        {
            "Anime":
                "scan-1",
        },
    )

    payload = (
        web_server
        .ArtworkReviewedApplyPayload(
            review_fingerprint=(
                "reviewed-anime-plan"
            )
        )
    )

    with pytest.raises(
        HTTPException,
    ) as caught:
        (
            web_server
            .start_artwork_reviewed_apply(
                "Anime",
                payload,
            )
        )

    assert (
        caught.value.status_code
        == 409
    )

    assert (
        "scan"
        in str(
            caught.value.detail
        ).lower()
    )


def test_artwork_scan_rejects_active_reviewed_apply(
    monkeypatch,
):
    monkeypatch.setattr(
        web_server,
        "load_config",
        lambda: {
            "services": {
                "artwork_manager": {
                    "enabled": True,
                },
            },
        },
    )

    monkeypatch.setattr(
        web_server,
        "ARTWORK_SCANS",
        {},
    )

    monkeypatch.setattr(
        web_server,
        "ARTWORK_ACTIVE_SCANS",
        {},
    )

    monkeypatch.setattr(
        web_server,
        "ARTWORK_APPLIES",
        {
            "apply-1": {
                "apply_id":
                    "apply-1",

                "library":
                    "Anime",

                "status":
                    "running",
            },
        },
    )

    monkeypatch.setattr(
        web_server,
        "ARTWORK_ACTIVE_APPLIES",
        {
            "Anime":
                "apply-1",
        },
    )

    with pytest.raises(
        HTTPException,
    ) as caught:
        (
            web_server
            .start_artwork_current_state_scan(
                "Anime"
            )
        )

    assert (
        caught.value.status_code
        == 409
    )

    assert (
        "apply"
        in str(
            caught.value.detail
        ).lower()
    )


def test_artwork_reviewed_apply_rejects_changed_cached_fingerprint(
    monkeypatch,
):
    monkeypatch.setattr(
        web_server,
        "load_config",
        lambda: {
            "services": {
                "artwork_manager": {
                    "enabled": True,
                },
            },
        },
    )

    monkeypatch.setattr(
        web_server,
        "load_artwork_current_state",
        lambda **kwargs:
            _reviewed_current_state(
                "newer-plan"
            ),
    )

    payload = (
        web_server
        .ArtworkReviewedApplyPayload(
            review_fingerprint=(
                "older-plan"
            )
        )
    )

    with pytest.raises(
        HTTPException,
    ) as caught:
        (
            web_server
            .start_artwork_reviewed_apply(
                "Anime",
                payload,
            )
        )

    assert (
        caught.value.status_code
        == 409
    )

    assert (
        "changed"
        in str(
            caught.value.detail
        ).lower()
    )


def test_artwork_reviewed_apply_worker_records_success(
    monkeypatch,
):
    from artwork.runner import (
        ArtworkRunOutcome,
    )

    monkeypatch.setattr(
        web_server,
        "ARTWORK_APPLIES",
        {
            "apply-1": {
                "apply_id":
                    "apply-1",

                "library":
                    "Anime",

                "review_fingerprint":
                    "reviewed-anime-plan",

                "status":
                    "running",

                "updated_at":
                    "start",
            },
        },
    )

    monkeypatch.setattr(
        web_server,
        "ARTWORK_ACTIVE_APPLIES",
        {
            "Anime":
                "apply-1",
        },
    )

    config = {
        "services": {
            "artwork_manager": {
                "enabled": True,
            },
        },
    }

    plex = object()

    monkeypatch.setattr(
        web_server,
        "load_config",
        lambda: config,
    )

    monkeypatch.setattr(
        web_server,
        "_connect_plex",
        lambda value:
            plex,
    )

    seen = {}

    def fake_run(
        **kwargs,
    ):
        seen.update(
            kwargs
        )

        callback = (
            kwargs[
                "progress_callback"
            ]
        )

        callback(
            web_server.ArtworkScanProgress(
                library="Anime",
                phase=(
                    web_server
                    .ArtworkScanPhase
                    .PLANNING
                ),
                completed=1,
                total=2,
                message=(
                    "Planning output"
                ),
            )
        )

        return SimpleNamespace(
            libraries=(
                SimpleNamespace(
                    outcome=(
                        ArtworkRunOutcome
                        .APPLIED
                    ),
                    error_type=None,
                    error_message=None,
                ),
            ),
        )

    monkeypatch.setattr(
        web_server,
        "run_configured_reviewed_artwork_manager",
        fake_run,
    )

    monkeypatch.setattr(
        web_server,
        "ARTWORK_HISTORY_DIR",
        "/data/artwork-manager",
    )

    web_server._run_artwork_reviewed_apply(
        "apply-1",
        "Anime",
        "reviewed-anime-plan",
    )

    record = (
        web_server
        .ARTWORK_APPLIES[
            "apply-1"
        ]
    )

    assert (
        record["status"]
        == "applied"
    )

    assert record[
        "finished_at"
    ] is not None

    assert record[
        "result"
    ] == {
        "outcome":
            "applied",

        "apply_mode":
            "manual",
    }

    assert record[
        "error"
    ] is None

    assert (
        record[
            "progress"
        ][
            "phase"
        ]
        == "planning"
    )

    assert (
        seen["plex"]
        is plex
    )

    assert (
        seen["config"]
        is config
    )

    assert (
        seen["library"]
        == "Anime"
    )

    assert (
        seen[
            "review_fingerprint"
        ]
        == "reviewed-anime-plan"
    )

    assert (
        seen[
            "history_directory"
        ]
        == "/data/artwork-manager"
    )

    assert (
        "Anime"
        not in
        web_server
        .ARTWORK_ACTIVE_APPLIES
    )


def test_artwork_reviewed_apply_worker_marks_stale_plan(
    monkeypatch,
):
    from artwork.runner import (
        ArtworkReviewMismatchError,
    )

    monkeypatch.setattr(
        web_server,
        "ARTWORK_APPLIES",
        {
            "apply-1": {
                "apply_id":
                    "apply-1",

                "library":
                    "Anime",

                "review_fingerprint":
                    "old-plan",

                "status":
                    "running",

                "updated_at":
                    "start",
            },
        },
    )

    monkeypatch.setattr(
        web_server,
        "ARTWORK_ACTIVE_APPLIES",
        {
            "Anime":
                "apply-1",
        },
    )

    monkeypatch.setattr(
        web_server,
        "load_config",
        lambda: {
            "services": {
                "artwork_manager": {
                    "enabled": True,
                },
            },
        },
    )

    monkeypatch.setattr(
        web_server,
        "_connect_plex",
        lambda value:
            object(),
    )

    monkeypatch.setattr(
        web_server,
        "run_configured_reviewed_artwork_manager",
        lambda **kwargs:
            (_ for _ in ())
            .throw(
                ArtworkReviewMismatchError(
                    "plan changed after review"
                )
            ),
    )

    web_server._run_artwork_reviewed_apply(
        "apply-1",
        "Anime",
        "old-plan",
    )

    record = (
        web_server
        .ARTWORK_APPLIES[
            "apply-1"
        ]
    )

    assert (
        record["status"]
        == "stale"
    )

    assert (
        record["result"]
        is None
    )

    assert (
        record[
            "error"
        ][
            "type"
        ]
        == "ArtworkReviewMismatchError"
    )

    assert (
        "Anime"
        not in
        web_server
        .ARTWORK_ACTIVE_APPLIES
    )


def test_artwork_reviewed_apply_status_unknown_is_404(
    monkeypatch,
):
    monkeypatch.setattr(
        web_server,
        "ARTWORK_APPLIES",
        {},
    )

    with pytest.raises(
        HTTPException,
    ) as caught:
        (
            web_server
            .get_artwork_reviewed_apply(
                "missing"
            )
        )

    assert (
        caught.value.status_code
        == 404
    )
