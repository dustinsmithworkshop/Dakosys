#!/usr/bin/env python3

"""
Full-library TVmaze provider comparison audit.

Compares TVmaze against the same Plex inventory and Sonarr baseline used by
the Dakosys TV metadata provider investigation.

Identity strategy:
1. Exact Plex TVDB ID -> TVmaze lookup.
2. If TVDB is not found, exact Plex IMDb ID -> TVmaze lookup.
3. No title search and no fuzzy matching.
4. Title/year differences are diagnostic warnings only.
5. If a TVDB match looks suspicious and IMDb is available, IMDb is
   cross-checked for a conflicting TVmaze ID.

The audit also compares:
- Sonarr lifecycle status vs TVmaze lifecycle status
- Sonarr nextAiring vs TVmaze nextepisode
- season/episode agreement
- air timestamp agreement

This script:
- reads data/plex_identity_audit.json
- reads data/sonarr_provider_audit.json
- reads Sonarr through its local API
- queries the public TVmaze API
- checkpoints TVmaze results under data/
- writes data/tvmaze_full_audit.json
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
from urllib.parse import urlparse

import requests


TVMAZE_URL = "https://api.tvmaze.com"

# TVmaze documents at least 20 calls per 10 seconds.
# 0.60 seconds between actual HTTP calls keeps this audit conservative.
REQUEST_INTERVAL_SECONDS = 0.60

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


def normalize_tvmaze_lifecycle(status):
    value = str(status or "").casefold()

    if value == "ended":
        return "ENDED"

    if value == "running":
        return "RETURNING"

    # Keep other TVmaze states visible rather than guessing.
    return "UNKNOWN"


def identity_warnings(plex, tvmaze):
    warnings = []

    plex_title = normalize_title(
        plex.get("title")
    )

    tvmaze_title = normalize_title(
        tvmaze.get("name")
    )

    if (
        plex_title
        and tvmaze_title
        and plex_title != tvmaze_title
    ):
        warnings.append("title_differs")

    plex_year = plex.get("year")
    tvmaze_year = year_from_date(
        tvmaze.get("premiered")
    )

    if (
        plex_year is not None
        and tvmaze_year is not None
        and int(plex_year) != tvmaze_year
    ):
        warnings.append(
            f"year_differs:"
            f"{plex_year}->{tvmaze_year}"
        )

    return warnings


def normalize_tvmaze_episode(episode):
    if not episode:
        return None

    return {
        "id": episode.get("id"),
        "name": episode.get("name"),
        "season": episode.get("season"),
        "episode": episode.get("number"),
        "airdate": episode.get("airdate"),
        "airtime": episode.get("airtime"),
        "airstamp": episode.get("airstamp"),
        "runtime": episode.get("runtime"),
        "type": episode.get("type"),
    }


def normalize_tvmaze_show(show):
    externals = show.get("externals") or {}
    embedded = show.get("_embedded") or {}

    return {
        "id": show.get("id"),
        "name": show.get("name"),
        "url": show.get("url"),
        "status": show.get("status"),
        "normalized_status": (
            normalize_tvmaze_lifecycle(
                show.get("status")
            )
        ),
        "premiered": show.get("premiered"),
        "ended": show.get("ended"),
        "type": show.get("type"),
        "language": show.get("language"),
        "tvdb_id": externals.get(
            "thetvdb"
        ),
        "imdb_id": externals.get(
            "imdb"
        ),
        "next_episode": (
            normalize_tvmaze_episode(
                embedded.get(
                    "nextepisode"
                )
            )
        ),
    }


class TVMazeClient:
    def __init__(self):
        self.session = requests.Session()

        self.session.headers.update(
            {
                "Accept": "application/json",
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
                    delay = 5.0 * attempt

                print(
                    f"  TVmaze rate limit; "
                    f"waiting {delay:.1f}s..."
                )

                response.close()
                time.sleep(delay)
                continue

            if 500 <= response.status_code < 600:
                delay = 2.0 * attempt

                print(
                    f"  TVmaze "
                    f"{response.status_code}; "
                    f"retrying in "
                    f"{delay:.1f}s..."
                )

                response.close()
                time.sleep(delay)
                continue

            return response

        raise RuntimeError(
            "TVmaze request failed after "
            f"{MAX_RETRIES} retries: {url}"
        )

    def lookup_id(
        self,
        source,
        value,
    ):
        if source == "tvdb":
            params = {
                "thetvdb": str(value)
            }
        elif source == "imdb":
            params = {
                "imdb": str(value)
            }
        else:
            raise ValueError(
                f"Unsupported TVmaze "
                f"lookup source: {source}"
            )

        response = self._request(
            "GET",
            f"{TVMAZE_URL}/lookup/shows",
            params=params,
            allow_redirects=False,
        )

        if response.status_code == 404:
            response.close()
            return None

        if response.status_code == 200:
            data = response.json()
            response.close()

            return data.get("id")

        if response.status_code in {
            301,
            302,
            307,
            308,
        }:
            location = response.headers.get(
                "Location",
                "",
            )

            response.close()

            parsed = urlparse(location)

            match = re.search(
                r"/shows/(\d+)",
                parsed.path,
            )

            if not match:
                raise RuntimeError(
                    "TVmaze lookup redirect "
                    "did not contain a show ID: "
                    f"{location}"
                )

            return int(match.group(1))

        response.raise_for_status()

        return None

    def fetch_show(
        self,
        tvmaze_id,
    ):
        response = self._request(
            "GET",
            f"{TVMAZE_URL}/shows/"
            f"{tvmaze_id}",
            params={
                "embed": "nextepisode"
            },
            allow_redirects=False,
        )

        response.raise_for_status()

        data = response.json()

        response.close()

        return data

    def resolve_show(
        self,
        plex,
    ):
        tvdb_id = plex.get("tvdb_id")
        imdb_id = plex.get("imdb_id")

        tvmaze_id = None
        lookup_source = None
        lookup_value = None
        attempts = []

        if tvdb_id:
            attempts.append(
                {
                    "source": "tvdb",
                    "value": tvdb_id,
                }
            )

        if imdb_id:
            attempts.append(
                {
                    "source": "imdb",
                    "value": imdb_id,
                }
            )

        for attempt in attempts:
            candidate_id = self.lookup_id(
                attempt["source"],
                attempt["value"],
            )

            if candidate_id is None:
                continue

            tvmaze_id = candidate_id
            lookup_source = (
                attempt["source"]
            )
            lookup_value = (
                attempt["value"]
            )
            break

        if tvmaze_id is None:
            return {
                "matched": False,
                "reason": "not_found",
                "lookup_source": None,
                "lookup_value": None,
                "identity_warnings": [],
                "identity_crosscheck": None,
                "tvmaze": None,
            }

        raw_show = self.fetch_show(
            tvmaze_id
        )

        tvmaze = normalize_tvmaze_show(
            raw_show
        )

        warnings = identity_warnings(
            plex,
            tvmaze,
        )

        crosscheck = None

        # If TVDB found a show but the visible
        # identity looks suspicious, check whether
        # Plex's IMDb ID maps to a different TVmaze
        # show. Do not silently change the match.
        if (
            warnings
            and lookup_source == "tvdb"
            and imdb_id
        ):
            imdb_tvmaze_id = self.lookup_id(
                "imdb",
                imdb_id,
            )

            crosscheck = {
                "imdb": imdb_id,
                "tvmaze_id": imdb_tvmaze_id,
                "conflicts": (
                    imdb_tvmaze_id is not None
                    and imdb_tvmaze_id
                    != tvmaze_id
                ),
            }

        return {
            "matched": True,
            "reason": None,
            "lookup_source": (
                lookup_source
            ),
            "lookup_value": (
                lookup_value
            ),
            "identity_warnings": warnings,
            "identity_crosscheck": (
                crosscheck
            ),
            "tvmaze": tvmaze,
        }


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


def load_tvmaze_cache(path):
    if not path.exists():
        return {}

    data = load_json(path)

    if isinstance(data, dict):
        return data

    return {}


def save_tvmaze_cache(
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
        f"metadata from {sonarr_url}..."
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

        sonarr_id = item["sonarr"].get(
            "id"
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
    plex,
    sonarr,
    tvmaze_result,
):
    comparison = {
        "lifecycle_comparable": False,
        "lifecycle_agrees": None,
        "sonarr_has_next": False,
        "tvmaze_has_next": False,
        "same_season_episode": None,
        "same_air_datetime": None,
    }

    if (
        sonarr
        and sonarr.get("matched")
        and tvmaze_result.get("matched")
    ):
        sonarr_status = sonarr.get(
            "normalized_status"
        )

        tvmaze_status = (
            tvmaze_result["tvmaze"].get(
                "normalized_status"
            )
        )

        if (
            sonarr_status
            in {"ENDED", "RETURNING"}
            and tvmaze_status
            in {"ENDED", "RETURNING"}
        ):
            comparison[
                "lifecycle_comparable"
            ] = True

            comparison[
                "lifecycle_agrees"
            ] = (
                sonarr_status
                == tvmaze_status
            )

    sonarr_episode = (
        sonarr.get("next_episode")
        if sonarr
        else None
    )

    tvmaze_episode = None

    if tvmaze_result.get("matched"):
        tvmaze_episode = (
            tvmaze_result[
                "tvmaze"
            ].get("next_episode")
        )

    comparison["sonarr_has_next"] = (
        sonarr_episode is not None
    )

    comparison["tvmaze_has_next"] = (
        tvmaze_episode is not None
    )

    if (
        sonarr_episode
        and tvmaze_episode
    ):
        comparison[
            "same_season_episode"
        ] = (
            sonarr_episode.get("season")
            == tvmaze_episode.get("season")
            and sonarr_episode.get(
                "episode"
            )
            == tvmaze_episode.get(
                "episode"
            )
        )

        sonarr_dt = parse_datetime(
            sonarr_episode.get(
                "air_datetime"
            )
        )

        tvmaze_dt = parse_datetime(
            tvmaze_episode.get(
                "airstamp"
            )
        )

        if (
            sonarr_dt is not None
            and tvmaze_dt is not None
        ):
            delta = abs(
                (
                    sonarr_dt
                    - tvmaze_dt
                ).total_seconds()
            )

            comparison[
                "same_air_datetime"
            ] = delta <= 60

    return comparison


def build_summary(shows):
    total = len(shows)

    matched = [
        item
        for item in shows
        if item["tvmaze"]["matched"]
    ]

    unmatched = [
        item
        for item in shows
        if not item["tvmaze"]["matched"]
    ]

    lookup_sources = Counter(
        item["tvmaze"].get(
            "lookup_source"
        )
        for item in matched
    )

    raw_statuses = Counter(
        item["tvmaze"]["tvmaze"].get(
            "status"
        )
        for item in matched
    )

    warnings = [
        item
        for item in matched
        if item["tvmaze"].get(
            "identity_warnings"
        )
    ]

    conflicts = [
        item
        for item in matched
        if (
            item["tvmaze"].get(
                "identity_crosscheck"
            )
            and item["tvmaze"][
                "identity_crosscheck"
            ].get("conflicts")
        )
    ]

    both_provider_matches = [
        item
        for item in shows
        if (
            item.get("sonarr", {}).get(
                "matched"
            )
            and item["tvmaze"]["matched"]
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

    sonarr_next = [
        item
        for item in shows
        if item["comparison"][
            "sonarr_has_next"
        ]
    ]

    sonarr_next_tvmaze_matched = [
        item
        for item in sonarr_next
        if item["tvmaze"]["matched"]
    ]

    sonarr_next_tvmaze_has_next = [
        item
        for item in sonarr_next
        if item["comparison"][
            "tvmaze_has_next"
        ]
    ]

    same_episode = [
        item
        for item
        in sonarr_next_tvmaze_has_next
        if item["comparison"][
            "same_season_episode"
        ]
        is True
    ]

    same_datetime = [
        item
        for item
        in sonarr_next_tvmaze_has_next
        if item["comparison"][
            "same_air_datetime"
        ]
        is True
    ]

    tvmaze_extra_next = [
        item
        for item in shows
        if (
            item.get("sonarr", {}).get(
                "matched"
            )
            and item["sonarr"].get(
                "normalized_status"
            )
            == "RETURNING"
            and not item["comparison"][
                "sonarr_has_next"
            ]
            and item["comparison"][
                "tvmaze_has_next"
            ]
        )
    ]

    return {
        "plex_shows": total,
        "tvmaze_matched": len(matched),
        "tvmaze_unmatched": len(unmatched),
        "lookup_sources": dict(
            lookup_sources.most_common()
        ),
        "raw_tvmaze_statuses": dict(
            raw_statuses.most_common()
        ),
        "identity_warning_count": len(
            warnings
        ),
        "cross_id_conflict_count": len(
            conflicts
        ),
        "both_sonarr_tvmaze_matched": len(
            both_provider_matches
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
        "sonarr_next_tvmaze_matched": len(
            sonarr_next_tvmaze_matched
        ),
        "sonarr_next_tvmaze_has_next": len(
            sonarr_next_tvmaze_has_next
        ),
        "same_season_episode": len(
            same_episode
        ),
        "same_air_datetime": len(
            same_datetime
        ),
        "tvmaze_next_when_sonarr_none": len(
            tvmaze_extra_next
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
            if item["tvmaze"]["matched"]
        )

        result[library_name] = {
            "plex_shows": len(items),
            "tvmaze_matched": matched,
            "tvmaze_unmatched": (
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


def print_report(report):
    summary = report["summary"]

    print()
    print(
        "TVMAZE FULL-LIBRARY PROVIDER AUDIT"
    )
    print("=" * 64)

    print(
        f"Plex shows:                    "
        f"{summary['plex_shows']:5}"
    )

    print(
        f"TVmaze matched:                "
        f"{summary['tvmaze_matched']:5}"
    )

    percent = (
        summary["tvmaze_matched"]
        / summary["plex_shows"]
        * 100
        if summary["plex_shows"]
        else 0.0
    )

    print(
        f"TVmaze coverage:               "
        f"{percent:6.2f}%"
    )

    print(
        f"TVmaze unmatched:              "
        f"{summary['tvmaze_unmatched']:5}"
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
    print("TVMAZE STATUS VALUES")
    print("=" * 64)

    for status, count in (
        summary[
            "raw_tvmaze_statuses"
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

    print(
        f"TVDB/IMDb ID conflicts:        "
        f"{summary['cross_id_conflict_count']}"
    )

    print()
    print("SONARR ↔ TVMAZE LIFECYCLE")
    print("=" * 64)

    print(
        f"Both providers matched:        "
        f"{summary['both_sonarr_tvmaze_matched']}"
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
    print("SONARR NEXT AIRING ↔ TVMAZE")
    print("=" * 64)

    print(
        f"Sonarr next-airing shows:      "
        f"{summary['sonarr_next_airing']}"
    )

    print(
        f"Matched by TVmaze:             "
        f"{summary['sonarr_next_tvmaze_matched']}"
    )

    print(
        f"TVmaze also has next episode:  "
        f"{summary['sonarr_next_tvmaze_has_next']}"
    )

    print(
        f"Same season/episode:           "
        f"{summary['same_season_episode']}"
    )

    print(
        f"Same air datetime:             "
        f"{summary['same_air_datetime']}"
    )

    print(
        f"TVmaze next when Sonarr none:  "
        f"{summary['tvmaze_next_when_sonarr_none']}"
    )

    print()
    print("BY LIBRARY")
    print("=" * 64)

    for library_name, item in (
        report["libraries"].items()
    ):
        print(
            f"{library_name:20} "
            f"{item['tvmaze_matched']:4}/"
            f"{item['plex_shows']:<4} "
            f"{item['match_percent']:6.2f}%"
        )

    unmatched = [
        item
        for item in report["shows"]
        if not item["tvmaze"]["matched"]
    ]

    if unmatched:
        print()
        print("TVMAZE UNMATCHED")
        print("=" * 64)

        for item in unmatched[:50]:
            plex = item["plex"]

            print(
                f"- {plex['library']}: "
                f"{plex['title']} "
                f"({plex['year']}) "
                f"TVDB={plex['tvdb_id']} "
                f"IMDb={plex['imdb_id']}"
            )

        if len(unmatched) > 50:
            print(
                f"... and "
                f"{len(unmatched) - 50} "
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
            tvmaze = item["tvmaze"][
                "tvmaze"
            ]

            print(
                f"- {plex['title']}: "
                f"Sonarr="
                f"{sonarr['normalized_status']} "
                f"TVmaze="
                f"{tvmaze['normalized_status']} "
                f"({tvmaze['status']})"
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
                "tvmaze_has_next"
            ]
            and (
                item["comparison"][
                    "same_season_episode"
                ]
                is False
                or item["comparison"][
                    "same_air_datetime"
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
            tvmaze_ep = (
                item["tvmaze"][
                    "tvmaze"
                ]["next_episode"]
            )

            print(
                f"- {plex['title']}"
            )

            print(
                f"    Sonarr: "
                f"S{sonarr_ep['season']:02d}"
                f"E{sonarr_ep['episode']:02d} "
                f"{sonarr_ep['air_datetime']}"
            )

            tvmaze_season = tvmaze_ep.get("season")
            tvmaze_number = tvmaze_ep.get("episode")

            season_text = (
                f"{tvmaze_season:02d}"
                if isinstance(tvmaze_season, int)
                else "??"
            )

            episode_text = (
                f"{tvmaze_number:02d}"
                if isinstance(tvmaze_number, int)
                else "??"
            )

            print(
                f"    TVmaze: "
                f"S{season_text}E{episode_text} "
                f"{tvmaze_ep.get('airstamp')}"
            )

    conflicts = [
        item
        for item in report["shows"]
        if (
            item["tvmaze"].get(
                "identity_crosscheck"
            )
            and item["tvmaze"][
                "identity_crosscheck"
            ].get("conflicts")
        )
    ]

    if conflicts:
        print()
        print("TVDB / IMDB ID CONFLICTS")
        print("=" * 64)

        for item in conflicts:
            plex = item["plex"]
            tvmaze = item["tvmaze"]
            cross = tvmaze[
                "identity_crosscheck"
            ]

            print(
                f"- {plex['title']}: "
                f"TVDB lookup -> "
                f"TVmaze {tvmaze['tvmaze']['id']}; "
                f"IMDb lookup -> "
                f"TVmaze {cross['tvmaze_id']}"
            )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Full-library TVmaze provider "
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
            "data/tvmaze_full_cache.json"
        ),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "data/tvmaze_full_audit.json"
        ),
    )

    parser.add_argument(
        "--fresh",
        action="store_true",
        help=(
            "Ignore and replace any "
            "existing TVmaze checkpoint."
        ),
    )

    args = parser.parse_args()

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

    if args.fresh and args.cache.exists():
        args.cache.unlink()

    cache = load_tvmaze_cache(
        args.cache
    )

    if cache:
        print(
            f"Resuming TVmaze audit with "
            f"{len(cache)} cached shows."
        )
    else:
        print(
            "Starting full TVmaze audit."
        )

    client = TVMazeClient()

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
        f"Remaining TVmaze lookups: "
        f"{len(uncached)}"
    )

    processed_this_run = 0

    try:
        for show in plex_shows:
            rating_key = show[
                "rating_key"
            ]

            if rating_key in cache:
                continue

            processed_this_run += 1

            overall_done = (
                len(cache) + 1
            )

            if (
                processed_this_run == 1
                or overall_done % 25 == 0
                or overall_done == total
            ):
                print(
                    f"TVmaze "
                    f"{overall_done}/"
                    f"{total}: "
                    f"{show['title']}",
                    flush=True,
                )

            result = client.resolve_show(
                show
            )

            cache[rating_key] = result

            if (
                len(cache) % 25 == 0
                or len(cache) == total
            ):
                save_tvmaze_cache(
                    args.cache,
                    cache,
                )

    except Exception:
        save_tvmaze_cache(
            args.cache,
            cache,
        )

        print()
        print(
            "Progress checkpointed to "
            f"{args.cache}"
        )

        print(
            "Fix the error and rerun the "
            "same command to resume."
        )

        raise

    save_tvmaze_cache(
        args.cache,
        cache,
    )

    print()
    print(
        "TVmaze scan complete."
    )

    sonarr_context = (
        fetch_sonarr_context(
            sonarr_audit
        )
    )

    shows = []

    for plex in plex_shows:
        rating_key = plex[
            "rating_key"
        ]

        tvmaze_result = cache.get(
            rating_key
        )

        if tvmaze_result is None:
            raise RuntimeError(
                f"Missing TVmaze cache "
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
            plex,
            sonarr,
            tvmaze_result,
        )

        shows.append(
            {
                "plex": plex,
                "sonarr": sonarr,
                "tvmaze": (
                    tvmaze_result
                ),
                "comparison": (
                    comparison
                ),
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
