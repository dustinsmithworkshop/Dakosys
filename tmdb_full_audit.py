#!/usr/bin/env python3

"""
Full-library TMDB provider comparison audit.

Compares TMDB against the same Plex inventory and Sonarr baseline used by
the Dakosys TV metadata provider investigation.

Identity strategy:
1. Use Plex TMDB ID directly when available.
2. If Plex has no TMDB ID, try exact TVDB -> TMDB lookup.
3. If that fails, try exact IMDb -> TMDB lookup.
4. No title search or fuzzy matching.
5. Title/year differences are diagnostic warnings only.

Comparison:
- TMDB identity coverage
- Sonarr vs TMDB lifecycle status
- Sonarr next-airing coverage
- same season/episode
- same AIR DATE
- TMDB episode_type values

This script:
- reads data/plex_identity_audit.json
- reads data/sonarr_provider_audit.json
- reads current Sonarr metadata
- queries TMDB
- checkpoints TMDB results
- writes data/tmdb_full_audit.json
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
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests


TMDB_URL = "https://api.themoviedb.org/3"

# ~20 requests/sec, comfortably below TMDB's documented
# approximate protective ceiling.
REQUEST_INTERVAL_SECONDS = 0.05

MAX_RETRIES = 5


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json_atomic(path, data):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp = path.with_suffix(
        path.suffix + ".tmp"
    )

    with temp.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            data,
            handle,
            indent=2,
            ensure_ascii=False,
        )

    temp.replace(path)


def normalize_title(value):
    if not value:
        return ""

    return re.sub(
        r"[^a-z0-9]+",
        "",
        str(value).casefold(),
    )


def year_from_date(value):
    if not value:
        return None

    try:
        return int(str(value)[:4])
    except (TypeError, ValueError):
        return None


def parse_datetime(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(
            str(value).replace(
                "Z",
                "+00:00",
            )
        )
    except ValueError:
        return None


def normalize_sonarr_lifecycle(status):
    value = str(status or "").casefold()

    if value == "ended":
        return "ENDED"

    if value == "continuing":
        return "RETURNING"

    return "UNKNOWN"


def normalize_tmdb_lifecycle(status):
    value = str(status or "").casefold()

    # For Dakosys purposes, cancelled and ended
    # mean the same thing.
    if value in {
        "ended",
        "canceled",
        "cancelled",
    }:
        return "ENDED"

    if value in {
        "returning series",
        "in production",
    }:
        return "RETURNING"

    # Planned/Pilot/etc. remain visible instead
    # of being guessed into an active state.
    return "UNKNOWN"


def normalize_tmdb_episode(episode):
    if not episode:
        return None

    return {
        "id": episode.get("id"),
        "name": episode.get("name"),
        "season": episode.get(
            "season_number"
        ),
        "episode": episode.get(
            "episode_number"
        ),
        "air_date": episode.get(
            "air_date"
        ),
        "episode_type": episode.get(
            "episode_type"
        ),
        "runtime": episode.get(
            "runtime"
        ),
    }


def normalize_tmdb_show(show):
    return {
        "id": show.get("id"),
        "name": show.get("name"),
        "original_name": show.get(
            "original_name"
        ),
        "status": show.get("status"),
        "normalized_status": (
            normalize_tmdb_lifecycle(
                show.get("status")
            )
        ),
        "first_air_date": show.get(
            "first_air_date"
        ),
        "last_air_date": show.get(
            "last_air_date"
        ),
        "in_production": show.get(
            "in_production"
        ),
        "number_of_seasons": show.get(
            "number_of_seasons"
        ),
        "number_of_episodes": show.get(
            "number_of_episodes"
        ),
        "type": show.get("type"),
        "next_episode": (
            normalize_tmdb_episode(
                show.get(
                    "next_episode_to_air"
                )
            )
        ),
        "last_episode": (
            normalize_tmdb_episode(
                show.get(
                    "last_episode_to_air"
                )
            )
        ),
    }


def identity_warnings(plex, tmdb):
    warnings = []

    plex_title = normalize_title(
        plex.get("title")
    )

    tmdb_titles = {
        normalize_title(
            tmdb.get("name")
        ),
        normalize_title(
            tmdb.get("original_name")
        ),
    }

    tmdb_titles.discard("")

    if (
        plex_title
        and tmdb_titles
        and plex_title not in tmdb_titles
    ):
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
        and int(plex_year) != tmdb_year
    ):
        warnings.append(
            f"year_differs:"
            f"{plex_year}->{tmdb_year}"
        )

    return warnings


def plex_record(show):
    ids = show.get("ids", {})

    return {
        "library": show.get("library"),
        "library_roles": show.get(
            "library_roles",
            [],
        ),
        "title": show.get("title"),
        "year": show.get("year"),
        "rating_key": str(
            show.get("plex_rating_key")
        ),
        "tmdb_id": ids.get("tmdb"),
        "tvdb_id": ids.get("tvdb"),
        "imdb_id": ids.get("imdb"),
    }


class TMDBClient:
    def __init__(self, token):
        self.session = requests.Session()

        self.session.headers.update(
            {
                "Authorization": (
                    f"Bearer {token}"
                ),
                "Accept": (
                    "application/json"
                ),
                "User-Agent": (
                    "Dakosys-TV-Metadata-"
                    "Provider-Audit"
                ),
            }
        )

        self.last_request_time = 0.0

    def _rate_limit(self):
        elapsed = (
            time.monotonic()
            - self.last_request_time
        )

        remaining = (
            REQUEST_INTERVAL_SECONDS
            - elapsed
        )

        if remaining > 0:
            time.sleep(remaining)

    def _request(
        self,
        method,
        url,
        **kwargs,
    ):
        for attempt in range(
            1,
            MAX_RETRIES + 1,
        ):
            self._rate_limit()

            response = self.session.request(
                method,
                url,
                timeout=30,
                **kwargs,
            )

            self.last_request_time = (
                time.monotonic()
            )

            if response.status_code == 429:
                retry_after = (
                    response.headers.get(
                        "Retry-After"
                    )
                )

                try:
                    delay = float(
                        retry_after
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    delay = (
                        2.0 * attempt
                    )

                print(
                    f"  TMDB rate limit; "
                    f"waiting "
                    f"{delay:.1f}s..."
                )

                response.close()
                time.sleep(delay)
                continue

            if (
                500
                <= response.status_code
                < 600
            ):
                delay = (
                    2.0 * attempt
                )

                print(
                    f"  TMDB "
                    f"{response.status_code}; "
                    f"retrying in "
                    f"{delay:.1f}s..."
                )

                response.close()
                time.sleep(delay)
                continue

            return response

        raise RuntimeError(
            "TMDB request failed after "
            f"{MAX_RETRIES} retries: "
            f"{url}"
        )

    def fetch_show(self, tmdb_id):
        response = self._request(
            "GET",
            f"{TMDB_URL}/tv/{tmdb_id}",
        )

        if response.status_code == 404:
            response.close()
            return None

        response.raise_for_status()

        data = response.json()

        response.close()

        return data

    def find_tv_show(
        self,
        source,
        value,
    ):
        if source == "tvdb":
            external_source = "tvdb_id"
        elif source == "imdb":
            external_source = "imdb_id"
        else:
            raise ValueError(
                f"Unsupported TMDB "
                f"external source: "
                f"{source}"
            )

        response = self._request(
            "GET",
            f"{TMDB_URL}/find/{value}",
            params={
                "external_source": (
                    external_source
                ),
            },
        )

        response.raise_for_status()

        data = response.json()

        response.close()

        tv_results = (
            data.get("tv_results")
            or []
        )

        if len(tv_results) == 0:
            return {
                "matched": False,
                "reason": "not_found",
                "candidate_count": 0,
                "tmdb_id": None,
            }

        if len(tv_results) > 1:
            return {
                "matched": False,
                "reason": (
                    "ambiguous_external_id"
                ),
                "candidate_count": (
                    len(tv_results)
                ),
                "tmdb_id": None,
            }

        return {
            "matched": True,
            "reason": None,
            "candidate_count": 1,
            "tmdb_id": (
                tv_results[0].get("id")
            ),
        }

    def resolve_show(self, plex):
        tmdb_id = plex.get("tmdb_id")

        lookup_source = None
        lookup_value = None

        if tmdb_id is not None:
            lookup_source = "tmdb"
            lookup_value = tmdb_id

        else:
            attempts = []

            if plex.get("tvdb_id"):
                attempts.append(
                    (
                        "tvdb",
                        plex["tvdb_id"],
                    )
                )

            if plex.get("imdb_id"):
                attempts.append(
                    (
                        "imdb",
                        plex["imdb_id"],
                    )
                )

            find_failures = []

            for source, value in attempts:
                result = (
                    self.find_tv_show(
                        source,
                        value,
                    )
                )

                if result["matched"]:
                    tmdb_id = result[
                        "tmdb_id"
                    ]
                    lookup_source = (
                        source
                    )
                    lookup_value = value
                    break

                find_failures.append(
                    {
                        "source": source,
                        "value": value,
                        "reason": result[
                            "reason"
                        ],
                        "candidate_count": (
                            result[
                                "candidate_count"
                            ]
                        ),
                    }
                )

            if tmdb_id is None:
                return {
                    "matched": False,
                    "reason": (
                        "external_id_lookup_failed"
                    ),
                    "lookup_source": None,
                    "lookup_value": None,
                    "find_failures": (
                        find_failures
                    ),
                    "identity_warnings": [],
                    "tmdb": None,
                }

        raw_show = self.fetch_show(
            tmdb_id
        )

        if raw_show is None:
            return {
                "matched": False,
                "reason": (
                    "tmdb_show_not_found"
                ),
                "lookup_source": (
                    lookup_source
                ),
                "lookup_value": (
                    lookup_value
                ),
                "find_failures": [],
                "identity_warnings": [],
                "tmdb": None,
            }

        tmdb = normalize_tmdb_show(
            raw_show
        )

        warnings = identity_warnings(
            plex,
            tmdb,
        )

        return {
            "matched": True,
            "reason": None,
            "lookup_source": (
                lookup_source
            ),
            "lookup_value": (
                lookup_value
            ),
            "find_failures": [],
            "identity_warnings": warnings,
            "tmdb": tmdb,
        }


def load_tmdb_cache(path):
    if not path.exists():
        return {}

    data = load_json(path)

    if isinstance(data, dict):
        return data

    return {}


def save_tmdb_cache(
    path,
    cache,
):
    write_json_atomic(
        path,
        cache,
    )


def fetch_sonarr_context(
    sonarr_audit,
):
    sonarr_url = os.environ.get(
        "SONARR_URL"
    )

    sonarr_api_key = os.environ.get(
        "SONARR_API_KEY"
    )

    if not sonarr_url:
        raise SystemExit(
            "SONARR_URL environment "
            "variable is not set."
        )

    if not sonarr_api_key:
        raise SystemExit(
            "SONARR_API_KEY environment "
            "variable is not set."
        )

    sonarr_url = sonarr_url.rstrip("/")

    session = requests.Session()

    session.headers.update(
        {
            "X-Api-Key": (
                sonarr_api_key
            )
        }
    )

    print(
        f"Loading current Sonarr "
        f"metadata from "
        f"{sonarr_url}..."
    )

    response = session.get(
        f"{sonarr_url}/api/v3/series",
        timeout=60,
    )

    response.raise_for_status()

    series = response.json()

    by_id = {
        item["id"]: item
        for item in series
        if item.get("id") is not None
    }

    result = {}

    matched_items = [
        item
        for item in sonarr_audit["shows"]
        if (
            item["match"]["matched"]
            and item.get("sonarr")
        )
    ]

    next_airing_items = []

    for item in matched_items:
        plex = item["plex"]

        rating_key = str(
            plex.get("rating_key")
        )

        sonarr_id = (
            item["sonarr"].get("id")
        )

        current = by_id.get(
            sonarr_id
        )

        if not current:
            result[rating_key] = {
                "matched": False,
                "reason": (
                    "sonarr_series_missing"
                ),
            }
            continue

        status = current.get("status")

        record = {
            "matched": True,
            "id": sonarr_id,
            "title": current.get(
                "title"
            ),
            "status": status,
            "normalized_status": (
                normalize_sonarr_lifecycle(
                    status
                )
            ),
            "next_airing": current.get(
                "nextAiring"
            ),
            "next_episode": None,
        }

        result[rating_key] = record

        if current.get("nextAiring"):
            next_airing_items.append(
                (
                    rating_key,
                    current,
                )
            )

    print(
        f"Resolving "
        f"{len(next_airing_items)} "
        f"Sonarr next-airing "
        f"episode records..."
    )

    for index, (
        rating_key,
        show,
    ) in enumerate(
        next_airing_items,
        1,
    ):
        if (
            index == 1
            or index % 25 == 0
            or index
            == len(next_airing_items)
        ):
            print(
                f"  Sonarr episodes "
                f"{index}/"
                f"{len(next_airing_items)}"
            )

        response = session.get(
            f"{sonarr_url}/api/v3/episode",
            params={
                "seriesId": show["id"]
            },
            timeout=60,
        )

        response.raise_for_status()

        episodes = response.json()

        target = parse_datetime(
            show.get("nextAiring")
        )

        exact = None

        for episode in episodes:
            candidate = parse_datetime(
                episode.get(
                    "airDateUtc"
                )
            )

            if (
                candidate is not None
                and target is not None
                and candidate == target
            ):
                exact = episode
                break

        if exact:
            result[
                rating_key
            ]["next_episode"] = {
                "season": exact.get(
                    "seasonNumber"
                ),
                "episode": exact.get(
                    "episodeNumber"
                ),
                "air_date": exact.get(
                    "airDate"
                ),
                "air_datetime": exact.get(
                    "airDateUtc"
                ),
                "title": exact.get(
                    "title"
                ),
                "finale_type": exact.get(
                    "finaleType"
                ),
            }

    return result


def compare_show(
    sonarr,
    tmdb_result,
):
    comparison = {
        "lifecycle_comparable": False,
        "lifecycle_agrees": None,
        "sonarr_has_next": False,
        "tmdb_has_next": False,
        "same_season_episode": None,
        "same_air_date": None,
    }

    if (
        sonarr
        and sonarr.get("matched")
        and tmdb_result.get("matched")
    ):
        sonarr_status = sonarr.get(
            "normalized_status"
        )

        tmdb_status = (
            tmdb_result["tmdb"].get(
                "normalized_status"
            )
        )

        if (
            sonarr_status
            in {"ENDED", "RETURNING"}
            and tmdb_status
            in {"ENDED", "RETURNING"}
        ):
            comparison[
                "lifecycle_comparable"
            ] = True

            comparison[
                "lifecycle_agrees"
            ] = (
                sonarr_status
                == tmdb_status
            )

    sonarr_episode = (
        sonarr.get("next_episode")
        if sonarr
        else None
    )

    tmdb_episode = None

    if tmdb_result.get("matched"):
        tmdb_episode = (
            tmdb_result[
                "tmdb"
            ].get("next_episode")
        )

    comparison["sonarr_has_next"] = (
        sonarr_episode is not None
    )

    comparison["tmdb_has_next"] = (
        tmdb_episode is not None
    )

    if (
        sonarr_episode
        and tmdb_episode
    ):
        comparison[
            "same_season_episode"
        ] = (
            sonarr_episode.get("season")
            == tmdb_episode.get("season")
            and sonarr_episode.get(
                "episode"
            )
            == tmdb_episode.get(
                "episode"
            )
        )

        sonarr_air_date = (
            sonarr_episode.get(
                "air_date"
            )
        )

        tmdb_air_date = (
            tmdb_episode.get(
                "air_date"
            )
        )

        if (
            sonarr_air_date
            and tmdb_air_date
        ):
            comparison[
                "same_air_date"
            ] = (
                sonarr_air_date
                == tmdb_air_date
            )

    return comparison


def build_summary(shows):
    total = len(shows)

    matched = [
        item
        for item in shows
        if item["tmdb"]["matched"]
    ]

    unmatched = [
        item
        for item in shows
        if not item["tmdb"]["matched"]
    ]

    lookup_sources = Counter(
        item["tmdb"].get(
            "lookup_source"
        )
        for item in matched
    )

    raw_statuses = Counter(
        item["tmdb"]["tmdb"].get(
            "status"
        )
        for item in matched
    )

    identity_warnings = [
        item
        for item in matched
        if item["tmdb"].get(
            "identity_warnings"
        )
    ]

    lifecycle_comparable = [
        item
        for item in shows
        if item["comparison"][
            "lifecycle_comparable"
        ]
    ]

    lifecycle_agree = [
        item
        for item in lifecycle_comparable
        if item["comparison"][
            "lifecycle_agrees"
        ]
    ]

    lifecycle_disagree = [
        item
        for item in lifecycle_comparable
        if not item["comparison"][
            "lifecycle_agrees"
        ]
    ]

    both_matches = [
        item
        for item in shows
        if (
            item.get(
                "sonarr",
                {},
            ).get("matched")
            and item["tmdb"]["matched"]
        )
    ]

    sonarr_next = [
        item
        for item in shows
        if item["comparison"][
            "sonarr_has_next"
        ]
    ]

    sonarr_next_tmdb_matched = [
        item
        for item in sonarr_next
        if item["tmdb"]["matched"]
    ]

    sonarr_next_tmdb_has_next = [
        item
        for item in sonarr_next
        if item["comparison"][
            "tmdb_has_next"
        ]
    ]

    same_episode = [
        item
        for item
        in sonarr_next_tmdb_has_next
        if item["comparison"][
            "same_season_episode"
        ]
        is True
    ]

    same_air_date = [
        item
        for item
        in sonarr_next_tmdb_has_next
        if item["comparison"][
            "same_air_date"
        ]
        is True
    ]

    tmdb_extra_next = [
        item
        for item in shows
        if (
            item.get(
                "sonarr",
                {},
            ).get("matched")
            and item["sonarr"].get(
                "normalized_status"
            )
            == "RETURNING"
            and not item["comparison"][
                "sonarr_has_next"
            ]
            and item["comparison"][
                "tmdb_has_next"
            ]
        )
    ]

    episode_types = Counter(
        item["tmdb"]["tmdb"][
            "next_episode"
        ].get("episode_type")
        for item in matched
        if item["tmdb"]["tmdb"].get(
            "next_episode"
        )
    )

    return {
        "plex_shows": total,
        "tmdb_matched": len(matched),
        "tmdb_unmatched": len(unmatched),
        "lookup_sources": dict(
            lookup_sources.most_common()
        ),
        "raw_tmdb_statuses": dict(
            raw_statuses.most_common()
        ),
        "identity_warning_count": len(
            identity_warnings
        ),
        "both_sonarr_tmdb_matched": len(
            both_matches
        ),
        "lifecycle_comparable": len(
            lifecycle_comparable
        ),
        "lifecycle_agree": len(
            lifecycle_agree
        ),
        "lifecycle_disagree": len(
            lifecycle_disagree
        ),
        "sonarr_next_airing": len(
            sonarr_next
        ),
        "sonarr_next_tmdb_matched": len(
            sonarr_next_tmdb_matched
        ),
        "sonarr_next_tmdb_has_next": len(
            sonarr_next_tmdb_has_next
        ),
        "same_season_episode": len(
            same_episode
        ),
        "same_air_date": len(
            same_air_date
        ),
        "tmdb_next_when_sonarr_none": len(
            tmdb_extra_next
        ),
        "tmdb_next_episode_types": dict(
            episode_types.most_common()
        ),
    }


def build_library_summary(shows):
    grouped = defaultdict(list)

    for item in shows:
        grouped[
            item["plex"]["library"]
        ].append(item)

    result = {}

    for library_name, items in sorted(
        grouped.items()
    ):
        matched = sum(
            1
            for item in items
            if item["tmdb"]["matched"]
        )

        result[library_name] = {
            "plex_shows": len(items),
            "tmdb_matched": matched,
            "tmdb_unmatched": (
                len(items) - matched
            ),
            "match_percent": (
                round(
                    matched
                    / len(items)
                    * 100,
                    2,
                )
                if items
                else 0.0
            ),
        }

    return result


def format_episode_number(value):
    if isinstance(value, int):
        return f"{value:02d}"

    return "??"


def print_report(report):
    summary = report["summary"]

    print()
    print(
        "TMDB FULL-LIBRARY PROVIDER AUDIT"
    )
    print("=" * 64)

    print(
        f"Plex shows:                    "
        f"{summary['plex_shows']:5}"
    )

    print(
        f"TMDB matched:                  "
        f"{summary['tmdb_matched']:5}"
    )

    percent = (
        summary["tmdb_matched"]
        / summary["plex_shows"]
        * 100
        if summary["plex_shows"]
        else 0.0
    )

    print(
        f"TMDB coverage:                 "
        f"{percent:6.2f}%"
    )

    print(
        f"TMDB unmatched:                "
        f"{summary['tmdb_unmatched']:5}"
    )

    print()
    print("LOOKUP SOURCES")
    print("=" * 64)

    for source, count in (
        summary["lookup_sources"].items()
    ):
        print(
            f"{str(source):25} "
            f"{count}"
        )

    print()
    print("TMDB STATUS VALUES")
    print("=" * 64)

    for status, count in (
        summary[
            "raw_tmdb_statuses"
        ].items()
    ):
        print(
            f"{str(status):25} "
            f"{count}"
        )

    print()
    print("IDENTITY DIAGNOSTICS")
    print("=" * 64)

    print(
        f"Title/year warnings:           "
        f"{summary['identity_warning_count']}"
    )

    print()
    print("SONARR ↔ TMDB LIFECYCLE")
    print("=" * 64)

    print(
        f"Both providers matched:        "
        f"{summary['both_sonarr_tmdb_matched']}"
    )

    print(
        f"Comparable lifecycle states:   "
        f"{summary['lifecycle_comparable']}"
    )

    print(
        f"Lifecycle agrees:              "
        f"{summary['lifecycle_agree']}"
    )

    print(
        f"Lifecycle disagrees:           "
        f"{summary['lifecycle_disagree']}"
    )

    print()
    print("SONARR NEXT AIRING ↔ TMDB")
    print("=" * 64)

    print(
        f"Sonarr next-airing shows:      "
        f"{summary['sonarr_next_airing']}"
    )

    print(
        f"Matched by TMDB:               "
        f"{summary['sonarr_next_tmdb_matched']}"
    )

    print(
        f"TMDB also has next episode:    "
        f"{summary['sonarr_next_tmdb_has_next']}"
    )

    print(
        f"Same season/episode:           "
        f"{summary['same_season_episode']}"
    )

    print(
        f"Same air date:                 "
        f"{summary['same_air_date']}"
    )

    print(
        f"TMDB next when Sonarr none:    "
        f"{summary['tmdb_next_when_sonarr_none']}"
    )

    print()
    print("TMDB NEXT EPISODE TYPES")
    print("=" * 64)

    if summary[
        "tmdb_next_episode_types"
    ]:
        for value, count in summary[
            "tmdb_next_episode_types"
        ].items():
            print(
                f"{str(value):25} "
                f"{count}"
            )
    else:
        print(
            "No TMDB next episodes found."
        )

    print()
    print("BY LIBRARY")
    print("=" * 64)

    for library_name, item in (
        report["libraries"].items()
    ):
        print(
            f"{library_name:20} "
            f"{item['tmdb_matched']:4}/"
            f"{item['plex_shows']:<4} "
            f"{item['match_percent']:6.2f}%"
        )

    unmatched = [
        item
        for item in report["shows"]
        if not item["tmdb"]["matched"]
    ]

    if unmatched:
        print()
        print("TMDB UNMATCHED")
        print("=" * 64)

        for item in unmatched[:50]:
            plex = item["plex"]

            print(
                f"- {plex['library']}: "
                f"{plex['title']} "
                f"({plex['year']}) "
                f"TMDB={plex['tmdb_id']} "
                f"TVDB={plex['tvdb_id']} "
                f"IMDb={plex['imdb_id']} "
                f"reason="
                f"{item['tmdb']['reason']}"
            )

    warnings = [
        item
        for item in report["shows"]
        if item["tmdb"].get(
            "identity_warnings"
        )
    ]

    if warnings:
        print()
        print("IDENTITY WARNINGS")
        print("=" * 64)

        for item in warnings[:50]:
            plex = item["plex"]
            tmdb = item["tmdb"]["tmdb"]

            print(
                f"- {plex['title']} "
                f"({plex['year']}) "
                f"-> {tmdb['name']} "
                f"({year_from_date(tmdb['first_air_date'])}) "
                f"{item['tmdb']['identity_warnings']}"
            )

        if len(warnings) > 50:
            print(
                f"... and "
                f"{len(warnings) - 50} "
                f"more; see JSON report."
            )

    disagreements = [
        item
        for item in report["shows"]
        if (
            item["comparison"][
                "lifecycle_comparable"
            ]
            and not item["comparison"][
                "lifecycle_agrees"
            ]
        )
    ]

    if disagreements:
        print()
        print("LIFECYCLE DISAGREEMENTS")
        print("=" * 64)

        for item in disagreements[:50]:
            plex = item["plex"]
            sonarr = item["sonarr"]
            tmdb = item["tmdb"]["tmdb"]

            print(
                f"- {plex['title']}: "
                f"Sonarr="
                f"{sonarr['normalized_status']} "
                f"TMDB="
                f"{tmdb['normalized_status']} "
                f"({tmdb['status']})"
            )

        if len(disagreements) > 50:
            print(
                f"... and "
                f"{len(disagreements) - 50} "
                f"more; see JSON report."
            )

    episode_mismatches = [
        item
        for item in report["shows"]
        if (
            item["comparison"][
                "sonarr_has_next"
            ]
            and item["comparison"][
                "tmdb_has_next"
            ]
            and (
                item["comparison"][
                    "same_season_episode"
                ]
                is False
                or item["comparison"][
                    "same_air_date"
                ]
                is False
            )
        )
    ]

    if episode_mismatches:
        print()
        print("NEXT-EPISODE DISAGREEMENTS")
        print("=" * 64)

        for item in (
            episode_mismatches[:50]
        ):
            plex = item["plex"]

            sonarr_ep = (
                item["sonarr"][
                    "next_episode"
                ]
            )

            tmdb_ep = (
                item["tmdb"][
                    "tmdb"
                ]["next_episode"]
            )

            print(
                f"- {plex['title']}"
            )

            print(
                f"    Sonarr: "
                f"S"
                f"{format_episode_number(sonarr_ep.get('season'))}"
                f"E"
                f"{format_episode_number(sonarr_ep.get('episode'))} "
                f"{sonarr_ep.get('air_date')} "
                f"{sonarr_ep.get('air_datetime')}"
            )

            print(
                f"    TMDB:   "
                f"S"
                f"{format_episode_number(tmdb_ep.get('season'))}"
                f"E"
                f"{format_episode_number(tmdb_ep.get('episode'))} "
                f"{tmdb_ep.get('air_date')} "
                f"type="
                f"{tmdb_ep.get('episode_type')!r}"
            )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Full-library TMDB provider "
            "comparison audit."
        )
    )

    parser.add_argument(
        "--plex-report",
        type=Path,
        default=Path(
            "data/plex_identity_audit.json"
        ),
    )

    parser.add_argument(
        "--sonarr-report",
        type=Path,
        default=Path(
            "data/sonarr_provider_audit.json"
        ),
    )

    parser.add_argument(
        "--cache",
        type=Path,
        default=Path(
            "data/tmdb_full_cache.json"
        ),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "data/tmdb_full_audit.json"
        ),
    )

    parser.add_argument(
        "--fresh",
        action="store_true",
        help=(
            "Ignore and replace any "
            "existing TMDB checkpoint."
        ),
    )

    args = parser.parse_args()

    token = os.environ.get(
        "TMDB_TOKEN"
    )

    if not token:
        raise SystemExit(
            "TMDB_TOKEN environment "
            "variable is not set."
        )

    if not args.plex_report.exists():
        raise SystemExit(
            f"Plex audit not found: "
            f"{args.plex_report}"
        )

    if not args.sonarr_report.exists():
        raise SystemExit(
            f"Sonarr audit not found: "
            f"{args.sonarr_report}"
        )

    plex_report = load_json(
        args.plex_report
    )

    sonarr_audit = load_json(
        args.sonarr_report
    )

    plex_shows = [
        plex_record(show)
        for show
        in plex_report["shows"]
    ]

    if (
        args.fresh
        and args.cache.exists()
    ):
        args.cache.unlink()

    cache = load_tmdb_cache(
        args.cache
    )

    if cache:
        print(
            f"Resuming TMDB audit with "
            f"{len(cache)} cached shows."
        )
    else:
        print(
            "Starting full TMDB audit."
        )

    client = TMDBClient(token)

    total = len(plex_shows)

    uncached = [
        show
        for show in plex_shows
        if show["rating_key"]
        not in cache
    ]

    print(
        f"Plex shows: {total}"
    )

    print(
        f"Remaining TMDB lookups: "
        f"{len(uncached)}"
    )

    try:
        for show in plex_shows:
            rating_key = (
                show["rating_key"]
            )

            if rating_key in cache:
                continue

            overall_done = (
                len(cache) + 1
            )

            if (
                overall_done == 1
                or overall_done % 50 == 0
                or overall_done == total
            ):
                print(
                    f"TMDB "
                    f"{overall_done}/"
                    f"{total}: "
                    f"{show['title']}",
                    flush=True,
                )

            result = (
                client.resolve_show(
                    show
                )
            )

            cache[rating_key] = result

            if (
                len(cache) % 50 == 0
                or len(cache) == total
            ):
                save_tmdb_cache(
                    args.cache,
                    cache,
                )

    except Exception:
        save_tmdb_cache(
            args.cache,
            cache,
        )

        print()
        print(
            "Progress checkpointed to "
            f"{args.cache}"
        )

        print(
            "Fix the error and rerun "
            "the same command to resume."
        )

        raise

    save_tmdb_cache(
        args.cache,
        cache,
    )

    print()
    print(
        "TMDB scan complete."
    )

    sonarr_context = (
        fetch_sonarr_context(
            sonarr_audit
        )
    )

    shows = []

    for plex in plex_shows:
        rating_key = (
            plex["rating_key"]
        )

        tmdb_result = cache.get(
            rating_key
        )

        if tmdb_result is None:
            raise RuntimeError(
                f"Missing TMDB cache "
                f"record for Plex "
                f"ratingKey={rating_key}"
            )

        sonarr = sonarr_context.get(
            rating_key,
            {
                "matched": False,
                "reason": (
                    "not_matched_in_sonarr"
                ),
            },
        )

        comparison = compare_show(
            sonarr,
            tmdb_result,
        )

        shows.append(
            {
                "plex": plex,
                "sonarr": sonarr,
                "tmdb": tmdb_result,
                "comparison": comparison,
            }
        )

    report = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "summary": build_summary(
            shows
        ),
        "libraries": (
            build_library_summary(
                shows
            )
        ),
        "shows": shows,
    }

    write_json_atomic(
        args.output,
        report,
    )

    print_report(report)

    print()
    print(
        f"Report written to: "
        f"{args.output}"
    )

    print(
        f"Checkpoint cache: "
        f"{args.cache}"
    )


if __name__ == "__main__":
    main()
