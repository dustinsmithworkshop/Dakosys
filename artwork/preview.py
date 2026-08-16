"""Semantic preview for Artwork Manager target execution.

Previewing is deliberately read only. It summarizes prospective Artwork
Manager state, validates that the state can be rendered as Kometa YAML,
and identifies conditions that must block a future apply operation.

No files are created or modified by this module.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from artwork.kometa import render_kometa_metadata
from artwork.models import ShowArtworkState
from artwork.projection import (
    project_show_target_items,
)

if TYPE_CHECKING:
    from artwork.inventory import ShowInventory
    from artwork.target_execution import ShowTargetExecution


class PreviewIssueCode(str, Enum):
    """Conditions that make a target unsafe to persist."""

    MISSING_IDENTITY = "missing_identity"
    AMBIGUOUS_IDENTITY = "ambiguous_identity"
    ORPHANED_STATE = "orphaned_state"
    PRIMARY_PROVIDER_ERROR = "primary_provider_error"
    TMDB_PROVIDER_ERROR = "tmdb_provider_error"
    MISSING_SET_CONTEXT = "missing_set_context"
    MANAGED_STATE_LOSS = "managed_state_loss"
    OUTPUT_IDENTITY_MISSING = "output_identity_missing"
    KOMETA_RENDER_ERROR = "kometa_render_error"


@dataclass(frozen=True)
class PreviewIssue:
    """One safety issue discovered while building a preview."""

    code: PreviewIssueCode
    message: str


@dataclass(frozen=True)
class EpisodeSourcePreview:
    """Before/after expected-episode coverage for one artwork source."""

    source: str
    before: int
    after: int

    @property
    def change(self) -> int:
        return (
            self.after
            - self.before
        )


@dataclass(frozen=True)
class ArtworkTargetPreview:
    """Semantic preview of one show-library target."""

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

    sources: tuple[
        EpisodeSourcePreview,
        ...,
    ]

    set_refresh_count: int
    set_migration_count: int

    tmdb_created_count: int
    tmdb_changed_count: int

    show_poster_count: int
    background_count: int
    shows_with_season_posters: int

    no_state_titles: tuple[str, ...]

    rendered_yaml_bytes: int
    issues: tuple[PreviewIssue, ...]

    @property
    def safe_to_apply(self) -> bool:
        """Whether semantic validation found any apply blockers."""

        return not self.issues

    @property
    def coverage_before(self) -> float:
        if not self.expected_episode_count:
            return 1.0

        return (
            self.episode_cards_before
            / self.expected_episode_count
        )

    @property
    def coverage_after(self) -> float:
        if not self.expected_episode_count:
            return 1.0

        return (
            self.episode_cards_after
            / self.expected_episode_count
        )

    @property
    def coverage_change(self) -> float:
        return (
            self.coverage_after
            - self.coverage_before
        )


def _inventory_key(
    inventory: ShowInventory,
) -> tuple[str, str]:
    return (
        inventory.identity.library,
        str(
            inventory.identity
            .plex_rating_key
        ),
    )


def _all_reconciled_inventories(
    execution: ShowTargetExecution,
) -> tuple[ShowInventory, ...]:
    """Return every Plex inventory represented by reconciliation."""

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

    for ambiguous in (
        reconciliation.ambiguous
    ):
        inventories.extend(
            ambiguous.inventories
        )

    by_key = {}

    for inventory in inventories:
        key = _inventory_key(
            inventory
        )

        if key in by_key:
            raise ValueError(
                "duplicate Plex inventory identity "
                "in Artwork Manager preview: "
                f"{key!r}"
            )

        by_key[
            key
        ] = inventory

    return tuple(
        by_key.values()
    )


def _baseline_state_map(
    execution: ShowTargetExecution,
) -> dict[
    tuple[str, str],
    ShowArtworkState,
]:
    """Return safely reconciled durable state before execution."""

    return {
        _inventory_key(
            item.inventory
        ): item.artwork
        for item
        in execution.reconciliation.matched
    }


def _proposed_state_map(
    execution: ShowTargetExecution,
) -> dict[
    tuple[str, str],
    ShowArtworkState,
]:
    """Return Plex-projected prospective state after execution."""

    states = {}

    for (
        inventory,
        state,
    ) in project_show_target_items(
        execution
    ):
        key = _inventory_key(
            inventory
        )

        if key in states:
            raise ValueError(
                "duplicate prospective Plex identity "
                "in Artwork Manager preview: "
                f"{key!r}"
            )

        states[
            key
        ] = state

    return states

def _card_for(
    state: ShowArtworkState | None,
    season_number: int,
    episode_number: int,
):
    if state is None:
        return None

    season = state.seasons.get(
        season_number
    )

    if season is None:
        return None

    episode = season.episodes.get(
        episode_number
    )

    if episode is None:
        return None

    card = episode.card

    if (
        card is None
        or not card.available
    ):
        return None

    return card


def _source_counts(
    inventories: tuple[
        ShowInventory,
        ...,
    ],
    states: dict[
        tuple[str, str],
        ShowArtworkState,
    ],
) -> Counter:
    """Count usable cards only for episodes actually expected by Plex."""

    counts = Counter()

    for inventory in inventories:
        state = states.get(
            _inventory_key(
                inventory
            )
        )

        for season in inventory.seasons:
            for episode_number in (
                season.episode_numbers
            ):
                card = _card_for(
                    state,
                    season.season_number,
                    episode_number,
                )

                if card is not None:
                    counts[
                        card.source.value
                    ] += 1

    return counts


def _expected_episode_count(
    inventories: tuple[
        ShowInventory,
        ...,
    ],
) -> int:
    return sum(
        len(
            season.episode_numbers
        )
        for inventory in inventories
        for season in inventory.seasons
    )


def _presentation_counts(
    inventories: tuple[
        ShowInventory,
        ...,
    ],
    states: dict[
        tuple[str, str],
        ShowArtworkState,
    ],
) -> tuple[int, int, int]:
    posters = 0
    backgrounds = 0
    shows_with_season_posters = 0

    for inventory in inventories:
        state = states.get(
            _inventory_key(
                inventory
            )
        )

        if state is None:
            continue

        if (
            state.poster is not None
            and state.poster.available
        ):
            posters += 1

        if (
            state.background is not None
            and state.background.available
        ):
            backgrounds += 1

        expected_seasons = {
            season.season_number
            for season in inventory.seasons
        }

        if any(
            (
                season_number
                in state.seasons
                and state.seasons[
                    season_number
                ].poster is not None
                and state.seasons[
                    season_number
                ].poster.available
            )
            for season_number
            in expected_seasons
        ):
            shows_with_season_posters += 1

    return (
        posters,
        backgrounds,
        shows_with_season_posters,
    )


def build_show_target_preview(
    execution: ShowTargetExecution,
) -> ArtworkTargetPreview:
    """Build a read-only semantic preview for a show target."""

    reconciliation = (
        execution.reconciliation
    )

    inventories = (
        _all_reconciled_inventories(
            execution
        )
    )

    baseline_states = (
        _baseline_state_map(
            execution
        )
    )

    proposed_states = (
        _proposed_state_map(
            execution
        )
    )

    before_sources = (
        _source_counts(
            inventories,
            baseline_states,
        )
    )

    after_sources = (
        _source_counts(
            inventories,
            proposed_states,
        )
    )

    expected_episodes = (
        _expected_episode_count(
            inventories
        )
    )

    before_cards = sum(
        before_sources.values()
    )

    after_cards = sum(
        after_sources.values()
    )

    before_gaps = (
        expected_episodes
        - before_cards
    )

    after_gaps = (
        expected_episodes
        - after_cards
    )

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
                    _inventory_key(
                        inventory
                    )
                    not in proposed_states
                )
            ),
            key=str.casefold,
        )
    )

    (
        poster_count,
        background_count,
        season_poster_show_count,
    ) = _presentation_counts(
        inventories,
        proposed_states,
    )

    source_names = sorted(
        set(before_sources)
        | set(after_sources)
    )

    sources = tuple(
        EpisodeSourcePreview(
            source=source,
            before=before_sources[
                source
            ],
            after=after_sources[
                source
            ],
        )
        for source in source_names
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
                    "Plex show(s) are missing required "
                    "artwork identity"
                ),
            )
        )

    if reconciliation.ambiguous:
        issues.append(
            PreviewIssue(
                code=(
                    PreviewIssueCode
                    .AMBIGUOUS_IDENTITY
                ),
                message=(
                    f"{len(reconciliation.ambiguous)} "
                    "managed identity match(es) are ambiguous"
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
                    "durable artwork state record(s) are orphaned"
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
                    "primary artwork provider request(s) failed"
                ),
            )
        )

    if execution.tmdb_provider_error_count:
        issues.append(
            PreviewIssue(
                code=(
                    PreviewIssueCode
                    .TMDB_PROVIDER_ERROR
                ),
                message=(
                    f"{execution.tmdb_provider_error_count} "
                    "TMDB fallback request(s) failed"
                ),
            )
        )

    if (
        execution.managed
        .missing_set_context_count
    ):
        issues.append(
            PreviewIssue(
                code=(
                    PreviewIssueCode
                    .MISSING_SET_CONTEXT
                ),
                message=(
                    f"{execution.managed.missing_set_context_count} "
                    "managed show(s) are missing durable "
                    "set-selection context"
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
                    f"{len(lost_managed)} previously managed "
                    "show(s) would disappear from proposed state"
                ),
            )
        )

    missing_output_identity = sum(
        1
        for state in proposed_states.values()
        if state.tvdb_id is None
    )

    if missing_output_identity:
        issues.append(
            PreviewIssue(
                code=(
                    PreviewIssueCode
                    .OUTPUT_IDENTITY_MISSING
                ),
                message=(
                    f"{missing_output_identity} proposed state(s) "
                    "lack the TVDB identity required by "
                    "Kometa artwork output"
                ),
            )
        )

    rendered_yaml_bytes = 0

    try:
        rendered = (
            render_kometa_metadata(
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

    return ArtworkTargetPreview(
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
        expected_episode_count=(
            expected_episodes
        ),
        episode_cards_before=(
            before_cards
        ),
        episode_cards_after=(
            after_cards
        ),
        episode_gaps_before=(
            before_gaps
        ),
        episode_gaps_after=(
            after_gaps
        ),
        sources=sources,
        set_refresh_count=(
            execution.managed
            .set_refresh_count
        ),
        set_migration_count=(
            execution.managed
            .set_migration_count
        ),
        tmdb_created_count=(
            execution.tmdb_created_count
        ),
        tmdb_changed_count=(
            execution.tmdb_changed_count
        ),
        show_poster_count=(
            poster_count
        ),
        background_count=(
            background_count
        ),
        shows_with_season_posters=(
            season_poster_show_count
        ),
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


def format_show_target_preview(
    preview: ArtworkTargetPreview,
) -> str:
    """Format a human-readable semantic preview."""

    lines = [
        (
            "Artwork preview: "
            f"{preview.library}"
        ),
        (
            "Output: "
            f"{preview.output_path}"
        ),
        "",
        (
            "Plex shows:              "
            f"{preview.plex_show_count}"
        ),
        (
            "Existing managed:        "
            f"{preview.existing_managed_count}"
        ),
        (
            "Proposed states:         "
            f"{preview.proposed_state_count}"
        ),
        (
            "Newly managed:           "
            f"{preview.newly_managed_count}"
        ),
        (
            "Lost managed:            "
            f"{preview.lost_managed_count}"
        ),
        "",
        (
            "Expected episodes:       "
            f"{preview.expected_episode_count}"
        ),
        (
            "Episode cards before:    "
            f"{preview.episode_cards_before}"
        ),
        (
            "Episode cards after:     "
            f"{preview.episode_cards_after}"
        ),
        (
            "Unresolved before:       "
            f"{preview.episode_gaps_before}"
        ),
        (
            "Unresolved after:        "
            f"{preview.episode_gaps_after}"
        ),
        (
            "Coverage before:         "
            f"{preview.coverage_before:.2%}"
        ),
        (
            "Coverage after:          "
            f"{preview.coverage_after:.2%}"
        ),
        (
            "Coverage improvement:    "
            f"{preview.coverage_change:+.2%}"
        ),
        "",
        "Episode sources:",
    ]

    if preview.sources:
        for source in preview.sources:
            lines.append(
                f"  {source.source:<18} "
                f"{source.before:>6} -> "
                f"{source.after:<6} "
                f"({source.change:+d})"
            )
    else:
        lines.append(
            "  none"
        )

    lines.extend(
        [
            "",
            (
                "Managed set refreshes:  "
                f"{preview.set_refresh_count}"
            ),
            (
                "Managed migrations:     "
                f"{preview.set_migration_count}"
            ),
            (
                "TMDB-created states:    "
                f"{preview.tmdb_created_count}"
            ),
            (
                "Shows changed by TMDB:  "
                f"{preview.tmdb_changed_count}"
            ),
            "",
            (
                "Shows with poster:      "
                f"{preview.show_poster_count}"
            ),
            (
                "Shows with background:  "
                f"{preview.background_count}"
            ),
            (
                "Shows with season art:  "
                f"{preview.shows_with_season_posters}"
            ),
            "",
            (
                "Rendered YAML size:     "
                f"{preview.rendered_yaml_bytes:,} bytes"
            ),
        ]
    )

    if preview.no_state_titles:
        lines.extend(
            [
                "",
                (
                    "Shows without useful "
                    f"state ({len(preview.no_state_titles)}):"
                ),
            ]
        )

        lines.extend(
            f"  {title}"
            for title
            in preview.no_state_titles
        )

    lines.append(
        ""
    )

    if preview.issues:
        lines.append(
            "Validation: BLOCKED"
        )

        for issue in preview.issues:
            lines.append(
                f"  [{issue.code.value}] "
                f"{issue.message}"
            )
    else:
        lines.append(
            "Validation: SAFE TO APPLY"
        )

    lines.append(
        "WRITE: disabled"
    )

    return "\n".join(
        lines
    )
