from types import SimpleNamespace

from artwork.item_store_bootstrap import (
    PersistedArtworkEvidence,
    ShowItemStoreBootstrapSeed,
)
from artwork.item_store_bootstrap_match import (
    MediuxBootstrapFamily,
)
from artwork.item_store_bootstrap_witness import (
    LegacyBootstrapContinuityPath,
    legacy_mediux_family_asset_ids,
    match_legacy_bootstrap_family_witness,
)
from artwork.models import (
    ArtworkKind,
    ArtworkSource,
)


def _mediux_url(
    asset_id,
):
    return (
        "https://api.mediux.pro/"
        f"assets/{asset_id}"
    )


def _asset(
    value,
):
    if value is None:
        return None

    if "://" in value:
        url = value
    else:
        url = _mediux_url(
            value
        )

    return SimpleNamespace(
        url=url
    )


def _seed(
    *,
    episode_ids=(),
    presentation_ids=(),
    tvdb_id=100,
):
    assets = []

    for asset_id in episode_ids:
        assets.append(
            PersistedArtworkEvidence(
                kind=(
                    ArtworkKind
                    .EPISODE_CARD
                ),
                source=(
                    ArtworkSource.MEDIUX
                ),
                url=_mediux_url(
                    asset_id
                ),
                provider_asset_id=(
                    asset_id
                ),
            )
        )

    for asset_id in presentation_ids:
        assets.append(
            PersistedArtworkEvidence(
                kind=(
                    ArtworkKind
                    .SHOW_POSTER
                ),
                source=(
                    ArtworkSource.MEDIUX
                ),
                url=_mediux_url(
                    asset_id
                ),
                provider_asset_id=(
                    asset_id
                ),
            )
        )

    return ShowItemStoreBootstrapSeed(
        plex_rating_key="10",
        tvdb_id=tvdb_id,
        filename="example.yaml",
        assets=tuple(
            assets
        ),
    )


def _legacy_state(
    *,
    episode_values=(),
    presentation_values=(),
    tvdb_id=100,
    set_id="500",
    source=ArtworkSource.MEDIUX,
):
    presentation = list(
        presentation_values
    )

    poster = (
        _asset(
            presentation.pop(0)
        )
        if presentation
        else None
    )

    background = (
        _asset(
            presentation.pop(0)
        )
        if presentation
        else None
    )

    season_poster = (
        _asset(
            presentation.pop(0)
        )
        if presentation
        else None
    )

    episodes = {
        index: SimpleNamespace(
            card=_asset(
                value
            )
        )
        for index, value
        in enumerate(
            episode_values,
            start=1,
        )
    }

    season = SimpleNamespace(
        poster=season_poster,
        episodes=episodes,
    )

    return SimpleNamespace(
        tvdb_id=tvdb_id,
        selected_set_id=set_id,
        selected_set_source=source,
        selected_creator="historical-user",
        poster=poster,
        background=background,
        seasons={
            1: season,
        },
    )


def test_exact_historical_continuity_recovers_set():
    result = (
        match_legacy_bootstrap_family_witness(
            seed=_seed(
                episode_ids=(
                    "a",
                    "b",
                ),
            ),
            legacy_state=_legacy_state(
                episode_values=(
                    "a",
                    "b",
                ),
            ),
            family=(
                MediuxBootstrapFamily
                .EPISODE
            ),
        )
    )

    assert (
        result.path
        is LegacyBootstrapContinuityPath.EXACT
    )
    assert result.recovered
    assert not result.blocks_bootstrap
    assert result.recovered_set_id == "500"
    assert (
        result.historical_creator
        == "historical-user"
    )


def test_current_subset_of_legacy_is_continuity():
    result = (
        match_legacy_bootstrap_family_witness(
            seed=_seed(
                episode_ids=(
                    "a",
                    "b",
                ),
            ),
            legacy_state=_legacy_state(
                episode_values=(
                    "a",
                    "b",
                    "removed",
                ),
            ),
            family=(
                MediuxBootstrapFamily
                .EPISODE
            ),
        )
    )

    assert (
        result.path
        is (
            LegacyBootstrapContinuityPath
            .CURRENT_SUBSET_OF_LEGACY
        )
    )
    assert result.recovered


