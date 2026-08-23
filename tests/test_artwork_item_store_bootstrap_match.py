from types import SimpleNamespace

from artwork.item_store_bootstrap import (
    PersistedArtworkEvidence,
    ShowItemStoreBootstrapSeed,
)
from artwork.item_store_bootstrap_match import (
    MediuxBootstrapFamily,
    MediuxBootstrapMatchPath,
    match_mediux_bootstrap_families,
    match_mediux_bootstrap_family,
    mediux_candidate_family_asset_ids,
)
from artwork.models import (
    ArtworkKind,
    ArtworkSource,
)


def _asset(
    asset_id,
    *,
    source=ArtworkSource.MEDIUX,
):
    return SimpleNamespace(
        source=source,
        provider_asset_id=asset_id,
    )


def _candidate(
    set_id,
    *,
    episode_ids=(),
    presentation_ids=(),
    provider=ArtworkSource.MEDIUX,
):
    presentation_ids = list(
        presentation_ids
    )

    poster = (
        _asset(
            presentation_ids.pop(0)
        )
        if presentation_ids
        else None
    )

    background = (
        _asset(
            presentation_ids.pop(0)
        )
        if presentation_ids
        else None
    )

    seasons = {}

    season = SimpleNamespace(
        poster=None,
        episodes={},
    )

    if presentation_ids:
        season.poster = _asset(
            presentation_ids.pop(0)
        )

    for index, asset_id in enumerate(
        episode_ids,
        start=1,
    ):
        season.episodes[
            index
        ] = SimpleNamespace(
            card=_asset(
                asset_id
            )
        )

    if (
        season.poster is not None
        or season.episodes
    ):
        seasons[1] = season

    return SimpleNamespace(
        provider=provider,
        set_id=str(
            set_id
        ),
        creator="creator",
        title=f"Set {set_id}",
        poster=poster,
        background=background,
        seasons=seasons,
    )


def _evidence(
    *,
    kind,
    asset_id,
):
    return PersistedArtworkEvidence(
        kind=kind,
        source=ArtworkSource.MEDIUX,
        url=(
            "https://api.mediux.pro/"
            f"assets/{asset_id}"
        ),
        provider_asset_id=asset_id,
    )


def _seed(
    *,
    episode_ids=(),
    presentation_ids=(),
):
    assets = []

    for asset_id in episode_ids:
        assets.append(
            _evidence(
                kind=(
                    ArtworkKind
                    .EPISODE_CARD
                ),
                asset_id=asset_id,
            )
        )

    presentation_kinds = (
        ArtworkKind.SHOW_POSTER,
        ArtworkKind.SHOW_BACKGROUND,
        ArtworkKind.SEASON_POSTER,
    )

    for index, asset_id in enumerate(
        presentation_ids
    ):
        assets.append(
            _evidence(
                kind=(
                    presentation_kinds[
                        min(
                            index,
                            len(
                                presentation_kinds
                            )
                            - 1,
                        )
                    ]
                ),
                asset_id=asset_id,
            )
        )

    return ShowItemStoreBootstrapSeed(
        plex_rating_key="100",
        tvdb_id=71489,
        filename=(
            "example--tvdb-71489.yaml"
        ),
        assets=tuple(
            assets
        ),
    )


def test_candidate_asset_ids_are_split_by_family():
    candidate = _candidate(
        "10",
        episode_ids=(
            "e1",
            "e2",
        ),
        presentation_ids=(
            "p1",
            "p2",
            "p3",
        ),
    )

    assert (
        mediux_candidate_family_asset_ids(
            candidate,
            family=(
                MediuxBootstrapFamily
                .EPISODE
            ),
        )
        == {
            "e1",
            "e2",
        }
    )

    assert (
        mediux_candidate_family_asset_ids(
            candidate,
            family=(
                MediuxBootstrapFamily
                .PRESENTATION
            ),
        )
        == {
            "p1",
            "p2",
            "p3",
        }
    )


