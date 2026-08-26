from pathlib import Path
from types import SimpleNamespace

import pytest

from artwork.episode_coverage import (
    EpisodeGeneratorOptions,
)
from artwork.generator_apply import (
    GeneratedArtworkApplyError,
    GeneratedArtworkPlanMismatchError,
    materialize_reviewed_generation_plans,
)
from artwork.generator_inputs import (
    EpisodeGenerationInput,
    EpisodeGenerationPath,
)
from artwork.generator_plan import (
    plan_generated_episode_card,
)
from artwork.generator_renderer import (
    ArtworkGeneratorRenderError,
)
from artwork.models import (
    ArtworkAsset,
    ArtworkKind,
    ArtworkQuality,
    ArtworkSource,
)


def _input(
    *,
    episode_number=1,
):
    return EpisodeGenerationInput(
        episode_number=episode_number,
        path=(
            EpisodeGenerationPath
            .GENERATE_MISSING
        ),
        title=(
            f"Episode {episode_number}"
        ),
        title_source=(
            ArtworkSource.PLEX
        ),
        image_ref=(
            "https://image.tmdb.org/"
            "t/p/original/"
            f"episode-{episode_number}.jpg"
        ),
        image_source=(
            ArtworkSource.TMDB
        ),
        image_provider_asset_id=(
            f"/episode-{episode_number}.jpg"
        ),
    )


def _plan(
    tmp_path: Path,
    *,
    episode_number=1,
):
    return plan_generated_episode_card(
        generation_input=(
            _input(
                episode_number=(
                    episode_number
                )
            )
        ),
        show_key="tmdb:1398",
        season_number=1,
        font_key="marcellus",
        local_root=(
            tmp_path
            / "generated"
        ),
        kometa_root=(
            "/config/assets/generated"
        ),
    )


def _options(
    tmp_path: Path,
):
    return EpisodeGeneratorOptions(
        enabled=True,
        font_key="marcellus",
        local_root=(
            tmp_path
            / "generated"
        ),
        kometa_root=(
            "/config/assets/generated"
        ),
        plex_base_url=(
            "http://plex:32400"
        ),
        plex_token="token",
    )


def _successful_materializer(
    calls,
    *,
    reused=False,
):
    def materialize(
        **kwargs,
    ):
        calls.append(
            kwargs
        )

        plan = (
            plan_generated_episode_card(
                generation_input=(
                    kwargs[
                        "generation_input"
                    ]
                ),
                show_key=(
                    kwargs[
                        "show_key"
                    ]
                ),
                season_number=(
                    kwargs[
                        "season_number"
                    ]
                ),
                font_key=(
                    kwargs[
                        "font_key"
                    ]
                ),
                local_root=(
                    kwargs[
                        "local_root"
                    ]
                ),
                kometa_root=(
                    kwargs[
                        "kometa_root"
                    ]
                ),
            )
        )

        plan.local_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        plan.local_path.write_bytes(
            b"generated-jpeg"
        )

        return SimpleNamespace(
            identity=plan.identity,
            local_path=plan.local_path,
            kometa_path=plan.kometa_path,
            fingerprint=plan.fingerprint,
            asset=plan.asset,
            reused=reused,
        )

    return materialize


def test_materializes_reviewed_plan(
    tmp_path: Path,
):
    plan = _plan(
        tmp_path
    )

    calls = []

    result = (
        materialize_reviewed_generation_plans(
            plans=(
                plan,
            ),
            options=(
                _options(
                    tmp_path
                )
            ),
            materialize_card=(
                _successful_materializer(
                    calls
                )
            ),
        )
    )

    assert result.count == 1
    assert (
        result.materialized_count
        == 1
    )
    assert result.reused_count == 0

    assert (
        result.items[0].plan
        == plan
    )

    assert (
        plan.local_path.read_bytes()
        == b"generated-jpeg"
    )

    assert len(calls) == 1


def test_reused_reviewed_plan_is_reported(
    tmp_path: Path,
):
    plan = _plan(
        tmp_path
    )

    result = (
        materialize_reviewed_generation_plans(
            plans=(
                plan,
            ),
            options=(
                _options(
                    tmp_path
                )
            ),
            materialize_card=(
                _successful_materializer(
                    [],
                    reused=True,
                )
            ),
        )
    )

    assert result.count == 1
    assert result.reused_count == 1
    assert (
        result.materialized_count
        == 0
    )


