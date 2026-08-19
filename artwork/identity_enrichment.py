"""Exact identity enrichment for Artwork Manager inventories."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from artwork.inventory import (
    ShowInventory,
)
from artwork.providers.tmdb import (
    TMDBArtworkClient,
)
from tv_metadata.models import (
    ShowIdentity,
)


class IdentityEnrichmentPath(
    str,
    Enum,
):
    ALREADY_COMPLETE = "already_complete"
    ENRICHED = "enriched"
    NO_TMDB_ID = "no_tmdb_id"
    NO_TVDB_RESULT = "no_tvdb_result"
    IMDB_CONFLICT = "imdb_conflict"
    PROVIDER_ERROR = "provider_error"


@dataclass(frozen=True)
class ShowIdentityEnrichment:
    inventory: ShowInventory
    path: IdentityEnrichmentPath

    provider_requested: bool = False

    error_type: str | None = None
    error_message: str | None = None

    @property
    def enriched(self) -> bool:
        return (
            self.path
            is IdentityEnrichmentPath.ENRICHED
        )


def enrich_show_inventory_tvdb(
    *,
    inventory: ShowInventory,
    tmdb_client: TMDBArtworkClient,
) -> ShowIdentityEnrichment:
    """Recover missing TVDB identity through an exact TMDB series ID.

    No title search or fuzzy matching is performed.

    When Plex and TMDB both supply IMDb identity, a disagreement blocks
    enrichment rather than guessing.
    """

    identity = inventory.identity

    if identity.tvdb_id is not None:
        return ShowIdentityEnrichment(
            inventory=inventory,
            path=(
                IdentityEnrichmentPath
                .ALREADY_COMPLETE
            ),
        )

    if identity.tmdb_id is None:
        return ShowIdentityEnrichment(
            inventory=inventory,
            path=(
                IdentityEnrichmentPath
                .NO_TMDB_ID
            ),
        )

    try:
        external = (
            tmdb_client.get_tv_external_ids(
                tmdb_id=identity.tmdb_id,
            )
        )

    except Exception as exc:
        return ShowIdentityEnrichment(
            inventory=inventory,
            path=(
                IdentityEnrichmentPath
                .PROVIDER_ERROR
            ),
            provider_requested=True,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )

    if external.tvdb_id is None:
        return ShowIdentityEnrichment(
            inventory=inventory,
            path=(
                IdentityEnrichmentPath
                .NO_TVDB_RESULT
            ),
            provider_requested=True,
        )

    if (
        identity.imdb_id
        and external.imdb_id
        and identity.imdb_id.casefold()
        != external.imdb_id.casefold()
    ):
        return ShowIdentityEnrichment(
            inventory=inventory,
            path=(
                IdentityEnrichmentPath
                .IMDB_CONFLICT
            ),
            provider_requested=True,
        )

    tmdb_id_candidates = list(
        getattr(
            identity,
            "tmdb_id_candidates",
            (),
        )
        or ()
    )

    if (
        identity.tmdb_id is not None
        and identity.tmdb_id
        not in tmdb_id_candidates
    ):
        tmdb_id_candidates.insert(
            0,
            identity.tmdb_id,
        )

    tvdb_id_candidates = list(
        getattr(
            identity,
            "tvdb_id_candidates",
            (),
        )
        or ()
    )

    if (
        external.tvdb_id
        not in tvdb_id_candidates
    ):
        tvdb_id_candidates.append(
            external.tvdb_id
        )

    imdb_id_candidates = list(
        getattr(
            identity,
            "imdb_id_candidates",
            (),
        )
        or ()
    )

    if (
        identity.imdb_id
        and identity.imdb_id
        not in imdb_id_candidates
    ):
        imdb_id_candidates.insert(
            0,
            identity.imdb_id,
        )

    if (
        external.imdb_id
        and external.imdb_id
        not in imdb_id_candidates
    ):
        imdb_id_candidates.append(
            external.imdb_id
        )

    enriched_identity = ShowIdentity(
        title=identity.title,
        year=identity.year,
        library=identity.library,
        plex_rating_key=(
            identity.plex_rating_key
        ),
        tmdb_id=identity.tmdb_id,
        tvdb_id=external.tvdb_id,
        imdb_id=(
            identity.imdb_id
            or external.imdb_id
        ),
        library_roles=(
            getattr(
                identity,
                "library_roles",
                (),
            )
            or ()
        ),
        tmdb_id_candidates=tuple(
            tmdb_id_candidates
        ),
        tvdb_id_candidates=tuple(
            tvdb_id_candidates
        ),
        imdb_id_candidates=tuple(
            imdb_id_candidates
        ),
    )

    return ShowIdentityEnrichment(
        inventory=ShowInventory(
            identity=enriched_identity,
            seasons=inventory.seasons,
        ),
        path=(
            IdentityEnrichmentPath
            .ENRICHED
        ),
        provider_requested=True,
    )
