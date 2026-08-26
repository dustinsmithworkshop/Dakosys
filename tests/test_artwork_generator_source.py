from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from artwork.generator_inputs import (
    EpisodeGenerationInput,
    EpisodeGenerationPath,
)
from artwork.generator_source import (
    ArtworkGeneratorSourceError,
    InvalidArtworkGeneratorSourceError,
    materialize_generation_source,
)
from artwork.models import (
    ArtworkSource,
)


def _jpeg_bytes() -> bytes:
    buffer = BytesIO()

    Image.new(
        "RGB",
        (4, 4),
        (
            32,
            64,
            128,
        ),
    ).save(
        buffer,
        format="JPEG",
    )

    return buffer.getvalue()


class FakeResponse:
    def __init__(
        self,
        *,
        body=None,
        status_code=200,
        content_type="image/jpeg",
    ):
        self.body = (
            _jpeg_bytes()
            if body is None
            else body
        )
        self.status_code = status_code
        self.headers = {
            "Content-Type":
                content_type,
        }

    def raise_for_status(
        self,
    ):
        if self.status_code >= 400:
            raise RuntimeError(
                f"HTTP {self.status_code}"
            )

    def iter_content(
        self,
        chunk_size,
    ):
        for index in range(
            0,
            len(self.body),
            chunk_size,
        ):
            yield self.body[
                index:
                index + chunk_size
            ]


class FakeSession:
    def __init__(
        self,
        response,
    ):
        self.response = response
        self.calls = []

    def get(
        self,
        url,
        *,
        headers,
        stream,
        timeout,
    ):
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "stream": stream,
                "timeout": timeout,
            }
        )

        return self.response


def _input(
    *,
    source=ArtworkSource.TMDB,
    image_ref=(
        "https://image.tmdb.org/"
        "t/p/original/episode.jpg"
    ),
    provider_asset_id="/episode.jpg",
):
    return EpisodeGenerationInput(
        episode_number=1,
        path=(
            EpisodeGenerationPath
            .GENERATE_MISSING
        ),
        title="Pilot",
        title_source=(
            ArtworkSource.PLEX
        ),
        image_ref=image_ref,
        image_source=source,
        image_provider_asset_id=(
            provider_asset_id
        ),
    )


def test_downloads_tmdb_image_without_plex_auth(
    tmp_path: Path,
):
    body = _jpeg_bytes()

    session = FakeSession(
        FakeResponse(
            body=body,
        )
    )

    destination = (
        tmp_path
        / "source.jpg"
    )

    result = materialize_generation_source(
        generation_input=_input(),
        destination=destination,
        session=session,
        timeout=12.0,
    )

    assert destination.read_bytes() == body

    assert result.path == destination
    assert (
        result.source
        is ArtworkSource.TMDB
    )
    assert result.byte_count == len(
        body
    )

    assert session.calls == [
        {
            "url": (
                "https://image.tmdb.org/"
                "t/p/original/"
                "episode.jpg"
            ),
            "headers": None,
            "stream": True,
            "timeout": 12.0,
        }
    ]


def test_tmdb_provider_path_can_be_materialized(
    tmp_path: Path,
):
    session = FakeSession(
        FakeResponse()
    )

    generation_input = _input(
        image_ref="/episode.jpg",
        provider_asset_id=(
            "/episode.jpg"
        ),
    )

    materialize_generation_source(
        generation_input=(
            generation_input
        ),
        destination=(
            tmp_path
            / "source.jpg"
        ),
        tmdb_image_root=(
            "https://images.example/"
            "original"
        ),
        session=session,
    )

    assert session.calls[0][
        "url"
    ] == (
        "https://images.example/"
        "original/episode.jpg"
    )


def test_downloads_plex_thumbnail_with_scoped_auth(
    tmp_path: Path,
):
    session = FakeSession(
        FakeResponse()
    )

    generation_input = _input(
        source=ArtworkSource.PLEX,
        image_ref=(
            "/library/metadata/"
            "123/thumb/456"
        ),
        provider_asset_id=None,
    )

    result = materialize_generation_source(
        generation_input=(
            generation_input
        ),
        destination=(
            tmp_path
            / "source.jpg"
        ),
        plex_base_url=(
            "http://192.168.1.10:32400"
        ),
        plex_token="secret-token",
        session=session,
    )

    assert (
        result.source
        is ArtworkSource.PLEX
    )

    assert session.calls == [
        {
            "url": (
                "http://192.168.1.10:32400"
                "/library/metadata/"
                "123/thumb/456"
            ),
            "headers": {
                "X-Plex-Token":
                    "secret-token",
            },
            "stream": True,
            "timeout": 30.0,
        }
    ]


def test_rejects_absolute_plex_url_for_different_host(
    tmp_path: Path,
):
    generation_input = _input(
        source=ArtworkSource.PLEX,
        image_ref=(
            "https://evil.example/"
            "image.jpg"
        ),
        provider_asset_id=None,
    )

    with pytest.raises(
        ArtworkGeneratorSourceError,
        match="does not match",
    ):
        materialize_generation_source(
            generation_input=(
                generation_input
            ),
            destination=(
                tmp_path
                / "source.jpg"
            ),
            plex_base_url=(
                "http://plex.local:32400"
            ),
            plex_token="secret-token",
            session=FakeSession(
                FakeResponse()
            ),
        )