def test_multiple_reviewed_plans_apply_in_order(
    tmp_path: Path,
):
    first = _plan(
        tmp_path,
        episode_number=1,
    )

    second = _plan(
        tmp_path,
        episode_number=2,
    )

    calls = []

    result = (
        materialize_reviewed_generation_plans(
            plans=(
                first,
                second,
            ),
            options=(
                _options(
                    tmp_path
                )
            ),
            materialize_card=(
                _successful_materializer(
                    calls
                )
            ),
        )
    )

    assert result.count == 2

    assert [
        call[
            "generation_input"
        ].episode_number
        for call in calls
    ] == [
        1,
        2,
    ]


def test_disabled_generator_rejects_apply_before_io(
    tmp_path: Path,
):
    plan = _plan(
        tmp_path
    )

    options = EpisodeGeneratorOptions(
        enabled=False,
        font_key="marcellus",
        local_root=(
            tmp_path
            / "generated"
        ),
        kometa_root=(
            "/config/assets/generated"
        ),
    )

    def unexpected(
        **_kwargs,
    ):
        raise AssertionError(
            "disabled generator must "
            "not materialize"
        )

    with pytest.raises(
        GeneratedArtworkApplyError,
        match="disabled",
    ):
        materialize_reviewed_generation_plans(
            plans=(
                plan,
            ),
            options=options,
            materialize_card=unexpected,
        )


def test_materializer_failure_retries_then_succeeds(
    tmp_path: Path,
):
    plan = _plan(
        tmp_path
    )

    attempt_count = 0
    sleeps = []

    successful = (
        _successful_materializer(
            []
        )
    )

    def flaky(
        **kwargs,
    ):
        nonlocal attempt_count

        attempt_count += 1

        if attempt_count < 3:
            raise RuntimeError(
                "temporary download failure"
            )

        return successful(
            **kwargs
        )

    result = (
        materialize_reviewed_generation_plans(
            plans=(
                plan,
            ),
            options=(
                _options(
                    tmp_path
                )
            ),
            materialize_card=flaky,
            sleep=sleeps.append,
        )
    )

    assert attempt_count == 3

    assert sleeps == [
        1.0,
        2.0,
    ]

    assert (
        result.materialized_count
        == 1
    )

    assert result.reused_count == 0


def test_renderer_failure_is_not_retried(
    tmp_path: Path,
):
    plan = _plan(
        tmp_path
    )

    attempt_count = 0
    sleeps = []

    def fail_render(
        **_kwargs,
    ):
        nonlocal attempt_count

        attempt_count += 1

        try:
            raise ArtworkGeneratorRenderError(
                "layout failed"
            )
        except ArtworkGeneratorRenderError as exc:
            raise RuntimeError(
                "materialization failed"
            ) from exc

    with pytest.raises(
        GeneratedArtworkApplyError,
        match="after 1 attempt",
    ) as caught:
        materialize_reviewed_generation_plans(
            plans=(
                plan,
            ),
            options=(
                _options(
                    tmp_path
                )
            ),
            materialize_card=fail_render,
            sleep=sleeps.append,
        )

    assert attempt_count == 1
    assert sleeps == []

    message = str(
        caught.value
    )

    assert (
        "ArtworkGeneratorRenderError: layout failed"
        in message
    )


def test_materializer_failure_is_wrapped_after_retries(
    tmp_path: Path,
):
    plan = _plan(
        tmp_path
    )

    attempt_count = 0
    sleeps = []

    def fail(
        **_kwargs,
    ):
        nonlocal attempt_count

        attempt_count += 1

        raise RuntimeError(
            "download failed"
        )

    with pytest.raises(
        GeneratedArtworkApplyError,
        match="could not materialize",
    ) as caught:
        materialize_reviewed_generation_plans(
            plans=(
                plan,
            ),
            options=(
                _options(
                    tmp_path
                )
            ),
            materialize_card=fail,
            sleep=sleeps.append,
        )

    assert attempt_count == 3

    assert sleeps == [
        1.0,
        2.0,
    ]

    message = str(
        caught.value
    )

    assert "tmdb:1398" in message
    assert "S01E01" in message
    assert "after 3 attempts" in message

    assert (
        "RuntimeError: download failed"
        in message
    )

    assert not (
        plan.local_path.exists()
    )

