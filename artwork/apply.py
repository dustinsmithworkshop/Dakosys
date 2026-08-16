"""Apply validated Artwork Manager target output.

This module is intentionally narrow.

Provider execution and semantic previewing happen before apply. Apply
only verifies that the supplied preview still exactly matches the
execution being persisted, rejects unsafe output, and delegates the
filesystem mutation to the atomic Kometa writer.

Apply does not contact Plex, artwork providers, or Kometa.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from artwork.kometa import (
    write_kometa_metadata,
)
from artwork.preview import (
    ArtworkTargetPreview,
    build_show_target_preview,
)
from artwork.projection import (
    project_show_target_states,
)
from artwork.target_execution import (
    ShowTargetExecution,
)


class ArtworkApplyError(RuntimeError):
    """Base class for Artwork Manager apply failures."""


class UnsafeArtworkPreviewError(
    ArtworkApplyError
):
    """Raised when semantic validation blocks persistence."""


class StaleArtworkPreviewError(
    ArtworkApplyError
):
    """Raised when the reviewed preview no longer matches execution."""


@dataclass(frozen=True)
class ArtworkApplyResult:
    """Result of one successfully persisted artwork target."""

    path: Path
    preview: ArtworkTargetPreview
    state_count: int

    @property
    def rendered_yaml_bytes(
        self,
    ) -> int:
        return (
            self.preview
            .rendered_yaml_bytes
        )


def apply_show_target(
    *,
    execution: ShowTargetExecution,
    preview: ArtworkTargetPreview,
) -> ArtworkApplyResult:
    """Persist one explicitly reviewed show-target execution.

    The preview is rebuilt immediately from the execution and must
    exactly equal the caller-supplied preview. This prevents applying
    an execution after the reviewed semantic result has become stale or
    was accidentally associated with another target.

    Unsafe previews never reach the filesystem writer.
    """

    current_preview = (
        build_show_target_preview(
            execution
        )
    )

    if preview != current_preview:
        raise StaleArtworkPreviewError(
            "reviewed Artwork Manager preview "
            "does not match the current target execution"
        )

    if not current_preview.safe_to_apply:
        issue_codes = ", ".join(
            issue.code.value
            for issue
            in current_preview.issues
        )

        raise UnsafeArtworkPreviewError(
            "Artwork Manager target is not "
            "safe to apply"
            + (
                f": {issue_codes}"
                if issue_codes
                else ""
            )
        )

    output_states = (
        project_show_target_states(
            execution
        )
    )

    if (
        len(output_states)
        != current_preview
        .proposed_state_count
    ):
        raise ArtworkApplyError(
            "projected state count does not "
            "match validated preview"
        )

    path = write_kometa_metadata(
        output_states,
        current_preview.output_path,
    )

    return ArtworkApplyResult(
        path=path,
        preview=current_preview,
        state_count=len(
            output_states
        ),
    )
