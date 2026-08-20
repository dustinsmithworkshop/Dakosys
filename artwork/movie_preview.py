"""Semantic preview for Artwork Manager movie execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from artwork.movie_execution import (
    MovieExecutionPath,
    MovieTargetExecution,
)
from artwork.movie_kometa import (
    movie_mapping_id,
    render_movie_kometa_metadata,
)
from artwork.models import (
    MovieArtworkState,
)
from artwork.preview import (
    PreviewIssue,
    PreviewIssueCode,
)


@dataclass(frozen=True)
class MovieArtworkTargetPreview:
    """Read-only semantic preview of one movie target."""

    library: str
    output_path: Path

    plex_show_count: int
    existing_managed_count: int
    proposed_state_count: int
    newly_managed_count: int
    lost_managed_count: int

    expected_episode_count: int
    episode_cards_before: int
    episode_cards_after: int
    episode_gaps_before: int
    episode_gaps_after: int

    sources: tuple

    set_refresh_count: int
    set_migration_count: int

    tmdb_created_count: int
    tmdb_changed_count: int

    show_poster_count: int
    background_count: int
    shows_with_season_posters: int

    no_state_titles: tuple[str, ...]

    rendered_yaml_bytes: int

    issues: tuple[
        PreviewIssue,
        ...,
    ]

    @property
    def safe_to_apply(
        self,
    ) -> bool:
        return not self.issues

    @property
    def coverage_before(
        self,
    ) -> float:
        return 1.0

    @property
    def coverage_after(
        self,
    ) -> float:
        return 1.0

    @property
    def coverage_change(
        self,
    ) -> float:
        return 0.0


def _key(
    inventory,
) -> tuple[str, str]:
    return (
        inventory.identity.library,
        inventory.identity.plex_rating_key,
    )


def build_movie_target_preview(
    execution: MovieTargetExecution,
) -> MovieArtworkTargetPreview:
    """Build the safety preview for one movie target."""

    reconciliation = (
        execution.reconciliation
    )

    inventories = []

    inventories.extend(
        item.inventory
        for item
        in reconciliation.matched
    )

    inventories.extend(
        reconciliation.unmanaged
    )

    inventories.extend(
        reconciliation.missing_identity
    )

    by_key = {}

    for inventory in inventories:
        key = _key(
            inventory
        )

        if key in by_key:
            raise ValueError(
                "duplicate Plex movie identity "
                "in Artwork Manager preview: "
                f"{key!r}"
            )

        by_key[
            key
        ] = inventory

    inventories = tuple(
        by_key.values()
    )

    baseline_states: dict[
        tuple[str, str],
        MovieArtworkState,
    ] = {
        _key(
            item.inventory
        ):
            item.artwork
        for item
        in reconciliation.matched
    }

    proposed_states: dict[
        tuple[str, str],
        MovieArtworkState,
    ] = {}

    for result in execution.results:
        if result.state is None:
            continue

        key = _key(
            result.inventory
        )

        if key in proposed_states:
            raise ValueError(
                "duplicate prospective Plex "
                "movie identity in preview: "
                f"{key!r}"
            )

        proposed_states[
            key
        ] = result.state

    baseline_keys = set(
        baseline_states
    )

    proposed_keys = set(
        proposed_states
    )

    newly_managed = (
        proposed_keys
        - baseline_keys
    )

    lost_managed = (
        baseline_keys
        - proposed_keys
    )

    no_state_titles = tuple(
        sorted(
            (
                inventory.identity.title
                for inventory
                in inventories
                if (
                    _key(
                        inventory
                    )
                    not in proposed_states
                )
            ),
            key=str.casefold,
        )
    )

    poster_count = sum(
        1
        for state
        in proposed_states.values()
        if (
            state.poster is not None
            and state.poster.available
        )
    )

    background_count = sum(
        1
        for state
        in proposed_states.values()
        if (
            state.background is not None
            and state.background.available
        )
    )

    issues = []

    if reconciliation.missing_identity:
        issues.append(
            PreviewIssue(
                code=(
                    PreviewIssueCode
                    .MISSING_IDENTITY
                ),
                message=(
                    f"{len(reconciliation.missing_identity)} "
                    "Plex movie(s) are missing required "
                    "artwork identity"
                ),
            )
        )

    if reconciliation.orphaned:
        issues.append(
            PreviewIssue(
                code=(
                    PreviewIssueCode
                    .ORPHANED_STATE
                ),
                message=(
                    f"{len(reconciliation.orphaned)} "
                    "durable movie artwork state "
                    "record(s) are orphaned"
                ),
            )
        )

    if execution.provider_error_count:
        issues.append(
            PreviewIssue(
                code=(
                    PreviewIssueCode
                    .PRIMARY_PROVIDER_ERROR
                ),
                message=(
                    f"{execution.provider_error_count} "
                    "primary artwork provider "
                    "request(s) failed"
                ),
            )
        )

    missing_set_context = sum(
        1
        for result
        in execution.results
        if (
            result.path
            is MovieExecutionPath
            .MISSING_SET_CONTEXT
        )
    )

    if missing_set_context:
        issues.append(
            PreviewIssue(
                code=(
                    PreviewIssueCode
                    .MISSING_SET_CONTEXT
                ),
                message=(
                    f"{missing_set_context} "
                    "managed movie(s) are missing "
                    "durable set-selection context"
                ),
            )
        )

    if lost_managed:
        issues.append(
            PreviewIssue(
                code=(
                    PreviewIssueCode
                    .MANAGED_STATE_LOSS
                ),
                message=(
                    f"{len(lost_managed)} previously "
                    "managed movie(s) would disappear "
                    "from proposed state"
                ),
            )
        )

    missing_output_identity = sum(
        1
        for state
        in proposed_states.values()
        if (
            movie_mapping_id(
                state
            )
            is None
        )
    )

    if missing_output_identity:
        issues.append(
            PreviewIssue(
                code=(
                    PreviewIssueCode
                    .OUTPUT_IDENTITY_MISSING
                ),
                message=(
                    f"{missing_output_identity} "
                    "proposed movie state(s) lack "
                    "TMDB/IMDb identity required "
                    "by Kometa artwork output"
                ),
            )
        )

    rendered_yaml_bytes = 0

    try:
        rendered = (
            render_movie_kometa_metadata(
                proposed_states.values()
            )
        )

        rendered_yaml_bytes = len(
            rendered.encode(
                "utf-8"
            )
        )

    except ValueError as exc:
        issues.append(
            PreviewIssue(
                code=(
                    PreviewIssueCode
                    .KOMETA_RENDER_ERROR
                ),
                message=str(
                    exc
                ),
            )
        )

    return MovieArtworkTargetPreview(
        library=(
            reconciliation
            .target
            .library
        ),
        output_path=(
            reconciliation
            .target
            .output_path
        ),
        plex_show_count=len(
            inventories
        ),
        existing_managed_count=len(
            baseline_states
        ),
        proposed_state_count=len(
            proposed_states
        ),
        newly_managed_count=len(
            newly_managed
        ),
        lost_managed_count=len(
            lost_managed
        ),
        expected_episode_count=0,
        episode_cards_before=0,
        episode_cards_after=0,
        episode_gaps_before=0,
        episode_gaps_after=0,
        sources=(),
        set_refresh_count=(
            execution.refresh_count
        ),
        set_migration_count=(
            execution.migration_count
        ),
        tmdb_created_count=0,
        tmdb_changed_count=0,
        show_poster_count=(
            poster_count
        ),
        background_count=(
            background_count
        ),
        shows_with_season_posters=0,
        no_state_titles=(
            no_state_titles
        ),
        rendered_yaml_bytes=(
            rendered_yaml_bytes
        ),
        issues=tuple(
            issues
        ),
    )