def test_uniquely_matches_historical_episode_set():
    seed = _seed(
        episode_ids=(
            "e1",
            "e2",
        ),
    )

    result = (
        match_mediux_bootstrap_family(
            seed=seed,
            candidates=(
                _candidate(
                    "10",
                    episode_ids=(
                        "other",
                    ),
                ),
                _candidate(
                    "20",
                    episode_ids=(
                        "e1",
                        "e2",
                    ),
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
        is MediuxBootstrapMatchPath.MATCHED
    )
    assert result.matched
    assert not result.blocks_bootstrap
    assert (
        result.candidate_set_ids
        == ("20",)
    )
    assert (
        result.matched_set.set_id
        == "20"
    )


def test_live_set_may_have_gained_artwork():
    seed = _seed(
        episode_ids=(
            "e1",
            "e2",
        ),
    )

    result = (
        match_mediux_bootstrap_family(
            seed=seed,
            candidates=(
                _candidate(
                    "20",
                    episode_ids=(
                        "e1",
                        "e2",
                        "new-e3",
                    ),
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
        is MediuxBootstrapMatchPath.MATCHED
    )
    assert (
        result.matched_set.set_id
        == "20"
    )


def test_partial_overlap_does_not_guess():
    seed = _seed(
        episode_ids=(
            "e1",
            "e2",
        ),
    )

    result = (
        match_mediux_bootstrap_family(
            seed=seed,
            candidates=(
                _candidate(
                    "10",
                    episode_ids=(
                        "e1",
                    ),
                ),
                _candidate(
                    "20",
                    episode_ids=(
                        "e2",
                    ),
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
        is MediuxBootstrapMatchPath.UNRESOLVED
    )
    assert result.blocks_bootstrap
    assert result.matched_set is None


def test_multiple_containing_sets_are_ambiguous():
    seed = _seed(
        episode_ids=(
            "e1",
        ),
    )

    result = (
        match_mediux_bootstrap_family(
            seed=seed,
            candidates=(
                _candidate(
                    "10",
                    episode_ids=(
                        "e1",
                        "e2",
                    ),
                ),
                _candidate(
                    "20",
                    episode_ids=(
                        "e1",
                        "e3",
                    ),
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
        is MediuxBootstrapMatchPath.AMBIGUOUS
    )
    assert result.blocks_bootstrap
    assert (
        result.candidate_set_ids
        == (
            "10",
            "20",
        )
    )
    assert result.matched_set is None


def test_no_mediux_evidence_needs_no_match():
    seed = _seed()

    result = (
        match_mediux_bootstrap_family(
            seed=seed,
            candidates=(),
            family=(
                MediuxBootstrapFamily
                .EPISODE
            ),
        )
    )

    assert (
        result.path
        is MediuxBootstrapMatchPath.NO_EVIDENCE
    )
    assert not result.blocks_bootstrap
    assert result.matched_set is None


def test_episode_and_presentation_sets_recover_independently():
    seed = _seed(
        episode_ids=(
            "episode-a",
        ),
        presentation_ids=(
            "poster-b",
        ),
    )

    episode, presentation = (
        match_mediux_bootstrap_families(
            seed=seed,
            candidates=(
                _candidate(
                    "episode-set",
                    episode_ids=(
                        "episode-a",
                    ),
                ),
                _candidate(
                    "presentation-set",
                    presentation_ids=(
                        "poster-b",
                    ),
                ),
            ),
        )
    )

    assert (
        episode.path
        is MediuxBootstrapMatchPath.MATCHED
    )
    assert (
        episode.matched_set.set_id
        == "episode-set"
    )

    assert (
        presentation.path
        is MediuxBootstrapMatchPath.MATCHED
    )
    assert (
        presentation.matched_set.set_id
        == "presentation-set"
    )


def test_non_mediux_candidate_cannot_match():
    seed = _seed(
        episode_ids=(
            "e1",
        ),
    )

    result = (
        match_mediux_bootstrap_family(
            seed=seed,
            candidates=(
                _candidate(
                    "10",
                    episode_ids=(
                        "e1",
                    ),
                    provider=(
                        ArtworkSource.TMDB
                    ),
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
        is MediuxBootstrapMatchPath.UNRESOLVED
    )
