#!/usr/bin/env python3

"""
Read-only TMDB fallback provider audit.

Tests Plex shows that were not exactly matched to Sonarr.

Identity strategy:
- exact Plex TMDB ID -> TMDB TV series ID

Title/year differences are reported as warnings only. They are not used
to reject an exact external-ID match because providers may model series
differently.

This script:
- reads data/sonarr_provider_audit.json
- queries TMDB TV series details
- writes data/tmdb_provider_audit.json
- does NOT modify Plex
- does NOT modify Sonarr
- does NOT call Trakt
- does NOT modify Kometa output
"""

import argparse
import json
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests


TMDB_URL = "https://api.themoviedb.org/3"


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_title(value):
    if not value:
        return ""

    return re.sub(
        r"[^a-z0-9]+",
        "",
        value.casefold(),
    )


def year_from_date(value):
    if not value:
        return None

    try:
        return int(value[:4])
    except (TypeError, ValueError):
        return None


def normalize_episode(episode):
    if not episode:
        return None

    return {
        "id": episode.get("id"),
        "name": episode.get("name"),
        "season": episode.get("season_number"),
        "episode": episode.get("episode_number"),
        "air_date": episode.get("air_date"),
        "episode_type": episode.get("episode_type"),
        "runtime": episode.get("runtime"),
    }


def normalize_show(show):
    return {
        "id": show.get("id"),
        "name": show.get("name"),
        "original_name": show.get("original_name"),
        "status": show.get("status"),
        "first_air_date": show.get("first_air_date"),
        "last_air_date": show.get("last_air_date"),
        "in_production": show.get("in_production"),
        "number_of_seasons": show.get("number_of_seasons"),
        "number_of_episodes": show.get("number_of_episodes"),
        "type": show.get("type"),
        "next_episode": normalize_episode(
            show.get("next_episode_to_air")
        ),
        "last_episode": normalize_episode(
            show.get("last_episode_to_air")
        ),
    }


def identity_warnings(plex, tmdb):
    warnings = []

    plex_title = normalize_title(
        plex.get("title")
    )

    tmdb_titles = {
        normalize_title(tmdb.get("name")),
        normalize_title(tmdb.get("original_name")),
    }

    tmdb_titles.discard("")

    if plex_title and plex_title not in tmdb_titles:
        warnings.append(
            "title_differs"
        )

    plex_year = plex.get("year")
    tmdb_year = year_from_date(
        tmdb.get("first_air_date")
    )

    if (
        plex_year is not None
        and tmdb_year is not None
        and plex_year != tmdb_year
    ):
        warnings.append(
            f"year_differs:{plex_year}->{tmdb_year}"
        )

    return warnings


def fetch_tmdb_show(session, tmdb_id):
    response = session.get(
        f"{TMDB_URL}/tv/{tmdb_id}",
        timeout=30,
    )

    if response.status_code == 404:
        return None, "not_found"

    response.raise_for_status()

    return response.json(), None


