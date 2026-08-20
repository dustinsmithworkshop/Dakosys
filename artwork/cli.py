"""Command-line interface for Artwork Manager."""

from __future__ import annotations

import json
import os
from pathlib import Path

import click
import yaml
from plexapi.server import PlexServer

from artwork.apply_policy import (
    resolve_artwork_apply_mode,
)
from artwork.run_history import (
    list_artwork_run_history,
    load_latest_artwork_run,
)
from artwork.progress import (
    ArtworkScanProgress,
)
from artwork.runtime import (
    build_configured_artwork_manager_workflow,
    run_configured_artwork_manager,
)
from artwork.serialization import (
    serialize_artwork_workflow,
)
from artwork.targets import (
    MediaType,
    discover_artwork_targets,
)


def _default_config_path() -> Path:
    if os.environ.get("RUNNING_IN_DOCKER") == "true":
        return Path("/app/config/config.yaml")

    return Path("config/config.yaml")


def _default_history_directory() -> Path:
    if os.environ.get("RUNNING_IN_DOCKER") == "true":
        return Path("/app/data/artwork-manager")

    return Path("data/artwork-manager")


def _load_config(path: Path) -> dict:
    try:
        payload = yaml.safe_load(
            path.read_text(
                encoding="utf-8",
            )
        )
    except Exception as exc:
        raise RuntimeError(
            f"Could not load Dakosys config: {path}"
        ) from exc

    if not isinstance(
        payload,
        dict,
    ):
        raise RuntimeError(
            "Dakosys config must contain a YAML mapping"
        )

    return payload


def _connect_plex(config: dict):
    plex_config = (
        config.get(
            "plex",
            {},
        )
        or {}
    )

    url = str(
        plex_config.get(
            "url",
            "",
        )
        or ""
    ).strip()

    token = str(
        plex_config.get(
            "token",
            "",
        )
        or ""
    ).strip()

    if not url:
        raise RuntimeError(
            "Plex URL is not configured"
        )

    if not token:
        raise RuntimeError(
            "Plex token is not configured"
        )

    return PlexServer(
        url,
        token,
    )


def _enum_value(value):
    return getattr(
        value,
        "value",
        value,
    )


def _json(payload) -> None:
    click.echo(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
    )


def _scan_progress_reporter():
    """Build a quiet-but-visible CLI progress reporter."""

    last_phase_by_library = {}

    def report(
        progress: ArtworkScanProgress,
    ) -> None:
        phase = progress.phase.value

        previous_phase = (
            last_phase_by_library.get(
                progress.library
            )
        )

        phase_changed = (
            previous_phase != phase
        )

        last_phase_by_library[
            progress.library
        ] = phase

        completed = (
            progress.completed
        )

        total = progress.total

        # Always show phase transitions and completion.
        #
        # For large phases, report every 25 items so
        # long-running scans remain visibly alive without
        # producing thousands of terminal lines.
        should_print = (
            phase_changed
            or completed == total
            or (
                completed > 0
                and completed % 25 == 0
            )
        )

        if not should_print:
            return

        label = (
            phase.replace(
                "_",
                " ",
            )
        )

        if total > 0:
            counter = (
                f"{completed}/{total}"
            )
        else:
            counter = str(
                completed
            )

        line = (
            f"{progress.library}: "
            f"{label} "
            f"{counter}"
        )

        if progress.current_title:
            line += (
                " - "
                + progress.current_title
            )

        elif progress.message:
            line += (
                " - "
                + progress.message
            )

        click.echo(
            line,
            err=True,
        )

    return report


def _selected_libraries(
    libraries: tuple[str, ...],
):
    return (
        libraries
        if libraries
        else None
    )


def _config_from_context(ctx) -> dict:
    return _load_config(
        ctx.obj[
            "config_path"
        ]
    )


