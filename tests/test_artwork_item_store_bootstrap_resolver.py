from types import SimpleNamespace

import pytest

from artwork.item_store_bootstrap import (
    PersistedArtworkEvidence,
    ShowItemStoreBootstrapSeed,
)
from artwork.item_store_bootstrap_match import (
    MediuxBootstrapFamily,
)
from artwork.item_store_bootstrap_resolver import (
    ArtworkItemStoreBootstrapResolutionError,
    BootstrapRecoverySource,
    resolve_show_item_store_bootstrap,
)
from artwork.models import (
    ArtworkAsset,
    ArtworkKind,
    ArtworkSet,
    ArtworkSource,
    EpisodeArtwork,
    SeasonArtwork,
    ShowArtworkState,
)


def _mediux_url(
    asset_id,
):
    return (
        "https://api.mediux.pro/"
        f"assets/{asset_id}"
    )


def _mediux_asset(
    *,
    kind,
    asset_id,
):
    return ArtworkAsset(
        kind=kind,
        source=ArtworkSource.MEDIUX,
        url=_mediux_url(
            asset_id
        ),
        provider_asset_id=asset_id,
    )


def _evidence(
    *,
    kind,
    source,
    asset_id,
    season=None,
    episode=None,
):
    if source is ArtworkSource.MEDIUX:
        url = _mediux_url(
            asset_id
        )

    else:
        url = (
            "https://image.tmdb.org/"
            "t/p/original"
            f"{asset_id}"
        )

    return PersistedArtworkEvidence(
        kind=kind,
        source=source,
        url=url,
        provider_asset_id=asset_id,
        season_number=season,
        episode_number=episode,
    )


def _seed(
    *,
    assets,
    rating_key="10",
    tvdb_id=100,
):
    return ShowItemStoreBootstrapSeed(
        plex_rating_key=rating_key,
        tvdb_id=tvdb_id,
        filename="example.yaml",
        assets=tuple(
            assets
        ),
    )


def _inventory(
    *,
    rating_key="10",
    tvdb_id=100,
):
    return SimpleNamespace(
        identity=SimpleNamespace(
            library="TV",
            plex_rating_key=(
                rating_key
            ),
            title="Example Show",
            year=2020,
            tvdb_id=tvdb_id,
            tmdb_id=200,
            imdb_id="tt0000200",
        ),
        seasons=(),
    )


def _candidate(
    set_id,
    *,
    episode_ids=(),
    presentation_ids=(),
):
    seasons = {}

    season = SeasonArtwork(
        season_number=1,
    )

    for number, asset_id in enumerate(
        episode_ids,
        start=1,
    ):
        season.episodes[
            number
        ] = EpisodeArtwork(
            episode_number=number,
            card=_mediux_asset(
                kind=(
                    ArtworkKind
                    .EPISODE_CARD
                ),
                asset_id=asset_id,
            ),
        )

    presentation_ids = list(
        presentation_ids
    )

    poster = None
    background = None

    if presentation_ids:
        poster = _mediux_asset(
            kind=(
                ArtworkKind
                .SHOW_POSTER
            ),
            asset_id=(
                presentation_ids.pop(
                    0
                )
            ),
        )

    if presentation_ids:
        background = _mediux_asset(
            kind=(
                ArtworkKind
                .SHOW_BACKGROUND
            ),
            asset_id=(
                presentation_ids.pop(
                    0
                )
            ),
        )

    if presentation_ids:
        season.poster = _mediux_asset(
            kind=(
                ArtworkKind
                .SEASON_POSTER
            ),
            asset_id=(
                presentation_ids.pop(
                    0
                )
            ),
        )

    if (
        season.episodes
        or season.poster is not None
    ):
        seasons[1] = season

    return ArtworkSet(
        provider=ArtworkSource.MEDIUX,
        set_id=set_id,
        creator=f"creator-{set_id}",
        title=f"Set {set_id}",
        poster=poster,
        background=background,
        seasons=seasons,
    )


