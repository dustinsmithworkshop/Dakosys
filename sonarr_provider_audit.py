#!/usr/bin/env python3

"""
Read-only Sonarr provider coverage audit.

Compares the Plex identity audit against Sonarr using exact TVDB IDs.

This script:
- reads data/plex_identity_audit.json
- reads all Sonarr series via GET /api/v3/series
- matches Plex -> Sonarr by exact TVDB ID
- writes data/sonarr_provider_audit.json
- does NOT modify Plex
- does NOT modify Sonarr
- does NOT call Trakt
- does NOT modify TV Status or Kometa output
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests


def percentage(value, total):
    if not total:
        return 0.0
    return round((value / total) * 100, 2)


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_tvdb_id(value):
    if value in (None, "", 0, "0"):
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def fetch_sonarr_series(base_url, api_key):
    url = f"{base_url.rstrip('/')}/api/v3/series"

    response = requests.get(
        url,
        headers={"X-Api-Key": api_key},
        timeout=60,
    )

    response.raise_for_status()

    data = response.json()

    if not isinstance(data, list):
        raise ValueError(
            f"Expected Sonarr /api/v3/series to return a list, "
            f"got {type(data).__name__}"
        )

    return data


def build_sonarr_index(series):
    by_tvdb = defaultdict(list)

    for item in series:
        tvdb_id = normalize_tvdb_id(item.get("tvdbId"))

        if tvdb_id is not None:
            by_tvdb[tvdb_id].append(item)

    return by_tvdb


def summarize(shows):
    total = len(shows)

    eligible = sum(
        1 for show in shows
        if show["plex"]["tvdb_id"] is not None
    )

    matched = sum(
        1 for show in shows
        if show["match"]["matched"]
    )

    unmatched = sum(
        1 for show in shows
        if (
            show["plex"]["tvdb_id"] is not None
            and not show["match"]["matched"]
        )
    )

    no_tvdb = sum(
        1 for show in shows
        if show["plex"]["tvdb_id"] is None
    )

    return {
        "plex_shows": total,
        "eligible_for_tvdb_match": eligible,
        "matched": matched,
        "matched_percent_of_all": percentage(matched, total),
        "matched_percent_of_eligible": percentage(matched, eligible),
        "unmatched_with_tvdb": unmatched,
        "no_plex_tvdb_id": no_tvdb,
    }


def print_summary(report):
    summary = report["summary"]

    print()
    print("SONARR PROVIDER COVERAGE AUDIT")
    print("=" * 46)
    print(f"Plex shows:                 {summary['plex_shows']:5}")
    print(f"Sonarr series:              {report['sonarr']['series_count']:5}")
    print()
    print(
        f"Eligible for TVDB match:    "
        f"{summary['eligible_for_tvdb_match']:5}"
    )
    print(
        f"Matched in Sonarr:          "
        f"{summary['matched']:5}"
        f"  ({summary['matched_percent_of_all']:6.2f}% of Plex)"
    )
    print(
        f"Match rate when eligible:   "
        f"{summary['matched_percent_of_eligible']:6.2f}%"
    )
    print(
        f"TVDB ID but not in Sonarr:  "
        f"{summary['unmatched_with_tvdb']:5}"
    )
    print(
        f"No Plex TVDB ID:            "
        f"{summary['no_plex_tvdb_id']:5}"
    )

    print()
    print("BY LIBRARY")
    print("=" * 46)

    for library_name, lib in report["libraries"].items():
        print()
        print(f"{library_name}")
        print(f"  Plex shows:               {lib['plex_shows']}")
        print(
            f"  Eligible:                 "
            f"{lib['eligible_for_tvdb_match']}"
        )
        print(
            f"  Matched:                  "
            f"{lib['matched']} "
            f"({lib['matched_percent_of_all']:.2f}% of Plex)"
        )
        print(
            f"  Eligible match rate:      "
            f"{lib['matched_percent_of_eligible']:.2f}%"
        )
        print(
            f"  TVDB but not in Sonarr:   "
            f"{lib['unmatched_with_tvdb']}"
        )
        print(
            f"  No Plex TVDB ID:          "
            f"{lib['no_plex_tvdb_id']}"
        )

    unmatched = [
        show
        for show in report["shows"]
        if (
            show["plex"]["tvdb_id"] is not None
            and not show["match"]["matched"]
        )
    ]

    if unmatched:
        print()
        print("PLEX SHOWS NOT FOUND IN SONARR")
        print("=" * 46)

        for show in unmatched[:50]:
            year = (
                f" ({show['plex']['year']})"
                if show["plex"]["year"]
                else ""
            )

            print(
                f"- {show['plex']['library']}: "
                f"{show['plex']['title']}{year} "
                f"[TVDB {show['plex']['tvdb_id']}]"
            )

        if len(unmatched) > 50:
            print(
                f"... and {len(unmatched) - 50} more; "
                "see JSON report."
            )

    no_tvdb = [
        show
        for show in report["shows"]
        if show["plex"]["tvdb_id"] is None
    ]

    if no_tvdb:
        print()
        print("PLEX SHOWS WITHOUT TVDB ID")
        print("=" * 46)

        for show in no_tvdb:
            print(
                f"- {show['plex']['library']}: "
                f"{show['plex']['title']} "
                f"TMDB={show['plex']['tmdb_id']} "
                f"IMDb={show['plex']['imdb_id']}"
            )

    if report["sonarr"]["duplicate_tvdb_ids"]:
        print()
        print("DUPLICATE TVDB IDs IN SONARR")
        print("=" * 46)

        for item in report["sonarr"]["duplicate_tvdb_ids"]:
            print(
                f"- TVDB {item['tvdb_id']}: "
                f"{', '.join(item['titles'])}"
            )


def main():
    parser = argparse.ArgumentParser(
        description="Audit exact Plex-to-Sonarr TVDB coverage."
    )

    parser.add_argument(
        "--plex-report",
        type=Path,
        default=Path("data/plex_identity_audit.json"),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/sonarr_provider_audit.json"),
    )

    args = parser.parse_args()

    sonarr_url = os.environ.get("SONARR_URL")
    sonarr_api_key = os.environ.get("SONARR_API_KEY")

    if not sonarr_url:
        raise SystemExit("SONARR_URL environment variable is not set.")

    if not sonarr_api_key:
        raise SystemExit(
            "SONARR_API_KEY environment variable is not set."
        )

    if not args.plex_report.exists():
        raise SystemExit(
            f"Plex identity report not found: {args.plex_report}"
        )

    plex_report = load_json(args.plex_report)

    print(f"Loading Plex identities from {args.plex_report}...")
    plex_shows = plex_report.get("shows", [])

    print(
        f"Fetching Sonarr series from "
        f"{sonarr_url.rstrip('/')}..."
    )

    try:
        sonarr_series = fetch_sonarr_series(
            sonarr_url,
            sonarr_api_key,
        )
    except requests.RequestException as exc:
        raise SystemExit(
            f"Failed to fetch Sonarr series: {exc}"
        )

    print(f"Sonarr returned {len(sonarr_series)} series.")

    sonarr_by_tvdb = build_sonarr_index(sonarr_series)

    results = []

    for plex_show in plex_shows:
        ids = plex_show.get("ids", {})

        tvdb_id = normalize_tvdb_id(ids.get("tvdb"))

        matches = (
            sonarr_by_tvdb.get(tvdb_id, [])
            if tvdb_id is not None
            else []
        )

        sonarr_match = matches[0] if len(matches) == 1 else None

        results.append(
            {
                "plex": {
                    "library": plex_show.get("library"),
                    "library_roles": plex_show.get(
                        "library_roles",
                        [],
                    ),
                    "title": plex_show.get("title"),
                    "year": plex_show.get("year"),
                    "rating_key": plex_show.get(
                        "plex_rating_key"
                    ),
                    "tmdb_id": ids.get("tmdb"),
                    "tvdb_id": tvdb_id,
                    "imdb_id": ids.get("imdb"),
                },
                "match": {
                    "matched": len(matches) == 1,
                    "candidate_count": len(matches),
                },
                "sonarr": (
                    {
                        "id": sonarr_match.get("id"),
                        "title": sonarr_match.get("title"),
                        "year": sonarr_match.get("year"),
                        "tvdb_id": normalize_tvdb_id(
                            sonarr_match.get("tvdbId")
                        ),
                        "status": sonarr_match.get("status"),
                        "ended": sonarr_match.get("ended"),
                        "monitored": sonarr_match.get(
                            "monitored"
                        ),
                        "season_count": (
                            len(
                                sonarr_match.get(
                                    "seasons",
                                    [],
                                )
                            )
                        ),
                    }
                    if sonarr_match
                    else None
                ),
            }
        )

    duplicate_tvdb_ids = []

    for tvdb_id, matches in sonarr_by_tvdb.items():
        if len(matches) > 1:
            duplicate_tvdb_ids.append(
                {
                    "tvdb_id": tvdb_id,
                    "titles": [
                        item.get("title", "<unknown>")
                        for item in matches
                    ],
                }
            )

    per_library = {}

    libraries = sorted(
        {
            show["plex"]["library"]
            for show in results
            if show["plex"]["library"]
        }
    )

    for library_name in libraries:
        library_results = [
            show
            for show in results
            if show["plex"]["library"] == library_name
        ]

        per_library[library_name] = summarize(
            library_results
        )

    matched_sonarr_ids = {
        show["sonarr"]["id"]
        for show in results
        if show["sonarr"] is not None
    }

    sonarr_only = [
        {
            "id": item.get("id"),
            "title": item.get("title"),
            "year": item.get("year"),
            "tvdb_id": normalize_tvdb_id(
                item.get("tvdbId")
            ),
            "status": item.get("status"),
        }
        for item in sonarr_series
        if item.get("id") not in matched_sonarr_ids
    ]

    report = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "sonarr": {
            "url": sonarr_url,
            "series_count": len(sonarr_series),
            "unique_tvdb_ids": len(sonarr_by_tvdb),
            "duplicate_tvdb_ids": duplicate_tvdb_ids,
            "unmatched_series_count": len(sonarr_only),
            "unmatched_series": sonarr_only,
        },
        "summary": summarize(results),
        "libraries": per_library,
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

    print_summary(report)

    print()
    print(f"Report written to: {args.output}")


if __name__ == "__main__":
    main()
