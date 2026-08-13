"""Field-aware TV metadata provider resolver."""

from __future__ import annotations

from collections.abc import Sequence

from .models import (
    ShowIdentity,
    ShowLifecycle,
    ShowStatus,
)
from .providers import TVMetadataProvider


class TVMetadataResolver:
    """Resolve TV metadata across ordered providers.

    Provider order expresses precedence.

    Lifecycle:
    - first matched provider with a known lifecycle wins
    - later providers never override it

    Next episode:
    - first matched provider with a next episode wins
    - fallback providers may supplement a lifecycle result
      that has no upcoming episode

    Resolution stops when:
    - an authoritative lifecycle is ENDED, or
    - both lifecycle and next episode are resolved, or
    - all providers are exhausted
    """

    def __init__(
        self,
        providers: Sequence[
            TVMetadataProvider
        ],
    ) -> None:
        self.providers = tuple(providers)

    def resolve(
        self,
        identity: ShowIdentity,
    ) -> ShowStatus:
        lifecycle = ShowLifecycle.UNKNOWN
        lifecycle_source: str | None = None

        next_episode = None

        warnings: list[str] = []

        for provider in self.providers:
            result = provider.get_metadata(
                identity
            )

            if not result.matched:
                continue

            for warning in result.warnings:
                warnings.append(
                    f"{result.source}:"
                    f"{warning}"
                )

            if (
                lifecycle
                is ShowLifecycle.UNKNOWN
                and result.lifecycle
                is not ShowLifecycle.UNKNOWN
            ):
                lifecycle = result.lifecycle
                lifecycle_source = (
                    result.source
                )

            if (
                next_episode is None
                and result.next_episode
                is not None
            ):
                next_episode = (
                    result.next_episode
                )

            # A higher-priority provider that
            # definitively says the show has ended
            # is authoritative. Do not search lower
            # priority providers for future episodes.
            if (
                lifecycle
                is ShowLifecycle.ENDED
            ):
                next_episode = None
                break

            # Both independently resolvable fields
            # are now satisfied.
            if (
                lifecycle
                is not ShowLifecycle.UNKNOWN
                and next_episode is not None
            ):
                break

        return ShowStatus(
            lifecycle=lifecycle,
            lifecycle_source=(
                lifecycle_source
            ),
            next_episode=next_episode,
            warnings=tuple(warnings),
        )
