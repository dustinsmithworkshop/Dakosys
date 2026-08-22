"""Docker packaging guarantees for Artwork Generator assets."""

from pathlib import Path


def test_docker_image_copies_generator_fonts() -> None:
    dockerfile = (
        Path(__file__)
        .resolve()
        .parent
        .parent
        / "Dockerfile"
    )

    contents = dockerfile.read_text(
        encoding="utf-8"
    )

    assert (
        "COPY fonts/artwork-generator/ "
        "/app/fonts/artwork-generator/"
        in contents
    )
