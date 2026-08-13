#!/usr/bin/env python3

"""
Three-provider consensus audit for Dakosys TV metadata.

Reads the completed full-library audit reports and examines only
provider disagreements / fallback cases.

No network access is performed.

Inputs:
- data/tmdb_full_audit.json
- data/tvmaze_full_audit.json

Output:
- data/tv_provider_consensus_audit.json
"""

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


VALID_STATES = {"ENDED", "RETURNING"}


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as handle:
        json.dump(
            data,
            handle,
            indent=2,
            ensure_ascii=False,
        )


def index_by_rating_key(report):
    result = {}

    for item in report.get("shows", []):
        plex = item.get("plex", {})
        rating_key = str(
            plex.get("rating_key")
        )

        if rating_key:
            result[rating_key] = item

    return result


def provider_status(item, provider):
    if not item:
        return None

    data = item.get(provider, {})

    if not data.get("matched"):
        return None

    provider_data = data.get(provider)

    if not provider_data:
        return None

    return provider_data.get(
        "normalized_status"
    )


def provider_next_episode(item, provider):
    if not item:
        return None

    data = item.get(provider, {})

    if not data.get("matched"):
        return None

    provider_data = data.get(provider)

    if not provider_data:
        return None

    return provider_data.get(
        "next_episode"
    )


def sonarr_status(item):
    if not item:
        return None

    data = item.get("sonarr", {})

    if not data.get("matched"):
        return None

    return data.get(
        "normalized_status"
    )


def sonarr_next_episode(item):
    if not item:
        return None

    data = item.get("sonarr", {})

    if not data.get("matched"):
        return None

    return data.get("next_episode")


def episode_air_date(
    episode,
    provider,
):
    if not episode:
        return None

    if provider == "sonarr":
        return episode.get("air_date")

    if provider == "tmdb":
        return episode.get("air_date")

    if provider == "tvmaze":
        return episode.get("airdate")

    return None


