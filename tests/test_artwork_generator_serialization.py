from types import SimpleNamespace

from artwork.serialization import (
    serialize_generator_activity,
)


def test_generator_activity_serializes_execution_metrics():
    execution = SimpleNamespace(
        generator_changed_count=111,
        generator_plan_count=3274,
        generator_cached_count=18,
        generator_materialization_needed_count=3256,
        generator_failure_count=2,
    )

    assert serialize_generator_activity(
        execution
    ) == {
        "changed_shows": 111,
        "planned_cards": 3274,
        "cached_cards": 18,
        "materialization_needed": 3256,
        "failures": 2,
    }


def test_generator_activity_is_zero_for_execution_without_generator():
    execution = SimpleNamespace()

    assert serialize_generator_activity(
        execution
    ) == {
        "changed_shows": 0,
        "planned_cards": 0,
        "cached_cards": 0,
        "materialization_needed": 0,
        "failures": 0,
    }
