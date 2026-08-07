import os
import re
import logging
import difflib

from plexapi.server import PlexServer

import anime_trakt_manager


logger = logging.getLogger("kometa_episode_mapper")


EPISODE_TYPE_CONFIG = {
    "filler": {
        "afl_type": "FILLER",
        "filename": "filler.txt",
    },
    "manga": {
        "afl_type": "MANGA CANON",
        "filename": "manga_canon.txt",
    },
    "anime": {
        "afl_type": "ANIME CANON",
        "filename": "anime_canon.txt",
    },
    "mixed": {
        "afl_type": "MIXED CANON/FILLER",
        "filename": "mixed.txt",
    },
}


def _clean_episode_number(value):
    """Return the numeric AFL episode number as a string."""
    match = re.search(r"\d+", str(value))
    return match.group(0) if match else None


def _title_similarity(left, right):
    """Compare AFL and Plex titles using Dakosys title normalization."""
    left_normalized = anime_trakt_manager.normalize_episode_title(
        left or ""
    )
    right_normalized = anime_trakt_manager.normalize_episode_title(
        right or ""
    )

    if not left_normalized or not right_normalized:
        return 0.0

    if left_normalized == right_normalized:
        return 1.0

    return difflib.SequenceMatcher(
        None,
        left_normalized,
        right_normalized,
    ).ratio()


def _build_episode_number_map(
    all_afl_episodes,
    episode_map,
    title_match_threshold=0.65,
):
    """
    Build an AFL absolute-number -> Plex episode mapping.

    Normal behavior uses direct absolute numbering:

        AFL 21 -> Plex absolute 21

    If AFL contains an extra numbered episode that Plex does not include
    among its regular aired-order episodes, detect that discrepancy and
    adjust subsequent AFL episode numbers with an offset.

    Example:

        AFL 24 -> Plex absolute 24
        AFL 25 -> AFL-only OVA; skip
        AFL 26 -> Plex absolute 25
        AFL 27 -> Plex absolute 26
    """
    lookup = {}
    warnings = []
    offset = 0

    sorted_afl = sorted(
        all_afl_episodes,
        key=lambda episode: int(
            _clean_episode_number(
                episode.get("number")
            ) or 999999999
        ),
    )

    for index, afl_episode in enumerate(sorted_afl):
        clean_number = _clean_episode_number(
            afl_episode.get("number")
        )

        if not clean_number:
            warnings.append(
                {
                    "type": "invalid_afl_number",
                    "afl_episode": afl_episode,
                }
            )
            continue

        afl_number = int(clean_number)

        # Normal mapping is direct AFL absolute number -> Plex absolute
        # number, adjusted only by a previously detected sequence offset.
        plex_absolute = afl_number + offset

        plex_episode = episode_map.get(
            str(plex_absolute)
        )

        if not plex_episode:
            lookup[clean_number] = None

            warnings.append(
                {
                    "type": "unmapped",
                    "afl_episode": afl_episode,
                    "plex_absolute": plex_absolute,
                }
            )
            continue

        similarity = _title_similarity(
            afl_episode.get("name"),
            plex_episode.get("title"),
        )

        if similarity >= title_match_threshold:
            lookup[clean_number] = plex_episode
            continue

        #
        # AFL-only episode detection.
        #
        # Suppose:
        #
        #   AFL 25 = Walking Alone
        #   AFL 26 = Dazai, Chuuya, Fifteen Years Old
        #
        # while Plex absolute 25 is:
        #
        #   Dazai, Chuuya, Fifteen Years Old
        #
        # If AFL N+1 matches the Plex episode currently expected for AFL N,
        # AFL N is likely an OVA/special included in AFL numbering but not
        # among Plex's regular aired-order episodes.
        #
        if index + 1 < len(sorted_afl):
            next_afl = sorted_afl[index + 1]

            next_number_string = _clean_episode_number(
                next_afl.get("number")
            )

            if next_number_string:
                next_number = int(
                    next_number_string
                )

                # Only use a truly consecutive AFL episode as evidence.
                if next_number == afl_number + 1:
                    next_score = _title_similarity(
                        next_afl.get("name"),
                        plex_episode.get("title"),
                    )

                    if next_score >= title_match_threshold:
                        lookup[clean_number] = None

                        # AFL now has one more numbered episode than Plex,
                        # so all following Plex absolute positions move back.
                        offset -= 1

                        warnings.append(
                            {
                                "type": "afl_extra",
                                "afl_episode": afl_episode,
                                "plex_episode": plex_episode,
                                "next_afl_episode": next_afl,
                                "score": next_score,
                                "new_offset": offset,
                            }
                        )

                        continue

        #
        # Plex-only episode detection.
        #
        # This is the inverse case. If the current AFL title matches the
        # NEXT Plex absolute episode, Plex may contain a regular episode
        # that AFL omitted from its numbering.
        #
        next_plex_episode = episode_map.get(
            str(plex_absolute + 1)
        )

        if next_plex_episode:
            next_plex_score = _title_similarity(
                afl_episode.get("name"),
                next_plex_episode.get("title"),
            )

            if next_plex_score >= title_match_threshold:
                offset += 1

                plex_absolute = (
                    afl_number + offset
                )

                plex_episode = episode_map.get(
                    str(plex_absolute)
                )

                lookup[clean_number] = plex_episode

                warnings.append(
                    {
                        "type": "plex_extra",
                        "afl_episode": afl_episode,
                        "plex_episode": plex_episode,
                        "score": next_plex_score,
                        "new_offset": offset,
                    }
                )

                continue

        #
        # Titles differ, but there is no strong evidence that numbering
        # has shifted. Keep the absolute-number mapping and emit a warning.
        #
        lookup[clean_number] = plex_episode

        warnings.append(
            {
                "type": "title_mismatch",
                "afl_episode": afl_episode,
                "plex_episode": plex_episode,
                "score": similarity,
                "offset": offset,
            }
        )

    return lookup, warnings