def episode_label(episode):
    if not episode:
        return None

    season = episode.get("season")
    number = episode.get("episode")

    season_text = (
        f"{season:02d}"
        if isinstance(season, int)
        else "??"
    )

    episode_text = (
        f"{number:02d}"
        if isinstance(number, int)
        else "??"
    )

    return f"S{season_text}E{episode_text}"


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Analyze Sonarr/TMDB/TVmaze "
            "provider consensus."
        )
    )

    parser.add_argument(
        "--tmdb-report",
        type=Path,
        default=Path(
            "data/tmdb_full_audit.json"
        ),
    )

    parser.add_argument(
        "--tvmaze-report",
        type=Path,
        default=Path(
            "data/tvmaze_full_audit.json"
        ),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "data/"
            "tv_provider_consensus_audit.json"
        ),
    )

    args = parser.parse_args()

    tmdb_report = load_json(
        args.tmdb_report
    )

    tvmaze_report = load_json(
        args.tvmaze_report
    )

    tmdb_by_key = index_by_rating_key(
        tmdb_report
    )

    tvmaze_by_key = index_by_rating_key(
        tvmaze_report
    )

    all_keys = sorted(
        set(tmdb_by_key)
        | set(tvmaze_by_key)
    )

    #
    # 1. Lifecycle disagreements:
    #    Sonarr vs TMDB, ask TVmaze to break tie.
    #

    lifecycle_cases = []
    lifecycle_votes = Counter()

    for key in all_keys:
        tmdb_item = tmdb_by_key.get(key)
        tvmaze_item = tvmaze_by_key.get(key)

        if not tmdb_item:
            continue

        sonarr = sonarr_status(
            tmdb_item
        )

        tmdb = provider_status(
            tmdb_item,
            "tmdb",
        )

        if (
            sonarr not in VALID_STATES
            or tmdb not in VALID_STATES
            or sonarr == tmdb
        ):
            continue

        tvmaze = provider_status(
            tvmaze_item,
            "tvmaze",
        )

        if tvmaze == sonarr:
            outcome = "TVMAZE_AGREES_SONARR"

        elif tvmaze == tmdb:
            outcome = "TVMAZE_AGREES_TMDB"

        elif tvmaze in VALID_STATES:
            outcome = "TVMAZE_THIRD_OPINION"

        else:
            outcome = "TVMAZE_UNAVAILABLE_OR_UNKNOWN"

        lifecycle_votes[outcome] += 1

        lifecycle_cases.append(
            {
                "plex": tmdb_item["plex"],
                "sonarr": sonarr,
                "tmdb": tmdb,
                "tvmaze": tvmaze,
                "outcome": outcome,
            }
        )

    #
    # 2. Sonarr has no next episode but TMDB does.
    #    Check whether TVmaze independently sees one.
    #

    tmdb_extra_next_cases = []
    tmdb_extra_votes = Counter()

    for key in all_keys:
        tmdb_item = tmdb_by_key.get(key)
        tvmaze_item = tvmaze_by_key.get(key)

        if not tmdb_item:
            continue

        sonarr = sonarr_next_episode(
            tmdb_item
        )

        tmdb = provider_next_episode(
            tmdb_item,
            "tmdb",
        )

        if sonarr or not tmdb:
            continue

        tvmaze = provider_next_episode(
            tvmaze_item,
            "tvmaze",
        )

        tmdb_date = episode_air_date(
            tmdb,
            "tmdb",
        )

        tvmaze_date = episode_air_date(
            tvmaze,
            "tvmaze",
        )

        if not tvmaze:
            outcome = "TMDB_ONLY"

        elif (
            tmdb_date
            and tvmaze_date
            and tmdb_date == tvmaze_date
        ):
            outcome = "TMDB_TVMAZE_SAME_DATE"

        else:
            outcome = "TMDB_TVMAZE_DIFFER"

        tmdb_extra_votes[outcome] += 1

        tmdb_extra_next_cases.append(
            {
                "plex": tmdb_item["plex"],
                "tmdb": {
                    "episode": (
                        episode_label(tmdb)
                    ),
                    "air_date": tmdb_date,
                },
                "tvmaze": (
                    {
                        "episode": (
                            episode_label(
                                tvmaze
                            )
                        ),
                        "air_date": (
                            tvmaze_date
                        ),
                    }
                    if tvmaze
                    else None
                ),
                "outcome": outcome,
            }
        )

    #
    # 3. Sonarr and TMDB both have next episodes
    #    but disagree on air date. Ask TVmaze.
    #

    next_date_cases = []
    next_date_votes = Counter()

    for key in all_keys:
        tmdb_item = tmdb_by_key.get(key)
        tvmaze_item = tvmaze_by_key.get(key)

        if not tmdb_item:
            continue

        sonarr = sonarr_next_episode(
            tmdb_item
        )

        tmdb = provider_next_episode(
            tmdb_item,
            "tmdb",
        )

        if not sonarr or not tmdb:
            continue

        sonarr_date = episode_air_date(
            sonarr,
            "sonarr",
        )

        tmdb_date = episode_air_date(
            tmdb,
            "tmdb",
        )

        if (
            not sonarr_date
            or not tmdb_date
            or sonarr_date == tmdb_date
        ):
            continue

        tvmaze = provider_next_episode(
            tvmaze_item,
            "tvmaze",
        )

        tvmaze_date = episode_air_date(
            tvmaze,
            "tvmaze",
        )

        if tvmaze_date == sonarr_date:
            outcome = "TVMAZE_AGREES_SONARR"

        elif tvmaze_date == tmdb_date:
            outcome = "TVMAZE_AGREES_TMDB"

        elif tvmaze_date:
            outcome = "ALL_THREE_DIFFER"

        else:
            outcome = "TVMAZE_NO_NEXT_EPISODE"

        next_date_votes[outcome] += 1

        next_date_cases.append(
            {
                "plex": tmdb_item["plex"],
                "sonarr": {
                    "episode": (
                        episode_label(
                            sonarr
                        )
                    ),
                    "air_date": sonarr_date,
                },
                "tmdb": {
                    "episode": (
                        episode_label(tmdb)
                    ),
                    "air_date": tmdb_date,
                },
                "tvmaze": (
                    {
                        "episode": (
                            episode_label(
                                tvmaze
                            )
                        ),
                        "air_date": (
                            tvmaze_date
                        ),
                    }
                    if tvmaze
                    else None
                ),
                "outcome": outcome,
            }
        )

    #
    # 4. TMDB misses: does TVmaze fill them?
    #

    tmdb_miss_cases = []

    for key in all_keys:
        tmdb_item = tmdb_by_key.get(key)
        tvmaze_item = tvmaze_by_key.get(key)

        if not tmdb_item:
            continue

        tmdb_data = tmdb_item.get(
            "tmdb",
            {},
        )

        if tmdb_data.get("matched"):
            continue

        tvmaze_data = (
            tvmaze_item.get(
                "tvmaze",
                {},
            )
            if tvmaze_item
            else {}
        )

        tmdb_miss_cases.append(
            {
                "plex": tmdb_item["plex"],
                "tmdb_reason": (
                    tmdb_data.get(
                        "reason"
                    )
                ),
                "tvmaze_matched": (
                    bool(
                        tvmaze_data.get(
                            "matched"
                        )
                    )
                ),
                "tvmaze_status": (
                    provider_status(
                        tvmaze_item,
                        "tvmaze",
                    )
                ),
            }
        )

    #
    # 5. TVmaze external-ID conflicts.
    #

    identity_conflicts = []

    for key, item in (
        tvmaze_by_key.items()
    ):
        tvmaze_data = item.get(
            "tvmaze",
            {},
        )

        crosscheck = tvmaze_data.get(
            "identity_crosscheck"
        )

        if (
            crosscheck
            and crosscheck.get(
                "conflicts"
            )
        ):
            identity_conflicts.append(
                {
                    "plex": item["plex"],
                    "tvmaze": (
                        tvmaze_data.get(
                            "tvmaze"
                        )
                    ),
                    "crosscheck": (
                        crosscheck
                    ),
                }
            )

    report = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "summary": {
            "lifecycle_disagreements": (
                len(lifecycle_cases)
            ),
            "lifecycle_consensus": dict(
                lifecycle_votes
            ),
            "tmdb_next_when_sonarr_none": (
                len(
                    tmdb_extra_next_cases
                )
            ),
            "tmdb_extra_next_consensus": (
                dict(tmdb_extra_votes)
            ),
            "sonarr_tmdb_date_disagreements": (
                len(next_date_cases)
            ),
            "next_date_consensus": dict(
                next_date_votes
            ),
            "tmdb_misses": len(
                tmdb_miss_cases
            ),
            "tmdb_misses_filled_by_tvmaze": (
                sum(
                    1
                    for item
                    in tmdb_miss_cases
                    if item[
                        "tvmaze_matched"
                    ]
                )
            ),
            "tvmaze_cross_id_conflicts": (
                len(identity_conflicts)
            ),
        },
        "lifecycle_cases": (
            lifecycle_cases
        ),
        "tmdb_extra_next_cases": (
            tmdb_extra_next_cases
        ),
        "next_date_cases": (
            next_date_cases
        ),
        "tmdb_miss_cases": (
            tmdb_miss_cases
        ),
        "identity_conflicts": (
            identity_conflicts
        ),
    }

    write_json(
        args.output,
        report,
    )

    summary = report["summary"]

    print()
    print(
        "TV PROVIDER CONSENSUS AUDIT"
    )
    print("=" * 64)

    print()
    print(
        "SONARR ↔ TMDB LIFECYCLE "
        "DISAGREEMENTS"
    )
    print("=" * 64)

    print(
        f"Cases: "
        f"{summary['lifecycle_disagreements']}"
    )

    for outcome, count in (
        summary[
            "lifecycle_consensus"
        ].items()
    ):
        print(
            f"{outcome:32} {count}"
        )

    print()
    print(
        "TMDB NEXT EPISODE WHEN "
        "SONARR HAS NONE"
    )
    print("=" * 64)

    print(
        f"Cases: "
        f"{summary['tmdb_next_when_sonarr_none']}"
    )

    for outcome, count in (
        summary[
            "tmdb_extra_next_consensus"
        ].items()
    ):
        print(
            f"{outcome:32} {count}"
        )

    print()

    for item in (
        report[
            "tmdb_extra_next_cases"
        ]
    ):
        plex = item["plex"]

        print(
            f"- {plex['title']}"
        )

        print(
            f"    TMDB:   "
            f"{item['tmdb']['episode']} "
            f"{item['tmdb']['air_date']}"
        )

        if item["tvmaze"]:
            print(
                f"    TVmaze: "
                f"{item['tvmaze']['episode']} "
                f"{item['tvmaze']['air_date']}"
            )
        else:
            print(
                "    TVmaze: no next episode"
            )

        print(
            f"    Result: "
            f"{item['outcome']}"
        )

    print()
    print(
        "SONARR ↔ TMDB NEXT-DATE "
        "DISAGREEMENTS"
    )
    print("=" * 64)

    print(
        f"Cases: "
        f"{summary['sonarr_tmdb_date_disagreements']}"
    )

    for outcome, count in (
        summary[
            "next_date_consensus"
        ].items()
    ):
        print(
            f"{outcome:32} {count}"
        )

    print()

    for item in report["next_date_cases"]:
        plex = item["plex"]

        print(
            f"- {plex['title']}"
        )

        print(
            f"    Sonarr: "
            f"{item['sonarr']['episode']} "
            f"{item['sonarr']['air_date']}"
        )

        print(
            f"    TMDB:   "
            f"{item['tmdb']['episode']} "
            f"{item['tmdb']['air_date']}"
        )

        if item["tvmaze"]:
            print(
                f"    TVmaze: "
                f"{item['tvmaze']['episode']} "
                f"{item['tvmaze']['air_date']}"
            )
        else:
            print(
                "    TVmaze: no next episode"
            )

        print(
            f"    Result: "
            f"{item['outcome']}"
        )

    print()
    print("TMDB COVERAGE GAPS")
    print("=" * 64)

    print(
        f"TMDB misses:                  "
        f"{summary['tmdb_misses']}"
    )

    print(
        f"Filled by TVmaze:             "
        f"{summary['tmdb_misses_filled_by_tvmaze']}"
    )

    for item in report[
        "tmdb_miss_cases"
    ]:
        plex = item["plex"]

        print(
            f"- {plex['title']}: "
            f"TVmaze="
            f"{item['tvmaze_matched']} "
            f"status="
            f"{item['tvmaze_status']}"
        )

    print()
    print("CROSS-ID CONFLICTS")
    print("=" * 64)

    print(
        f"Cases: "
        f"{summary['tvmaze_cross_id_conflicts']}"
    )

    for item in (
        report["identity_conflicts"]
    ):
        plex = item["plex"]
        tvmaze = item["tvmaze"]
        cross = item["crosscheck"]

        print(
            f"- {plex['title']}: "
            f"primary TVmaze="
            f"{tvmaze.get('id')} "
            f"IMDb TVmaze="
            f"{cross.get('tvmaze_id')}"
        )

    print()
    print(
        f"Report written to: "
        f"{args.output}"
    )


if __name__ == "__main__":
    main()
