from artwork.activity_log import (
    write_artwork_activity,
)


def test_artwork_activity_log_writes_single_line(
    tmp_path,
):
    path = (
        tmp_path
        / "artwork_manager.log"
    )

    write_artwork_activity(
        path,
        "info",
        "scan complete\nsecond line",
    )

    text = path.read_text(
        encoding="utf-8"
    )

    assert "[INFO]" in text
    assert (
        "scan complete | second line"
        in text
    )

    assert len(
        text.splitlines()
    ) == 1


def test_artwork_activity_log_rotates(
    tmp_path,
):
    path = (
        tmp_path
        / "artwork_manager.log"
    )

    path.write_text(
        "old data",
        encoding="utf-8",
    )

    write_artwork_activity(
        path,
        "INFO",
        "new data",
        max_bytes=1,
        backup_count=2,
    )

    assert (
        tmp_path
        / "artwork_manager.log.1"
    ).read_text(
        encoding="utf-8"
    ) == "old data"

    assert "new data" in (
        path.read_text(
            encoding="utf-8"
        )
    )