def _log_mapping_warnings(
    anime_name,
    warnings,
    stats,
):
    """Log mapping warnings and update aggregate statistics."""
    for warning in warnings:
        warning_type = warning["type"]

        if warning_type == "afl_extra":
            afl_episode = warning["afl_episode"]

            logger.warning(
                f"{anime_name}: AFL episode "
                f"{afl_episode.get('number')} "
                f"'{afl_episode.get('name')}' appears to be "
                f"an AFL-only special/OVA; "
                f"subsequent Plex mapping offset is "
                f"{warning['new_offset']}"
            )

            stats["afl_only_episodes"] += 1
            stats["sequence_realignments"] += 1

        elif warning_type == "plex_extra":
            afl_episode = warning["afl_episode"]
            plex_episode = warning["plex_episode"]

            logger.warning(
                f"{anime_name}: Plex appears to contain an extra "
                f"regular episode before AFL episode "
                f"{afl_episode.get('number')} "
                f"'{afl_episode.get('name')}'; "
                f"realigned to Plex "
                f"S{plex_episode['season']:02d}"
                f"E{plex_episode['episode']:02d}; "
                f"subsequent mapping offset is "
                f"{warning['new_offset']}"
            )

            stats["sequence_realignments"] += 1

        elif warning_type == "title_mismatch":
            afl_episode = warning["afl_episode"]
            plex_episode = warning["plex_episode"]

            logger.warning(
                f"{anime_name} episode "
                f"{afl_episode.get('number')}: "
                f"title mismatch "
                f"AFL='{afl_episode.get('name')}' "
                f"Plex='{plex_episode.get('title')}' "
                f"({warning['score']:.0%})"
            )

            stats["title_warnings"] += 1

        elif warning_type == "invalid_afl_number":
            afl_episode = warning["afl_episode"]

            logger.warning(
                f"{anime_name}: invalid AFL episode number "
                f"'{afl_episode.get('number')}'"
            )

        elif warning_type == "unmapped":
            afl_episode = warning["afl_episode"]

            logger.warning(
                f"{anime_name}: AFL episode "
                f"{afl_episode.get('number')} "
                f"'{afl_episode.get('name')}' "
                f"has no Plex regular episode at adjusted "
                f"absolute position "
                f"{warning['plex_absolute']}"
            )


