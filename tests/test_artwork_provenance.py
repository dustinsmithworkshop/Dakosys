import pytest

from artwork.models import (
    ArtworkSetSelection,
    ArtworkSource,
    SelectionMode,
    ShowArtworkState,
)


def test_artwork_set_selection_requires_set_id():
    with pytest.raises(
        ValueError,
        match="cannot be empty",
    ):
        ArtworkSetSelection(
            provider=ArtworkSource.MEDIUX,
            set_id="   ",
        )


def test_legacy_selection_applies_to_both_families():
    state = ShowArtworkState(
        title="Example",
        tvdb_id=12345,
        selected_set_id="100",
        selected_set_source=ArtworkSource.MEDIUX,
        selected_creator="creator-a",
        selection_mode=SelectionMode.PREFERRED,
    )

    episode = (
        state.effective_episode_selection
    )

    presentation = (
        state.effective_presentation_selection
    )

    assert episode is not None
    assert presentation is not None

    assert episode.provider is ArtworkSource.MEDIUX
    assert episode.set_id == "100"
    assert episode.creator == "creator-a"
    assert episode.mode is SelectionMode.PREFERRED

    assert presentation == episode


def test_episode_selection_can_override_legacy_selection():
    state = ShowArtworkState(
        title="Example",
        tvdb_id=12345,
        selected_set_id="legacy",
        selected_set_source=ArtworkSource.MEDIUX,
        episode_selection=ArtworkSetSelection(
            provider=ArtworkSource.MEDIUX,
            set_id="cards",
            creator="card-creator",
        ),
    )

    assert (
        state.effective_episode_selection.set_id
        == "cards"
    )

    assert (
        state.effective_presentation_selection.set_id
        == "legacy"
    )


def test_presentation_and_episode_selections_can_differ():
    state = ShowArtworkState(
        title="Example",
        tvdb_id=12345,
        episode_selection=ArtworkSetSelection(
            provider=ArtworkSource.MEDIUX,
            set_id="episode-set",
            creator="episode-creator",
        ),
        presentation_selection=ArtworkSetSelection(
            provider=ArtworkSource.MEDIUX,
            set_id="presentation-set",
            creator="presentation-creator",
            mode=SelectionMode.LOCKED,
        ),
    )

    assert (
        state.effective_episode_selection.set_id
        == "episode-set"
    )

    assert (
        state.effective_presentation_selection.set_id
        == "presentation-set"
    )

    assert (
        state.effective_presentation_selection.mode
        is SelectionMode.LOCKED
    )


def test_state_without_provenance_has_no_effective_selection():
    state = ShowArtworkState(
        title="Example",
        tvdb_id=12345,
    )

    assert (
        state.effective_episode_selection
        is None
    )

    assert (
        state.effective_presentation_selection
        is None
    )
