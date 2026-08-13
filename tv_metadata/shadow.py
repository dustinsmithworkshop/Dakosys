"""Comparison helpers for TV metadata shadow-mode audits."""

from __future__ import annotations

import re
from typing import Any


_DATE_PATTERN = re.compile(
    r"(?<!\d)(\d{2}/\d{2})(?!\d)"
)


def presented_date(
    info: dict[str, Any] | None,
) -> str | None:
    """Extract the rendered DD/MM or MM/DD date from legacy show info."""
    if not info:
        return None

    text = str(
        info.get("text_content")
        or ""
    )

    match = _DATE_PATTERN.search(text)

    if match is None:
        return None

    return match.group(1)


def normalized_status_type(
    info: dict[str, Any] | None,
) -> str | None:
    """Normalize presentation statuses for migration comparison."""
    if not info:
        return None

    raw = info.get("status_type")

    if not raw:
        return None

    value = str(raw).upper()

    # The provider architecture intentionally collapses
    # canceled/ended into one terminal lifecycle.
    if value == "CANCELLED":
        return "ENDED"

    return value


def compare_presentations(
    legacy_info: dict[str, Any] | None,
    provider_info: dict[str, Any] | None,
) -> str:
    """Classify one legacy-Trakt vs provider presentation comparison."""
    if legacy_info is None and provider_info is None:
        return "BOTH_NONE"

    if legacy_info is None:
        return "PROVIDER_ONLY"

    if provider_info is None:
        return "LEGACY_ONLY"

    legacy_status = normalized_status_type(
        legacy_info
    )
    provider_status = normalized_status_type(
        provider_info
    )

    legacy_date = presented_date(
        legacy_info
    )
    provider_date = presented_date(
        provider_info
    )

    status_matches = (
        legacy_status == provider_status
    )

    date_matches = (
        legacy_date == provider_date
    )

    if status_matches and date_matches:
        return "MATCH"

    if status_matches:
        return "DATE_DIFFERS"

    if date_matches:
        return "STATUS_DIFFERS"

    return "STATUS_AND_DATE_DIFFER"
