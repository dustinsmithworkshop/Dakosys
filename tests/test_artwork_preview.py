from pathlib import Path
from types import SimpleNamespace

from artwork.inventory import (
    SeasonInventory,
    ShowInventory,
)
from artwork.models import (
    ArtworkAsset,
    ArtworkKind,
    ArtworkQuality,
    ArtworkSource,
    EpisodeArtwork,
    SeasonArtwork,
    ShowArtworkState,
)
from artwork.preview import (
    PreviewIssueCode,
    build_show_target_preview,
    format_show_target_preview,
)
from artwork.targets import (
    ArtworkTarget,
    MediaType,
)


def _inventory(
    rating_key,
    title,
    tvdb_id,
    episodes=(1, 2),
):
    return ShowInventory(
        identity=SimpleNamespace(
            library="TV",
            plex_rating_key=rating_key,
            title=title,
            tvdb_id=tvdb_id,
        ),
        seasons=(
            SeasonInventory(
                season_number=1,
                episode_numbers=frozenset(
                    episodes
                ),
            ),
        ),
    )


def _card(
    source,
    asset_id,
):
    quality = (
        ArtworkQuality.CURATED
        if source
        is ArtworkSource.MEDIUX
        else ArtworkQuality.RAW_STILL
    )

    return ArtworkAsset(
        kind=ArtworkKind.EPISODE_CARD,
        source=source,
        url=(
            "https://example/"
            f"{asset_id}.jpg"
        ),
        provider_asset_id=asset_id,
        quality=quality,
    )


def _state(
    tvdb_id,
    cards,
    *,
    poster=False,
    background=False,
    season_poster=False,
):
    seasons = {
        1: SeasonArtwork(
            season_number=1,
            poster=(
                ArtworkAsset(
                    kind=ArtworkKind.SEASON_POSTER,
                    source=ArtworkSource.MEDIUX,
                    url=(
                        "https://example/"
                        "season.jpg"
                    ),
                    provider_asset_id="season",
                    quality=ArtworkQuality.CURATED,
                )
                if season_poster
                else None
            ),
            episodes={
                number: EpisodeArtwork(
                    episode_number=number,
                    card=card,
                )
                for number, card
                in cards.items()
            },
        ),
    }

    return ShowArtworkState(
        title="Example",
        tvdb_id=tvdb_id,
        poster=(
            ArtworkAsset(
                kind=ArtworkKind.SHOW_POSTER,
                source=ArtworkSource.MEDIUX,
                url=(
                    "https://example/"
                    "poster.jpg"
                ),
                provider_asset_id="poster",
                quality=ArtworkQuality.CURATED,
            )
            if poster
            else None
        ),
        background=(
            ArtworkAsset(
                kind=ArtworkKind.SHOW_BACKGROUND,
                source=ArtworkSource.MEDIUX,
                url=(
                    "https://example/"
                    "background.jpg"
                ),
                provider_asset_id="background",
                quality=ArtworkQuality.CURATED,
            )
            if background
            else None
        ),
        seasons=seasons,
    )


def _target():
    return ArtworkTarget(
        name="TV",
        library="TV",
        media_type=MediaType.SHOW,
        output_path=Path(
            "/tmp/artwork-tv.yaml"
        ),
    )


def _execution(
    *,
    managed_inventory=None,
    managed_before=None,
    managed_after=None,
    unmanaged_inventory=None,
    unmanaged_after=None,
    missing_identity=(),
    ambiguous=(),
    orphaned=(),
    provider_errors=0,
    tmdb_errors=0,
    missing_set_context=0,
    refreshes=0,
    migrations=0,
    tmdb_created=0,
    tmdb_changed=0,
):
    matched = ()

    managed_results = ()
    managed_coverage = ()

    if (
        managed_inventory is not None
        and managed_before is not None
    ):
        matched = (
            SimpleNamespace(
                inventory=managed_inventory,
                artwork=managed_before,
            ),
        )

        managed_result = (
            SimpleNamespace(
                inventory=managed_inventory,
                state=managed_after,
            )
        )

        managed_results = (
            managed_result,
        )

        managed_coverage = (
            managed_result,
        )

    unmanaged = ()
    discovery_results = ()
    discovery_coverage = ()

    if unmanaged_inventory is not None:
        unmanaged = (
            unmanaged_inventory,
        )

        discovery_result = (
            SimpleNamespace(
                inventory=unmanaged_inventory,
                state=unmanaged_after,
            )
        )

        discovery_results = (
            discovery_result,
        )

        discovery_coverage = (
            discovery_result,
        )

    resolved_states = tuple(
        result.state
        for result
        in (
            managed_coverage
            + discovery_coverage
        )
        if result.state is not None
    )

    reconciliation = (
        SimpleNamespace(
            target=_target(),
            matched=matched,
            unmanaged=unmanaged,
            missing_identity=tuple(
                missing_identity
            ),
            ambiguous=tuple(
                ambiguous
            ),
            orphaned=tuple(
                orphaned
            ),
        )
    )

    managed = SimpleNamespace(
        results=managed_results,
        provider_error_count=(
            provider_errors
        ),
        missing_set_context_count=(
            missing_set_context
        ),
        set_refresh_count=refreshes,
        set_migration_count=migrations,
    )

    discovery = SimpleNamespace(
        results=discovery_results,
        provider_error_count=0,
    )

    return SimpleNamespace(
        reconciliation=reconciliation,
        managed=managed,
        discovery=discovery,
        managed_coverage=(
            managed_coverage
        ),
        discovery_coverage=(
            discovery_coverage
        ),
        coverage_enabled=True,
        resolved_states=(
            resolved_states
        ),
        provider_error_count=(
            provider_errors
        ),
        tmdb_provider_error_count=(
            tmdb_errors
        ),
        tmdb_created_count=(
            tmdb_created
        ),
        tmdb_changed_count=(
            tmdb_changed
        ),
    )


