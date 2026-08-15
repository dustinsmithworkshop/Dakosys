"""Coverage analysis for cohesive artwork sets."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from artwork.models import ArtworkSet, ArtworkSource


@dataclass(frozen=True)
class SeasonCoverage:
    """Coverage of one artwork set against one expected season."""

    season_number: int
    expected_episodes: frozenset[int]
    available_episodes: frozenset[int]
    missing_episodes: frozenset[int]
    extra_episodes: frozenset[int]

    @property
    def expected_count(self) -> int:
        return len(self.expected_episodes)

    @property
    def available_count(self) -> int:
        return len(
            self.expected_episodes
            & self.available_episodes
        )

    @property
    def missing_count(self) -> int:
        return len(self.missing_episodes)

    @property
    def coverage_ratio(self) -> float:
        if not self.expected_episodes:
            return 0.0

        return (
            self.available_count
            / self.expected_count
        )

    @property
    def complete(self) -> bool:
        return (
            bool(self.expected_episodes)
            and not self.missing_episodes
        )


@dataclass(frozen=True)
class ArtworkSetCoverage:
    """Coverage summary for one coherent artwork set."""

    provider: ArtworkSource
    set_id: str
    seasons: tuple[SeasonCoverage, ...]

    @property
    def expected_episode_count(self) -> int:
        return sum(
            season.expected_count
            for season in self.seasons
        )

    @property
    def available_episode_count(self) -> int:
        return sum(
            season.available_count
            for season in self.seasons
        )

    @property
    def missing_episode_count(self) -> int:
        return sum(
            season.missing_count
            for season in self.seasons
        )

    @property
    def coverage_ratio(self) -> float:
        expected = self.expected_episode_count

        if expected == 0:
            return 0.0

        return (
            self.available_episode_count
            / expected
        )

    @property
    def complete(self) -> bool:
        return (
            self.expected_episode_count > 0
            and self.missing_episode_count == 0
        )

    def season(
        self,
        season_number: int,
    ) -> SeasonCoverage | None:
        for season in self.seasons:
            if season.season_number == season_number:
                return season

        return None


def _available_episode_numbers(
    artwork_set: ArtworkSet,
    season_number: int,
) -> frozenset[int]:
    season = artwork_set.seasons.get(
        season_number
    )

    if season is None:
        return frozenset()

    return frozenset(
        episode_number
        for episode_number, episode
        in season.episodes.items()
        if (
            episode.card is not None
            and episode.card.url
        )
    )


def analyze_set_coverage(
    artwork_set: ArtworkSet,
    expected_episodes: Mapping[
        int,
        Iterable[int],
    ],
) -> ArtworkSetCoverage:
    """Compare one coherent artwork set to a Plex-style inventory.

    ``expected_episodes`` maps season numbers to episode numbers that
    currently exist in the user's library.

    Extra provider artwork does not reduce completeness. Only artwork
    missing for episodes that actually exist in the expected inventory
    counts against coverage.
    """

    season_results: list[SeasonCoverage] = []

    for season_number in sorted(
        expected_episodes
    ):
        expected = frozenset(
            int(number)
            for number
            in expected_episodes[
                season_number
            ]
        )

        if not expected:
            continue

        available = (
            _available_episode_numbers(
                artwork_set,
                season_number,
            )
        )

        season_results.append(
            SeasonCoverage(
                season_number=season_number,
                expected_episodes=expected,
                available_episodes=available,
                missing_episodes=(
                    expected - available
                ),
                extra_episodes=(
                    available - expected
                ),
            )
        )

    return ArtworkSetCoverage(
        provider=artwork_set.provider,
        set_id=artwork_set.set_id,
        seasons=tuple(season_results),
    )
