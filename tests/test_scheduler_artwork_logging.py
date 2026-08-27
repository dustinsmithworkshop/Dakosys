from types import SimpleNamespace

import artwork.runtime
import plexapi.server
import scheduler


def test_scheduled_artwork_run_writes_activity_log(
    monkeypatch,
):
    activity = []

    monkeypatch.setattr(
        scheduler,
        "load_config",
        lambda: {
            "services": {
                "artwork_manager": {
                    "enabled": True,
                },
            },
            "plex": {
                "url": "http://plex.test",
                "token": "test-token",
            },
        },
    )

    monkeypatch.setattr(
        scheduler,
        "_artwork_log",
        lambda level, message:
            activity.append(
                (level, message)
            ),
    )

    fake_plex = object()

    monkeypatch.setattr(
        plexapi.server,
        "PlexServer",
        lambda url, token:
            fake_plex,
    )

    outcome = SimpleNamespace(
        value="no_changes"
    )

    result = SimpleNamespace(
        applied_count=0,
        no_changes_count=1,
        pending_review_count=0,
        blocked_count=0,
        failed_count=0,
        skipped=[],
        libraries=[
            SimpleNamespace(
                library="TV",
                outcome=outcome,
            ),
        ],
    )

    monkeypatch.setattr(
        artwork.runtime,
        "run_configured_artwork_manager",
        lambda **kwargs:
            result,
    )

    assert (
        scheduler
        .run_artwork_manager_update()
        is True
    )

    assert (
        "INFO",
        "Scheduled run started",
    ) in activity

    assert any(
        level == "INFO"
        and "Scheduled run complete:" in message
        and "1 no changes" in message
        for level, message in activity
    )

    assert (
        "INFO",
        (
            "Scheduled library result: "
            "TV, outcome=no_changes"
        ),
    ) in activity