def _base_execution():
    managed_inventory = _inventory(
        "1",
        "Managed",
        100,
    )

    unmanaged_inventory = _inventory(
        "2",
        "New",
        200,
        episodes=(1,),
    )

    managed_before = _state(
        100,
        {
            1: _card(
                ArtworkSource.MEDIUX,
                "mediux-1",
            ),
        },
    )

    managed_after = _state(
        100,
        {
            1: _card(
                ArtworkSource.MEDIUX,
                "mediux-1",
            ),
            2: _card(
                ArtworkSource.TMDB,
                "tmdb-2",
            ),
        },
        poster=True,
        background=True,
        season_poster=True,
    )

    unmanaged_after = _state(
        200,
        {
            1: _card(
                ArtworkSource.TMDB,
                "tmdb-new-1",
            ),
        },
    )

    return _execution(
        managed_inventory=(
            managed_inventory
        ),
        managed_before=managed_before,
        managed_after=managed_after,
        unmanaged_inventory=(
            unmanaged_inventory
        ),
        unmanaged_after=unmanaged_after,
        refreshes=1,
        tmdb_created=1,
        tmdb_changed=2,
    )


def _codes(preview):
    return {
        issue.code
        for issue
        in preview.issues
    }


def test_preview_reports_semantic_before_after_counts():
    preview = (
        build_show_target_preview(
            _base_execution()
        )
    )

    assert preview.plex_show_count == 2
    assert preview.existing_managed_count == 1
    assert preview.proposed_state_count == 2
    assert preview.newly_managed_count == 1
    assert preview.lost_managed_count == 0

    assert (
        preview.expected_episode_count
        == 3
    )

    assert (
        preview.episode_cards_before
        == 1
    )

    assert (
        preview.episode_cards_after
        == 3
    )

    assert (
        preview.episode_gaps_before
        == 2
    )

    assert (
        preview.episode_gaps_after
        == 0
    )

    assert (
        preview.coverage_before
        == 1 / 3
    )

    assert (
        preview.coverage_after
        == 1.0
    )

    sources = {
        item.source: item
        for item
        in preview.sources
    }

    assert sources[
        "mediux"
    ].before == 1

    assert sources[
        "mediux"
    ].after == 1

    assert sources[
        "tmdb"
    ].before == 0

    assert sources[
        "tmdb"
    ].after == 2

    assert (
        preview.show_poster_count
        == 1
    )

    assert (
        preview.background_count
        == 1
    )

    assert (
        preview.shows_with_season_posters
        == 1
    )

    assert preview.safe_to_apply
    assert preview.rendered_yaml_bytes > 0


def test_no_state_is_reported_but_does_not_block_apply():
    execution = (
        _base_execution()
    )

    execution = _execution(
        managed_inventory=(
            execution
            .managed_coverage[0]
            .inventory
        ),
        managed_before=(
            execution
            .reconciliation
            .matched[0]
            .artwork
        ),
        managed_after=(
            execution
            .managed_coverage[0]
            .state
        ),
        unmanaged_inventory=(
            execution
            .discovery_coverage[0]
            .inventory
        ),
        unmanaged_after=None,
    )

    preview = (
        build_show_target_preview(
            execution
        )
    )

    assert (
        preview.no_state_titles
        == ("New",)
    )

    assert preview.safe_to_apply


