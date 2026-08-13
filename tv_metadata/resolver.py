"""Field-aware TV metadata provider resolver."""

from __future__ import annotations

from collections.abc import Sequence

from .models import (
    ShowIdentity,
    ShowLifecycle,
    ShowStatus,
)
from .providers import TVMetadataProvider


DEFAULT_LIFECYCLE_ORDER = (
    "tmdb",
    "sonarr",
    "tvmaze",
)

DEFAULT_NEXT_EPISODE_ORDER = (
    "sonarr",
    "tmdb",
    "tvmaze",
)


class TVMetadataResolver:
    """Resolve lifecycle and next episode independently.

    Lifecycle precedence:
        TMDB -> Sonarr -> TVmaze

    Next-episode precedence:
        Sonarr -> TMDB -> TVmaze

    Each provider is called at most once per show.
    """

    def __init__(
        self,
        providers: Sequence[
            TVMetadataProvider
        ],
        *,
        lifecycle_order: Sequence[str] = (
            DEFAULT_LIFECYCLE_ORDER
        ),
        next_episode_order: Sequence[str] = (
            DEFAULT_NEXT_EPISODE_ORDER
        ),
    ) -> None:
        self.providers = tuple(providers)

        self._providers_by_name = {
            provider.name: provider
            for provider in self.providers
        }

        self.lifecycle_order = tuple(
            lifecycle_order
        )

        self.next_episode_order = tuple(
            next_episode_order
        )

    def resolve(
        self,
        identity: ShowIdentity,
    ) -> ShowStatus:
        results = {}
        warnings: list[str] = []

        def get_result(
            provider_name: str,
        ):
            if provider_name in results:
                return results[
                    provider_name
                ]

            provider = (
                self._providers_by_name.get(
                    provider_name
                )
            )

            if provider is None:
                return None

            result = provider.get_metadata(
                identity
            )

            results[
                provider_name
            ] = result

            if result.matched:
                for warning in (
                    result.warnings
                ):
                    warnings.append(
                        f"{result.source}:"
                        f"{warning}"
                    )

            return result

        lifecycle = ShowLifecycle.UNKNOWN
        lifecycle_source = None

        for provider_name in (
            self.lifecycle_order
        ):
            result = get_result(
                provider_name
            )

            if (
                result is None
                or not result.matched
                or result.lifecycle
                is ShowLifecycle.UNKNOWN
            ):
                continue

            lifecycle = result.lifecycle
            lifecycle_source = (
                result.source
            )
            break

        next_episode = None

        for provider_name in (
            self.next_episode_order
        ):
            result = get_result(
                provider_name
            )

            if (
                result is None
                or not result.matched
                or result.next_episode
                is None
            ):
                continue

            next_episode = (
                result.next_episode
            )
            break

        if (
            lifecycle
            is ShowLifecycle.ENDED
            and next_episode is not None
        ):
            warnings.append(
                "resolver:"
                "ended_with_next_episode"
            )

        return ShowStatus(
            lifecycle=lifecycle,
            lifecycle_source=(
                lifecycle_source
            ),
            next_episode=next_episode,
            warnings=tuple(warnings),
        )
