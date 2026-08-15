"""Artwork Manager read-only service orchestration.

This module connects Plex discovery, inventory, reconciliation, and
planning without contacting artwork providers or writing output files.

Library names are supplied by discovered ArtworkTarget objects. Dakosys
does not assign special meaning to names such as TV, Anime, or Movies.
"""

from __future__ import annotations

from collections.abc import (
    Iterable,
    Mapping,
)
from dataclasses import dataclass
from enum import Enum

from artwork.inventory import build_show_inventory
from artwork.models import ShowArtworkState
from artwork.planner import (
    PlanAction,
    TargetPlan,
    build_target_plan,
)
from artwork.reconciliation import (
    reconcile_show_target,
)
from artwork.targets import (
    ArtworkTarget,
    MediaType,
)


class TargetSkipReason(str, Enum):
    """Why a discovered target was not planned."""

    MOVIE_SUPPORT_PENDING = (
        "movie_support_pending"
    )


@dataclass(frozen=True)
class SkippedArtworkTarget:
    """A discovered Plex target not yet supported by the planner."""

    target: ArtworkTarget
    reason: TargetSkipReason


@dataclass(frozen=True)
class ArtworkServicePlan:
    """Combined read-only Artwork Manager plan."""

    plans: tuple[TargetPlan, ...]
    skipped: tuple[SkippedArtworkTarget, ...]

    @property
    def planned_target_count(self) -> int:
        return len(self.plans)

    @property
    def skipped_target_count(self) -> int:
        return len(self.skipped)

    @property
    def target_count(self) -> int:
        return (
            self.planned_target_count
            + self.skipped_target_count
        )

    @property
    def item_count(self) -> int:
        return sum(
            plan.item_count
            for plan in self.plans
        )

    @property
    def stable_count(self) -> int:
        return sum(
            plan.stable_count
            for plan in self.plans
        )

    @property
    def provider_search_count(self) -> int:
        return sum(
            plan.provider_search_count
            for plan in self.plans
        )

    @property
    def identity_review_count(self) -> int:
        return sum(
            plan.identity_review_count
            for plan in self.plans
        )

    @property
    def ambiguity_review_count(self) -> int:
        return sum(
            plan.ambiguity_review_count
            for plan in self.plans
        )

    @property
    def orphan_review_count(self) -> int:
        return sum(
            plan.orphan_review_count
            for plan in self.plans
        )

    def plan_for_library(
        self,
        library: str,
    ) -> TargetPlan | None:
        """Return the plan for one Plex library."""

        for plan in self.plans:
            if (
                plan.target.library
                == library
            ):
                return plan

        return None


def build_artwork_service_plan(
    *,
    plex,
    targets: Iterable[ArtworkTarget],
    managed_by_library: Mapping[
        str,
        Iterable[ShowArtworkState],
    ] | None = None,
) -> ArtworkServicePlan:
    """Build a complete read-only plan for discovered Plex targets.

    Show libraries are scanned and reconciled.

    Movie libraries are reported as skipped until the movie artwork
    model is implemented.

    Existing managed state is keyed by exact Plex library name. The
    service does not infer library roles from names.
    """

    target_list = tuple(
        targets
    )

    target_libraries = [
        target.library
        for target in target_list
    ]

    duplicate_libraries = sorted(
        {
            library
            for library in target_libraries
            if target_libraries.count(
                library
            ) > 1
        }
    )

    if duplicate_libraries:
        formatted = ", ".join(
            repr(library)
            for library
            in duplicate_libraries
        )

        raise ValueError(
            "duplicate Artwork Manager target "
            f"libraries: {formatted}"
        )

    managed = {
        library: tuple(states)
        for library, states
        in (
            managed_by_library
            or {}
        ).items()
    }

    unknown_managed = sorted(
        set(managed)
        - set(target_libraries)
    )

    if unknown_managed:
        formatted = ", ".join(
            repr(library)
            for library
            in unknown_managed
        )

        raise ValueError(
            "managed artwork was provided for "
            "unknown target libraries: "
            f"{formatted}"
        )

    plans: list[
        TargetPlan
    ] = []

    skipped: list[
        SkippedArtworkTarget
    ] = []

    for target in target_list:
        if (
            target.media_type
            is MediaType.MOVIE
        ):
            skipped.append(
                SkippedArtworkTarget(
                    target=target,
                    reason=(
                        TargetSkipReason
                        .MOVIE_SUPPORT_PENDING
                    ),
                )
            )
            continue

        if (
            target.media_type
            is not MediaType.SHOW
        ):
            raise ValueError(
                "unsupported Artwork Manager "
                f"media type {target.media_type!r}"
            )

        section = plex.library.section(
            target.library
        )

        inventories = tuple(
            build_show_inventory(
                show,
                target.library,
            )
            for show in section.all()
        )

        reconciliation = (
            reconcile_show_target(
                target=target,
                inventories=inventories,
                managed_shows=managed.get(
                    target.library,
                    (),
                ),
            )
        )

        plans.append(
            build_target_plan(
                reconciliation
            )
        )

    return ArtworkServicePlan(
        plans=tuple(plans),
        skipped=tuple(skipped),
    )
