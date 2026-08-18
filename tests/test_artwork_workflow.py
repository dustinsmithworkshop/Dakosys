from pathlib import Path
from types import SimpleNamespace

import pytest

from artwork.targets import (
    ArtworkTarget,
    MediaType,
)
from artwork.workflow import (
    ArtworkLibraryWorkflow,
    ArtworkWorkflowSkipReason,
    apply_artwork_library_workflow,
    build_artwork_manager_workflow,
)


class FakeSection:
    def __init__(
        self,
        title,
        section_type,
        items=(),
    ):
        self.title = title
        self.type = section_type
        self._items = list(items)

    def all(self):
        return list(self._items)


class FakeLibrary:
    def __init__(
        self,
        sections,
    ):
        self._sections = list(sections)

    def sections(self):
        return list(self._sections)

    def section(
        self,
        name,
    ):
        for section in self._sections:
            if section.title == name:
                return section

        raise KeyError(name)


class FakePlex:
    def __init__(
        self,
        *sections,
    ):
        self.library = FakeLibrary(
            sections
        )


def _config():
    return {
        "services": {
            "artwork_manager": {
                "enabled": True,
                "output_dir": "/metadata",
            },
        },
    }


def _stub_show_pipeline(
    monkeypatch,
):
    calls = {
        "baseline": [],
        "inventory": [],
        "execution": [],
        "preview": [],
        "plan": [],
    }

    def fake_baseline(
        *,
        directory,
        library,
        legacy_metadata=None,
    ):
        calls["baseline"].append(
            (
                Path(directory),
                library,
                legacy_metadata,
            )
        )

        return SimpleNamespace(
            library=library,
            states=(
                f"managed:{library}",
            ),
            source="fake",
        )

    def fake_inventory(
        show,
        library,
    ):
        value = (
            f"inventory:{library}:{show}"
        )

        calls["inventory"].append(
            value
        )

        return value

    def fake_execution(
        *,
        target,
        inventories,
        managed_shows,
        provider,
        tmdb_client=None,
        incomplete_migration_threshold=0.25,
    ):
        value = SimpleNamespace(
            target=target,
            inventories=tuple(
                inventories
            ),
            managed_shows=tuple(
                managed_shows
            ),
            provider=provider,
            tmdb_client=tmdb_client,
            threshold=(
                incomplete_migration_threshold
            ),
        )

        calls["execution"].append(
            value
        )

        return value

    def fake_preview(
        execution,
    ):
        value = SimpleNamespace(
            execution=execution,
            safe_to_apply=True,
            issues=(),
        )

        calls["preview"].append(
            value
        )

        return value

    def fake_plan(
        execution,
    ):
        value = SimpleNamespace(
            execution=execution,
            desired_count=1,
            added_count=0,
            updated_count=0,
            removed_count=0,
        )

        calls["plan"].append(
            value
        )

        return value

    monkeypatch.setattr(
        "artwork.workflow."
        "load_show_managed_state_baseline",
        fake_baseline,
    )

    monkeypatch.setattr(
        "artwork.workflow."
        "build_show_inventory",
        fake_inventory,
    )

    monkeypatch.setattr(
        "artwork.workflow."
        "execute_show_target",
        fake_execution,
    )

    monkeypatch.setattr(
        "artwork.workflow."
        "build_show_target_preview",
        fake_preview,
    )

    monkeypatch.setattr(
        "artwork.workflow."
        "build_show_item_store_plan",
        fake_plan,
    )

    return calls


def test_workflow_discovers_arbitrary_library_names(
    monkeypatch,
):
    calls = _stub_show_pipeline(
        monkeypatch
    )

    plex = FakePlex(
        FakeSection(
            "Bob's Shows",
            "show",
            items=("alpha",),
        ),
        FakeSection(
            "Kids & Family",
            "show",
            items=("beta",),
        ),
        FakeSection(
            "Feature Films",
            "movie",
        ),
        FakeSection(
            "Music Stuff",
            "artist",
        ),
    )

    provider = object()

    workflow = (
        build_artwork_manager_workflow(
            plex=plex,
            config=_config(),
            provider=provider,
        )
    )

    assert [
        run.library
        for run in workflow.libraries
    ] == [
        "Bob's Shows",
        "Kids & Family",
    ]

    assert [
        run.output_path
        for run in workflow.libraries
    ] == [
        Path(
            "/metadata/"
            "artwork-bob-s-shows"
        ),
        Path(
            "/metadata/"
            "artwork-kids-family"
        ),
    ]

    assert len(
        workflow.skipped
    ) == 1

    assert (
        workflow.skipped[0]
        .target.library
        == "Feature Films"
    )

    assert (
        workflow.skipped[0]
        .reason
        is ArtworkWorkflowSkipReason
        .MOVIE_SUPPORT_PENDING
    )

    assert calls["inventory"] == [
        "inventory:Bob's Shows:alpha",
        "inventory:Kids & Family:beta",
    ]

    assert workflow.safe_to_apply
    assert workflow.changed_file_count == 0


def test_workflow_can_select_one_exact_library(
    monkeypatch,
):
    calls = _stub_show_pipeline(
        monkeypatch
    )

    plex = FakePlex(
        FakeSection(
            "Animation Archive",
            "show",
            items=("one",),
        ),
        FakeSection(
            "Series",
            "show",
            items=("two",),
        ),
    )

    workflow = (
        build_artwork_manager_workflow(
            plex=plex,
            config=_config(),
            provider=object(),
            selected_libraries=(
                "Series"
            ),
        )
    )

    assert [
        run.library
        for run in workflow.libraries
    ] == [
        "Series",
    ]

    assert calls["inventory"] == [
        "inventory:Series:two",
    ]

    assert (
        workflow.run_for_library(
            "Series"
        )
        is workflow.libraries[0]
    )

    assert (
        workflow.run_for_library(
            "Animation Archive"
        )
        is None
    )


