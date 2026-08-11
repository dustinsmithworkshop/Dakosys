# Dakosys automatic scheduled-anime feature

Files:
- scheduled_anime_manager.py
- install_auto_schedule.py
- config-example.yaml

Behavior:
- Generates config/scheduled-anime.yaml from Plex + AFL + Trakt.
- Active/returning series are scheduled.
- Explicitly ended/canceled series are removed.
- Ambiguous AFL/Trakt results carry forward an already-scheduled show.
- Discord sends only when list membership changes.
- Discovery failure keeps the previous generated/legacy schedule.

Install from the CURRENT repo root:

    cp scheduled_anime_manager.py ~/workdir/Dakosys/
    cp install_auto_schedule.py ~/workdir/Dakosys/
    cd ~/workdir/Dakosys
    git status --short
    python3 install_auto_schedule.py
    python3 -m py_compile scheduled_anime_manager.py anime_trakt_manager.py
    git diff --check
    git diff

Add the auto_schedule block from config-example.yaml to your LOCAL config.yaml.

Targeted test in container after rebuilding:

    cd /app
    python3 anime_trakt_manager.py refresh-schedule --force --no-notify

Inspect:

    cat /app/config/scheduled-anime.yaml

Then:

    python3 anime_trakt_manager.py refresh-schedule --force --notify

If membership did not change, no Discord notification is sent.

Normal `run-update anime_episode_type` refreshes the automatic schedule first,
subject to refresh_hours, then processes the generated list.

Keep the legacy scheduler.scheduled_anime list during migration. It acts as the
first-run/failure fallback.