class FakeProvider:
    def __init__(
        self,
        candidates=(),
        error=None,
    ):
        self.candidates = tuple(
            candidates
        )
        self.error = error
        self.requests = []

    def find_sets(
        self,
        request,
    ):
        self.requests.append(
            request
        )

        if self.error is not None:
            raise self.error

        return list(
            self.candidates
        )


def _legacy_state(
    *,
    set_id,
    episode_ids=(),
    tvdb_id=100,
):
    season = SeasonArtwork(
        season_number=1,
        episodes={
            number: EpisodeArtwork(
                episode_number=number,
                card=_mediux_asset(
                    kind=(
                        ArtworkKind
                        .EPISODE_CARD
                    ),
                    asset_id=asset_id,
                ),
            )
            for number, asset_id
            in enumerate(
                episode_ids,
                start=1,
            )
        },
    )

    return ShowArtworkState(
        title="Example Show",
        tvdb_id=tvdb_id,
        seasons={
            1: season,
        },
        selected_set_id=set_id,
        selected_set_source=(
            ArtworkSource.MEDIUX
        ),
        selected_creator=(
            f"creator-{set_id}"
        ),
    )


def test_recovers_episode_and_presentation_independently():
    seed = _seed(
        assets=(
            _evidence(
                kind=(
                    ArtworkKind
                    .EPISODE_CARD
                ),
                source=(
                    ArtworkSource.MEDIUX
                ),
                asset_id="episode",
                season=1,
                episode=1,
            ),
            _evidence(
                kind=(
                    ArtworkKind
                    .SHOW_POSTER
                ),
                source=(
                    ArtworkSource.MEDIUX
                ),
                asset_id="poster",
            ),
        )
    )

    provider = FakeProvider(
        (
            _candidate(
                "EPISODES",
                episode_ids=(
                    "episode",
                ),
            ),
            _candidate(
                "PRESENTATION",
                presentation_ids=(
                    "poster",
                ),
            ),
        )
    )

    result = (
        resolve_show_item_store_bootstrap(
            seeds=(seed,),
            inventories=(
                _inventory(),
            ),
            provider=provider,
        )
    )

    assert (
        result.provider_request_count
        == 1
    )

    assert len(
        provider.requests
    ) == 1

    state = result.states[0]

    assert (
        state
        .episode_selection
        .set_id
        == "EPISODES"
    )

    assert (
        state
        .presentation_selection
        .set_id
        == "PRESENTATION"
    )

    assert (
        state.selected_set_id
        == "EPISODES"
    )

    assert (
        result.recovery_count(
            family=(
                MediuxBootstrapFamily
                .EPISODE
            ),
            source=(
                BootstrapRecoverySource
                .CURRENT_PROVIDER
            ),
        )
        == 1
    )

    assert (
        result.recovery_count(
            family=(
                MediuxBootstrapFamily
                .PRESENTATION
            ),
            source=(
                BootstrapRecoverySource
                .CURRENT_PROVIDER
            ),
        )
        == 1
    )


def test_historical_witness_recovers_membership_drift():
    seed = _seed(
        assets=(
            _evidence(
                kind=(
                    ArtworkKind
                    .EPISODE_CARD
                ),
                source=(
                    ArtworkSource.MEDIUX
                ),
                asset_id="old-a",
                season=1,
                episode=1,
            ),
            _evidence(
                kind=(
                    ArtworkKind
                    .EPISODE_CARD
                ),
                source=(
                    ArtworkSource.MEDIUX
                ),
                asset_id="old-b",
                season=1,
                episode=2,
            ),
        )
    )

    provider = FakeProvider(
        (
            _candidate(
                "CURRENT-A",
                episode_ids=(
                    "old-a",
                ),
            ),
            _candidate(
                "CURRENT-B",
                episode_ids=(
                    "old-b",
                ),
            ),
        )
    )

    result = (
        resolve_show_item_store_bootstrap(
            seeds=(seed,),
            inventories=(
                _inventory(),
            ),
            provider=provider,
            legacy_states=(
                _legacy_state(
                    set_id="HISTORICAL",
                    episode_ids=(
                        "old-a",
                        "old-b",
                    ),
                ),
            ),
        )
    )

    state = result.states[0]

    assert (
        state
        .episode_selection
        .set_id
        == "HISTORICAL"
    )

    assert (
        result.recovery_count(
            family=(
                MediuxBootstrapFamily
                .EPISODE
            ),
            source=(
                BootstrapRecoverySource
                .HISTORICAL_WITNESS
            ),
        )
        == 1
    )


