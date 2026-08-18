"""Cohesion rules for managed artwork sets.

Provider state is refresh input, not destructive source of truth.

For the same provider/set ID, Dakosys may add newly available artwork
while retaining previously managed artwork that the provider no longer
returns.

A migration to a different cohesive set must not silently remove
non-episode artwork already supplied by the current set.
"""

from __future__ import annotations

from dataclasses import dataclass

from artwork.assessment import ArtworkSetAssessment
from artwork.models import (
    ArtworkAsset,
    ArtworkSet,
    EpisodeArtwork,
    SeasonArtwork,
)
from artwork.source_policy import (
    prefer_stored_or_primary_asset,
)


def _prefer_existing_asset(
    stored: ArtworkAsset | None,
    live: ArtworkAsset | None,
    *,
    primary_provider,
) -> ArtworkAsset | None:
    """Preserve durable art unless live primary upgrades fallback."""

    return prefer_stored_or_primary_asset(
        stored,
        live,
        primary_provider=primary_provider,
    )


def merge_same_artwork_set(
    stored: ArtworkSet,
    live: ArtworkSet,
) -> ArtworkSet:
    """Add live artwork to durable state for the same cohesive set.

    This is intentionally additive:

    - stored usable assets survive provider regressions;
    - live assets fill previously missing positions;
    - imagery from different provider/set IDs is never merged.
    """

    if (
        stored.provider is not live.provider
        or stored.set_id != live.set_id
    ):
        raise ValueError(
            "only the same provider/set ID can be merged"
        )

    seasons: dict[int, SeasonArtwork] = {}

    season_numbers = sorted(
        set(stored.seasons)
        | set(live.seasons)
    )

    for season_number in season_numbers:
        stored_season = stored.seasons.get(
            season_number
        )

        live_season = live.seasons.get(
            season_number
        )

        stored_poster = (
            stored_season.poster
            if stored_season is not None
            else None
        )

        live_poster = (
            live_season.poster
            if live_season is not None
            else None
        )

        stored_episodes = (
            stored_season.episodes
            if stored_season is not None
            else {}
        )

        live_episodes = (
            live_season.episodes
            if live_season is not None
            else {}
        )

        episodes: dict[
            int,
            EpisodeArtwork,
        ] = {}

        episode_numbers = sorted(
            set(stored_episodes)
            | set(live_episodes)
        )

        for episode_number in episode_numbers:
            stored_episode = (
                stored_episodes.get(
                    episode_number
                )
            )

            live_episode = (
                live_episodes.get(
                    episode_number
                )
            )

            stored_card = (
                stored_episode.card
                if stored_episode is not None
                else None
            )

            live_card = (
                live_episode.card
                if live_episode is not None
                else None
            )

            episodes[
                episode_number
            ] = EpisodeArtwork(
                episode_number=episode_number,
                card=_prefer_existing_asset(
                    stored_card,
                    live_card,
                    primary_provider=stored.provider,
                ),
            )

        seasons[
            season_number
        ] = SeasonArtwork(
            season_number=season_number,
            poster=_prefer_existing_asset(
                stored_poster,
                live_poster,
                primary_provider=stored.provider,
            ),
            episodes=episodes,
        )

    return ArtworkSet(
        provider=stored.provider,
        set_id=stored.set_id,
        creator=(
            stored.creator
            or live.creator
        ),
        title=(
            stored.title
            or live.title
        ),
        poster=_prefer_existing_asset(
            stored.poster,
            live.poster,
            primary_provider=stored.provider,
        ),
        background=_prefer_existing_asset(
            stored.background,
            live.background,
            primary_provider=stored.provider,
        ),
        seasons=seasons,
    )


@dataclass(frozen=True)
class MigrationCompatibility:
    """Non-episode regressions caused by changing cohesive sets."""

    show_poster_regression: bool = False
    show_background_regression: bool = False
    season_poster_regressions: tuple[
        int,
        ...,
    ] = ()

    episode_card_regressions: tuple[
        tuple[int, int],
        ...,
    ] = ()

    @property
    def eligible(self) -> bool:
        return not (
            self.show_poster_regression
            or self.show_background_regression
            or self.season_poster_regressions
            or self.episode_card_regressions
        )

    @property
    def reasons(self) -> tuple[str, ...]:
        reasons: list[str] = []

        if self.show_poster_regression:
            reasons.append(
                "show_poster_regression"
            )

        if self.show_background_regression:
            reasons.append(
                "show_background_regression"
            )

        if self.season_poster_regressions:
            reasons.append(
                "season_poster_regression"
            )

        if self.episode_card_regressions:
            reasons.append(
                "episode_card_regression"
            )

        return tuple(reasons)


def _inventory_signature(
    assessment: ArtworkSetAssessment,
) -> tuple[
    tuple[int, tuple[int, ...]],
    ...,
]:
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
        in assessment
        .episode_coverage
        .seasons
    )


def assess_migration_compatibility(
    current: ArtworkSetAssessment,
    challenger: ArtworkSetAssessment,
) -> MigrationCompatibility:
    """Determine whether migration would remove existing artwork.

    Episode-card improvement is deliberately not evaluated here.
    artwork.policy remains responsible for determining whether the
    challenger's episode coverage justifies migration.

    This function is the cohesion gate before that policy.
    """

    if (
        _inventory_signature(current)
        != _inventory_signature(
            challenger
        )
    ):
        raise ValueError(
            "current and challenger must use the same "
            "expected episode inventory"
        )

    current_seasons = set(
        current
        .available_expected_season_poster_numbers
    )

    challenger_seasons = set(
        challenger
        .available_expected_season_poster_numbers
    )

    current_cards: set[
        tuple[int, int]
    ] = set()

    challenger_cards: set[
        tuple[int, int]
    ] = set()

    for season in (
        current
        .episode_coverage
        .seasons
    ):
        current_cards.update(
            (
                season.season_number,
                episode_number,
            )
            for episode_number
            in season.available_episodes
        )

    for season in (
        challenger
        .episode_coverage
        .seasons
    ):
        challenger_cards.update(
            (
                season.season_number,
                episode_number,
            )
            for episode_number
            in season.available_episodes
        )

    episode_card_regressions = tuple(
        sorted(
            current_cards
            - challenger_cards
        )
    )

    return MigrationCompatibility(
        show_poster_regression=(
            current.show_poster_available
            and not challenger.show_poster_available
        ),
        show_background_regression=(
            current.show_background_available
            and not challenger.show_background_available
        ),
        season_poster_regressions=tuple(
            sorted(
                current_seasons
                - challenger_seasons
            )
        ),
        episode_card_regressions=(
            episode_card_regressions
        ),
    )
