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


_ROMAN_PARTS = {
    "i": 1,
    "ii": 2,
    "iii": 3,
    "iv": 4,
    "v": 5,
    "vi": 6,
    "vii": 7,
    "viii": 8,
    "ix": 9,
    "x": 10,
}


def _normalize_episode_match_title(value):
    """
    Normalize an episode title for mapper-local title comparison.

    Dakosys already performs the general title cleanup. This additional
    mapper-only layer canonicalizes a trailing Roman or Arabic part number:

        Endless Eight II
        Endless Eight (2)

    both become:

        endless 8 part 2

    Keeping this logic local avoids changing title behavior elsewhere in
    Dakosys.
    """
    normalized = anime_trakt_manager.normalize_episode_title(
        value or ""
    )

    if not normalized:
        return ""

    parts = normalized.split()

    if not parts:
        return normalized

    last = parts[-1]

    if last in _ROMAN_PARTS:
        parts[-1:] = [
            "part",
            str(_ROMAN_PARTS[last]),
        ]

    elif last.isdigit():
        parts[-1:] = [
            "part",
            last,
        ]

    return " ".join(parts)


def _title_similarity(left, right):
    """Compare AFL and Plex titles using mapper-aware normalization."""
    left_normalized = _normalize_episode_match_title(
        left
    )
    right_normalized = _normalize_episode_match_title(
        right
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


def _normalize_special_match_title(value):
    """Normalize titles for conservative Plex-special matching."""
    normalized = _normalize_episode_match_title(value)

    # The generic mapper normalization intentionally canonicalizes trailing
    # numbers as "part N". If the source already contained the word
    # "part", that can yield "part part N". Collapse that only for
    # special-title matching so existing regular-episode behavior is unchanged.
    while "part part " in normalized:
        normalized = normalized.replace(
            "part part ",
            "part ",
        )

    return normalized


def _special_title_score(left, right):
    """Return a conservative similarity score for an AFL/Plex special pair."""
    left_normalized = _normalize_special_match_title(left)
    right_normalized = _normalize_special_match_title(right)

    if not left_normalized or not right_normalized:
        return 0.0

    if left_normalized == right_normalized:
        return 1.0

    shorter, longer = sorted(
        (left_normalized, right_normalized),
        key=len,
    )

    # Plex special titles often prepend an OVA/movie label, for example:
    #
    #   AFL:  The Lost Cat
    #   Plex: Trust & Betrayal: Act 2 - The Lost Cat
    #
    # Treat meaningful contained titles as strong evidence while rejecting
    # tiny/generic substrings.
    if (
        len(shorter) >= 7
        and len(shorter.split()) >= 2
        and shorter in longer
    ):
        return 1.0

    return difflib.SequenceMatcher(
        None,
        left_normalized,
        right_normalized,
    ).ratio()


def _build_plex_special_episode_map(show):
    """Return Plex Season 0 episodes keyed by their season episode number."""
    special_map = {}

    try:
        special_season = None

        for season in show.seasons():
            if int(season.index) == 0:
                special_season = season
                break

        if special_season is None:
            return special_map

        for episode in sorted(
            special_season.episodes(),
            key=lambda item: item.index,
        ):
            special_map[str(episode.index)] = {
                "season": 0,
                "episode": episode.index,
                "title": episode.title,
                "rating_key": episode.ratingKey,
            }

    except Exception as e:
        logger.debug(
            f"Could not inspect Plex specials for "
            f"'{getattr(show, 'title', 'unknown')}': {e}"
        )

    return special_map


def _find_matching_plex_special(
    title,
    special_episode_map,
    threshold=0.80,
    ambiguity_margin=0.05,
):
    """Find one confident Plex Season 0 match for an AFL episode title."""
    if not special_episode_map:
        return None, 0.0

    candidates = []

    for special_episode in special_episode_map.values():
        score = _special_title_score(
            title,
            special_episode.get("title"),
        )

        candidates.append(
            (score, special_episode)
        )

    candidates.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    if not candidates:
        return None, 0.0

    best_score, best_episode = candidates[0]

    if best_score < threshold:
        return None, best_score

    second_score = (
        candidates[1][0]
        if len(candidates) > 1
        else 0.0
    )

    # If multiple specials are equally plausible, fail closed rather than
    # assigning an overlay to an arbitrary Season 0 episode.
    if (
        second_score >= threshold
        and best_score - second_score < ambiguity_margin
    ):
        return None, best_score

    return best_episode, best_score

def _afl_episode_number(episode):
    """Return an AFL episode number as int, or None."""
    clean_number = _clean_episode_number(
        episode.get("number")
    )

    if not clean_number:
        return None

    try:
        return int(clean_number)
    except (TypeError, ValueError):
        return None


def _title_exists_elsewhere_in_plex(
    title,
    episode_map,
    excluded_absolute=None,
    threshold=0.80,
):
    """
    Return True if a title has a strong match somewhere else
    in the Plex regular-episode sequence.

    This prevents a reordered episode from being mistaken for
    an AFL-only episode.
    """
    for absolute_string, plex_episode in episode_map.items():
        try:
            absolute_number = int(absolute_string)
        except (TypeError, ValueError):
            continue

        if (
            excluded_absolute is not None
            and absolute_number == excluded_absolute
        ):
            continue

        score = _title_similarity(
            title,
            plex_episode.get("title"),
        )

        if score >= threshold:
            return True

    return False


def _title_exists_elsewhere_in_afl(
    title,
    sorted_afl,
    excluded_index=None,
    threshold=0.80,
):
    """
    Return True if a Plex title has a strong match somewhere else
    in the AFL sequence.

    This prevents an AFL/Plex reorder from being mistaken for a
    Plex-only regular episode.
    """
    for index, afl_episode in enumerate(sorted_afl):
        if (
            excluded_index is not None
            and index == excluded_index
        ):
            continue

        score = _title_similarity(
            title,
            afl_episode.get("name"),
        )

        if score >= threshold:
            return True

    return False


def _confirm_afl_extra_sequence(
    sorted_afl,
    index,
    episode_map,
    plex_absolute,
    threshold,
    confirmations=3,
):
    """
    Confirm that skipping the current AFL episode produces a stable
    sequence alignment.

    Example:

        AFL 25 = possible AFL-only episode
        AFL 26 ~= Plex 25
        AFL 27 ~= Plex 26
        AFL 28 ~= Plex 27

    All confirmation matches must succeed.
    """
    current_number = _afl_episode_number(
        sorted_afl[index]
    )

    if current_number is None:
        return False, []

    scores = []

    for step in range(1, confirmations + 1):
        afl_index = index + step

        if afl_index >= len(sorted_afl):
            return False, scores

        candidate_afl = sorted_afl[afl_index]

        candidate_number = _afl_episode_number(
            candidate_afl
        )

        # Require an actually consecutive AFL sequence.
        if candidate_number != current_number + step:
            return False, scores

        candidate_plex = episode_map.get(
            str(plex_absolute + step - 1)
        )

        if not candidate_plex:
            return False, scores

        score = _title_similarity(
            candidate_afl.get("name"),
            candidate_plex.get("title"),
        )

        scores.append(score)

        if score < threshold:
            return False, scores

    return True, scores


def _confirm_plex_extra_sequence(
    sorted_afl,
    index,
    episode_map,
    plex_absolute,
    threshold,
    confirmations=3,
):
    """
    Confirm that skipping the current Plex episode produces a stable
    sequence alignment.

    Example:

        Plex 25 = possible Plex-only episode
        AFL 25 ~= Plex 26
        AFL 26 ~= Plex 27
        AFL 27 ~= Plex 28

    All confirmation matches must succeed.
    """
    current_number = _afl_episode_number(
        sorted_afl[index]
    )

    if current_number is None:
        return False, []

    scores = []

    for step in range(confirmations):
        afl_index = index + step

        if afl_index >= len(sorted_afl):
            return False, scores

        candidate_afl = sorted_afl[afl_index]

        candidate_number = _afl_episode_number(
            candidate_afl
        )

        if candidate_number != current_number + step:
            return False, scores

        candidate_plex = episode_map.get(
            str(plex_absolute + step + 1)
        )

        if not candidate_plex:
            return False, scores

        score = _title_similarity(
            candidate_afl.get("name"),
            candidate_plex.get("title"),
        )

        scores.append(score)

        if score < threshold:
            return False, scores

    return True, scores


def _build_episode_number_map(
    all_afl_episodes,
    episode_map,
    special_episode_map=None,
    title_match_threshold=0.65,
    realignment_match_threshold=0.80,
    realignment_confirmations=3,
    special_match_threshold=0.80,
):
    """
    Build an AFL absolute-number -> Plex episode mapping.

    Direct absolute numbering is preferred:

        AFL 21 -> Plex absolute 21

    Sequence offsets are changed only when there is strong evidence
    that one side contains an episode absent from the other.

    Realignment deliberately requires multiple consecutive title
    matches. A single neighboring title match is not sufficient,
    because some shows use substantially different episode orders.
    """
    lookup = {}
    warnings = []
    offset = 0
    special_episode_map = special_episode_map or {}

    # Structural sequence changes should require stronger evidence
    # than ordinary title-warning suppression.
    structural_threshold = max(
        title_match_threshold,
        realignment_match_threshold,
    )

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

        plex_absolute = afl_number + offset

        plex_episode = episode_map.get(
            str(plex_absolute)
        )

        if not plex_episode:
            (
                plex_special,
                special_score,
            ) = _find_matching_plex_special(
                afl_episode.get("name"),
                special_episode_map,
                threshold=special_match_threshold,
            )

            if plex_special:
                lookup[clean_number] = plex_special

                warnings.append(
                    {
                        "type": "plex_special",
                        "afl_episode": afl_episode,
                        "plex_special": plex_special,
                        "score": special_score,
                        "new_offset": offset,
                        "sequence_shift_confirmed": False,
                        "confirmation_scores": [],
                    }
                )
                continue

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
        # Before treating a weak regular-episode title match as translation
        # variation or structural reordering, check whether AFL is actually
        # describing a Plex Season 0 item. This prevents an appended OVA from
        # being silently assigned to the last regular episode merely because
        # their absolute numbers collide.
        #
        (
            plex_special,
            special_score,
        ) = _find_matching_plex_special(
            afl_episode.get("name"),
            special_episode_map,
            threshold=special_match_threshold,
        )

        if plex_special:
            lookup[clean_number] = plex_special

            # A Season 0 match does not, by itself, prove that the special
            # consumes a position in AFL's regular absolute sequence.
            #
            # Appended OVAs are common: AFL may continue numbering them after
            # the TV run while Plex keeps the final regular episode at that
            # same absolute number. Automatically changing the offset here
            # would make the next AFL special collide with the last regular
            # episode.
            #
            # Shift only when several following AFL episodes prove that,
            # after skipping this special, regular numbering resumes one
            # position earlier in Plex.
            (
                confirmed_special_shift,
                confirmation_scores,
            ) = _confirm_afl_extra_sequence(
                sorted_afl,
                index,
                episode_map,
                plex_absolute,
                threshold=structural_threshold,
                confirmations=realignment_confirmations,
            )

            if confirmed_special_shift:
                offset -= 1

            warnings.append(
                {
                    "type": "plex_special",
                    "afl_episode": afl_episode,
                    "plex_special": plex_special,
                    "score": special_score,
                    "new_offset": offset,
                    "sequence_shift_confirmed": (
                        confirmed_special_shift
                    ),
                    "confirmation_scores": confirmation_scores,
                }
            )
            continue

        #
        # Candidate AFL-only episode.
        #
        # Never decide this from one neighboring title.
        #
        # We require:
        #
        #   1. The current AFL title does NOT appear elsewhere in Plex.
        #      If it does, this may simply be a reordered show.
        #
        #   2. Several consecutive following AFL episodes align with
        #      consecutive Plex episodes after skipping the current AFL
        #      episode.
        #
        current_afl_exists_elsewhere = (
            _title_exists_elsewhere_in_plex(
                afl_episode.get("name"),
                episode_map,
                excluded_absolute=plex_absolute,
                threshold=structural_threshold,
            )
        )

        if not current_afl_exists_elsewhere:
            (
                confirmed_afl_extra,
                confirmation_scores,
            ) = _confirm_afl_extra_sequence(
                sorted_afl,
                index,
                episode_map,
                plex_absolute,
                threshold=structural_threshold,
                confirmations=realignment_confirmations,
            )

            if confirmed_afl_extra:
                lookup[clean_number] = None

                offset -= 1

                warnings.append(
                    {
                        "type": "afl_extra",
                        "afl_episode": afl_episode,
                        "plex_episode": plex_episode,
                        "confirmation_scores": (
                            confirmation_scores
                        ),
                        "new_offset": offset,
                    }
                )

                continue

        #
        # Candidate Plex-only episode.
        #
        # Again, require sequence-level evidence rather than a single
        # nearby title match.
        #
        # If the current Plex title appears elsewhere in AFL, the show
        # may simply use a different episode order and should NOT cause
        # a permanent offset.
        #
        current_plex_exists_elsewhere = (
            _title_exists_elsewhere_in_afl(
                plex_episode.get("title"),
                sorted_afl,
                excluded_index=index,
                threshold=structural_threshold,
            )
        )

        if not current_plex_exists_elsewhere:
            (
                confirmed_plex_extra,
                confirmation_scores,
            ) = _confirm_plex_extra_sequence(
                sorted_afl,
                index,
                episode_map,
                plex_absolute,
                threshold=structural_threshold,
                confirmations=realignment_confirmations,
            )

            if confirmed_plex_extra:
                offset += 1

                plex_absolute = (
                    afl_number + offset
                )

                plex_episode = episode_map.get(
                    str(plex_absolute)
                )

                if plex_episode:
                    lookup[clean_number] = plex_episode

                    warnings.append(
                        {
                            "type": "plex_extra",
                            "afl_episode": afl_episode,
                            "plex_episode": plex_episode,
                            "confirmation_scores": (
                                confirmation_scores
                            ),
                            "new_offset": offset,
                        }
                    )

                    continue

                # Defensive fallback: if the newly calculated position
                # unexpectedly does not exist, undo the tentative shift.
                offset -= 1

        #
        # No sufficiently strong sequence evidence.
        #
        # Preserve direct absolute numbering. A title mismatch is much
        # safer than changing every subsequent episode based on weak
        # evidence.
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



def _assess_lookup_confidence(
    all_afl_episodes,
    number_lookup,
    threshold=0.65,
):
    """
    Measure how well a proposed AFL -> Plex mapping agrees by title.

    Only mapped AFL episodes are compared. An AFL episode that was
    conservatively identified as absent from the Plex regular-episode
    sequence does not reduce the score.
    """
    compared = 0
    strong_matches = 0
    total_score = 0.0

    for afl_episode in all_afl_episodes:
        clean_number = _clean_episode_number(
            afl_episode.get("number")
        )

        if not clean_number:
            continue

        plex_episode = number_lookup.get(clean_number)

        if not plex_episode:
            continue

        score = _title_similarity(
            afl_episode.get("name"),
            plex_episode.get("title"),
        )

        compared += 1
        total_score += score

        if score >= threshold:
            strong_matches += 1

    if compared == 0:
        return {
            "compared": 0,
            "strong_matches": 0,
            "strong_ratio": 0.0,
            "average_score": 0.0,
        }

    return {
        "compared": compared,
        "strong_matches": strong_matches,
        "strong_ratio": strong_matches / compared,
        "average_score": total_score / compared,
    }



def _assess_off_position_evidence(
    all_afl_episodes,
    episode_map,
    strong_threshold=0.80,
):
    """
    Measure evidence that AFL and Plex use different episode ordering.

    For each AFL episode that has a direct Plex absolute-number candidate:
      - direct_strong: direct title similarity >= threshold
      - off_position_strong: direct match is weak, but the AFL title has a
        strong match at a different Plex absolute position
      - neither: no strong title match at the direct or any other position

    A high off-position ratio is evidence of structural reordering.
    A low off-position ratio with many "neither" results is more consistent
    with translation/title variation while numbering remains aligned.
    """
    direct_strong = 0
    off_position_strong = 0
    neither = 0

    for afl_episode in all_afl_episodes:
        clean_number = _clean_episode_number(
            afl_episode.get("number")
        )
        if not clean_number:
            continue

        direct_episode = episode_map.get(clean_number)
        if not direct_episode:
            continue

        direct_score = _title_similarity(
            afl_episode.get("name"),
            direct_episode.get("title"),
        )
        if direct_score >= strong_threshold:
            direct_strong += 1
            continue

        found_elsewhere = False
        for plex_number, plex_episode in episode_map.items():
            if plex_number == clean_number:
                continue
            score = _title_similarity(
                afl_episode.get("name"),
                plex_episode.get("title"),
            )
            if score >= strong_threshold:
                found_elsewhere = True
                break

        if found_elsewhere:
            off_position_strong += 1
        else:
            neither += 1

    total = direct_strong + off_position_strong + neither
    if total == 0:
        return {
            "total": 0,
            "direct_strong": 0,
            "off_position_strong": 0,
            "neither": 0,
            "direct_ratio": 0.0,
            "off_position_ratio": 0.0,
            "neither_ratio": 0.0,
        }

    return {
        "total": total,
        "direct_strong": direct_strong,
        "off_position_strong": off_position_strong,
        "neither": neither,
        "direct_ratio": direct_strong / total,
        "off_position_ratio": off_position_strong / total,
        "neither_ratio": neither / total,
    }

def _build_title_based_episode_map(
    all_afl_episodes,
    episode_map,
    title_match_threshold=0.80,
    ambiguity_margin=0.08,
):
    """
    Build an AFL absolute-number -> Plex mapping using episode titles.

    This is used only when direct aired-order numbering has poor title
    agreement. Plex episodes are consumed one-to-one so two AFL episodes
    cannot accidentally map to the same regular Plex episode.

    Matching happens in two passes:

      1. Unique exact normalized-title matches.
      2. Conservative fuzzy matches for unresolved episodes.

    A fuzzy match must clear title_match_threshold and be sufficiently
    better than the second-best unused Plex candidate.
    """
    sorted_afl = sorted(
        all_afl_episodes,
        key=lambda episode: int(
            _clean_episode_number(
                episode.get("number")
            ) or 999999999
        ),
    )

    plex_items = []

    for absolute_string, plex_episode in episode_map.items():
        try:
            absolute_number = int(absolute_string)
        except (TypeError, ValueError):
            continue

        plex_items.append(
            (absolute_number, plex_episode)
        )

    plex_items.sort(
        key=lambda item: item[0]
    )

    lookup = {}
    warnings = []
    used_plex_absolutes = set()

    normalized_plex = {}

    for absolute_number, plex_episode in plex_items:
        normalized = (
            _normalize_episode_match_title(
                plex_episode.get("title") or ""
            )
        )

        if normalized:
            normalized_plex.setdefault(
                normalized,
                [],
            ).append(
                (absolute_number, plex_episode)
            )

    unresolved = []

    #
    # Pass 1: unique exact normalized-title matches.
    #
    for afl_episode in sorted_afl:
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

        normalized = (
            _normalize_episode_match_title(
                afl_episode.get("name") or ""
            )
        )

        exact_candidates = [
            candidate
            for candidate in normalized_plex.get(
                normalized,
                [],
            )
            if candidate[0] not in used_plex_absolutes
        ]

        if len(exact_candidates) == 1:
            absolute_number, plex_episode = (
                exact_candidates[0]
            )

            lookup[clean_number] = plex_episode
            used_plex_absolutes.add(
                absolute_number
            )
            continue

        unresolved.append(
            (
                clean_number,
                afl_episode,
            )
        )

    #
    # Pass 2: conservative fuzzy title matching.
    #
    for clean_number, afl_episode in unresolved:
        scored_candidates = []

        for absolute_number, plex_episode in plex_items:
            if absolute_number in used_plex_absolutes:
                continue

            score = _title_similarity(
                afl_episode.get("name"),
                plex_episode.get("title"),
            )

            scored_candidates.append(
                (
                    score,
                    absolute_number,
                    plex_episode,
                )
            )

        scored_candidates.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        if not scored_candidates:
            lookup[clean_number] = None

            warnings.append(
                {
                    "type": "title_unmapped",
                    "afl_episode": afl_episode,
                    "best_score": 0.0,
                    "second_score": 0.0,
                }
            )
            continue

        (
            best_score,
            best_absolute,
            best_episode,
        ) = scored_candidates[0]

        second_score = (
            scored_candidates[1][0]
            if len(scored_candidates) > 1
            else 0.0
        )

        sufficiently_distinct = (
            best_score - second_score
            >= ambiguity_margin
        )

        if (
            best_score >= title_match_threshold
            and sufficiently_distinct
        ):
            lookup[clean_number] = best_episode
            used_plex_absolutes.add(
                best_absolute
            )
            continue

        lookup[clean_number] = None

        warnings.append(
            {
                "type": "title_unmapped",
                "afl_episode": afl_episode,
                "best_score": best_score,
                "second_score": second_score,
            }
        )

    valid_afl_count = sum(
        1
        for episode in sorted_afl
        if _clean_episode_number(
            episode.get("number")
        )
    )

    mapped_count = sum(
        1
        for plex_episode in lookup.values()
        if plex_episode
    )

    coverage = (
        mapped_count / valid_afl_count
        if valid_afl_count
        else 0.0
    )

    return (
        lookup,
        warnings,
        {
            "total": valid_afl_count,
            "mapped": mapped_count,
            "unmapped": (
                valid_afl_count - mapped_count
            ),
            "coverage": coverage,
        },
    )


def _log_title_mapping_warnings(
    anime_name,
    warnings,
):
    """Log unresolved title-based mapping cases."""
    unresolved = [
        warning
        for warning in warnings
        if warning.get("type") == "title_unmapped"
    ]

    invalid = [
        warning
        for warning in warnings
        if warning.get("type") == "invalid_afl_number"
    ]

    if unresolved:
        logger.warning(
            f"{anime_name}: title-based mapping left "
            f"{len(unresolved)} AFL episodes unresolved"
        )

        for warning in unresolved[:10]:
            afl_episode = warning["afl_episode"]

            logger.warning(
                f"{anime_name}: could not confidently title-map "
                f"AFL episode {afl_episode.get('number')} "
                f"'{afl_episode.get('name')}' "
                f"(best {warning['best_score']:.0%}, "
                f"second {warning['second_score']:.0%})"
            )

        if len(unresolved) > 10:
            logger.warning(
                f"{anime_name}: "
                f"{len(unresolved) - 10} additional "
                f"title-based mapping failures suppressed"
            )

    for warning in invalid:
        afl_episode = warning["afl_episode"]

        logger.warning(
            f"{anime_name}: invalid AFL episode number "
            f"'{afl_episode.get('number')}'"
        )

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

            scores = warning.get(
                "confirmation_scores",
                [],
            )

            score_text = ", ".join(
                f"{score:.0%}"
                for score in scores
            )

            logger.warning(
                f"{anime_name}: AFL episode "
                f"{afl_episode.get('number')} "
                f"'{afl_episode.get('name')}' appears absent "
                f"from the Plex regular-episode sequence; "
                f"{len(scores)} subsequent episode matches "
                f"confirmed realignment"
                + (
                    f" ({score_text})"
                    if score_text
                    else ""
                )
                + f"; subsequent Plex mapping offset is "
                f"{warning['new_offset']}"
            )

            stats["afl_only_episodes"] += 1
            stats["sequence_realignments"] += 1

        elif warning_type == "plex_extra":
            afl_episode = warning["afl_episode"]
            plex_episode = warning["plex_episode"]

            scores = warning.get(
                "confirmation_scores",
                [],
            )

            score_text = ", ".join(
                f"{score:.0%}"
                for score in scores
            )

            logger.warning(
                f"{anime_name}: Plex appears to contain "
                f"a regular episode absent from the AFL sequence "
                f"before AFL episode "
                f"{afl_episode.get('number')} "
                f"'{afl_episode.get('name')}'; "
                f"{len(scores)} subsequent episode matches "
                f"confirmed realignment"
                + (
                    f" ({score_text})"
                    if score_text
                    else ""
                )
                + f"; realigned to Plex "
                f"S{plex_episode['season']:02d}"
                f"E{plex_episode['episode']:02d}; "
                f"subsequent mapping offset is "
                f"{warning['new_offset']}"
            )

            stats["sequence_realignments"] += 1

        elif warning_type == "plex_special":
            afl_episode = warning["afl_episode"]
            plex_special = warning["plex_special"]

            shift_confirmed = warning.get(
                "sequence_shift_confirmed",
                False,
            )

            scores = warning.get(
                "confirmation_scores",
                [],
            )

            score_text = ", ".join(
                f"{score:.0%}"
                for score in scores
            )

            logger.warning(
                f"{anime_name}: AFL episode "
                f"{afl_episode.get('number')} "
                f"'{afl_episode.get('name')}' matched Plex special "
                f"S00E{plex_special['episode']:02d} "
                f"'{plex_special.get('title')}' "
                f"({warning['score']:.0%}); using Season 0 mapping"
                + (
                    f"; {len(scores)} subsequent regular episode "
                    f"matches confirmed sequence shift"
                    + (
                        f" ({score_text})"
                        if score_text
                        else ""
                    )
                    + f"; subsequent mapping offset is "
                    f"{warning['new_offset']}"
                    if shift_confirmed
                    else ""
                )
            )

            stats["special_episodes_mapped"] += 1

            if shift_confirmed:
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
        "special_episodes_mapped": 0,
        "direct_order_shows": 0,
        "title_mapped_shows": 0,
        "ordering_rejected_shows": 0,
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

        special_episode_map = (
            _build_plex_special_episode_map(show)
        )

        if special_episode_map:
            logger.debug(
                f"{anime_name}: {len(special_episode_map)} Plex "
                f"Season 0 episodes available for title matching"
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

        #
        # First try direct absolute numbering plus conservative sequence
        # reconciliation. Then verify that the resulting show-level map
        # actually agrees with episode titles.
        #
        number_lookup, mapping_warnings = (
            _build_episode_number_map(
                all_afl_episodes,
                episode_map,
                special_episode_map=(
                    special_episode_map
                ),
                title_match_threshold=(
                    title_warning_threshold
                ),
            )
        )

        special_afl_numbers = {
            _clean_episode_number(
                warning["afl_episode"].get("number")
            )
            for warning in mapping_warnings
            if warning.get("type") == "plex_special"
        }

        regular_afl_episodes = [
            episode
            for episode in all_afl_episodes
            if _clean_episode_number(
                episode.get("number")
            ) not in special_afl_numbers
        ]

        ordering_confidence = (
            _assess_lookup_confidence(
                regular_afl_episodes,
                number_lookup,
                threshold=title_warning_threshold,
            )
        )

        direct_order_min_ratio = 0.75
        reorder_evidence_threshold = 0.20
        title_mapping_min_coverage = 0.75

        if (
            ordering_confidence["strong_ratio"]
            >= direct_order_min_ratio
        ):
            logger.info(
                f"{anime_name}: using Plex aired-order mapping; "
                f"title agreement "
                f"{ordering_confidence['strong_matches']}/"
                f"{ordering_confidence['compared']} "
                f"({ordering_confidence['strong_ratio']:.0%}), "
                f"average similarity "
                f"{ordering_confidence['average_score']:.0%}"
            )

            _log_mapping_warnings(
                anime_name,
                mapping_warnings,
                stats,
            )

            stats["direct_order_shows"] += 1

        else:
            reorder_evidence = _assess_off_position_evidence(
                regular_afl_episodes,
                episode_map,
                strong_threshold=0.80,
            )

            if (
                reorder_evidence["off_position_ratio"]
                < reorder_evidence_threshold
            ):
                logger.warning(
                    f"{anime_name}: Plex aired-order mapping has low "
                    f"title agreement "
                    f"{ordering_confidence['strong_matches']}/"
                    f"{ordering_confidence['compared']} "
                    f"({ordering_confidence['strong_ratio']:.0%}), "
                    f"but only "
                    f"{reorder_evidence['off_position_strong']}/"
                    f"{reorder_evidence['total']} episodes "
                    f"({reorder_evidence['off_position_ratio']:.0%}) "
                    f"have strong title matches at different Plex "
                    f"positions; treating differences as title/"
                    f"translation variation and retaining direct numbering"
                )

                _log_mapping_warnings(
                    anime_name,
                    mapping_warnings,
                    stats,
                )

                stats["direct_order_shows"] += 1

            else:
                logger.warning(
                    f"{anime_name}: Plex aired-order mapping has low "
                    f"title agreement "
                    f"{ordering_confidence['strong_matches']}/"
                    f"{ordering_confidence['compared']} "
                    f"({ordering_confidence['strong_ratio']:.0%}) "
                    f"and "
                    f"{reorder_evidence['off_position_strong']}/"
                    f"{reorder_evidence['total']} episodes "
                    f"({reorder_evidence['off_position_ratio']:.0%}) "
                    f"have strong title matches at different Plex "
                    f"positions; trying title-based episode mapping"
                )

                (
                    title_lookup,
                    title_mapping_warnings,
                    title_mapping_stats,
                ) = _build_title_based_episode_map(
                    regular_afl_episodes,
                    episode_map,
                    title_match_threshold=0.80,
                    ambiguity_margin=0.08,
                )

                for special_number in special_afl_numbers:
                    special_episode = number_lookup.get(
                        special_number
                    )

                    if special_episode:
                        title_lookup[special_number] = (
                            special_episode
                        )

                if (
                    title_mapping_stats["coverage"]
                    >= title_mapping_min_coverage
                ):
                    number_lookup = title_lookup

                    logger.warning(
                        f"{anime_name}: using title-based episode mapping; "
                        f"{title_mapping_stats['mapped']}/"
                        f"{title_mapping_stats['total']} AFL episodes "
                        f"matched unambiguously "
                        f"({title_mapping_stats['coverage']:.0%})"
                    )

                    _log_title_mapping_warnings(
                        anime_name,
                        title_mapping_warnings,
                    )

                    _log_mapping_warnings(
                        anime_name,
                        [
                            warning
                            for warning in mapping_warnings
                            if warning.get("type") == "plex_special"
                        ],
                        stats,
                    )

                    stats["title_mapped_shows"] += 1

                else:
                    logger.error(
                        f"Skipping {anime_name}: episode ordering is "
                        f"incompatible with Plex aired order and only "
                        f"{title_mapping_stats['mapped']}/"
                        f"{title_mapping_stats['total']} episodes "
                        f"could be matched unambiguously by title "
                        f"({title_mapping_stats['coverage']:.0%})"
                    )

                    _log_title_mapping_warnings(
                        anime_name,
                        title_mapping_warnings,
                    )

                    stats["ordering_rejected_shows"] += 1
                    stats["shows_failed"] += 1
                    continue

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