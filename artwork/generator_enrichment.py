"""Show-wide read-only episode artwork planning through Artwork Generator."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from artwork.generator_config import (
    ArtworkGeneratorConfig,
)
from artwork.generator_inputs import (
    EpisodeGenerationPath,
    resolve_episode_generation_input,
)
from artwork.generator_plan import (
    GeneratedEpisodeCardPlan,
    plan_generated_episode_card,
)
from artwork.inventory import (
    ShowInventory,
)
from artwork.models import (
    EpisodeArtwork,
    SeasonArtwork,
    SelectionMode,
    ShowArtworkState,
)
from artwork.providers.tmdb import (
    TMDBArtworkClient,
)


class GeneratorEnrichmentPath(
    str,
    Enum,
):
    """High-level outcome for one show."""

    DISABLED = "disabled"
    LOCKED = "locked"
    NO_CHANGES = "no_changes"
    CHANGED = "changed"
    IDENTITY_MISMATCH = (
        "identity_mismatch"
    )


@dataclass(frozen=True)
class GeneratorSeasonFailure:
    """TMDB metadata failure isolated to one season."""

    season_number: int
    error_type: str
    error_message: str


@dataclass(frozen=True)
class GeneratorEpisodeFailure:
    """Generation planning failure isolated to one episode."""

    season_number: int
    episode_number: int
    error_type: str
    error_message: str


@dataclass(frozen=True)
class GeneratorEnrichmentResult:
    """Read-only generator planning result for one show."""

    initial_state: ShowArtworkState | None
    state: ShowArtworkState | None

    path: GeneratorEnrichmentPath

    tmdb_request_count: int = 0

    plan_attempt_count: int = 0
    changed_episode_count: int = 0

    cached_plan_count: int = 0
    materialization_needed_count: int = 0

    kept_primary_count: int = 0
    kept_generated_count: int = 0

    no_title_count: int = 0
    no_source_image_count: int = 0

    generation_plans: tuple[
        GeneratedEpisodeCardPlan,
        ...,
    ] = ()

    season_failures: tuple[
        GeneratorSeasonFailure,
        ...,
    ] = ()

    episode_failures: tuple[
        GeneratorEpisodeFailure,
        ...,
    ] = ()

    @property
    def changed(
        self,
    ) -> bool:
        """Whether prospective semantic state changed."""

        return (
            self.changed_episode_count
            > 0
        )

    @property
    def planned_count(
        self,
    ) -> int:
        return len(
            self.generation_plans
        )

    @property
    def needs_materialization(
        self,
    ) -> bool:
        return (
            self.materialization_needed_count
            > 0
        )

    @property
    def failure_count(
        self,
    ) -> int:
        return (
            len(
                self.season_failures
            )
            + len(
                self.episode_failures
            )
        )


def enrich_show_with_generated_episode_cards(
    *,
    inventory: ShowInventory,
    state: ShowArtworkState | None,
    enabled: bool,
    local_root: str | Path,
    kometa_root: str,
    creative_config: (
        ArtworkGeneratorConfig
        | None
    ) = None,
    font_key: str | None = None,
    tmdb_client: (
        TMDBArtworkClient
        | None
    ) = None,
    plan_card=(
        plan_generated_episode_card
    ),
) -> GeneratorEnrichmentResult:
    """Plan generated episode cards without modifying the filesystem.

    Existing primary/curated artwork remains untouched.

    Missing or upgradeable raw fallback artwork may become prospective
    generated artwork.

    Existing generated artwork is reevaluated so its deterministic
    fingerprint decides whether an existing cache file can be reused.

    This function performs no source downloads and no rendering.
    """

    if not enabled:
        return GeneratorEnrichmentResult(
            initial_state=state,
            state=state,
            path=(
                GeneratorEnrichmentPath
                .DISABLED
            ),
        )

    selection_mode = (
        _episode_selection_mode(
            state
        )
    )

    if (
        selection_mode
        is SelectionMode.LOCKED
    ):
        return GeneratorEnrichmentResult(
            initial_state=state,
            state=state,
            path=(
                GeneratorEnrichmentPath
                .LOCKED
            ),
        )

    if _tmdb_identity_mismatch(
        inventory=inventory,
        state=state,
    ):
        return GeneratorEnrichmentResult(
            initial_state=state,
            state=state,
            path=(
                GeneratorEnrichmentPath
                .IDENTITY_MISMATCH
            ),
        )

    working = (
        deepcopy(
            state
        )
        if state is not None
        else _identity_state(
            inventory
        )
    )

    resolved_tmdb_id = (
        _initial_tmdb_id(
            inventory=inventory,
            state=state,
        )
    )

    if (
        resolved_tmdb_id is None
        and tmdb_client is not None
    ):
        try:
            (
                resolved_tmdb_id,
                _resolution_source,
            ) = (
                tmdb_client
                .resolve_tmdb_id(
                    inventory.identity
                )
            )

        except Exception:
            # Exact TMDB identity resolution is optional for generation.
            # Plex identity can still provide a stable fallback key.
            resolved_tmdb_id = None

    show_key = _show_key(
        inventory=inventory,
        tmdb_id=resolved_tmdb_id,
    )

    if font_key is None:
        creative_config = (
            creative_config
            or ArtworkGeneratorConfig()
        )

        resolved_style = (
            creative_config
            .resolve_style(
                library=(
                    inventory
                    .identity
                    .library
                ),
                show_id=show_key,
            )
        )

        resolved_font_key = (
            resolved_style.font
        )

    else:
        # Explicit override retained for focused tests and direct
        # low-level callers. Configured runtime uses creative_config.
        resolved_font_key = (
            font_key
        )

    tmdb_request_count = 0

    plan_attempt_count = 0
    changed_episode_count = 0

    cached_plan_count = 0
    materialization_needed_count = 0

    kept_primary_count = 0
    kept_generated_count = 0

    no_title_count = 0
    no_source_image_count = 0

    generation_plans: list[
        GeneratedEpisodeCardPlan
    ] = []

    season_failures: list[
        GeneratorSeasonFailure
    ] = []

    episode_failures: list[
        GeneratorEpisodeFailure
    ] = []

    expected = (
        inventory.expected_episodes()
    )

    for season_number in sorted(
        expected
    ):
        tmdb_episodes = {}

        if (
            tmdb_client is not None
            and resolved_tmdb_id
            is not None
        ):
            tmdb_request_count += 1

            try:
                tmdb_episodes = (
                    tmdb_client
                    .get_season_episode_artwork(
                        tmdb_id=(
                            resolved_tmdb_id
                        ),
                        season_number=(
                            season_number
                        ),
                    )
                )

            except Exception as exc:
                season_failures.append(
                    GeneratorSeasonFailure(
                        season_number=(
                            season_number
                        ),
                        error_type=(
                            type(exc).__name__
                        ),
                        error_message=str(
                            exc
                        ),
                    )
                )

                tmdb_episodes = {}

        inventory_season = (
            inventory.season(
                season_number
            )
        )

        for episode_number in sorted(
            expected[
                season_number
            ]
        ):
            plex_episode = (
                inventory_season.episode(
                    episode_number
                )
                if inventory_season
                is not None
                else None
            )

            tmdb_episode = (
                tmdb_episodes.get(
                    episode_number
                )
            )

            current_card = (
                _current_card(
                    working,
                    season_number=(
                        season_number
                    ),
                    episode_number=(
                        episode_number
                    ),
                )
            )

            generation_input = (
                resolve_episode_generation_input(
                    episode_number=(
                        episode_number
                    ),
                    plex_episode=(
                        plex_episode
                    ),
                    tmdb_episode=(
                        tmdb_episode
                    ),
                    current_card=(
                        current_card
                    ),
                    selection_mode=(
                        selection_mode
                    ),
                )
            )

            if (
                generation_input.path
                is EpisodeGenerationPath
                .KEEP_PRIMARY
            ):
                kept_primary_count += 1
                continue

            if (
                generation_input.path
                is EpisodeGenerationPath
                .KEEP_GENERATED
            ):
                kept_generated_count += 1
                continue

            if (
                generation_input.path
                is EpisodeGenerationPath
                .NO_TITLE
            ):
                no_title_count += 1
                continue

            if (
                generation_input.path
                is EpisodeGenerationPath
                .NO_SOURCE_IMAGE
            ):
                no_source_image_count += 1
                continue

            if not (
                generation_input
                .should_generate
            ):
                continue

            plan_attempt_count += 1

            try:
                planned = (
                    plan_card(
                        generation_input=(
                            generation_input
                        ),
                        show_key=show_key,
                        season_number=(
                            season_number
                        ),
                        font_key=(
                            resolved_font_key
                        ),
                        local_root=local_root,
                        kometa_root=(
                            kometa_root
                        ),
                    )
                )

            except Exception as exc:
                episode_failures.append(
                    GeneratorEpisodeFailure(
                        season_number=(
                            season_number
                        ),
                        episode_number=(
                            episode_number
                        ),
                        error_type=(
                            type(exc).__name__
                        ),
                        error_message=str(
                            exc
                        ),
                    )
                )

                continue

            generation_plans.append(
                planned
            )

            if planned.cached:
                cached_plan_count += 1
            else:
                materialization_needed_count += 1

            if (
                planned.asset
                == current_card
            ):
                continue

            _set_card(
                working,
                season_number=(
                    season_number
                ),
                episode_number=(
                    episode_number
                ),
                card=planned.asset,
            )

            changed_episode_count += 1

    if (
        changed_episode_count > 0
        and working.tmdb_id is None
        and resolved_tmdb_id is not None
    ):
        working.tmdb_id = (
            resolved_tmdb_id
        )

    if state is None:
        resolved_state = (
            working
            if changed_episode_count > 0
            else None
        )

    else:
        resolved_state = working

    return GeneratorEnrichmentResult(
        initial_state=state,
        state=resolved_state,
        path=(
            GeneratorEnrichmentPath.CHANGED
            if changed_episode_count > 0
            else GeneratorEnrichmentPath
            .NO_CHANGES
        ),
        tmdb_request_count=(
            tmdb_request_count
        ),
        plan_attempt_count=(
            plan_attempt_count
        ),
        changed_episode_count=(
            changed_episode_count
        ),
        cached_plan_count=(
            cached_plan_count
        ),
        materialization_needed_count=(
            materialization_needed_count
        ),
        kept_primary_count=(
            kept_primary_count
        ),
        kept_generated_count=(
            kept_generated_count
        ),
        no_title_count=(
            no_title_count
        ),
        no_source_image_count=(
            no_source_image_count
        ),
        generation_plans=tuple(
            generation_plans
        ),
        season_failures=tuple(
            season_failures
        ),
        episode_failures=tuple(
            episode_failures
        ),
    )


def _identity_state(
    inventory: ShowInventory,
) -> ShowArtworkState:
    identity = (
        inventory.identity
    )

    return ShowArtworkState(
        title=identity.title,
        tvdb_id=identity.tvdb_id,
        tmdb_id=identity.tmdb_id,
        imdb_id=identity.imdb_id,
    )


def _initial_tmdb_id(
    *,
    inventory: ShowInventory,
    state: ShowArtworkState | None,
) -> int | None:
    if (
        state is not None
        and state.tmdb_id is not None
    ):
        return state.tmdb_id

    return (
        inventory.identity.tmdb_id
    )


def _tmdb_identity_mismatch(
    *,
    inventory: ShowInventory,
    state: ShowArtworkState | None,
) -> bool:
    if state is None:
        return False

    state_tmdb_id = (
        state.tmdb_id
    )

    plex_tmdb_id = (
        inventory.identity.tmdb_id
    )

    return (
        state_tmdb_id is not None
        and plex_tmdb_id is not None
        and state_tmdb_id
        != plex_tmdb_id
    )


def _episode_selection_mode(
    state: ShowArtworkState | None,
) -> SelectionMode:
    if state is None:
        return SelectionMode.AUTO

    selection = (
        state.effective_episode_selection
    )

    if selection is not None:
        return selection.mode

    return state.selection_mode


def _show_key(
    *,
    inventory: ShowInventory,
    tmdb_id: int | None,
) -> str:
    if tmdb_id is not None:
        return (
            f"tmdb:{tmdb_id}"
        )

    tvdb_id = (
        inventory.identity.tvdb_id
    )

    if tvdb_id is not None:
        return (
            f"tvdb:{tvdb_id}"
        )

    rating_key = str(
        inventory
        .identity
        .plex_rating_key
    ).strip()

    if not rating_key:
        raise ValueError(
            "Artwork Generator requires "
            "a stable show identity"
        )

    return (
        f"plex:{rating_key}"
    )


def _current_card(
    state: ShowArtworkState,
    *,
    season_number: int,
    episode_number: int,
):
    season = (
        state.seasons.get(
            season_number
        )
    )

    if season is None:
        return None

    episode = (
        season.episodes.get(
            episode_number
        )
    )

    if episode is None:
        return None

    return episode.card


def _set_card(
    state: ShowArtworkState,
    *,
    season_number: int,
    episode_number: int,
    card,
) -> None:
    season = (
        state.seasons.get(
            season_number
        )
    )

    if season is None:
        season = SeasonArtwork(
            season_number=(
                season_number
            )
        )

        state.seasons[
            season_number
        ] = season

    episode = (
        season.episodes.get(
            episode_number
        )
    )

    if episode is None:
        episode = EpisodeArtwork(
            episode_number=(
                episode_number
            )
        )

        season.episodes[
            episode_number
        ] = episode

    episode.card = card
