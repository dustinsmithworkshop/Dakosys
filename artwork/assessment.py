"""Assessment of cohesive artwork-set candidates.

Coverage answers whether episode cards exist for the episodes actually
present in Plex.

Assessment adds the other dimensions of a provider artwork set without
collapsing them into a single arbitrary score. Selection policy can then
reason about episode coverage, show artwork, and season artwork
explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Collection, Mapping

from artwork.coverage import (
    ArtworkSetCoverage,
    analyze_set_coverage,
)
from artwork.models import ArtworkSet


@dataclass(frozen=True)
class ArtworkSetAssessment:
    """Independent quality dimensions for one cohesive artwork set."""

    artwork_set: ArtworkSet
    episode_coverage: ArtworkSetCoverage

    show_poster_available: bool
    show_background_available: bool

    expected_season_numbers: tuple[int, ...]
    season_poster_numbers: tuple[int, ...]

    @property
    def set_id(self) -> str:
        return self.artwork_set.set_id

    @property
    def creator(self) -> str | None:
        return self.artwork_set.creator

    @property
    def expected_season_poster_count(self) -> int:
        return len(
            self.expected_season_numbers
        )

    @property
    def available_expected_season_poster_numbers(
        self,
    ) -> tuple[int, ...]:
        expected = set(
            self.expected_season_numbers
        )

        return tuple(
            number
            for number
            in self.season_poster_numbers
            if number in expected
        )

    @property
    def available_expected_season_poster_count(
        self,
    ) -> int:
        return len(
            self.available_expected_season_poster_numbers
        )

    @property
    def missing_season_poster_numbers(
        self,
    ) -> tuple[int, ...]:
        available = set(
            self.season_poster_numbers
        )

        return tuple(
            number
            for number
            in self.expected_season_numbers
            if number not in available
        )

    @property
    def extra_season_poster_numbers(
        self,
    ) -> tuple[int, ...]:
        expected = set(
            self.expected_season_numbers
        )

        return tuple(
            number
            for number
            in self.season_poster_numbers
            if number not in expected
        )

    @property
    def season_poster_ratio(
        self,
    ) -> float | None:
        expected = (
            self.expected_season_poster_count
        )

        if expected == 0:
            return None

        return (
            self.available_expected_season_poster_count
            / expected
        )


def assess_artwork_set(
    artwork_set: ArtworkSet,
    expected_episodes: Mapping[
        int,
        Collection[int],
    ],
) -> ArtworkSetAssessment:
    """Assess one provider set against the actual Plex inventory."""

    coverage = analyze_set_coverage(
        artwork_set,
        expected_episodes,
    )

    expected_season_numbers = tuple(
        season.season_number
        for season in coverage.seasons
        if season.expected_episodes
    )

    season_poster_numbers = tuple(
        sorted(
            season_number
            for season_number, season
            in artwork_set.seasons.items()
            if (
                season.poster is not None
                and season.poster.available
            )
        )
    )

    show_poster_available = bool(
        artwork_set.poster is not None
        and artwork_set.poster.available
    )

    show_background_available = bool(
        artwork_set.background is not None
        and artwork_set.background.available
    )

    return ArtworkSetAssessment(
        artwork_set=artwork_set,
        episode_coverage=coverage,
        show_poster_available=(
            show_poster_available
        ),
        show_background_available=(
            show_background_available
        ),
        expected_season_numbers=(
            expected_season_numbers
        ),
        season_poster_numbers=(
            season_poster_numbers
        ),
    )
