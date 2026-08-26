"""Apply reviewed Artwork Generator plans."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
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
from artwork.generator_renderer import (
    ArtworkGeneratorRenderError,
)
from artwork.generator_source import (
    InvalidArtworkGeneratorSourceError,
)
from artwork.generator_source_failures import (
    record_invalid_generation_source,
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


def _exception_chain_contains(
    exc: Exception,
    exception_type: type[BaseException],
) -> bool:
    """Whether one exception type appears anywhere in the cause chain."""

    seen = set()
    current = exc

    while (
        isinstance(
            current,
            BaseException,
        )
        and id(current) not in seen
    ):
        seen.add(
            id(current)
        )

        if isinstance(
            current,
            exception_type,
        ):
            return True

        current = (
            current.__cause__
            if isinstance(
                current.__cause__,
                BaseException,
            )
            else None
        )

    return False


def _exception_chain_summary(
    exc: Exception,
) -> str:
    """Return a compact diagnostic summary of one exception chain."""

    parts = []
    seen = set()
    current = exc

    while (
        isinstance(current, Exception)
        and id(current) not in seen
    ):
        seen.add(
            id(current)
        )

        detail = str(
            current
        ).strip()

        part = (
            f"{type(current).__name__}: "
            f"{detail}"
            if detail
            else type(current).__name__
        )

        if part not in parts:
            parts.append(
                part
            )

        current = (
            current.__cause__
            if isinstance(
                current.__cause__,
                Exception,
            )
            else None
        )

    return " <- ".join(
        parts
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
    attempts: int = 3,
    retry_delays: tuple[
        float,
        ...
    ] = (
        1.0,
        2.0,
    ),
    sleep=time.sleep,
) -> GeneratedArtworkApplyResult:
    """Materialize exactly the generator plans approved by preview.

    Cache state may change between preview and apply. That is safe:
    materialization may reuse a file that appeared after preview, or
    recreate one that disappeared.

    Transient materialization failures are retried per card. Semantic
    validation failures are deliberately not retried.

    Semantic identity may not change. Every materialized result must
    exactly match the reviewed fingerprint, output paths, and asset.
    """

    if not options.enabled:
        raise GeneratedArtworkApplyError(
            "cannot apply generated artwork "
            "while Artwork Generator is disabled"
        )

    if (
        not isinstance(
            attempts,
            int,
        )
        or isinstance(
            attempts,
            bool,
        )
        or attempts <= 0
    ):
        raise ValueError(
            "materialization attempts must "
            "be a positive integer"
        )

    normalized_delays = []

    for delay in retry_delays:
        if (
            not isinstance(
                delay,
                (int, float),
            )
            or isinstance(
                delay,
                bool,
            )
            or delay < 0
        ):
            raise ValueError(
                "materialization retry delays "
                "must be non-negative numbers"
            )

        normalized_delays.append(
            float(delay)
        )

    retry_delays = tuple(
        normalized_delays
    )

    reviewed = tuple(
        plans
    )

    applied = []

    for plan in reviewed:
        result = None

        for attempt in range(
            1,
            attempts + 1,
        ):
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

                break

            except Exception as exc:
                non_retryable = (
                    _exception_chain_contains(
                        exc,
                        ArtworkGeneratorRenderError,
                    )
                )

                if (
                    non_retryable
                    or attempt >= attempts
                ):
                    invalid_source_recorded = False
                    marker_error = None

                    if (
                        attempt >= attempts
                        and _exception_chain_contains(
                            exc,
                            InvalidArtworkGeneratorSourceError,
                        )
                    ):
                        try:
                            record_invalid_generation_source(
                                root=options.local_root,
                                generation_input=(
                                    plan.generation_input
                                ),
                                reason=(
                                    _exception_chain_summary(
                                        exc
                                    )
                                ),
                            )

                            invalid_source_recorded = True

                        except Exception as marker_exc:
                            marker_error = marker_exc

                    episode = (
                        f"S{plan.identity.season_number:02d}"
                        f"E{plan.identity.episode_number:02d}"
                    )

                    attempt_label = (
                        "attempt"
                        if attempt == 1
                        else "attempts"
                    )

                    marker_detail = ""

                    if invalid_source_recorded:
                        marker_detail = (
                            "; source marked temporarily "
                            "invalid for future scans"
                        )

                    elif marker_error is not None:
                        marker_detail = (
                            "; invalid-source marker "
                            "could not be written: "
                            f"{_exception_chain_summary(marker_error)}"
                        )

                    raise GeneratedArtworkApplyError(
                        "could not materialize "
                        "reviewed generated artwork "
                        f"for {plan.identity.show_key} "
                        f"{episode} after "
                        f"{attempt} {attempt_label}: "
                        f"{_exception_chain_summary(exc)}"
                        f"{marker_detail}"
                    ) from exc

                delay = 0.0

                if retry_delays:
                    delay = (
                        retry_delays[
                            min(
                                attempt - 1,
                                len(
                                    retry_delays
                                ) - 1,
                            )
                        ]
                    )

                if delay > 0:
                    sleep(
                        delay
                    )

        if result is None:
            raise GeneratedArtworkApplyError(
                "generated artwork "
                "materializer returned no result"
            )

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
