"""Apply reviewed Artwork Generator plans."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from artwork.episode_coverage import (
    EpisodeGeneratorOptions,
)
from artwork.generator_materializer import (
    GeneratedEpisodeCardResult,
    materialize_generated_episode_card,
)
from artwork.generator_plan import (
    GeneratedEpisodeCardPlan,
)


class GeneratedArtworkApplyError(
    RuntimeError
):
    """Reviewed generated artwork could not be safely materialized."""


class GeneratedArtworkPlanMismatchError(
    GeneratedArtworkApplyError
):
    """Materialized output no longer matches the reviewed plan."""


@dataclass(frozen=True)
class AppliedGeneratedEpisodeCard:
    """One reviewed generation plan after materialization."""

    plan: GeneratedEpisodeCardPlan
    result: GeneratedEpisodeCardResult

    @property
    def reused(self) -> bool:
        return self.result.reused

    @property
    def materialized(self) -> bool:
        return not self.result.reused


@dataclass(frozen=True)
class GeneratedArtworkApplyResult:
    """Result of materializing reviewed generation plans."""

    items: tuple[
        AppliedGeneratedEpisodeCard,
        ...,
    ]

    @property
    def count(self) -> int:
        return len(
            self.items
        )

    @property
    def reused_count(self) -> int:
        return sum(
            1
            for item in self.items
            if item.reused
        )

    @property
    def materialized_count(self) -> int:
        return sum(
            1
            for item in self.items
            if item.materialized
        )


def materialize_reviewed_generation_plans(
    *,
    plans: Iterable[
        GeneratedEpisodeCardPlan
    ],
    options: EpisodeGeneratorOptions,
    materialize_card=(
        materialize_generated_episode_card
    ),
) -> GeneratedArtworkApplyResult:
    """Materialize exactly the generator plans approved by preview.

    Cache state may change between preview and apply. That is safe:
    materialization may reuse a file that appeared after preview, or
    recreate one that disappeared.

    Semantic identity may not change. Every materialized result must
    exactly match the reviewed fingerprint, output paths, and asset.
    """

    if not options.enabled:
        raise GeneratedArtworkApplyError(
            "cannot apply generated artwork "
            "while Artwork Generator is disabled"
        )

    reviewed = tuple(
        plans
    )

    applied = []

    for plan in reviewed:
        try:
            result = (
                materialize_card(
                    generation_input=(
                        plan.generation_input
                    ),
                    show_key=(
                        plan.identity.show_key
                    ),
                    season_number=(
                        plan.identity
                        .season_number
                    ),
                    font_key=(
                        plan.identity.font_key
                    ),
                    local_root=(
                        options.local_root
                    ),
                    kometa_root=(
                        options.kometa_root
                    ),
                    font_dir=(
                        options.font_dir
                    ),
                    plex_base_url=(
                        options.plex_base_url
                    ),
                    plex_token=(
                        options.plex_token
                    ),
                    session=(
                        options.session
                    ),
                )
            )

        except Exception as exc:
            raise GeneratedArtworkApplyError(
                "could not materialize "
                "reviewed generated artwork "
                f"for season "
                f"{plan.identity.season_number} "
                f"episode "
                f"{plan.identity.episode_number}"
            ) from exc

        _validate_materialized_result(
            plan=plan,
            result=result,
        )

        applied.append(
            AppliedGeneratedEpisodeCard(
                plan=plan,
                result=result,
            )
        )

    return GeneratedArtworkApplyResult(
        items=tuple(
            applied
        )
    )


def _validate_materialized_result(
    *,
    plan: GeneratedEpisodeCardPlan,
    result: GeneratedEpisodeCardResult,
) -> None:
    """Require materialization to match the reviewed plan exactly."""

    mismatches = []

    if (
        result.identity
        != plan.identity
    ):
        mismatches.append(
            "identity"
        )

    if (
        result.fingerprint
        != plan.fingerprint
    ):
        mismatches.append(
            "fingerprint"
        )

    if (
        Path(
            result.local_path
        )
        != Path(
            plan.local_path
        )
    ):
        mismatches.append(
            "local_path"
        )

    if (
        result.kometa_path
        != plan.kometa_path
    ):
        mismatches.append(
            "kometa_path"
        )

    if (
        result.asset
        != plan.asset
    ):
        mismatches.append(
            "asset"
        )

    if mismatches:
        raise GeneratedArtworkPlanMismatchError(
            "materialized generated artwork "
            "does not match reviewed plan: "
            + ", ".join(
                mismatches
            )
        )

    try:
        usable = (
            result.local_path.is_file()
            and result.local_path.stat().st_size
            > 0
        )

    except OSError:
        usable = False

    if not usable:
        raise GeneratedArtworkApplyError(
            "materialized generated artwork "
            "file is missing or empty"
        )