def _print_run_record(
    record: dict,
) -> None:
    summary = record[
        "summary"
    ]

    click.echo(
        f"Artwork Manager "
        f"({record['apply_mode']})"
    )

    click.echo(
        "  "
        f"{summary['applied']} applied, "
        f"{summary['no_changes']} no changes, "
        f"{summary['pending_review']} pending review, "
        f"{summary['blocked']} blocked, "
        f"{summary['failed']} failed, "
        f"{summary['skipped_count']} skipped"
    )

    for library in record[
        "libraries"
    ]:
        decision = library[
            "decision"
        ]

        line = (
            f"  {library['library']}: "
            f"{decision['outcome']}"
        )

        error = library.get(
            "error"
        )

        if error:
            line += (
                " - "
                + str(
                    error.get(
                        "message"
                    )
                )
            )

        click.echo(
            line
        )

    for skipped in record[
        "skipped"
    ]:
        click.echo(
            f"  {skipped['library']}: "
            f"skipped "
            f"({skipped['reason']})"
        )


@click.group()
@click.option(
    "--config",
    "config_path",
    type=click.Path(
        path_type=Path,
    ),
    default=None,
    help="Dakosys config.yaml path.",
)
@click.option(
    "--history-directory",
    type=click.Path(
        path_type=Path,
    ),
    default=None,
    help="Artwork Manager history directory.",
)
@click.pass_context
def cli(
    ctx,
    config_path,
    history_directory,
):
    """Dakosys Artwork Manager CLI."""

    ctx.ensure_object(
        dict
    )

    ctx.obj[
        "config_path"
    ] = (
        config_path
        or _default_config_path()
    )

    ctx.obj[
        "history_directory"
    ] = (
        history_directory
        or _default_history_directory()
    )


@cli.command()
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit JSON.",
)
@click.pass_context
def status(
    ctx,
    as_json,
):
    """Show Artwork Manager configuration and Plex targets."""

    try:
        config = (
            _config_from_context(
                ctx
            )
        )

        plex = _connect_plex(
            config
        )

        targets = tuple(
            discover_artwork_targets(
                plex,
                config,
            )
        )

        service = (
            config
            .get(
                "services",
                {},
            )
            .get(
                "artwork_manager",
                {},
            )
            or {}
        )

        schedule = (
            config
            .get(
                "scheduler",
                {},
            )
            .get(
                "artwork_manager",
            )
        )

        payload = {
            "enabled":
                bool(
                    service.get(
                        "enabled",
                        False,
                    )
                ),

            "apply_mode":
                resolve_artwork_apply_mode(
                    config
                ).value,

            "schedule":
                schedule,

            "libraries": [
                {
                    "library":
                        target.library,

                    "media_type":
                        _enum_value(
                            target.media_type
                        ),

                    "output_path":
                        str(
                            target.output_path
                        ),

                    "supported":
                        True,

                    "skip_reason":
                        None,
                }
                for target
                in targets
            ],
        }

    except Exception as exc:
        raise click.ClickException(
            str(exc)
        ) from exc

    if as_json:
        _json(
            payload
        )

        return

    click.echo(
        "Artwork Manager"
    )

    click.echo(
        f"  Enabled: "
        f"{payload['enabled']}"
    )

    click.echo(
        f"  Apply mode: "
        f"{payload['apply_mode']}"
    )

    click.echo(
        f"  Schedule: "
        f"{payload['schedule']}"
    )

    click.echo()
    click.echo(
        "Plex libraries:"
    )

    for library in payload[
        "libraries"
    ]:
        if library[
            "supported"
        ]:
            state = "supported"
        else:
            state = (
                "skipped "
                f"({library['skip_reason']})"
            )

        click.echo(
            f"  {library['library']}: "
            f"{library['media_type']} - "
            f"{state}"
        )