def test_legacy_subset_of_current_is_continuity():
    result = (
        match_legacy_bootstrap_family_witness(
            seed=_seed(
                episode_ids=(
                    "a",
                    "b",
                    "new",
                ),
            ),
            legacy_state=_legacy_state(
                episode_values=(
                    "a",
                    "b",
                ),
            ),
            family=(
                MediuxBootstrapFamily
                .EPISODE
            ),
        )
    )

    assert (
        result.path
        is (
            LegacyBootstrapContinuityPath
            .LEGACY_SUBSET_OF_CURRENT
        )
    )
    assert result.recovered


def test_partial_overlap_does_not_recover_old_set():
    result = (
        match_legacy_bootstrap_family_witness(
            seed=_seed(
                episode_ids=(
                    "shared",
                    "current-only",
                ),
            ),
            legacy_state=_legacy_state(
                episode_values=(
                    "shared",
                    "legacy-only",
                ),
            ),
            family=(
                MediuxBootstrapFamily
                .EPISODE
            ),
        )
    )

    assert (
        result.path
        is (
            LegacyBootstrapContinuityPath
            .PARTIAL_OVERLAP
        )
    )
    assert not result.recovered
    assert result.blocks_bootstrap


def test_disjoint_evidence_does_not_recover_old_set():
    result = (
        match_legacy_bootstrap_family_witness(
            seed=_seed(
                episode_ids=(
                    "current",
                ),
            ),
            legacy_state=_legacy_state(
                episode_values=(
                    "legacy",
                ),
            ),
            family=(
                MediuxBootstrapFamily
                .EPISODE
            ),
        )
    )

    assert (
        result.path
        is LegacyBootstrapContinuityPath.DISJOINT
    )
    assert not result.recovered
    assert result.blocks_bootstrap


def test_tmdb_urls_in_old_metadata_are_not_mediux_evidence():
    legacy = _legacy_state(
        episode_values=(
            "mediux-card",
            (
                "https://image.tmdb.org/"
                "t/p/original/still.jpg"
            ),
        ),
    )

    ids = (
        legacy_mediux_family_asset_ids(
            legacy,
            family=(
                MediuxBootstrapFamily
                .EPISODE
            ),
        )
    )

    assert ids == {
        "mediux-card",
    }


def test_missing_explicit_mediux_selection_blocks_recovery():
    result = (
        match_legacy_bootstrap_family_witness(
            seed=_seed(
                episode_ids=(
                    "a",
                ),
            ),
            legacy_state=_legacy_state(
                episode_values=(
                    "a",
                ),
                set_id=None,
            ),
            family=(
                MediuxBootstrapFamily
                .EPISODE
            ),
        )
    )

    assert (
        result.path
        is (
            LegacyBootstrapContinuityPath
            .NO_MEDIUX_SELECTION
        )
    )
    assert not result.recovered
    assert result.blocks_bootstrap


def test_non_mediux_historical_selection_is_not_used():
    result = (
        match_legacy_bootstrap_family_witness(
            seed=_seed(
                episode_ids=(
                    "a",
                ),
            ),
            legacy_state=_legacy_state(
                episode_values=(
                    "a",
                ),
                source=ArtworkSource.MANUAL,
            ),
            family=(
                MediuxBootstrapFamily
                .EPISODE
            ),
        )
    )

    assert (
        result.path
        is (
            LegacyBootstrapContinuityPath
            .NO_MEDIUX_SELECTION
        )
    )
    assert not result.recovered


def test_tvdb_identity_mismatch_blocks_witness():
    result = (
        match_legacy_bootstrap_family_witness(
            seed=_seed(
                episode_ids=(
                    "a",
                ),
                tvdb_id=100,
            ),
            legacy_state=_legacy_state(
                episode_values=(
                    "a",
                ),
                tvdb_id=200,
            ),
            family=(
                MediuxBootstrapFamily
                .EPISODE
            ),
        )
    )

    assert (
        result.path
        is (
            LegacyBootstrapContinuityPath
            .IDENTITY_MISMATCH
        )
    )
    assert not result.recovered
    assert result.blocks_bootstrap


def test_no_current_mediux_evidence_needs_no_witness():
    result = (
        match_legacy_bootstrap_family_witness(
            seed=_seed(),
            legacy_state=None,
            family=(
                MediuxBootstrapFamily
                .EPISODE
            ),
        )
    )

    assert (
        result.path
        is (
            LegacyBootstrapContinuityPath
            .NO_CURRENT_EVIDENCE
        )
    )
    assert not result.recovered
    assert not result.blocks_bootstrap
