"""Build Artwork Manager inventory from Plex library objects."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from tv_metadata.identity import build_show_identity
from tv_metadata.models import ShowIdentity


@dataclass(frozen=True)
class SeasonInventory:
    """Episodes currently present in one Plex season."""

    season_number: int
    episode_numbers: frozenset[int]


@dataclass(frozen=True)
class ShowInventory:
    """Normalized Plex inventory used by Artwork Manager."""

    identity: ShowIdentity
    seasons: tuple[SeasonInventory, ...]

    def season(
        self,
        season_number: int,
    ) -> SeasonInventory | None:
        for season in self.seasons:
            if season.season_number == season_number:
                return season

        return None

    def expected_episodes(
        self,
    ) -> dict[int, frozenset[int]]:
        """Return the shape consumed by artwork coverage analysis."""

        return {
            season.season_number: season.episode_numbers
            for season in self.seasons
        }


def _positive_integer(
    value,
) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None

    if parsed < 0:
        return None

    return parsed


def build_show_inventory(
    show,
    library: str,
    *,
    library_roles: Iterable[str] = (),
) -> ShowInventory:
    """Build normalized artwork inventory from one Plex show."""

    identity = build_show_identity(
        show,
        library,
        library_roles=library_roles,
    )

    seasons: list[SeasonInventory] = []

    for plex_season in show.seasons():
        season_number = _positive_integer(
            getattr(
                plex_season,
                "index",
                None,
            )
        )

        if season_number is None:
            continue

        episode_numbers: set[int] = set()

        for plex_episode in plex_season.episodes():
            episode_number = _positive_integer(
                getattr(
                    plex_episode,
                    "index",
                    None,
                )
            )

            if (
                episode_number is None
                or episode_number == 0
            ):
                continue

            episode_numbers.add(
                episode_number
            )

        if not episode_numbers:
            continue

        seasons.append(
            SeasonInventory(
                season_number=season_number,
                episode_numbers=frozenset(
                    episode_numbers
                ),
            )
        )

    seasons.sort(
        key=lambda item: item.season_number
    )

    return ShowInventory(
        identity=identity,
        seasons=tuple(seasons),
    )
