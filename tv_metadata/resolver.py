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

        def episode_date(
            episode,
        ):
            if episode.air_date is not None:
                return episode.air_date

            if episode.air_datetime is not None:
                return episode.air_datetime.date()

            return None

        def next_episode_is_corroborated(
            provider_name,
            candidate,
        ):
            candidate_date = episode_date(
                candidate
            )

            if candidate_date is None:
                return False

            for other_name in (
                self.next_episode_order
            ):
                if other_name == provider_name:
                    continue

                other = get_result(
                    other_name
                )

                if (
                    other is None
                    or not other.matched
                    or other.next_episode
                    is None
                ):
                    continue

                if (
                    episode_date(
                        other.next_episode
                    )
                    == candidate_date
                ):
                    return True

            return False

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

            candidate = result.next_episode

            requires_corroboration = (
                lifecycle
                is ShowLifecycle.ENDED
                and result.lifecycle
                is ShowLifecycle.ENDED
            )

            if (
                requires_corroboration
                and not next_episode_is_corroborated(
                    provider_name,
                    candidate,
                )
            ):
                warnings.append(
                    "resolver:"
                    "rejected_unconfirmed_ended_next:"
                    f"{result.source}"
                )
                continue

            next_episode = candidate
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
