"""Post-resolution episode artwork coverage enrichment."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from artwork.generator_config import (
    ArtworkGeneratorConfig,
)
from artwork.generator_enrichment import (
    GeneratorEnrichmentResult,
    enrich_show_with_generated_episode_cards,
)
from artwork.inventory import ShowInventory
from artwork.models import ShowArtworkState
from artwork.providers.tmdb import TMDBArtworkClient
from artwork.tmdb_fallback import (
    TMDBFallbackPath,
    TMDBFallbackResult,
    fill_tmdb_episode_gaps,
)


@dataclass(frozen=True)
class EpisodeGeneratorOptions:
    """Runtime inputs needed for optional episode-card generation."""

    enabled: bool

    local_root: str | Path
    kometa_root: str

    creative_config: (
        ArtworkGeneratorConfig
    ) = field(
        default_factory=(
            ArtworkGeneratorConfig
        )
    )

    # Explicit compatibility/testing override.
    # Normal configured runtime should leave this unset and use
    # creative_config so Show > Library > Global inheritance applies.
    font_key: str | None = None

    plex_base_url: str | None = None
    plex_token: str | None = None

    font_dir: str | Path = (
        "fonts/artwork-generator"
    )

    session: object | None = None


@dataclass(frozen=True)
class EpisodeCoverageResult:
    """Result of post-primary episode artwork enrichment."""

    inventory: ShowInventory

    initial_state: ShowArtworkState | None
    state: ShowArtworkState | None

    tmdb: TMDBFallbackResult | None = None

    generator: (
        GeneratorEnrichmentResult
        | None
    ) = None

    @property
    def resolved(self) -> bool:
        """Whether useful durable state exists after coverage."""

        return self.state is not None

    @property
    def changed(self) -> bool:
        """Whether any coverage stage changed artwork state."""

        return (
            (
                self.tmdb is not None
                and self.tmdb.changed
            )
            or (
                self.generator is not None
                and self.generator.changed
            )
        )

    @property
    def created(self) -> bool:
        """Whether coverage created state for an unmanaged show."""

        return (
            self.initial_state is None
            and self.state is not None
        )

    # ------------------------------------------------------------------
    # Existing TMDB-facing compatibility properties.
    #
    # These deliberately remain TMDB-specific so current metrics do not
    # silently change meaning when generator support is enabled.
    # ------------------------------------------------------------------

    @property
    def gaps_before(self) -> int:
        return (
            self.tmdb.gaps_before
            if self.tmdb is not None
            else 0
        )

    @property
    def gaps_filled(self) -> int:
        return (
            self.tmdb.gaps_filled
            if self.tmdb is not None
            else 0
        )

    @property
    def gaps_remaining(self) -> int:
        return (
            self.tmdb.gaps_remaining
            if self.tmdb is not None
            else 0
        )

    @property
    def season_request_count(self) -> int:
        return (
            self.tmdb.season_request_count
            if self.tmdb is not None
            else 0
        )

    @property
    def provider_error_count(self) -> int:
        return (
            self.tmdb.provider_error_count
            if self.tmdb is not None
            else 0
        )

    @property
    def tmdb_path(
        self,
    ) -> TMDBFallbackPath | None:
        return (
            self.tmdb.path
            if self.tmdb is not None
            else None
        )

    # ------------------------------------------------------------------
    # Generator-facing metrics.
    # ------------------------------------------------------------------

    @property
    def generator_changed_count(
        self,
    ) -> int:
        if self.generator is None:
            return 0

        return (
            self.generator
            .changed_episode_count
        )

    @property
    def generator_plan_count(
        self,
    ) -> int:
        if self.generator is None:
            return 0

        return (
            self.generator
            .planned_count
        )

    @property
    def generator_cached_count(
        self,
    ) -> int:
        if self.generator is None:
            return 0

        return (
            self.generator
            .cached_plan_count
        )

    @property
    def generator_materialization_needed_count(
        self,
    ) -> int:
        if self.generator is None:
            return 0

        return (
            self.generator
            .materialization_needed_count
        )

    @property
    def generator_failure_count(
        self,
    ) -> int:
        if self.generator is None:
            return 0

        return (
            self.generator
            .failure_count
        )


def _identity_state(
    inventory: ShowInventory,
) -> ShowArtworkState:
    """Create temporary state used only during TMDB fallback."""

    identity = inventory.identity

    return ShowArtworkState(
        title=identity.title,
        tvdb_id=identity.tvdb_id,
        tmdb_id=identity.tmdb_id,
        imdb_id=identity.imdb_id,
    )


def resolve_episode_coverage(
    *,
    inventory: ShowInventory,
    state: ShowArtworkState | None,
    tmdb_client: TMDBArtworkClient | None = None,
    generator_options: (
        EpisodeGeneratorOptions
        | None
    ) = None,
) -> EpisodeCoverageResult:
    """Resolve post-primary episode artwork coverage.

    Stage order:

        primary/cohesive artwork
            ↓
        optional TMDB raw fallback
            ↓
        optional Artwork Generator

    TMDB fills only unresolved gaps.

    Artwork Generator may then:
    - fill remaining gaps;
    - upgrade raw TMDB/Plex fallback;
    - reevaluate existing generated cards.

    Primary/curated and locked artwork remains protected by generator
    policy.

    Neither stage performs Plex changes.
    """

    if (
        state is not None
        and state.tvdb_id is not None
        and inventory.identity.tvdb_id is not None
        and state.tvdb_id
        != inventory.identity.tvdb_id
    ):
        raise ValueError(
            "artwork state TVDB ID does not "
            "match Plex inventory"
        )

    resolved_state = state

    tmdb_result = None

    shared_tmdb_episode_artwork = {}
    shared_tmdb_attempted_seasons = (
        frozenset()
    )

    # ------------------------------------------------------------------
    # Existing v3.0 TMDB fallback stage.
    # ------------------------------------------------------------------

    if tmdb_client is not None:
        working_state = (
            state
            if state is not None
            else _identity_state(
                inventory
            )
        )

        tmdb_result = (
            fill_tmdb_episode_gaps(
                inventory=inventory,
                state=working_state,
                client=tmdb_client,
            )
        )

        shared_tmdb_episode_artwork = (
            tmdb_result
            .episode_artwork_by_season
        )

        shared_tmdb_attempted_seasons = (
            tmdb_result
            .attempted_seasons
        )

        # Existing durable state is always preserved regardless of
        # whether TMDB contributed anything.
        if state is not None:
            resolved_state = (
                tmdb_result.state
            )

        # Previously unmanaged shows become durable only if TMDB
        # actually contributed artwork.
        elif tmdb_result.changed:
            resolved_state = (
                tmdb_result.state
            )

        else:
            resolved_state = None

    # ------------------------------------------------------------------
    # Optional Artwork Generator stage.
    #
    # This intentionally also runs when tmdb_client is None. Plex title
    # + thumbnail alone may be sufficient to generate episode artwork.
    # ------------------------------------------------------------------

    generator_result = None

    if (
        generator_options is not None
        and generator_options.enabled
    ):
        generator_result = (
            enrich_show_with_generated_episode_cards(
                inventory=inventory,
                state=resolved_state,
                enabled=True,
                local_root=(
                    generator_options
                    .local_root
                ),
                kometa_root=(
                    generator_options
                    .kometa_root
                ),
                creative_config=(
                    generator_options
                    .creative_config
                ),
                font_key=(
                    generator_options
                    .font_key
                ),
                tmdb_client=tmdb_client,
                tmdb_episode_artwork_by_season=(
                    shared_tmdb_episode_artwork
                ),
                tmdb_attempted_seasons=(
                    shared_tmdb_attempted_seasons
                ),
            )
        )

        resolved_state = (
            generator_result.state
        )

    return EpisodeCoverageResult(
        inventory=inventory,
        initial_state=state,
        state=resolved_state,
        tmdb=tmdb_result,
        generator=generator_result,
    )
