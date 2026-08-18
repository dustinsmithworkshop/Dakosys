import json
from pathlib import Path
from types import SimpleNamespace

from artwork.managed_state import (
    ManagedStateBaselineSource,
)
from artwork.preview import (
    PreviewIssueCode,
)
from artwork.targets import (
    ArtworkTarget,
    MediaType,
)
from artwork.workflow import (
    ArtworkLibraryWorkflow,
    ArtworkManagerWorkflow,
    ArtworkWorkflowSkipReason,
    SkippedArtworkWorkflowTarget,
)
from artwork.serialization import (
    serialize_artwork_library,
    serialize_artwork_workflow,
)


class FakeSource:
    source = "mediux"
    before = 10
    after = 12

    @property
    def change(self):
        return (
            self.after
            - self.before
        )


def _library_run():
    target = ArtworkTarget(
        name="Family Animation",
        library="Family Animation",
        media_type=MediaType.SHOW,
        output_path=(
            "/metadata/"
            "artwork-family-animation"
        ),
    )

    baseline = SimpleNamespace(
        source=(
            ManagedStateBaselineSource
            .DURABLE_STATE
        ),
        state_count=4,
    )

    execution = SimpleNamespace(
        provider_request_count=3,
        provider_error_count=0,
        identity_enrichment_request_count=1,
        identity_enriched_count=1,
        identity_enrichment_error_count=0,
        tmdb_request_count=5,
        tmdb_provider_error_count=0,
        tmdb_created_count=1,
        tmdb_changed_count=2,
        tmdb_gap_fill_count=8,
        tmdb_gap_remaining_count=3,
    )

    issue = SimpleNamespace(
        code=(
            PreviewIssueCode
            .MISSING_IDENTITY
        ),
        message="one item needs review",
    )

    preview = SimpleNamespace(
        safe_to_apply=False,
        issues=(issue,),
        plex_show_count=6,
        existing_managed_count=4,
        proposed_state_count=5,
        newly_managed_count=1,
        lost_managed_count=0,
        no_state_titles=("Odd Show",),
        expected_episode_count=20,
        episode_cards_before=10,
        episode_cards_after=17,
        episode_gaps_before=10,
        episode_gaps_after=3,
        coverage_before=0.5,
        coverage_after=0.85,
        coverage_change=0.35,
        sources=(FakeSource(),),
        show_poster_count=4,
        background_count=2,
        shows_with_season_posters=3,
        set_refresh_count=1,
        set_migration_count=0,
        rendered_yaml_bytes=1234,
    )

    plan = SimpleNamespace(
        desired_count=5,
        added_count=1,
        updated_count=2,
        unchanged_count=2,
        removed_count=1,
        write_count=3,
        preserved_unowned=(
            "notes.txt",
        ),
        added=(
            "added.yaml",
        ),
        updated=(
            "changed-a.yaml",
            "changed-b.yaml",
        ),
        removed=(
            "removed.yaml",
        ),
    )

    return ArtworkLibraryWorkflow(
        target=target,
        baseline=baseline,
        execution=execution,
        preview=preview,
        plan=plan,
    )


def test_library_serialization_is_json_safe():
    result = serialize_artwork_library(
        _library_run()
    )

    encoded = json.dumps(result)

    assert encoded
    assert (
        result["library"]
        == "Family Animation"
    )

    assert (
        result["media_type"]
        == "show"
    )

    assert (
        result["baseline"]["source"]
        == "durable_state"
    )

    assert (
        result["safety"]
        ["safe_to_apply"]
        is False
    )

    assert (
        result["safety"]
        ["issues"][0]["code"]
        == "missing_identity"
    )


def test_library_serialization_exposes_gui_summary_values():
    result = serialize_artwork_library(
        _library_run()
    )

    assert result["inventory"] == {
        "plex_shows": 6,
        "managed_before": 4,
        "managed_after": 5,
        "newly_managed": 1,
        "lost_managed": 0,
        "shows_without_state": 1,
        "no_state_titles": [
            "Odd Show",
        ],
    }

    assert (
        result["coverage"]
        ["coverage_after"]
        == 0.85
    )

    assert (
        result["coverage"]
        ["sources"][0]
        == {
            "source": "mediux",
            "before": 10,
            "after": 12,
            "change": 2,
        }
    )


def test_library_serialization_exposes_provider_activity():
    result = serialize_artwork_library(
        _library_run()
    )

    assert (
        result["provider_activity"]
        ["identity_enrichment"]
        == {
            "requests": 1,
            "enriched": 1,
            "errors": 0,
        }
    )

    assert (
        result["provider_activity"]
        ["tmdb"]
        == {
            "requests": 5,
            "errors": 0,
            "created_states": 1,
            "changed_shows": 2,
            "gaps_filled": 8,
            "gaps_remaining": 3,
        }
    )


def test_library_serialization_exposes_reviewed_file_plan():
    result = serialize_artwork_library(
        _library_run()
    )

    assert (
        result["output"]
        ["changed_files"]
        == 4
    )

    assert (
        result["output"]["files"]
        == {
            "added": [
                "added.yaml"
            ],
            "updated": [
                "changed-a.yaml",
                "changed-b.yaml",
            ],
            "removed": [
                "removed.yaml"
            ],
        }
    )


def test_workflow_serialization_includes_skipped_targets():
    run = _library_run()

    skipped_target = ArtworkTarget(
        name="Cinema Vault",
        library="Cinema Vault",
        media_type=MediaType.MOVIE,
        output_path=(
            "/metadata/"
            "artwork-cinema-vault"
        ),
    )

    workflow = ArtworkManagerWorkflow(
        libraries=(run,),
        skipped=(
            SkippedArtworkWorkflowTarget(
                target=skipped_target,
                reason=(
                    ArtworkWorkflowSkipReason
                    .MOVIE_SUPPORT_PENDING
                ),
            ),
        ),
    )

    result = (
        serialize_artwork_workflow(
            workflow
        )
    )

    json.dumps(result)

    assert result["summary"] == {
        "library_count": 1,
        "skipped_count": 1,
        "safe_to_apply": False,
        "changed_files": 4,
    }

    assert result["skipped"] == [
        {
            "library": "Cinema Vault",
            "media_type": "movie",
            "output_path": (
                "/metadata/"
                "artwork-cinema-vault"
            ),
            "reason": (
                "movie_support_pending"
            ),
        }
    ]


def test_empty_workflow_serializes_cleanly():
    result = serialize_artwork_workflow(
        ArtworkManagerWorkflow(
            libraries=(),
            skipped=(),
        )
    )

    assert result == {
        "summary": {
            "library_count": 0,
            "skipped_count": 0,
            "safe_to_apply": True,
            "changed_files": 0,
        },
        "libraries": [],
        "skipped": [],
    }

    json.dumps(result)


def test_library_serialization_exposes_real_apply_requirement():
    result = serialize_artwork_library(
        _library_run()
    )

    assert (
        result["output"]["needs_apply"]
        is True
    )
