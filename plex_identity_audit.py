#!/usr/bin/env python3

"""
Read-only Plex TV/Anime identity audit.

Scans configured Plex TV and Anime libraries and reports the external IDs
already available on each show. This is the baseline for the future
TV metadata provider architecture.

This script:
- reads Plex metadata
- writes a JSON report under data/
- does NOT call Trakt
- does NOT modify Plex
- does NOT modify Kometa output
"""

import argparse
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml
from plexapi.server import PlexServer


def default_config_path():
    if os.environ.get("RUNNING_IN_DOCKER") == "true":
        return Path("/app/config/config.yaml")
    return Path("config/config.yaml")


def default_output_path():
    if os.environ.get("RUNNING_IN_DOCKER") == "true":
        return Path("/app/data/plex_identity_audit.json")
    return Path("data/plex_identity_audit.json")


def load_config(path):
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}

    plex = config.get("plex", {})

    if not plex.get("url"):
        raise ValueError("plex.url is missing from config")

    if not plex.get("token"):
        raise ValueError("plex.token is missing from config")

    return config


def as_list(value):
    if value is None:
        return []

    if isinstance(value, list):
        return value

    return [value]


def configured_libraries(config):
    libraries = config.get("plex", {}).get("libraries", {})

    roles = defaultdict(set)

    for name in as_list(libraries.get("anime")):
        if name:
            roles[str(name)].add("anime")

    for name in as_list(libraries.get("tv")):
        if name:
            roles[str(name)].add("tv")

    return roles


def parse_external_ids(show):
    ids = {
        "tmdb": None,
        "tvdb": None,
        "imdb": None,
    }

    raw_guids = []

    for guid in getattr(show, "guids", []) or []:
        raw = str(getattr(guid, "id", guid))
        raw_guids.append(raw)

        if raw.startswith("tmdb://"):
            value = raw.removeprefix("tmdb://").split("?")[0]
            if value:
                try:
                    ids["tmdb"] = int(value)
                except ValueError:
                    ids["tmdb"] = value

        elif raw.startswith("tvdb://"):
            value = raw.removeprefix("tvdb://").split("?")[0]
            if value:
                try:
                    ids["tvdb"] = int(value)
                except ValueError:
                    ids["tvdb"] = value

        elif raw.startswith("imdb://"):
            value = raw.removeprefix("imdb://").split("?")[0]
            if value:
                ids["imdb"] = value

    return ids, raw_guids


def percentage(value, total):
    if not total:
        return 0.0

    return round((value / total) * 100, 2)


def make_summary(shows):
    total = len(shows)

    has_tmdb = sum(1 for show in shows if show["ids"]["tmdb"] is not None)
    has_tvdb = sum(1 for show in shows if show["ids"]["tvdb"] is not None)
    has_imdb = sum(1 for show in shows if show["ids"]["imdb"] is not None)

    has_tmdb_or_tvdb = sum(
        1
        for show in shows
        if show["ids"]["tmdb"] is not None
        or show["ids"]["tvdb"] is not None
    )

    has_any_external_id = sum(
        1
        for show in shows
        if any(show["ids"].values())
    )

    no_external_id = total - has_any_external_id

    return {
        "shows": total,
        "has_tmdb": has_tmdb,
        "has_tmdb_percent": percentage(has_tmdb, total),
        "has_tvdb": has_tvdb,
        "has_tvdb_percent": percentage(has_tvdb, total),
        "has_imdb": has_imdb,
        "has_imdb_percent": percentage(has_imdb, total),
        "has_tmdb_or_tvdb": has_tmdb_or_tvdb,
        "has_tmdb_or_tvdb_percent": percentage(
            has_tmdb_or_tvdb,
            total,
        ),
        "has_any_external_id": has_any_external_id,
        "has_any_external_id_percent": percentage(
            has_any_external_id,
            total,
        ),
        "no_external_id": no_external_id,
    }


def scan_library(plex, library_name, roles):
    library = plex.library.section(library_name)

    shows = []

    for show in library.all():
        ids, raw_guids = parse_external_ids(show)

        shows.append(
            {
                "library": library_name,
                "library_roles": sorted(roles),
                "title": show.title,
                "year": getattr(show, "year", None),
                "plex_rating_key": str(show.ratingKey),
                "ids": ids,
                "raw_guids": raw_guids,
            }
        )

    return shows


