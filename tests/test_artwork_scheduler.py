from pathlib import Path
from types import SimpleNamespace


def test_scheduled_artwork_manager_uses_configured_runner(
    monkeypatch,
    tmp_path,
):
    import scheduler

    config = {
        "plex": {
            "url": "http://plex.example:32400",
            "token": "token",
        },
        "services": {
            "artwork_manager": {
                "enabled": True,
                "apply_mode": "manual",
            },
        },
    }

    monkeypatch.setattr(
        scheduler,
        "load_config",
        lambda:
            config,
    )

    monkeypatch.setattr(
        scheduler,
        "DATA_DIR",
        str(tmp_path),
    )

    plex = object()
    seen = {}

    class FakePlexServer:
        def __new__(
            cls,
            url,
            token,
        ):
            seen["plex"] = (
                url,
                token,
            )

            return plex

    import plexapi.server

    monkeypatch.setattr(
        plexapi.server,
        "PlexServer",
        FakePlexServer,
    )

    result = SimpleNamespace(
        applied_count=0,
        no_changes_count=1,
        pending_review_count=1,
        blocked_count=1,
        failed_count=0,
        libraries=(
            SimpleNamespace(
                library="Series One",
                outcome=SimpleNamespace(
                    value="blocked"
                ),
            ),
            SimpleNamespace(
                library="Series Two",
                outcome=SimpleNamespace(
                    value="pending_review"
                ),
            ),
        ),
        skipped=(),
    )

    def fake_run(
        *,
        plex,
        config,
        history_directory,
    ):
        seen["run"] = {
            "plex": plex,
            "config": config,
            "history_directory":
                history_directory,
        }

        return result

    import artwork.runtime

    monkeypatch.setattr(
        artwork.runtime,
        "run_configured_artwork_manager",
        fake_run,
    )

    assert (
        scheduler
        .run_artwork_manager_update()
        is True
    )

    assert seen["plex"] == (
        "http://plex.example:32400",
        "token",
    )

    assert (
        seen["run"]["plex"]
        is plex
    )

    assert (
        seen["run"]["config"]
        is config
    )

    assert (
        Path(
            seen["run"]
            ["history_directory"]
        )
        == (
            tmp_path
            / "artwork-manager"
        )
    )


def test_scheduler_registers_artwork_manager(
    monkeypatch,
):
    import scheduler

    config = {
        "services": {
            "artwork_manager": {
                "enabled": True,
            },
            "anime_episode_type": {
                "enabled": False,
            },
            "tv_status_tracker": {
                "enabled": False,
            },
            "size_overlay": {
                "enabled": False,
            },
        },
        "scheduler": {
            "artwork_manager": {
                "type": "daily",
                "times": [
                    "04:30",
                ],
            },
            "auto_schedule": {
                "enabled": False,
            },
        },
    }

    monkeypatch.setattr(
        scheduler,
        "load_config",
        lambda:
            config,
    )

    monkeypatch.setattr(
        scheduler.schedule,
        "clear",
        lambda:
            None,
    )

    seen = []

    def fake_setup(
        service_name,
        schedule_config,
        job_func,
    ):
        seen.append(
            (
                service_name,
                schedule_config,
                job_func,
            )
        )

        return True

    monkeypatch.setattr(
        scheduler,
        "setup_service_schedule",
        fake_setup,
    )

    assert (
        scheduler.setup_scheduler()
        is True
    )

    assert len(seen) == 1

    (
        service_name,
        schedule_config,
        job_func,
    ) = seen[0]

    assert (
        service_name
        == "artwork_manager"
    )

    assert schedule_config == {
        "type": "daily",
        "times": [
            "04:30",
        ],
    }

    assert (
        job_func
        is scheduler
        .run_artwork_manager_update
    )
