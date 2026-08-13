#!/usr/bin/env python3

"""
Read-only TVmaze fallback provider audit.

Tests only Plex shows that were not exactly matched to Sonarr.

Identity strategy:
1. TVDB exact lookup when Plex has a TVDB ID.
2. IMDb exact lookup when TVDB is unavailable.

No fuzzy title matching is performed.

This script:
- reads data/sonarr_provider_audit.json
- queries the public TVmaze API
- writes data/tvmaze_provider_audit.json
- does NOT modify Plex
- does NOT modify Sonarr
- does NOT call Trakt
- does NOT modify Kometa output
"""

import argparse
import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests


TVMAZE_URL = "https://api.tvmaze.com"


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def lookup_tvmaze_show(session, plex):
    tvdb_id = plex.get("tvdb_id")
    imdb_id = plex.get("imdb_id")

    if tvdb_id:
        source = "tvdb"
        value = str(tvdb_id)
        params = {"thetvdb": value}

    elif imdb_id:
        source = "imdb"
        value = str(imdb_id)
        params = {"imdb": value}

    else:
        return {
            "matched": False,
            "lookup_source": None,
            "lookup_value": None,
            "reason": "no_supported_external_id",
            "show": None,
        }

    response = session.get(
        f"{TVMAZE_URL}/lookup/shows",
        params=params,
        timeout=30,
    )

    if response.status_code == 404:
        return {
            "matched": False,
            "lookup_source": source,
            "lookup_value": value,
            "reason": "not_found",
            "show": None,
        }

    response.raise_for_status()

    show = response.json()

    tvmaze_id = show.get("id")

    if tvmaze_id is None:
        return {
            "matched": False,
            "lookup_source": source,
            "lookup_value": value,
            "reason": "lookup_missing_tvmaze_id",
            "show": None,
        }

    # Lookup redirects intentionally do not preserve embed parameters,
    # so resolve the TVmaze ID first, then fetch the show directly.
    detail_response = session.get(
        f"{TVMAZE_URL}/shows/{tvmaze_id}",
        params={"embed": "nextepisode"},
        timeout=30,
    )

    detail_response.raise_for_status()

    return {
        "matched": True,
        "lookup_source": source,
        "lookup_value": value,
        "reason": None,
        "show": detail_response.json(),
    }


def normalize_show(show):
    embedded = show.get("_embedded") or {}
    next_episode = embedded.get("nextepisode")

    externals = show.get("externals") or {}

    result = {
        "id": show.get("id"),
        "name": show.get("name"),
        "status": show.get("status"),
        "premiered": show.get("premiered"),
        "ended": show.get("ended"),
        "type": show.get("type"),
        "language": show.get("language"),
        "tvdb_id": externals.get("thetvdb"),
        "imdb_id": externals.get("imdb"),
        "next_episode": None,
    }

    if next_episode:
        result["next_episode"] = {
            "id": next_episode.get("id"),
            "name": next_episode.get("name"),
            "season": next_episode.get("season"),
            "episode": next_episode.get("number"),
            "type": next_episode.get("type"),
            "airdate": next_episode.get("airdate"),
            "airtime": next_episode.get("airtime"),
            "airstamp": next_episode.get("airstamp"),
        }

    return result


def print_report(report):
    summary = report["summary"]

    print()
    print("TVMAZE FALLBACK PROVIDER AUDIT")
    print("=" * 60)
    print(
        f"Fallback candidates:       "
        f"{summary['candidates']}"
    )
    print(
        f"Matched in TVmaze:         "
        f"{summary['matched']}"
    )
    print(
        f"Unmatched in TVmaze:       "
        f"{summary['unmatched']}"
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
    print("RAW TVMAZE STATUS VALUES")
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
        lookup = item["lookup"]

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
            f"  lookup: "
            f"{lookup['source']}="
            f"{lookup['value']}"
        )

        if not item["matched"]:
            print(
                f"  TVmaze: NOT FOUND "
                f"({item['reason']})"
            )
            continue

        tvmaze = item["tvmaze"]

        print(
            f"  TVmaze: {tvmaze['name']} "
            f"[id={tvmaze['id']}]"
        )
        print(
            f"  status: {tvmaze['status']}"
        )

        ep = tvmaze.get("next_episode")

        if ep:
            print(
                f"  next: "
                f"S{ep['season']:02d}"
                f"E{ep['episode']:02d} "
                f"{ep['airstamp']} "
                f"{ep['name']}"
            )
        else:
            print("  next: none")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Audit TVmaze coverage for Plex shows "
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
            "data/tvmaze_provider_audit.json"
        ),
    )

    args = parser.parse_args()

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
            "Accept": "application/json",
            "User-Agent": (
                "Dakosys-TV-Metadata-Provider-Audit"
            ),
        }
    )

    results = []

    for index, item in enumerate(candidates, 1):
        plex = item["plex"]

        print(
            f"[{index}/{len(candidates)}] "
            f"{plex['title']}..."
        )

        try:
            lookup = lookup_tvmaze_show(
                session,
                plex,
            )

            if lookup["matched"]:
                normalized = normalize_show(
                    lookup["show"]
                )
            else:
                normalized = None

            results.append(
                {
                    "plex": plex,
                    "matched": lookup["matched"],
                    "reason": lookup["reason"],
                    "lookup": {
                        "source": lookup[
                            "lookup_source"
                        ],
                        "value": lookup[
                            "lookup_value"
                        ],
                    },
                    "tvmaze": normalized,
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
                    "lookup": {
                        "source": (
                            "tvdb"
                            if plex.get("tvdb_id")
                            else "imdb"
                        ),
                        "value": (
                            plex.get("tvdb_id")
                            or plex.get("imdb_id")
                        ),
                    },
                    "tvmaze": None,
                }
            )

        # Small courtesy delay. Only a handful of
        # requests are made during this audit.
        time.sleep(0.25)

    matched = [
        item for item in results
        if item["matched"]
    ]

    with_next = [
        item
        for item in matched
        if item["tvmaze"].get("next_episode")
    ]

    status_counts = Counter(
        item["tvmaze"].get("status")
        for item in matched
    )

    report = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "summary": {
            "candidates": len(results),
            "matched": len(matched),
            "unmatched": (
                len(results) - len(matched)
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
