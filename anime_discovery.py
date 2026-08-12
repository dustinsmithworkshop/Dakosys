#!/usr/bin/env python3
from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

import mappings_manager


logger = logging.getLogger("anime_discovery")


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
