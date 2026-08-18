"""JSON-safe presentation models for Artwork Manager.

This module converts Artwork Manager domain/workflow objects into plain
Python dictionaries containing only JSON-compatible values.

It is intentionally independent of FastAPI, the CLI, and the frontend.
Those callers should consume this representation rather than reaching
into domain objects directly.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from artwork.workflow import (
    ArtworkLibraryWorkflow,
    ArtworkManagerWorkflow,
    SkippedArtworkWorkflowTarget,
)


def _value(
    value: Any,
) -> Any:
    """Normalize common domain values for JSON serialization."""

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, Path):
        return str(value)

    return value


def serialize_preview_issue(
    issue,
) -> dict[str, Any]:
    """Serialize one semantic preview issue."""

    return {
        "code": _value(issue.code),
        "message": issue.message,
    }


def serialize_episode_source(
    source,
) -> dict[str, Any]:
    """Serialize one before/after episode-card source count."""

    return {
        "source": source.source,
        "before": source.before,
        "after": source.after,
        "change": source.change,
    }


def serialize_artwork_library(
    run: ArtworkLibraryWorkflow,
) -> dict[str, Any]:
    """Serialize one complete reviewed library workflow."""

    preview = run.preview
    plan = run.plan
    execution = run.execution

    plan_available = (
        plan is not None
    )

    return {
        "library": run.library,
        "media_type": _value(
            run.target.media_type
        ),
        "output_path": str(
            run.output_path
        ),
        "baseline": {
            "source": _value(
                run.baseline.source
            ),
            "state_count": (
                run.baseline.state_count
            ),
        },
        "safety": {
            "safe_to_apply": (
                run.safe_to_apply
            ),
            "issues": [
                serialize_preview_issue(
                    issue
                )
                for issue in preview.issues
            ],
        },
        "inventory": {
            "plex_shows": (
                preview.plex_show_count
            ),
            "managed_before": (
                preview.existing_managed_count
            ),
            "managed_after": (
                preview.proposed_state_count
            ),
            "newly_managed": (
                preview.newly_managed_count
            ),
            "lost_managed": (
                preview.lost_managed_count
            ),
            "shows_without_state": (
                len(
                    preview.no_state_titles
                )
            ),
            "no_state_titles": list(
                preview.no_state_titles
            ),
        },
        "coverage": {
            "expected_episodes": (
                preview.expected_episode_count
            ),
            "cards_before": (
                preview.episode_cards_before
            ),
            "cards_after": (
                preview.episode_cards_after
            ),
            "gaps_before": (
                preview.episode_gaps_before
            ),
            "gaps_after": (
                preview.episode_gaps_after
            ),
            "coverage_before": (
                preview.coverage_before
            ),
            "coverage_after": (
                preview.coverage_after
            ),
            "coverage_change": (
                preview.coverage_change
            ),
            "sources": [
                serialize_episode_source(
                    source
                )
                for source
                in preview.sources
            ],
        },
        "presentation": {
            "show_posters": (
                preview.show_poster_count
            ),
            "backgrounds": (
                preview.background_count
            ),
            "shows_with_season_art": (
                preview.shows_with_season_posters
            ),
        },
        "provider_activity": {
            "primary_requests": (
                execution.provider_request_count
            ),
            "primary_errors": (
                execution.provider_error_count
            ),
            "identity_enrichment": {
                "requests": (
                    execution
                    .identity_enrichment_request_count
                ),
                "enriched": (
                    execution
                    .identity_enriched_count
                ),
                "errors": (
                    execution
                    .identity_enrichment_error_count
                ),
            },
            "tmdb": {
                "requests": (
                    execution.tmdb_request_count
                ),
                "errors": (
                    execution
                    .tmdb_provider_error_count
                ),
                "created_states": (
                    execution.tmdb_created_count
                ),
                "changed_shows": (
                    execution.tmdb_changed_count
                ),
                "gaps_filled": (
                    execution.tmdb_gap_fill_count
                ),
                "gaps_remaining": (
                    execution
                    .tmdb_gap_remaining_count
                ),
            },
        },
        "selection_activity": {
            "set_refreshes": (
                preview.set_refresh_count
            ),
            "set_migrations": (
                preview.set_migration_count
            ),
        },
        "output": {
            "rendered_yaml_bytes": (
                preview.rendered_yaml_bytes
            ),
            "desired": (
                run.desired_count
            ),
            "added": (
                run.added_count
            ),
            "updated": (
                run.updated_count
            ),
            "unchanged": (
                plan.unchanged_count
                if plan is not None
                else 0
            ),
            "removed": (
                run.removed_count
            ),
            "preserved_unowned": (
                len(
                    plan.preserved_unowned
                )
                if plan is not None
                else 0
            ),
            "changed_files": (
                run.changed_file_count
            ),
            "needs_apply": (
                run.needs_apply
            ),
            "plan_available": (
                plan_available
            ),
            "files": {
                "added": (
                    list(plan.added)
                    if plan is not None
                    else []
                ),
                "updated": (
                    list(plan.updated)
                    if plan is not None
                    else []
                ),
                "removed": (
                    list(plan.removed)
                    if plan is not None
                    else []
                ),
            },
        },
    }


def serialize_skipped_target(
    skipped: SkippedArtworkWorkflowTarget,
) -> dict[str, Any]:
    """Serialize one discovered but unsupported target."""

    return {
        "library": (
            skipped.target.library
        ),
        "media_type": _value(
            skipped.target.media_type
        ),
        "output_path": str(
            skipped.target.output_path
        ),
        "reason": _value(
            skipped.reason
        ),
    }


def serialize_artwork_workflow(
    workflow: ArtworkManagerWorkflow,
) -> dict[str, Any]:
    """Serialize the complete Artwork Manager workflow."""

    return {
        "summary": {
            "library_count": (
                workflow.library_count
            ),
            "skipped_count": (
                workflow.skipped_count
            ),
            "safe_to_apply": (
                workflow.safe_to_apply
            ),
            "changed_files": (
                workflow.changed_file_count
            ),
        },
        "libraries": [
            serialize_artwork_library(
                run
            )
            for run in workflow.libraries
        ],
        "skipped": [
            serialize_skipped_target(
                target
            )
            for target in workflow.skipped
        ],
    }