def test_primary_and_tmdb_provider_errors_block_apply():
    execution = (
        _base_execution()
    )

    execution.provider_error_count = 2
    execution.tmdb_provider_error_count = 1

    preview = (
        build_show_target_preview(
            execution
        )
    )

    codes = _codes(
        preview
    )

    assert (
        PreviewIssueCode
        .PRIMARY_PROVIDER_ERROR
        in codes
    )

    assert (
        PreviewIssueCode
        .TMDB_PROVIDER_ERROR
        in codes
    )

    assert not preview.safe_to_apply


def test_reconciliation_safety_issues_block_apply():
    execution = (
        _base_execution()
    )

    missing = _inventory(
        "3",
        "Missing",
        None,
        episodes=(1,),
    )

    ambiguous_inventory = (
        _inventory(
            "4",
            "Ambiguous",
            400,
            episodes=(1,),
        )
    )

    execution.reconciliation.missing_identity = (
        missing,
    )

    execution.reconciliation.ambiguous = (
        SimpleNamespace(
            inventories=(
                ambiguous_inventory,
            ),
        ),
    )

    execution.reconciliation.orphaned = (
        object(),
    )

    preview = (
        build_show_target_preview(
            execution
        )
    )

    codes = _codes(
        preview
    )

    assert (
        PreviewIssueCode
        .MISSING_IDENTITY
        in codes
    )

    assert (
        PreviewIssueCode
        .AMBIGUOUS_IDENTITY
        in codes
    )

    assert (
        PreviewIssueCode
        .ORPHANED_STATE
        in codes
    )

    assert not preview.safe_to_apply


def test_missing_set_context_and_managed_state_loss_block_apply():
    managed_inventory = _inventory(
        "1",
        "Managed",
        100,
    )

    managed_before = _state(
        100,
        {
            1: _card(
                ArtworkSource.MEDIUX,
                "old",
            ),
        },
    )

    execution = _execution(
        managed_inventory=(
            managed_inventory
        ),
        managed_before=(
            managed_before
        ),
        managed_after=None,
        missing_set_context=1,
    )

    preview = (
        build_show_target_preview(
            execution
        )
    )

    codes = _codes(
        preview
    )

    assert preview.lost_managed_count == 1

    assert (
        PreviewIssueCode
        .MISSING_SET_CONTEXT
        in codes
    )

    assert (
        PreviewIssueCode
        .MANAGED_STATE_LOSS
        in codes
    )

    assert not preview.safe_to_apply


def test_proposed_state_without_tvdb_identity_blocks_apply():
    execution = (
        _base_execution()
    )

    unmanaged = (
        execution
        .discovery_coverage[0]
        .inventory
    )

    unmanaged_state = _state(
        None,
        {
            1: _card(
                ArtworkSource.TMDB,
                "tmdb-no-tvdb",
            ),
        },
    )

    execution.discovery_coverage = (
        SimpleNamespace(
            inventory=unmanaged,
            state=unmanaged_state,
        ),
    )

    preview = (
        build_show_target_preview(
            execution
        )
    )

    assert (
        PreviewIssueCode
        .OUTPUT_IDENTITY_MISSING
        in _codes(preview)
    )

    assert not preview.safe_to_apply


def test_duplicate_tvdb_output_identity_blocks_apply():
    execution = (
        _base_execution()
    )

    unmanaged = (
        execution
        .discovery_coverage[0]
        .inventory
    )

    duplicate_state = _state(
        100,
        {
            1: _card(
                ArtworkSource.TMDB,
                "duplicate",
            ),
        },
    )

    execution.discovery_coverage = (
        SimpleNamespace(
            inventory=unmanaged,
            state=duplicate_state,
        ),
    )

    preview = (
        build_show_target_preview(
            execution
        )
    )

    assert (
        PreviewIssueCode
        .KOMETA_RENDER_ERROR
        in _codes(preview)
    )

    assert preview.rendered_yaml_bytes == 0
    assert not preview.safe_to_apply


def test_formatted_preview_is_human_readable_and_never_claims_write():
    preview = (
        build_show_target_preview(
            _base_execution()
        )
    )

    text = (
        format_show_target_preview(
            preview
        )
    )

    assert (
        "Artwork preview: TV"
        in text
    )

    assert (
        "Existing managed:        1"
        in text
    )

    assert (
        "Proposed states:         2"
        in text
    )

    assert (
        "Coverage after:          100.00%"
        in text
    )

    assert (
        "Validation: SAFE TO APPLY"
        in text
    )

    assert (
        "WRITE: disabled"
        in text
    )