def print_summary(report):
    summary = report["summary"]

    print()
    print("PLEX TV METADATA IDENTITY AUDIT")
    print("=" * 40)
    print(f"Shows scanned:       {summary['shows']}")
    print()
    print(
        f"Has TMDB ID:         {summary['has_tmdb']:5}"
        f"  ({summary['has_tmdb_percent']:6.2f}%)"
    )
    print(
        f"Has TVDB ID:         {summary['has_tvdb']:5}"
        f"  ({summary['has_tvdb_percent']:6.2f}%)"
    )
    print(
        f"Has IMDb ID:         {summary['has_imdb']:5}"
        f"  ({summary['has_imdb_percent']:6.2f}%)"
    )
    print(
        f"Has TMDB or TVDB:    {summary['has_tmdb_or_tvdb']:5}"
        f"  ({summary['has_tmdb_or_tvdb_percent']:6.2f}%)"
    )
    print(
        f"Has any external ID: {summary['has_any_external_id']:5}"
        f"  ({summary['has_any_external_id_percent']:6.2f}%)"
    )
    print(f"No external ID:      {summary['no_external_id']:5}")

    print()
    print("BY LIBRARY")
    print("=" * 40)

    for library_name, library_summary in report["libraries"].items():
        roles = ", ".join(library_summary["roles"])

        print()
        print(f"{library_name} [{roles}]")
        print(f"  Shows:             {library_summary['shows']}")
        print(
            f"  TMDB:              {library_summary['has_tmdb']}"
            f" ({library_summary['has_tmdb_percent']:.2f}%)"
        )
        print(
            f"  TVDB:              {library_summary['has_tvdb']}"
            f" ({library_summary['has_tvdb_percent']:.2f}%)"
        )
        print(
            f"  IMDb:              {library_summary['has_imdb']}"
            f" ({library_summary['has_imdb_percent']:.2f}%)"
        )
        print(
            f"  TMDB or TVDB:      {library_summary['has_tmdb_or_tvdb']}"
            f" ({library_summary['has_tmdb_or_tvdb_percent']:.2f}%)"
        )
        print(
            f"  No external ID:    {library_summary['no_external_id']}"
        )

    missing = [
        show
        for show in report["shows"]
        if not any(show["ids"].values())
    ]

    if missing:
        print()
        print("SHOWS WITH NO EXTERNAL ID")
        print("=" * 40)

        for show in missing[:25]:
            year = f" ({show['year']})" if show["year"] else ""
            print(
                f"- {show['library']}: "
                f"{show['title']}{year} "
                f"[ratingKey={show['plex_rating_key']}]"
            )

        if len(missing) > 25:
            print(
                f"... and {len(missing) - 25} more; "
                "see the JSON report."
            )


def main():
    parser = argparse.ArgumentParser(
        description="Audit Plex TV/Anime external IDs."
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=default_config_path(),
        help="Path to Dakosys config.yaml",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=default_output_path(),
        help="JSON report path",
    )

    args = parser.parse_args()

    config = load_config(args.config)

    library_roles = configured_libraries(config)

    if not library_roles:
        raise SystemExit(
            "No Plex anime or TV libraries are configured."
        )

    print(
        f"Connecting to Plex at "
        f"{config['plex']['url']}..."
    )

    plex = PlexServer(
        config["plex"]["url"],
        config["plex"]["token"],
    )

    print("Connected.")

    all_shows = []
    library_summaries = {}

    # Scan each physical Plex library only once. A library may be configured
    # in both anime and tv roles.
    for library_name, roles in library_roles.items():
        print(
            f"Scanning {library_name} "
            f"[{', '.join(sorted(roles))}]..."
        )

        shows = scan_library(
            plex,
            library_name,
            roles,
        )

        all_shows.extend(shows)

        library_summary = make_summary(shows)
        library_summary["roles"] = sorted(roles)

        library_summaries[library_name] = library_summary

        print(f"  Found {len(shows)} shows.")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "plex_url": config["plex"]["url"],
        "summary": make_summary(all_shows),
        "libraries": library_summaries,
        "shows": all_shows,
    }

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with args.output.open("w", encoding="utf-8") as handle:
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
