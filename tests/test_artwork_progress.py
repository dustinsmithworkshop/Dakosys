from artwork.progress import (
    ArtworkScanPhase,
    emit_artwork_progress,
)


def test_progress_fraction_is_truthful_phase_progress():
    seen = []

    emit_artwork_progress(
        seen.append,
        library="Series",
        phase=(
            ArtworkScanPhase
            .PRIMARY_MANAGED
        ),
        completed=25,
        total=100,
        message="Checking artwork",
        current_title="Example",
    )

    assert len(
        seen
    ) == 1

    progress = seen[0]

    assert (
        progress.library
        == "Series"
    )

    assert (
        progress.phase
        is ArtworkScanPhase
        .PRIMARY_MANAGED
    )

    assert (
        progress.completed
        == 25
    )

    assert (
        progress.total
        == 100
    )

    assert (
        progress.fraction
        == 0.25
    )

    assert (
        progress.current_title
        == "Example"
    )


def test_progress_without_meaningful_total_has_no_fraction():
    seen = []

    emit_artwork_progress(
        seen.append,
        library="Series",
        phase=(
            ArtworkScanPhase
            .PLANNING
        ),
        completed=0,
        total=0,
    )

    assert (
        seen[0].fraction
        is None
    )


def test_none_progress_callback_is_noop():
    emit_artwork_progress(
        None,
        library="Series",
        phase=(
            ArtworkScanPhase
            .COMPLETE
        ),
        completed=1,
        total=1,
    )
