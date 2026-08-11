#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import io
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import requests
import yaml
import trakt_auth

logger = logging.getLogger("scheduled_anime_manager")

TRAKT_API = "https://api.trakt.tv"
DEFAULT_ACTIVE_STATUSES = {
    "returning series",
    "in production",
    "planned",
    "continuing",
}
DEFAULT_INACTIVE_STATUSES = {
    "ended",
    "canceled",
    "cancelled",
}


def _docker_mode() -> bool:
    return os.environ.get("RUNNING_IN_DOCKER") == "true"


def _default_schedule_path() -> Path:
    return (
        Path("/app/config/scheduled-anime.yaml")
        if _docker_mode()
        else Path("config/scheduled-anime.yaml")
    )


def _resolve_schedule_path(config: dict[str, Any]) -> Path:
    auto = config.get("scheduler", {}).get("auto_schedule", {}) or {}
    raw = str(auto.get("file") or "").strip()
    if not raw:
        return _default_schedule_path()

    path = Path(raw)
    if path.is_absolute():
        return path

    if _docker_mode():
        return Path("/app") / path

    return path


def _quiet_call(func, *args, **kwargs):
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        return func(*args, **kwargs)


def _get_afl_catalog() -> list[str]:
    command = [sys.executable, "anime_trakt_manager.py", "list-anime"]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    combined = "\n".join(
        part for part in (result.stdout, result.stderr) if part
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"`{' '.join(command)}` failed with exit code {result.returncode}: "
            f"{combined[-1500:]}"
        )

    pattern = re.compile(
        r"^\s*\d+\.\s+(.+?)(?:\s+\(Mapped to: .+\))?\s*$"
    )
    slugs: list[str] = []
    for line in combined.splitlines():
        match = pattern.match(line)
        if match:
            slugs.append(match.group(1).strip())

    if not slugs:
        raise RuntimeError("No AnimeFillerList entries could be parsed.")

    return list(dict.fromkeys(slugs))


def _get_tmdb_id(show) -> Optional[str]:
    for guid in getattr(show, "guids", []) or []:
        guid_id = getattr(guid, "id", "")
        if guid_id.startswith("tmdb://"):
            return guid_id.split("://", 1)[1]
    return None


def _trakt_show_by_tmdb(
    tmdb_id: str,
    headers: dict[str, str],
) -> tuple[Optional[dict[str, Any]], str]:
    search = requests.get(
        f"{TRAKT_API}/search/tmdb/{tmdb_id}",
        headers=headers,
        params={"type": "show"},
        timeout=30,
    )
    if search.status_code != 200:
        return None, f"Trakt TMDB search HTTP {search.status_code}"

    items = search.json()
    show_obj = next(
        (
            item.get("show")
            for item in items
            if item.get("type") == "show" and item.get("show")
        ),
        None,
    )
    if not show_obj:
        return None, "No Trakt show found for TMDB ID"

    trakt_id = (show_obj.get("ids") or {}).get("trakt")
    if not trakt_id:
        return None, "Trakt show has no Trakt ID"

    summary = requests.get(
        f"{TRAKT_API}/shows/{trakt_id}",
        headers=headers,
        params={"extended": "full"},
        timeout=30,
    )
    if summary.status_code != 200:
        return None, f"Trakt show summary HTTP {summary.status_code}"

    return summary.json(), ""


def _normalize_statuses(values: Any, defaults: set[str]) -> set[str]:
    if not values:
        return set(defaults)
    return {
        str(value).strip().lower()
        for value in values
        if str(value).strip()
    }