def test_changed_fingerprint_is_rejected(
    tmp_path: Path,
):
    plan = _plan(
        tmp_path
    )

    calls = 0

    def mismatch(
        **_kwargs,
    ):
        nonlocal calls

        calls += 1
        plan.local_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        plan.local_path.write_bytes(
            b"generated-jpeg"
        )

        return SimpleNamespace(
            identity=plan.identity,
            local_path=plan.local_path,
            kometa_path=plan.kometa_path,
            fingerprint="wrong",
            asset=plan.asset,
            reused=False,
        )

    with pytest.raises(
        GeneratedArtworkPlanMismatchError,
        match="fingerprint",
    ):
        materialize_reviewed_generation_plans(
            plans=(
                plan,
            ),
            options=(
                _options(
                    tmp_path
                )
            ),
            materialize_card=mismatch,
        )

    assert calls == 1


def test_changed_asset_is_rejected(
    tmp_path: Path,
):
    plan = _plan(
        tmp_path
    )

    wrong_asset = ArtworkAsset(
        kind=(
            ArtworkKind.EPISODE_CARD
        ),
        source=(
            ArtworkSource.GENERATED
        ),
        provider_asset_id="wrong",
        quality=(
            ArtworkQuality.GENERATED
        ),
        file_path=(
            plan.kometa_path
        ),
    )

    def mismatch(
        **_kwargs,
    ):
        plan.local_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        plan.local_path.write_bytes(
            b"generated-jpeg"
        )

        return SimpleNamespace(
            identity=plan.identity,
            local_path=plan.local_path,
            kometa_path=plan.kometa_path,
            fingerprint=plan.fingerprint,
            asset=wrong_asset,
            reused=False,
        )

    with pytest.raises(
        GeneratedArtworkPlanMismatchError,
        match="asset",
    ):
        materialize_reviewed_generation_plans(
            plans=(
                plan,
            ),
            options=(
                _options(
                    tmp_path
                )
            ),
            materialize_card=mismatch,
        )


def test_missing_materialized_file_is_rejected(
    tmp_path: Path,
):
    plan = _plan(
        tmp_path
    )

    def missing_file(
        **_kwargs,
    ):
        return SimpleNamespace(
            identity=plan.identity,
            local_path=plan.local_path,
            kometa_path=plan.kometa_path,
            fingerprint=plan.fingerprint,
            asset=plan.asset,
            reused=False,
        )

    with pytest.raises(
        GeneratedArtworkApplyError,
        match="missing or empty",
    ):
        materialize_reviewed_generation_plans(
            plans=(
                plan,
            ),
            options=(
                _options(
                    tmp_path
                )
            ),
            materialize_card=missing_file,
        )


def test_empty_plan_collection_is_noop(
    tmp_path: Path,
):
    result = (
        materialize_reviewed_generation_plans(
            plans=(),
            options=(
                _options(
                    tmp_path
                )
            ),
        )
    )

    assert result.count == 0
    assert result.reused_count == 0
    assert (
        result.materialized_count
        == 0
    )


def test_repeated_invalid_source_failure_records_marker(
    tmp_path: Path,
):
    from artwork.generator_materializer import (
        ArtworkGeneratorMaterializationError,
    )
    from artwork.generator_source import (
        InvalidArtworkGeneratorSourceError,
    )
    from artwork.generator_source_failures import (
        is_generation_source_known_invalid,
    )

    plan = _plan(
        tmp_path
    )

    options = _options(
        tmp_path
    )

    attempt_count = 0
    sleeps = []

    def fail_invalid_source(
        **_kwargs,
    ):
        nonlocal attempt_count

        attempt_count += 1

        try:
            raise InvalidArtworkGeneratorSourceError(
                "generation source returned "
                "invalid image data"
            )

        except InvalidArtworkGeneratorSourceError as exc:
            raise ArtworkGeneratorMaterializationError(
                "could not materialize generated "
                "episode artwork"
            ) from exc

    with pytest.raises(
        GeneratedArtworkApplyError,
        match=(
            "source marked temporarily "
            "invalid for future scans"
        ),
    ):
        materialize_reviewed_generation_plans(
            plans=(plan,),
            options=options,
            materialize_card=(
                fail_invalid_source
            ),
            sleep=sleeps.append,
        )

    assert attempt_count == 3

    assert sleeps == [
        1.0,
        2.0,
    ]

    assert (
        is_generation_source_known_invalid(
            root=options.local_root,
            generation_input=(
                plan.generation_input
            ),
        )
    )