def print_report(report):
    summary = report["summary"]

    print()
    print("TMDB FALLBACK PROVIDER AUDIT")
    print("=" * 60)
    print(
        f"Fallback candidates:       "
        f"{summary['candidates']}"
    )
    print(
        f"With Plex TMDB ID:         "
        f"{summary['with_tmdb_id']}"
    )
    print(
        f"Matched in TMDB:           "
        f"{summary['matched']}"
    )
    print(
        f"Unmatched in TMDB:         "
        f"{summary['unmatched']}"
    )
    print(
        f"Identity warnings:         "
        f"{summary['identity_warning_count']}"
    )
    print(
        f"With next episode:         "
        f"{summary['with_next_episode']}"
    )
    print(
        f"Without next episode:      "
        f"{summary['without_next_episode']}"
    )

    print()
    print("RAW TMDB STATUS VALUES")
    print("=" * 60)

    if summary["statuses"]:
        for status, count in summary["statuses"].items():
            print(f"{status!r:25} {count}")
    else:
        print("No matches.")

    print()
    print("RESULTS")
    print("=" * 60)

    for item in report["shows"]:
        plex = item["plex"]

        year = (
            f" ({plex['year']})"
            if plex.get("year")
            else ""
        )

        print()
        print(
            f"{plex['library']}: "
            f"{plex['title']}{year}"
        )

        print(
            f"  TMDB lookup: "
            f"{plex.get('tmdb_id')}"
        )

        if not item["matched"]:
            print(
                f"  TMDB: NOT FOUND "
                f"({item['reason']})"
            )
            continue

        tmdb = item["tmdb"]

        print(
            f"  TMDB: {tmdb['name']} "
            f"[id={tmdb['id']}]"
        )

        if (
            tmdb.get("original_name")
            and tmdb["original_name"]
            != tmdb["name"]
        ):
            print(
                f"  original: "
                f"{tmdb['original_name']}"
            )

        print(
            f"  first aired: "
            f"{tmdb['first_air_date']}"
        )

        print(
            f"  status: "
            f"{tmdb['status']}"
        )

        print(
            f"  in production: "
            f"{tmdb['in_production']}"
        )

        if item["identity_warnings"]:
            print(
                "  identity warnings: "
                + ", ".join(
                    item["identity_warnings"]
                )
            )

        ep = tmdb.get("next_episode")

        if ep:
            print(
                f"  next: "
                f"S{ep['season']:02d}"
                f"E{ep['episode']:02d} "
                f"{ep['air_date']} "
                f"{ep['name']}"
            )

            if ep.get("episode_type"):
                print(
                    f"  episode type: "
                    f"{ep['episode_type']}"
                )
        else:
            print("  next: none")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Audit TMDB coverage for Plex shows "
            "not matched to Sonarr."
        )
    )

    parser.add_argument(
        "--sonarr-report",
        type=Path,
        default=Path(
            "data/sonarr_provider_audit.json"
        ),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "data/tmdb_provider_audit.json"
        ),
    )

    args = parser.parse_args()

    token = os.environ.get("TMDB_TOKEN")

    if not token:
        raise SystemExit(
            "TMDB_TOKEN environment variable "
            "is not set."
        )

    if not args.sonarr_report.exists():
        raise SystemExit(
            f"Sonarr audit not found: "
            f"{args.sonarr_report}"
        )

    sonarr_report = load_json(
        args.sonarr_report
    )

    candidates = [
        item
        for item in sonarr_report["shows"]
        if not item["match"]["matched"]
    ]

    print(
        f"Testing {len(candidates)} "
        f"Sonarr fallback candidates..."
    )

    session = requests.Session()
    session.headers.update(
        {
            "Authorization": (
                f"Bearer {token}"
            ),
            "Accept": "application/json",
        }
    )

    results = []

    for index, item in enumerate(
        candidates,
        1,
    ):
        plex = item["plex"]

        print(
            f"[{index}/{len(candidates)}] "
            f"{plex['title']}..."
        )

        tmdb_id = plex.get("tmdb_id")

        if tmdb_id is None:
            results.append(
                {
                    "plex": plex,
                    "matched": False,
                    "reason": "no_plex_tmdb_id",
                    "identity_warnings": [],
                    "tmdb": None,
                }
            )
            continue

        try:
            raw_show, reason = fetch_tmdb_show(
                session,
                tmdb_id,
            )

            if raw_show is None:
                results.append(
                    {
                        "plex": plex,
                        "matched": False,
                        "reason": reason,
                        "identity_warnings": [],
                        "tmdb": None,
                    }
                )
                continue

            tmdb = normalize_show(
                raw_show
            )

            warnings = identity_warnings(
                plex,
                tmdb,
            )

            results.append(
                {
                    "plex": plex,
                    "matched": True,
                    "reason": None,
                    "identity_warnings": warnings,
                    "tmdb": tmdb,
                }
            )

        except requests.RequestException as exc:
            results.append(
                {
                    "plex": plex,
                    "matched": False,
                    "reason": (
                        f"request_error: {exc}"
                    ),
                    "identity_warnings": [],
                    "tmdb": None,
                }
            )

        time.sleep(0.10)

    matched = [
        item
        for item in results
        if item["matched"]
    ]

    with_next = [
        item
        for item in matched
        if item["tmdb"].get("next_episode")
    ]

    warning_count = sum(
        1
        for item in matched
        if item["identity_warnings"]
    )

    status_counts = Counter(
        item["tmdb"].get("status")
        for item in matched
    )

    report = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "summary": {
            "candidates": len(results),
            "with_tmdb_id": sum(
                1
                for item in results
                if item["plex"].get(
                    "tmdb_id"
                )
            ),
            "matched": len(matched),
            "unmatched": (
                len(results) - len(matched)
            ),
            "identity_warning_count": (
                warning_count
            ),
            "with_next_episode": len(
                with_next
            ),
            "without_next_episode": (
                len(matched) - len(with_next)
            ),
            "statuses": dict(
                status_counts.most_common()
            ),
        },
        "shows": results,
    }

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with args.output.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            report,
            handle,
            indent=2,
            ensure_ascii=False,
        )

    print_report(report)

    print()
    print(
        f"Report written to: "
        f"{args.output}"
    )


if __name__ == "__main__":
    main()