def test_workflow_rejects_unknown_selected_library(
    monkeypatch,
):
    _stub_show_pipeline(
        monkeypatch
    )

    plex = FakePlex(
        FakeSection(
            "Documentaries",
            "show",
        ),
    )

    with pytest.raises(
        ValueError,
        match=(
            "were not discovered in Plex"
        ),
    ):
        build_artwork_manager_workflow(
            plex=plex,
            config=_config(),
            provider=object(),
            selected_libraries=(
                "Definitely Not Here"
            ),
        )


def test_legacy_migration_is_explicit_by_library(
    monkeypatch,
):
    calls = _stub_show_pipeline(
        monkeypatch
    )

    plex = FakePlex(
        FakeSection(
            "Imported Shows",
            "show",
            items=("one",),
        ),
        FakeSection(
            "Fresh Shows",
            "show",
            items=("two",),
        ),
    )

    build_artwork_manager_workflow(
        plex=plex,
        config=_config(),
        provider=object(),
        legacy_metadata_by_library={
            "Imported Shows": (
                "/imports/"
                "old-kometa.yml"
            ),
        },
    )

    assert calls["baseline"] == [
        (
            Path(
                "/metadata/"
                "artwork-imported-shows"
            ),
            "Imported Shows",
            Path(
                "/imports/"
                "old-kometa.yml"
            ),
        ),
        (
            Path(
                "/metadata/"
                "artwork-fresh-shows"
            ),
            "Fresh Shows",
            None,
        ),
    ]


def test_legacy_migration_is_not_inferred_for_non_show_target(
    monkeypatch,
):
    _stub_show_pipeline(
        monkeypatch
    )

    plex = FakePlex(
        FakeSection(
            "Cinema",
            "movie",
        ),
    )

    with pytest.raises(
        ValueError,
        match=(
            "not discovered show targets"
        ),
    ):
        build_artwork_manager_workflow(
            plex=plex,
            config=_config(),
            provider=object(),
            legacy_metadata_by_library={
                "Cinema": (
                    "/imports/"
                    "cinema.yml"
                ),
            },
        )


def test_apply_uses_exact_reviewed_library_artifacts(
    monkeypatch,
):
    target = ArtworkTarget(
        name="Anything Goes",
        library="Anything Goes",
        media_type=MediaType.SHOW,
        output_path=(
            "/metadata/"
            "artwork-anything-goes"
        ),
    )

    baseline = object()
    execution = object()

    preview = SimpleNamespace(
        safe_to_apply=True,
    )

    plan = SimpleNamespace(
        desired_count=3,
        added_count=1,
        updated_count=1,
        removed_count=0,
    )

    run = ArtworkLibraryWorkflow(
        target=target,
        baseline=baseline,
        execution=execution,
        preview=preview,
        plan=plan,
    )

    expected_result = object()
    seen = {}

    def fake_apply(
        *,
        execution,
        preview,
        plan,
    ):
        seen["execution"] = execution
        seen["preview"] = preview
        seen["plan"] = plan

        return expected_result

    monkeypatch.setattr(
        "artwork.workflow."
        "apply_show_item_store",
        fake_apply,
    )

    result = (
        apply_artwork_library_workflow(
            run
        )
    )

    assert result is expected_result
    assert seen == {
        "execution": execution,
        "preview": preview,
        "plan": plan,
    }

    assert run.library == (
        "Anything Goes"
    )

    assert run.changed_file_count == 2


def test_workflow_preserves_unplannable_preview_as_blocked(
    monkeypatch,
):
    from artwork.preview import (
        PreviewIssue,
        PreviewIssueCode,
    )

    _stub_show_pipeline(
        monkeypatch
    )

    preview = SimpleNamespace(
        safe_to_apply=False,
        issues=(
            PreviewIssue(
                code=(
                    PreviewIssueCode
                    .KOMETA_RENDER_ERROR
                ),
                message=(
                    "duplicate TVDB identity "
                    "in Kometa artwork output: 188551"
                ),
            ),
        ),
    )

    monkeypatch.setattr(
        "artwork.workflow."
        "build_show_target_preview",
        lambda execution:
            preview,
    )

    def fail_if_planned(
        execution,
    ):
        raise AssertionError(
            "unsafe Kometa output must not "
            "build a filesystem plan"
        )

    monkeypatch.setattr(
        "artwork.workflow."
        "build_show_item_store_plan",
        fail_if_planned,
    )

    plex = FakePlex(
        FakeSection(
            "Anime",
            "show",
            items=("panty",),
        ),
    )

    workflow = (
        build_artwork_manager_workflow(
            plex=plex,
            config=_config(),
            provider=object(),
        )
    )

    assert len(
        workflow.libraries
    ) == 1

    run = (
        workflow.libraries[0]
    )

    assert (
        run.library
        == "Anime"
    )

    assert (
        run.safe_to_apply
        is False
    )

    assert (
        run.plan
        is None
    )

    assert (
        run.plan_available
        is False
    )

    assert (
        run.needs_apply
        is False
    )

    assert (
        run.desired_count
        == 0
    )

    assert (
        run.changed_file_count
        == 0
    )