def _load_generated(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return {}


def load_scheduled_anime(
    config: dict[str, Any],
    *,
    fallback_to_config: bool = True,
) -> list[str]:
    generated = _load_generated(_resolve_schedule_path(config))
    scheduled = generated.get("scheduled_anime")
    if isinstance(scheduled, list):
        return [str(item) for item in scheduled if str(item).strip()]

    if fallback_to_config:
        legacy = config.get("scheduler", {}).get("scheduled_anime", []) or []
        return [str(item) for item in legacy if str(item).strip()]

    return []


def _parse_generated_at(data: dict[str, Any]) -> Optional[datetime]:
    raw = str(data.get("generated_at") or "").strip()
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _notification_webhook(config: dict[str, Any]) -> str:
    notifications = config.get("notifications", {}) or {}
    discord = notifications.get("discord", {}) or {}

    candidates = [
        os.getenv("DISCORD_WEBHOOK_URL"),
        os.getenv("DISCORD_WEBHOOK"),
        notifications.get("webhook_url"),
        notifications.get("webhook"),
        notifications.get("discord_webhook_url"),
        notifications.get("discord_webhook"),
        discord.get("webhook_url") if isinstance(discord, dict) else None,
        discord.get("webhook") if isinstance(discord, dict) else None,
    ]
    return next(
        (
            str(value).strip()
            for value in candidates
            if value and str(value).strip()
        ),
        "",
    )


def _notifications_enabled(config: dict[str, Any]) -> bool:
    notifications = config.get("notifications", {}) or {}
    return bool(notifications.get("enabled", False))


def _send_change_notification(
    config: dict[str, Any],
    *,
    path: Path,
    added: list[str],
    removed: list[str],
    total: int,
) -> bool:
    auto = config.get("scheduler", {}).get("auto_schedule", {}) or {}
    if not auto.get("notify_on_change", True):
        return False
    if not _notifications_enabled(config):
        return False

    webhook = _notification_webhook(config)
    if not webhook:
        logger.warning(
            "Scheduled anime changed, but Discord notifications are enabled "
            "and no webhook URL could be resolved."
        )
        return False

    def field_lines(items: list[str]) -> str:
        if not items:
            return "None"
        shown = items[:20]
        text = "\n".join(f"• `{item}`" for item in shown)
        if len(items) > len(shown):
            text += f"\n… and {len(items) - len(shown)} more"
        return text

    embed = {
        "title": "Dakosys Scheduled Anime Updated",
        "description": (
            f"`{path.name}` changed automatically from Plex + "
            "AnimeFillerList + Trakt status."
        ),
        "fields": [
            {
                "name": f"Added ({len(added)})",
                "value": field_lines(added),
                "inline": False,
            },
            {
                "name": f"Removed ({len(removed)})",
                "value": field_lines(removed),
                "inline": False,
            },
            {
                "name": "Scheduled total",
                "value": str(total),
                "inline": True,
            },
        ],
        "footer": {"text": "Dakosys automatic anime scheduler"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    payload = {
        "username": "Dakosys",
        "embeds": [embed],
        "allowed_mentions": {"parse": []},
    }

    response = requests.post(
        webhook,
        params={"wait": "true"},
        json=payload,
        timeout=30,
    )
    if response.status_code not in {200, 204}:
        raise RuntimeError(
            f"Discord webhook failed: HTTP {response.status_code}: "
            f"{response.text[:300]}"
        )
    return True


def _write_generated(
    path: Path,
    *,
    scheduled: list[str],
    active: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    stats: dict[str, int],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "_comment": (
            "Generated automatically by Dakosys. "
            "Do not edit scheduled_anime here; use scheduler.auto_schedule "
            "overrides in config.yaml."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "Plex + AnimeFillerList + Trakt",
        "scheduled_anime": scheduled,
        "shows": {
            item["slug"]: {
                "plex_title": item.get("plex_title", ""),
                "trakt_title": item.get("trakt_title", ""),
                "trakt_status": item.get("trakt_status", ""),
                "decision": item.get("decision", ""),
            }
            for item in sorted(active, key=lambda row: row["slug"])
        },
        "review": {
            item["slug"]: {
                "plex_title": item.get("plex_title", ""),
                "reason": item.get("reason", ""),
                "carried_forward": bool(item.get("carried_forward", False)),
            }
            for item in sorted(reviews, key=lambda row: row["slug"])
        },
        "stats": stats,
    }

    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(
            data,
            handle,
            sort_keys=False,
            allow_unicode=True,
        )
    temp.replace(path)


def refresh_scheduled_anime(
    config: dict[str, Any],
    *,
    force: bool = False,
    notify: bool = True,
) -> dict[str, Any]:
    import anime_trakt_manager as atm

    auto = config.get("scheduler", {}).get("auto_schedule", {}) or {}
    path = _resolve_schedule_path(config)
    previous_data = _load_generated(path)
    previous = set(load_scheduled_anime(config, fallback_to_config=True))

    refresh_hours = float(auto.get("refresh_hours", 24) or 24)
    generated_at = _parse_generated_at(previous_data)
    if (
        not force
        and generated_at is not None
        and datetime.now(timezone.utc) - generated_at
        < timedelta(hours=refresh_hours)
    ):
        return {
            "success": True,
            "changed": False,
            "scheduled_anime": sorted(previous),
            "added": [],
            "removed": [],
            "path": str(path),
            "skipped": True,
            "error": "",
        }

    active_statuses = _normalize_statuses(
        auto.get("active_statuses"),
        DEFAULT_ACTIVE_STATUSES,
    )
    inactive_statuses = _normalize_statuses(
        auto.get("inactive_statuses"),
        DEFAULT_INACTIVE_STATUSES,
    )
    always_include = {
        str(item).strip()
        for item in (auto.get("always_include", []) or [])
        if str(item).strip()
    }
    always_exclude = {
        str(item).strip()
        for item in (auto.get("always_exclude", []) or [])
        if str(item).strip()
    }

    try:
        plex = _quiet_call(atm.connect_to_plex)
        if plex is None:
            raise RuntimeError("Could not connect to Plex")

        access_token = trakt_auth.ensure_trakt_auth(quiet=True)
        if not access_token:
            raise RuntimeError("Could not obtain Trakt access token")

        headers = trakt_auth.get_trakt_headers(access_token)
        if not headers:
            raise RuntimeError("Could not build Trakt request headers")

        slugs = _get_afl_catalog()
    except Exception as exc:
        logger.error("Automatic scheduled-anime refresh failed: %s", exc)
        return {
            "success": False,
            "changed": False,
            "scheduled_anime": sorted(previous),
            "added": [],
            "removed": [],
            "path": str(path),
            "skipped": False,
            "error": str(exc),
        }

    recommended: set[str] = set()
    resolved_plex_slugs: set[str] = set()
    active_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []

    stats = {
        "afl_catalog": len(slugs),
        "plex_afl_matches": 0,
        "afl_valid": 0,
        "active_or_returning": 0,
        "inactive": 0,
        "review": 0,
        "carried_forward": 0,
    }

    for slug in slugs:
        show = _quiet_call(atm.get_plex_anime_show, plex, slug)
        if not show:
            continue

        resolved_plex_slugs.add(slug)
        stats["plex_afl_matches"] += 1

        if slug in always_exclude:
            continue

        plex_title = str(getattr(show, "title", "") or slug)

        episodes = _quiet_call(
            atm.get_anime_episodes,
            slug,
            None,
            silent=True,
        )
        if not episodes:
            carried = slug in previous
            if carried:
                recommended.add(slug)
                stats["carried_forward"] += 1
            stats["review"] += 1
            review_rows.append(
                {
                    "slug": slug,
                    "plex_title": plex_title,
                    "reason": (
                        "AFL returned no episodes or failed identity validation"
                    ),
                    "carried_forward": carried,
                }
            )
            continue

        stats["afl_valid"] += 1

        tmdb_id = _get_tmdb_id(show)
        if not tmdb_id:
            tmdb_id = _quiet_call(atm.get_tmdb_id_from_plex, plex, slug)

        if not tmdb_id:
            carried = slug in previous
            if carried:
                recommended.add(slug)
                stats["carried_forward"] += 1
            stats["review"] += 1
            review_rows.append(
                {
                    "slug": slug,
                    "plex_title": plex_title,
                    "reason": "Plex show has no resolvable TMDB ID",
                    "carried_forward": carried,
                }
            )
            continue

        try:
            trakt_show, error = _trakt_show_by_tmdb(
                str(tmdb_id),
                headers,
            )
        except requests.RequestException as exc:
            trakt_show, error = None, f"Trakt request failed: {exc}"

        if not trakt_show:
            carried = slug in previous
            if carried:
                recommended.add(slug)
                stats["carried_forward"] += 1
            stats["review"] += 1
            review_rows.append(
                {
                    "slug": slug,
                    "plex_title": plex_title,
                    "reason": error or "Could not retrieve Trakt metadata",
                    "carried_forward": carried,
                }
            )
            continue

        status = str(trakt_show.get("status") or "").strip()
        normalized = status.lower()

        if slug in always_include:
            decision = "always_include"
            recommended.add(slug)
        elif normalized in active_statuses:
            decision = "active"
            recommended.add(slug)
        elif normalized in inactive_statuses:
            stats["inactive"] += 1
            continue
        else:
            carried = slug in previous
            if carried:
                recommended.add(slug)
                stats["carried_forward"] += 1
            stats["review"] += 1
            review_rows.append(
                {
                    "slug": slug,
                    "plex_title": plex_title,
                    "reason": (
                        f"Unrecognized/ambiguous Trakt status: {status!r}"
                    ),
                    "carried_forward": carried,
                }
            )
            continue

        stats["active_or_returning"] += 1
        active_rows.append(
            {
                "slug": slug,
                "plex_title": plex_title,
                "trakt_title": str(trakt_show.get("title") or ""),
                "trakt_status": status,
                "decision": decision,
            }
        )

    for slug in sorted(always_include - resolved_plex_slugs):
        stats["review"] += 1
        review_rows.append(
            {
                "slug": slug,
                "plex_title": "",
                "reason": (
                    "always_include requested, but show did not resolve in "
                    "the Plex/AFL intersection"
                ),
                "carried_forward": False,
            }
        )

    recommended -= always_exclude
    scheduled = sorted(recommended)
    current = set(scheduled)

    added = sorted(current - previous)
    removed = sorted(previous - current)
    changed = bool(added or removed)

    _write_generated(
        path,
        scheduled=scheduled,
        active=active_rows,
        reviews=review_rows,
        stats=stats,
    )

    if changed:
        logger.info(
            "Scheduled anime changed: +%d -%d (%d total)",
            len(added),
            len(removed),
            len(scheduled),
        )
        if notify:
            try:
                _send_change_notification(
                    config,
                    path=path,
                    added=added,
                    removed=removed,
                    total=len(scheduled),
                )
            except Exception as exc:
                logger.error(
                    "Failed to send scheduled-anime Discord notification: %s",
                    exc,
                )

    return {
        "success": True,
        "changed": changed,
        "scheduled_anime": scheduled,
        "added": added,
        "removed": removed,
        "path": str(path),
        "skipped": False,
        "error": "",
        "stats": stats,
    }
