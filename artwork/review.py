"""Stable review identity for Artwork Manager library plans."""

from __future__ import annotations

from hashlib import sha256
import json

from artwork.workflow import (
    ArtworkLibraryWorkflow,
)


REVIEW_SCHEMA_VERSION = 1


def _sha256_text(
    value: str,
) -> str:
    return sha256(
        value.encode(
            "utf-8"
        )
    ).hexdigest()


def _issue_code(
    issue,
) -> str:
    code = issue.code

    return str(
        getattr(
            code,
            "value",
            code,
        )
    )


def build_artwork_review_payload(
    run: ArtworkLibraryWorkflow,
) -> dict:
    """Build the canonical data defining one reviewed plan.

    The payload intentionally contains no timestamps or transient request
    counts. It identifies the exact semantic/filesystem result that the
    user reviewed.
    """

    plan = run.plan
    preview = run.preview

    desired_files = sorted(
        (
            {
                "filename": item.filename,
                "sha256": item.sha256,
            }
            for item
            in plan.files
        ),
        key=lambda item:
            item["filename"].casefold(),
    )

    return {
        "schema_version":
            REVIEW_SCHEMA_VERSION,

        "library":
            run.library,

        "output_path":
            str(
                run.output_path
            ),

        "safe_to_apply":
            run.safe_to_apply,

        "needs_apply":
            run.needs_apply,

        "issues": [
            {
                "code":
                    _issue_code(
                        issue
                    ),
                "message":
                    issue.message,
            }
            for issue
            in preview.issues
        ],

        "desired_files":
            desired_files,

        "manifest_sha256":
            _sha256_text(
                plan.manifest.to_json()
            ),

        "state_sha256":
            _sha256_text(
                plan.state_store.to_json()
            ),

        "filesystem": {
            "added":
                sorted(
                    plan.added,
                    key=str.casefold,
                ),

            "updated":
                sorted(
                    plan.updated,
                    key=str.casefold,
                ),

            "unchanged":
                sorted(
                    plan.unchanged,
                    key=str.casefold,
                ),

            "removed":
                sorted(
                    plan.removed,
                    key=str.casefold,
                ),

            "preserved_unowned":
                sorted(
                    plan.preserved_unowned,
                    key=str.casefold,
                ),
        },

        "selection_activity": {
            "set_refreshes":
                preview.set_refresh_count,

            "set_migrations":
                preview.set_migration_count,
        },
    }


def build_artwork_review_fingerprint(
    run: ArtworkLibraryWorkflow,
) -> str:
    """Return a deterministic SHA-256 identity for one reviewed plan."""

    encoded = json.dumps(
        build_artwork_review_payload(
            run
        ),
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=False,
    )

    return _sha256_text(
        encoded
    )
