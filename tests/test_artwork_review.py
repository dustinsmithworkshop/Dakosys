from types import SimpleNamespace

from artwork.review import (
    build_artwork_review_fingerprint,
    build_artwork_review_payload,
)


class JsonValue:
    def __init__(
        self,
        value,
    ):
        self.value = value

    def to_json(
        self,
    ):
        return self.value


def _run(
    *,
    state_json='{"state":1}\n',
    manifest_json='{"manifest":1}\n',
    file_hash="aaa",
    preserved_unowned=(),
):
    plan = SimpleNamespace(
        files=(
            SimpleNamespace(
                filename="example.yaml",
                sha256=file_hash,
            ),
        ),
        manifest=JsonValue(
            manifest_json
        ),
        state_store=JsonValue(
            state_json
        ),
        added=(),
        updated=(
            "example.yaml",
        ),
        unchanged=(),
        removed=(),
        preserved_unowned=(
            preserved_unowned
        ),
    )

    preview = SimpleNamespace(
        issues=(),
        set_refresh_count=1,
        set_migration_count=0,
    )

    return SimpleNamespace(
        library="Series",
        output_path=(
            "/metadata/"
            "artwork-series"
        ),
        safe_to_apply=True,
        needs_apply=True,
        plan=plan,
        preview=preview,
    )


def test_review_fingerprint_is_deterministic():
    first = (
        build_artwork_review_fingerprint(
            _run()
        )
    )

    second = (
        build_artwork_review_fingerprint(
            _run()
        )
    )

    assert first == second
    assert len(first) == 64


def test_review_fingerprint_changes_with_desired_output():
    first = (
        build_artwork_review_fingerprint(
            _run(
                file_hash="aaa"
            )
        )
    )

    second = (
        build_artwork_review_fingerprint(
            _run(
                file_hash="bbb"
            )
        )
    )

    assert first != second


def test_review_fingerprint_changes_with_durable_state():
    first = (
        build_artwork_review_fingerprint(
            _run(
                state_json='{"state":1}\n'
            )
        )
    )

    second = (
        build_artwork_review_fingerprint(
            _run(
                state_json='{"state":2}\n'
            )
        )
    )

    assert first != second


def test_review_fingerprint_tracks_unowned_filesystem_context():
    first = (
        build_artwork_review_fingerprint(
            _run()
        )
    )

    second = (
        build_artwork_review_fingerprint(
            _run(
                preserved_unowned=(
                    "notes.txt",
                )
            )
        )
    )

    assert first != second


def test_review_payload_contains_no_transient_provider_activity():
    payload = (
        build_artwork_review_payload(
            _run()
        )
    )

    assert (
        "provider_activity"
        not in payload
    )

    assert (
        payload["library"]
        == "Series"
    )