def generate_kometa_episode_files(
    config,
    anime_specs,
    output_dir,
    title_warning_threshold=0.65,
):
    """
    Generate Kometa text_file sources using Plex aired-order numbering.

    anime_specs is an iterable of dictionaries:

        {
            "anime_name": "bleach",
            "episode_type": "manga"
        }

    episode_type must be one of:
        filler, manga, anime, mixed
    """
    anime_trakt_manager.CONFIG = config

    plex_config = config.get(
        "plex",
        {},
    )

    plex_url = plex_config.get("url")
    plex_token = plex_config.get("token")

    if not plex_url or not plex_token:
        logger.error(
            "Plex URL/token missing from configuration"
        )
        return False, {}

    try:
        plex = PlexServer(
            plex_url,
            plex_token,
        )
    except Exception as e:
        logger.error(
            f"Could not connect to Plex: {e}"
        )
        return False, {}

    os.makedirs(
        output_dir,
        exist_ok=True,
    )

    output_entries = {
        key: set()
        for key in EPISODE_TYPE_CONFIG
    }

    stats = {
        "shows_processed": 0,
        "episodes_mapped": 0,
        "episodes_unmapped": 0,
        "title_warnings": 0,
        "sequence_realignments": 0,
        "afl_only_episodes": 0,
        "shows_failed": 0,
    }

    unique_specs = {
        (
            spec["anime_name"],
            spec["episode_type"],
        )
        for spec in anime_specs
    }

    #
    # Group classifications by anime. This allows us to build the
    # AFL -> Plex numbering map once for each show.
    #
    requested_types_by_anime = {}

    for anime_name, episode_type in unique_specs:
        requested_types_by_anime.setdefault(
            anime_name,
            set(),
        ).add(
            episode_type
        )

    for anime_name in sorted(
        requested_types_by_anime
    ):
        requested_types = (
            requested_types_by_anime[
                anime_name
            ]
        )

        show = (
            anime_trakt_manager.get_plex_anime_show(
                plex,
                anime_name,
            )
        )

        if not show:
            logger.warning(
                f"Skipping {anime_name}: "
                f"Plex show not found"
            )

            stats["shows_failed"] += 1
            continue

        tvdb_id = (
            anime_trakt_manager.get_tvdb_id_from_show(
                show
            )
        )

        if not tvdb_id:
            logger.warning(
                f"Skipping {anime_name}: "
                f"Plex show has no TVDb GUID"
            )

            stats["shows_failed"] += 1
            continue

        episode_map = (
            anime_trakt_manager
            .build_plex_absolute_episode_map(
                show
            )
        )

        if not episode_map:
            logger.warning(
                f"Skipping {anime_name}: "
                f"could not build Plex episode map"
            )

            stats["shows_failed"] += 1
            continue

        logger.info(
            f"{show.title}: "
            f"TVDb {tvdb_id}, "
            f"{len(episode_map)} "
            f"regular Plex episodes"
        )

        #
        # Build the most complete AFL chronological sequence available.
        #
        # We explicitly merge all four classifications rather than using
        # get_anime_episodes(..., None), because our earlier testing showed
        # that None did not reliably provide the complete sequence needed
        # for reconciliation.
        #
        all_afl_by_number = {}

        for type_config in (
            EPISODE_TYPE_CONFIG.values()
        ):
            classified_episodes = (
                anime_trakt_manager
                .get_anime_episodes(
                    anime_name,
                    type_config["afl_type"],
                    silent=True,
                )
            )

            for episode in (
                classified_episodes or []
            ):
                clean_number = (
                    _clean_episode_number(
                        episode.get("number")
                    )
                )

                if clean_number:
                    all_afl_by_number[
                        clean_number
                    ] = episode

        all_afl_episodes = list(
            all_afl_by_number.values()
        )

        if not all_afl_episodes:
            logger.warning(
                f"Skipping {anime_name}: "
                f"no AFL episodes found"
            )

            stats["shows_failed"] += 1
            continue

        number_lookup, mapping_warnings = (
            _build_episode_number_map(
                all_afl_episodes,
                episode_map,
                title_match_threshold=(
                    title_warning_threshold
                ),
            )
        )

        _log_mapping_warnings(
            anime_name,
            mapping_warnings,
            stats,
        )

        stats["shows_processed"] += 1

        #
        # Now apply the already-established show-level mapping to each
        # requested classification.
        #
        for episode_type in sorted(
            requested_types
        ):
            type_config = (
                EPISODE_TYPE_CONFIG.get(
                    episode_type
                )
            )

            if not type_config:
                logger.warning(
                    f"Unknown episode type "
                    f"'{episode_type}' "
                    f"for {anime_name}"
                )
                continue

            afl_episodes = (
                anime_trakt_manager
                .get_anime_episodes(
                    anime_name,
                    type_config["afl_type"],
                    silent=True,
                )
            )

            if not afl_episodes:
                logger.warning(
                    f"{anime_name}: "
                    f"no AFL episodes found for "
                    f"{type_config['afl_type']}"
                )
                continue

            mapped_for_type = 0
            unmapped_for_type = 0

            for afl_episode in afl_episodes:
                clean_number = (
                    _clean_episode_number(
                        afl_episode.get("number")
                    )
                )

                if not clean_number:
                    logger.warning(
                        f"{anime_name}: "
                        f"invalid AFL episode number "
                        f"'{afl_episode.get('number')}'"
                    )

                    stats[
                        "episodes_unmapped"
                    ] += 1

                    unmapped_for_type += 1
                    continue

                plex_episode = (
                    number_lookup.get(
                        clean_number
                    )
                )

                if not plex_episode:
                    logger.warning(
                        f"{anime_name}: "
                        f"AFL episode "
                        f"{afl_episode.get('number')} "
                        f"'{afl_episode.get('name')}' "
                        f"could not be mapped to "
                        f"a regular Plex episode"
                    )

                    stats[
                        "episodes_unmapped"
                    ] += 1

                    unmapped_for_type += 1
                    continue

                kometa_id = (
                    f"tvdb_episode:{tvdb_id}_"
                    f"{plex_episode['season']}_"
                    f"{plex_episode['episode']}"
                )

                output_entries[
                    episode_type
                ].add(
                    kometa_id
                )

                stats[
                    "episodes_mapped"
                ] += 1

                mapped_for_type += 1

            logger.info(
                f"{anime_name} "
                f"[{episode_type}]: "
                f"{mapped_for_type} mapped, "
                f"{unmapped_for_type} unmapped"
            )

    #
    # Write Kometa text_file sources.
    #
    for (
        episode_type,
        type_config,
    ) in EPISODE_TYPE_CONFIG.items():
        output_path = os.path.join(
            output_dir,
            type_config["filename"],
        )

        entries = sorted(
            output_entries[
                episode_type
            ],
            key=_kometa_episode_sort_key,
        )

        with open(
            output_path,
            "w",
            encoding="utf-8",
        ) as file:
            file.write(
                "# Generated by Dakosys\n"
                "# AnimeFillerList classifications "
                "mapped through Plex aired-order "
                "numbering\n\n"
            )

            for entry in entries:
                file.write(
                    f"{entry}\n"
                )

        logger.info(
            f"Wrote {len(entries)} entries "
            f"to {output_path}"
        )

    return True, stats


def _kometa_episode_sort_key(value):
    """
    Sort:

        tvdb_episode:74796_2_1

    numerically by TVDb show, season, episode.
    """
    try:
        payload = value.split(
            ":",
            1,
        )[1]

        tvdb_id, season, episode = (
            payload.split("_")
        )

        return (
            int(tvdb_id),
            int(season),
            int(episode),
        )

    except Exception:
        return (
            999999999,
            999999,
            999999,
        )