def test_unproven_mediux_identity_blocks():
    seed = _seed(
        assets=(
            _evidence(
                kind=(
                    ArtworkKind
                    .EPISODE_CARD
                ),
                source=(
                    ArtworkSource.MEDIUX
                ),
                asset_id="old-a",
                season=1,
                episode=1,
            ),
            _evidence(
                kind=(
                    ArtworkKind
                    .EPISODE_CARD
                ),
                source=(
                    ArtworkSource.MEDIUX
                ),
                asset_id="old-b",
                season=1,
                episode=2,
            ),
        )
    )

    provider = FakeProvider(
        (
            _candidate(
                "PARTIAL",
                episode_ids=(
                    "old-a",
                ),
            ),
        )
    )

    with pytest.raises(
        ArtworkItemStoreBootstrapResolutionError,
        match="could not prove",
    ):
        resolve_show_item_store_bootstrap(
            seeds=(seed,),
            inventories=(
                _inventory(),
            ),
            provider=provider,
        )


def test_tmdb_only_state_needs_no_provider_request():
    seed = _seed(
        assets=(
            _evidence(
                kind=(
                    ArtworkKind
                    .EPISODE_CARD
                ),
                source=(
                    ArtworkSource.TMDB
                ),
                asset_id="/still.jpg",
                season=1,
                episode=1,
            ),
        )
    )

    provider = FakeProvider(
        error=AssertionError(
            "provider must not be called"
        )
    )

    result = (
        resolve_show_item_store_bootstrap(
            seeds=(seed,),
            inventories=(
                _inventory(),
            ),
            provider=provider,
        )
    )

    assert (
        result.provider_request_count
        == 0
    )

    assert provider.requests == []

    state = result.states[0]

    assert (
        state.seasons[
            1
        ].episodes[
            1
        ].card.source
        is ArtworkSource.TMDB
    )

    assert state.episode_selection is None
    assert (
        state.presentation_selection
        is None
    )

    assert (
        result.recovery_count(
            family=(
                MediuxBootstrapFamily
                .EPISODE
            ),
            source=(
                BootstrapRecoverySource
                .NO_EVIDENCE
            ),
        )
        == 1
    )


def test_provider_failure_blocks_bootstrap():
    seed = _seed(
        assets=(
            _evidence(
                kind=(
                    ArtworkKind
                    .EPISODE_CARD
                ),
                source=(
                    ArtworkSource.MEDIUX
                ),
                asset_id="episode",
                season=1,
                episode=1,
            ),
        )
    )

    provider = FakeProvider(
        error=RuntimeError(
            "temporary failure"
        )
    )

    with pytest.raises(
        ArtworkItemStoreBootstrapResolutionError,
        match="primary provider failed",
    ):
        resolve_show_item_store_bootstrap(
            seeds=(seed,),
            inventories=(
                _inventory(),
            ),
            provider=provider,
        )


def test_manifest_owned_show_missing_from_plex_blocks():
    seed = _seed(
        assets=()
    )

    with pytest.raises(
        ArtworkItemStoreBootstrapResolutionError,
        match="missing from current Plex",
    ):
        resolve_show_item_store_bootstrap(
            seeds=(seed,),
            inventories=(),
            provider=FakeProvider(),
        )