def test_non_image_response_is_rejected(
    tmp_path: Path,
):
    destination = (
        tmp_path
        / "source.jpg"
    )

    session = FakeSession(
        FakeResponse(
            body=b"<html>nope</html>",
            content_type="text/html",
        )
    )

    with pytest.raises(
        ArtworkGeneratorSourceError,
        match="non-image",
    ):
        materialize_generation_source(
            generation_input=_input(),
            destination=destination,
            session=session,
        )

    assert not destination.exists()


def test_corrupt_image_body_is_rejected_and_removed(
    tmp_path: Path,
):
    destination = (
        tmp_path
        / "source.jpg"
    )

    session = FakeSession(
        FakeResponse(
            body=(
                b"\x00"
                * 134246
            ),
            content_type="image/jpeg",
        )
    )

    with pytest.raises(
        InvalidArtworkGeneratorSourceError,
        match="invalid image data",
    ) as caught:
        materialize_generation_source(
            generation_input=_input(
                source=ArtworkSource.PLEX,
                image_ref=(
                    "/library/metadata/"
                    "114373/thumb/1786889881"
                ),
                provider_asset_id=None,
            ),
            destination=destination,
            plex_base_url=(
                "http://plex.local:32400"
            ),
            plex_token="secret-token",
            session=session,
        )

    assert not destination.exists()
    assert (
        caught.value.__cause__
        is not None
    )


def test_truncated_image_body_is_rejected_and_removed(
    tmp_path: Path,
):
    destination = (
        tmp_path
        / "source.jpg"
    )

    # Removing only the final byte leaves a JPEG whose structure passes
    # Pillow verify(), but whose pixel data fails during full decoding.
    body = _jpeg_bytes()[:-1]

    with Image.open(
        BytesIO(body)
    ) as image:
        image.verify()

    session = FakeSession(
        FakeResponse(
            body=body,
            content_type="image/jpeg",
        )
    )

    with pytest.raises(
        InvalidArtworkGeneratorSourceError,
        match="invalid image data",
    ) as caught:
        materialize_generation_source(
            generation_input=_input(),
            destination=destination,
            session=session,
        )

    assert not destination.exists()

    assert (
        caught.value.__cause__
        is not None
    )


def test_truncated_image_body_is_rejected_and_removed(
    tmp_path: Path,
):
    destination = (
        tmp_path
        / "source.jpg"
    )

    # Removing only the final byte leaves a JPEG whose structure passes
    # Pillow verify(), but whose pixel data fails during full decoding.
    body = _jpeg_bytes()[:-1]

    with Image.open(
        BytesIO(body)
    ) as image:
        image.verify()

    session = FakeSession(
        FakeResponse(
            body=body,
            content_type="image/jpeg",
        )
    )

    with pytest.raises(
        InvalidArtworkGeneratorSourceError,
        match="invalid image data",
    ) as caught:
        materialize_generation_source(
            generation_input=_input(),
            destination=destination,
            session=session,
        )

    assert not destination.exists()

    assert (
        caught.value.__cause__
        is not None
    )


def test_empty_image_is_rejected(
    tmp_path: Path,
):
    destination = (
        tmp_path
        / "source.jpg"
    )

    session = FakeSession(
        FakeResponse(
            body=b"",
        )
    )

    with pytest.raises(
        ArtworkGeneratorSourceError,
        match="empty",
    ):
        materialize_generation_source(
            generation_input=_input(),
            destination=destination,
            session=session,
        )

    assert not destination.exists()


def test_oversized_image_is_rejected_and_removed(
    tmp_path: Path,
):
    destination = (
        tmp_path
        / "source.jpg"
    )

    session = FakeSession(
        FakeResponse(
            body=b"123456",
        )
    )

    with pytest.raises(
        ArtworkGeneratorSourceError,
        match="maximum size",
    ):
        materialize_generation_source(
            generation_input=_input(),
            destination=destination,
            session=session,
            max_bytes=5,
        )

    assert not destination.exists()


def test_http_failure_is_wrapped_and_partial_file_removed(
    tmp_path: Path,
):
    destination = (
        tmp_path
        / "source.jpg"
    )

    session = FakeSession(
        FakeResponse(
            status_code=503,
        )
    )

    with pytest.raises(
        ArtworkGeneratorSourceError,
        match="could not download",
    ):
        materialize_generation_source(
            generation_input=_input(),
            destination=destination,
            session=session,
        )

    assert not destination.exists()


def test_non_generation_input_is_rejected(
    tmp_path: Path,
):
    generation_input = (
        EpisodeGenerationInput(
            episode_number=1,
            path=(
                EpisodeGenerationPath
                .KEEP_PRIMARY
            ),
        )
    )

    with pytest.raises(
        ArtworkGeneratorSourceError,
        match="not eligible",
    ):
        materialize_generation_source(
            generation_input=(
                generation_input
            ),
            destination=(
                tmp_path
                / "source.jpg"
            ),
            session=FakeSession(
                FakeResponse()
            ),
        )
