"""Candidate selection helpers for cohesive artwork sets.

This module ranks provider candidates but does not decide whether an
existing managed selection should migrate. Migration policy remains in
artwork.policy.

Discovery and reevaluation deliberately use different workflows:

- discovery ranks all candidates;
- reevaluation first locates and evaluates the currently selected set,
  then considers challengers only when appropriate.
"""

from __future__ import annotations

from collections.abc import Iterable

from artwork.assessment import ArtworkSetAssessment
from artwork.models import ArtworkSource


def _expected_inventory_signature(
    assessment: ArtworkSetAssessment,
) -> tuple[tuple[int, tuple[int, ...]], ...]:
    """Return the Plex inventory used to assess this candidate."""

    return tuple(
        (
            season.season_number,
            tuple(
                sorted(
                    season.expected_episodes
                )
            ),
        )
        for season
        in assessment.episode_coverage.seasons
    )


def _validate_same_inventory(
    assessments: tuple[
        ArtworkSetAssessment,
        ...,
    ],
) -> None:
    """Ensure candidates were assessed against one Plex item."""

    if len(assessments) < 2:
        return

    expected = _expected_inventory_signature(
        assessments[0]
    )

    for assessment in assessments[1:]:
        if (
            _expected_inventory_signature(
                assessment
            )
            != expected
        ):
            raise ValueError(
                "artwork candidates must use the same "
                "expected episode inventory"
            )


def candidate_quality_key(
    assessment: ArtworkSetAssessment,
) -> tuple[int, bool, int, bool]:
    """Return the provider-neutral discovery quality dimensions.

    Ordering intentionally remains lexicographic rather than using an
    arbitrary weighted score.

    Priority:

    1. episode cards matching actual Plex episodes;
    2. show poster availability;
    3. season posters matching actual Plex seasons;
    4. show background availability.
    """

    return (
        assessment
        .episode_coverage
        .available_episode_count,
        assessment.show_poster_available,
        assessment
        .available_expected_season_poster_count,
        assessment.show_background_available,
    )


def rank_artwork_candidates(
    assessments: Iterable[
        ArtworkSetAssessment
    ],
) -> tuple[
    ArtworkSetAssessment,
    ...,
]:
    """Rank candidates for initial discovery.

    Exact quality ties use provider + set ID only for deterministic
    ordering. They are not considered meaningfully different in
    artwork quality.
    """

    candidates = tuple(
        assessments
    )

    _validate_same_inventory(
        candidates
    )

    # Stable deterministic fallback for exact quality ties.
    ordered = sorted(
        candidates,
        key=lambda assessment: (
            assessment
            .artwork_set
            .provider
            .value,
            assessment.set_id,
        ),
    )

    # Stable sort preserves the fallback ordering for exact ties.
    ordered.sort(
        key=candidate_quality_key,
        reverse=True,
    )

    return tuple(
        ordered
    )


def choose_discovery_candidate(
    assessments: Iterable[
        ArtworkSetAssessment
    ],
) -> ArtworkSetAssessment | None:
    """Return the strongest candidate for an unmanaged Plex item."""

    ranked = rank_artwork_candidates(
        assessments
    )

    if not ranked:
        return None

    return ranked[0]


def find_selected_candidate(
    assessments: Iterable[
        ArtworkSetAssessment
    ],
    *,
    provider: ArtworkSource,
    set_id: str,
) -> ArtworkSetAssessment | None:
    """Find the live candidate matching the managed selection."""

    matches = tuple(
        assessment
        for assessment in assessments
        if (
            assessment.artwork_set.provider
            is provider
            and assessment.set_id == set_id
        )
    )

    if len(matches) > 1:
        raise ValueError(
            "duplicate provider/set ID candidate"
        )

    if not matches:
        return None

    return matches[0]


def rank_challengers(
    assessments: Iterable[
        ArtworkSetAssessment
    ],
    *,
    current_provider: ArtworkSource,
    current_set_id: str,
) -> tuple[
    ArtworkSetAssessment,
    ...,
]:
    """Rank every candidate except the currently selected set."""

    challengers = tuple(
        assessment
        for assessment in assessments
        if not (
            assessment.artwork_set.provider
            is current_provider
            and assessment.set_id
            == current_set_id
        )
    )

    return rank_artwork_candidates(
        challengers
    )



def choose_episode_candidate(
    assessments: Iterable[ArtworkSetAssessment],
) -> ArtworkSetAssessment | None:
    """Choose the best cohesive set that actually supplies episode cards."""

    candidates = tuple(
        assessment
        for assessment in assessments
        if (
            assessment
            .episode_coverage
            .available_episode_count
            > 0
        )
    )

    if not candidates:
        return None

    return choose_discovery_candidate(
        candidates
    )


def presentation_quality_key(
    assessment: ArtworkSetAssessment,
) -> tuple[bool, int, bool]:
    """Rank one cohesive show/season presentation set.

    Episode-card coverage is intentionally excluded here.
    """

    expected_seasons = set(
        assessment.expected_season_numbers
    )

    provider_seasons = set(
        assessment.season_poster_numbers
    )

    expected_season_posters = len(
        expected_seasons
        & provider_seasons
    )

    return (
        assessment.show_poster_available,
        expected_season_posters,
        assessment.show_background_available,
    )


def choose_presentation_candidate(
    assessments: Iterable[ArtworkSetAssessment],
    *,
    preferred: ArtworkSetAssessment | None = None,
) -> ArtworkSetAssessment | None:
    """Choose one cohesive show/season presentation set.

    When presentation quality ties exactly, prefer the episode-card set
    so Dakosys avoids splitting families unnecessarily.
    """

    candidates = tuple(
        assessment
        for assessment in assessments
        if (
            assessment.show_poster_available
            or assessment.show_background_available
            or bool(
                set(
                    assessment.expected_season_numbers
                )
                & set(
                    assessment.season_poster_numbers
                )
            )
        )
    )

    if not candidates:
        return None

    best_key = max(
        presentation_quality_key(
            assessment
        )
        for assessment in candidates
    )

    tied = tuple(
        assessment
        for assessment in candidates
        if (
            presentation_quality_key(
                assessment
            )
            == best_key
        )
    )

    if preferred is not None:
        for assessment in tied:
            if (
                assessment.artwork_set.provider
                is preferred.artwork_set.provider
                and assessment.set_id
                == preferred.set_id
            ):
                return assessment

    return min(
        tied,
        key=lambda assessment: (
            assessment.artwork_set.provider.value,
            assessment.set_id,
        ),
    )