@cli.command()
@click.option(
    "--library",
    "libraries",
    multiple=True,
    help=(
        "Exact Plex library name. "
        "May be specified multiple times."
    ),
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit JSON.",
)
@click.pass_context
def scan(
    ctx,
    libraries,
    as_json,
):
    """Build a read-only Artwork Manager preview."""

    try:
        config = (
            _config_from_context(
                ctx
            )
        )

        plex = _connect_plex(
            config
        )

        workflow = (
            build_configured_artwork_manager_workflow(
                plex=plex,
                config=config,
                selected_libraries=(
                    _selected_libraries(
                        libraries
                    )
                ),
                progress_callback=(
                    _scan_progress_reporter()
                ),
            )
        )

        payload = (
            serialize_artwork_workflow(
                workflow
            )
        )

    except Exception as exc:
        raise click.ClickException(
            str(exc)
        ) from exc

    if as_json:
        _json(
            payload
        )

        return

    click.echo(
        "Artwork Manager READ-ONLY scan"
    )

    for library in payload[
        "libraries"
    ]:
        safety = library[
            "safety"
        ]

        output = library[
            "output"
        ]

        state = (
            "SAFE"
            if safety[
                "safe_to_apply"
            ]
            else "BLOCKED"
        )

        click.echo(
            f"  {library['library']}: "
            f"{state}, "
            f"needs_apply="
            f"{output['needs_apply']}, "
            f"changed_files="
            f"{output['changed_files']}"
        )

    for skipped in payload[
        "skipped"
    ]:
        click.echo(
            f"  {skipped['library']}: "
            f"skipped "
            f"({skipped['reason']})"
        )


@cli.command(
    name="run"
)
@click.option(
    "--library",
    "libraries",
    multiple=True,
    help=(
        "Exact Plex library name. "
        "May be specified multiple times."
    ),
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit JSON.",
)
@click.pass_context
def run_command(
    ctx,
    libraries,
    as_json,
):
    """Run Artwork Manager using configured apply_mode."""

    try:
        config = (
            _config_from_context(
                ctx
            )
        )

        plex = _connect_plex(
            config
        )

        history_directory = (
            ctx.obj[
                "history_directory"
            ]
        )

        result = (
            run_configured_artwork_manager(
                plex=plex,
                config=config,
                selected_libraries=(
                    _selected_libraries(
                        libraries
                    )
                ),
                history_directory=(
                    history_directory
                ),
            )
        )

        if result is None:
            raise RuntimeError(
                "Artwork Manager is disabled"
            )

        record = (
            load_latest_artwork_run(
                history_directory
            )
        )

        if record is None:
            raise RuntimeError(
                "Artwork Manager completed but "
                "did not persist run history"
            )

    except Exception as exc:
        raise click.ClickException(
            str(exc)
        ) from exc

    if as_json:
        _json(
            record
        )

    else:
        _print_run_record(
            record
        )

    if (
        record[
            "summary"
        ][
            "failed"
        ]
        > 0
    ):
        raise click.exceptions.Exit(
            1
        )


@cli.command()
@click.option(
    "--limit",
    type=click.IntRange(
        min=1,
    ),
    default=10,
    show_default=True,
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit JSON.",
)
@click.pass_context
def history(
    ctx,
    limit,
    as_json,
):
    """Show recent Artwork Manager runs."""

    try:
        records = (
            list_artwork_run_history(
                ctx.obj[
                    "history_directory"
                ],
                limit=limit,
            )
        )

    except Exception as exc:
        raise click.ClickException(
            str(exc)
        ) from exc

    if as_json:
        _json(
            list(
                records
            )
        )

        return

    if not records:
        click.echo(
            "No Artwork Manager history."
        )

        return

    for record in records:
        summary = record[
            "summary"
        ]

        click.echo(
            f"{record['generated_at']} "
            f"{record['apply_mode']} - "
            f"{summary['applied']} applied, "
            f"{summary['no_changes']} no changes, "
            f"{summary['pending_review']} pending, "
            f"{summary['blocked']} blocked, "
            f"{summary['failed']} failed"
        )


if __name__ == "__main__":
    cli()
