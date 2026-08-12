#!/usr/bin/env python3
from __future__ import annotations

import logging

import requests
from bs4 import BeautifulSoup
from collections.abc import Iterable
from typing import Any

import mappings_manager


logger = logging.getLogger("anime_discovery")


AFL_SHOWS_URL = "https://www.animefillerlist.com/shows"


def get_afl_catalog() -> list[str]:
    """
    Return the current AnimeFillerList show slugs.

    Catalog membership is discovery input only. Valid historical AFL pages may
    be supplemented later by known Dakosys mapping identities.
    """

    response = requests.get(
        AFL_SHOWS_URL,
        timeout=30,
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    slugs = {
        href[len("/shows/"):].strip("/")
        for link in soup.find_all("a", href=True)
        if (
            (href := str(link.get("href") or "")).startswith("/shows/")
            and href[len("/shows/"):].strip("/")
        )
    }

    if not slugs:
        raise RuntimeError(
            "No AnimeFillerList entries could be discovered."
        )

    return sorted(slugs)


# These mapping sections are keyed by the canonical Dakosys anime identity.
#
# A key appearing here does NOT make the anime trusted. It only nominates the
# identity for discovery. Plex resolution and AnimeFillerList identity
# validation still decide whether the candidate is usable.
DISCOVERY_MAPPING_SECTIONS = (
    "mappings",
    "tvdb_mappings",
    "trakt_mappings",
    "title_mappings",
    "afl_mappings",
    "afl_identity_aliases",
)


def _clean_identity(value: Any) -> str:
    return str(value or "").strip()


def build_discovery_candidates(
    afl_catalog: Iterable[str],
    *,
    mappings_data: dict[str, Any] | None = None,
) -> list[str]:
    """
    Build the complete set of Dakosys anime identities worth validating.

    AnimeFillerList's current /shows catalog is not authoritative: valid
    historical show pages may remain accessible after disappearing from the
    catalog. Known Dakosys mapping keys therefore supplement the live catalog.

    This function performs candidate discovery only. It does not validate Plex
    ownership or AnimeFillerList page identity.
    """

    candidates = {
        identity
        for item in afl_catalog
        if (identity := _clean_identity(item))
    }

    if mappings_data is None:
        try:
            mappings_data = mappings_manager.load_mappings() or {}
        except Exception as exc:
            logger.warning(
                "Could not load mappings while building anime discovery "
                "candidates: %s",
                exc,
            )
            mappings_data = {}

    for section_name in DISCOVERY_MAPPING_SECTIONS:
        section = mappings_data.get(section_name, {}) or {}

        if not isinstance(section, dict):
            logger.warning(
                "Ignoring non-mapping %s section during anime discovery",
                section_name,
            )
            continue

        for key in section:
            identity = _clean_identity(key)
            if identity:
                candidates.add(identity)

    ignored = {
        identity.lower()
        for item in (mappings_data.get("afl_ignored", []) or [])
        if (identity := _clean_identity(item))
    }

    candidates = {
        identity
        for identity in candidates
        if identity.lower() not in ignored
    }

    return sorted(candidates)
