from artwork.identity_enrichment import (
    IdentityEnrichmentPath,
    enrich_show_inventory_tvdb,
)
from artwork.inventory import (
    SeasonInventory,
    ShowInventory,
)
from artwork.providers.tmdb import (
    TMDBTVExternalIds,
)
from tv_metadata.models import (
    ShowIdentity,
)


class FakeTMDBClient:
    def __init__(
        self,
        *,
        external=None,
        error=None,
    ):
        self.external = (
            external
            if external is not None
            else TMDBTVExternalIds()
        )
        self.error = error
        self.requests = []

    def get_tv_external_ids(
        self,
        *,
        tmdb_id,
    ):
        self.requests.append(
            tmdb_id
        )

        if self.error is not None:
            raise self.error

        return self.external


def _inventory(
    *,
    tvdb_id=None,
    tmdb_id=39980,
    imdb_id="tt1138300",
):
    return ShowInventory(
        identity=ShowIdentity(
            title="Digimon Data Squad",
            year=2006,
            library="Cartoons",
            plex_rating_key="52789",
            tmdb_id=tmdb_id,
            tvdb_id=tvdb_id,
            imdb_id=imdb_id,
            library_roles=(
                "cartoons",
            ),
        ),
        seasons=(
            SeasonInventory(
                season_number=1,
                episode_numbers=frozenset(
                    {
                        1,
                        2,
                        3,
                    }
                ),
            ),
        ),
    )


def test_existing_tvdb_identity_needs_no_enrichment():
    inventory = _inventory(
        tvdb_id=339733,
    )

    client = FakeTMDBClient()

    result = enrich_show_inventory_tvdb(
        inventory=inventory,
        tmdb_client=client,
    )

    assert (
        result.path
        is IdentityEnrichmentPath.ALREADY_COMPLETE
    )

    assert result.inventory is inventory
    assert result.provider_requested is False
    assert client.requests == []


def test_missing_tmdb_identity_cannot_be_enriched():
    inventory = _inventory(
        tmdb_id=None,
        imdb_id="tt1138300",
    )

    client = FakeTMDBClient()

    result = enrich_show_inventory_tvdb(
        inventory=inventory,
        tmdb_client=client,
    )

    assert (
        result.path
        is IdentityEnrichmentPath.NO_TMDB_ID
    )

    assert result.inventory is inventory
    assert result.provider_requested is False
    assert client.requests == []


def test_exact_tmdb_bridge_recovers_tvdb_identity():
    inventory = _inventory()

    client = FakeTMDBClient(
        external=TMDBTVExternalIds(
            tvdb_id=339733,
            imdb_id="tt1138300",
        )
    )

    result = enrich_show_inventory_tvdb(
        inventory=inventory,
        tmdb_client=client,
    )

    assert (
        result.path
        is IdentityEnrichmentPath.ENRICHED
    )

    assert result.enriched is True
    assert result.provider_requested is True
    assert client.requests == [
        39980,
    ]

    identity = result.inventory.identity

    assert identity.title == "Digimon Data Squad"
    assert identity.year == 2006
    assert identity.library == "Cartoons"
    assert identity.plex_rating_key == "52789"

    assert identity.tmdb_id == 39980
    assert identity.tvdb_id == 339733
    assert identity.imdb_id == "tt1138300"

    assert identity.library_roles == (
        "cartoons",
    )

    assert identity.tmdb_id_candidates == (
        39980,
    )

    assert identity.tvdb_id_candidates == (
        339733,
    )

    assert identity.imdb_id_candidates == (
        "tt1138300",
    )

    assert (
        result.inventory.seasons
        == inventory.seasons
    )


def test_enrichment_can_adopt_tmdb_imdb_when_plex_has_none():
    inventory = _inventory(
        imdb_id=None,
    )

    client = FakeTMDBClient(
        external=TMDBTVExternalIds(
            tvdb_id=339733,
            imdb_id="tt1138300",
        )
    )

    result = enrich_show_inventory_tvdb(
        inventory=inventory,
        tmdb_client=client,
    )

    assert (
        result.path
        is IdentityEnrichmentPath.ENRICHED
    )

    assert (
        result.inventory.identity.tvdb_id
        == 339733
    )

    assert (
        result.inventory.identity.imdb_id
        == "tt1138300"
    )


def test_imdb_conflict_blocks_identity_enrichment():
    inventory = _inventory(
        imdb_id="tt1138300",
    )

    client = FakeTMDBClient(
        external=TMDBTVExternalIds(
            tvdb_id=339733,
            imdb_id="tt9999999",
        )
    )

    result = enrich_show_inventory_tvdb(
        inventory=inventory,
        tmdb_client=client,
    )

    assert (
        result.path
        is IdentityEnrichmentPath.IMDB_CONFLICT
    )

    assert result.enriched is False
    assert result.provider_requested is True

    assert (
        result.inventory.identity.tvdb_id
        is None
    )


def test_missing_tmdb_tvdb_result_stays_unresolved():
    inventory = _inventory()

    client = FakeTMDBClient(
        external=TMDBTVExternalIds(
            tvdb_id=None,
            imdb_id="tt1138300",
        )
    )

    result = enrich_show_inventory_tvdb(
        inventory=inventory,
        tmdb_client=client,
    )

    assert (
        result.path
        is IdentityEnrichmentPath.NO_TVDB_RESULT
    )

    assert result.enriched is False
    assert result.provider_requested is True

    assert (
        result.inventory.identity.tvdb_id
        is None
    )


def test_provider_failure_stays_unresolved():
    inventory = _inventory()

    client = FakeTMDBClient(
        error=RuntimeError(
            "TMDB unavailable"
        )
    )

    result = enrich_show_inventory_tvdb(
        inventory=inventory,
        tmdb_client=client,
    )

    assert (
        result.path
        is IdentityEnrichmentPath.PROVIDER_ERROR
    )

    assert result.enriched is False
    assert result.provider_requested is True
    assert result.error_type == "RuntimeError"
    assert (
        result.error_message
        == "TMDB unavailable"
    )

    assert (
        result.inventory.identity.tvdb_id
        is None
    )
