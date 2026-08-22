"""Build Artwork Manager inventory from Plex library objects."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from tv_metadata.identity import build_show_identity
from tv_metadata.models import ShowIdentity


@dataclass(frozen=True)
class EpisodeInventory:
    """Generation-relevant metadata for one Plex episode."""

    episode_number: int
    title: str | None = None
    plex_thumb: str | None = None


@dataclass(frozen=True)
class SeasonInventory:
    """Episodes currently present in one Plex season."""

    season_number: int
    episode_numbers: frozenset[int]
    episodes: tuple[EpisodeInventory, ...] = ()

    def episode(
        self,
        episode_number: int,
    ) -> EpisodeInventory | None:
        """Return metadata for one episode when present."""

        for episode in self.episodes:
            if (
                episode.episode_number
                == episode_number
            ):
                return episode

        return None


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


def _clean_optional_text(
    value,
) -> str | None:
    """Normalize optional Plex text metadata."""

    if not isinstance(
        value,
        str,
    ):
        return None

    value = value.strip()

    return value or None


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

        episodes: dict[
            int,
            EpisodeInventory,
        ] = {}

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

            # Duplicate episode numbers are already normalized by the
            # v3 inventory model. Preserve the first usable Plex entry
            # so generation inputs are deterministic too.
            episodes.setdefault(
                episode_number,
                EpisodeInventory(
                    episode_number=(
                        episode_number
                    ),
                    title=(
                        _clean_optional_text(
                            getattr(
                                plex_episode,
                                "title",
                                None,
                            )
                        )
                    ),
                    plex_thumb=(
                        _clean_optional_text(
                            getattr(
                                plex_episode,
                                "thumb",
                                None,
                            )
                        )
                    ),
                ),
            )

        if not episodes:
            continue

        episode_numbers = frozenset(
            episodes
        )

        seasons.append(
            SeasonInventory(
                season_number=season_number,
                episode_numbers=(
                    episode_numbers
                ),
                episodes=tuple(
                    episodes[
                        episode_number
                    ]
                    for episode_number
                    in sorted(episodes)
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
