from __future__ import annotations

import unittest
from typing import FrozenSet, Sequence

from mosaic.core import (
    ExternalId,
    ImageInfo,
    ImageType,
    LibraryKind,
    MediaItem,
    MediaItemKind,
    MediaLibrary,
    MediaSource,
)
from mosaic.servers import (
    MediaServer,
    MediaServerCapability,
    MediaServerItemNotFoundError,
    UnsupportedMediaServerCapabilityError,
)


class FakeMediaServer(MediaServer):
    """In-memory adapter used to exercise the platform-neutral contract."""

    def __init__(
        self,
        *,
        capabilities: FrozenSet[MediaServerCapability] | None = None,
    ) -> None:
        self._capabilities = (
            capabilities
            if capabilities is not None
            else frozenset(MediaServerCapability)
        )

        self.library = MediaLibrary(
            server_library_id="library-1",
            name="TV",
            kind=LibraryKind.SHOWS,
        )
        self.show = MediaItem(
            server_item_id="show-1",
            library_id="library-1",
            kind=MediaItemKind.SHOW,
            title="Example Show",
            year=2026,
            path="/media/Example Show",
        )
        self.season = MediaItem(
            server_item_id="season-1",
            library_id="library-1",
            kind=MediaItemKind.SEASON,
            title="Season 1",
            parent_id="show-1",
            season_number=1,
        )
        self.episode = MediaItem(
            server_item_id="episode-1",
            library_id="library-1",
            kind=MediaItemKind.EPISODE,
            title="Pilot",
            parent_id="season-1",
            season_number=1,
            episode_number=1,
            path="/media/Example Show/Season 01/S01E01.mkv",
        )

        self._items = {
            self.show.server_item_id: self.show,
            self.season.server_item_id: self.season,
            self.episode.server_item_id: self.episode,
        }

    @property
    def server_type(self) -> str:
        return "fake"

    @property
    def instance_name(self) -> str:
        return "test-server"

    @property
    def capabilities(self) -> FrozenSet[MediaServerCapability]:
        return self._capabilities

    def _ensure_item(self, item_id: str) -> MediaItem:
        try:
            return self._items[item_id]
        except KeyError as exc:
            raise MediaServerItemNotFoundError(
                f"unknown item {item_id!r}",
                server_type=self.server_type,
                server_instance=self.instance_name,
                operation="item_lookup",
            ) from exc

    def list_libraries(self) -> Sequence[MediaLibrary]:
        self.require_capability(MediaServerCapability.LIBRARIES)
        return (self.library,)

    def list_movies(self, library_id: str) -> Sequence[MediaItem]:
        self.require_capability(MediaServerCapability.MOVIES)
        return ()

    def list_shows(self, library_id: str) -> Sequence[MediaItem]:
        self.require_capability(MediaServerCapability.SHOWS)
        if library_id != self.library.server_library_id:
            return ()
        return (self.show,)

    def list_seasons(self, show_id: str) -> Sequence[MediaItem]:
        self.require_capability(MediaServerCapability.SEASONS)
        if show_id != self.show.server_item_id:
            return ()
        return (self.season,)

    def list_episodes(self, show_id: str) -> Sequence[MediaItem]:
        self.require_capability(MediaServerCapability.EPISODES)
        if show_id != self.show.server_item_id:
            return ()
        return (self.episode,)

    def get_item(self, item_id: str) -> MediaItem:
        self.require_capability(MediaServerCapability.ITEM_DETAILS)
        return self._ensure_item(item_id)

    def get_external_ids(self, item_id: str) -> Sequence[ExternalId]:
        self.require_capability(MediaServerCapability.EXTERNAL_IDS)
        self._ensure_item(item_id)
        return (
            ExternalId(provider="tmdb", value="1234"),
            ExternalId(provider="tmdb", value="4321"),
            ExternalId(provider="tvdb", value="5678"),
        )

    def get_media_sources(self, item_id: str) -> Sequence[MediaSource]:
        self.require_capability(MediaServerCapability.MEDIA_SOURCES)
        item = self._ensure_item(item_id)
        return (
            MediaSource(
                source_id="source-1",
                path=item.path,
                size_bytes=1024,
                container="mkv",
            ),
        )

    def get_image_info(
        self,
        item_id: str,
        image_type: ImageType,
    ) -> ImageInfo | None:
        self.require_capability(MediaServerCapability.IMAGE_INFO)
        self._ensure_item(item_id)
        return ImageInfo(
            image_type=image_type,
            tag="image-tag-1",
            width=1000,
            height=1500,
        )

    def get_image(
        self,
        item_id: str,
        image_type: ImageType,
    ) -> bytes:
        self.require_capability(MediaServerCapability.IMAGE_CONTENT)
        self._ensure_item(item_id)
        return b"image-bytes"


class MediaServerContractTests(unittest.TestCase):
    def test_fake_adapter_returns_only_normalized_models(self) -> None:
        server = FakeMediaServer()

        libraries = server.list_libraries()
        shows = server.list_shows("library-1")
        seasons = server.list_seasons("show-1")
        episodes = server.list_episodes("show-1")

        self.assertIsInstance(libraries[0], MediaLibrary)
        self.assertIsInstance(shows[0], MediaItem)
        self.assertEqual(shows[0].kind, MediaItemKind.SHOW)
        self.assertEqual(seasons[0].season_number, 1)
        self.assertEqual(episodes[0].episode_number, 1)

    def test_external_id_evidence_preserves_multiple_candidates(self) -> None:
        server = FakeMediaServer()

        external_ids = server.get_external_ids("show-1")

        self.assertEqual(
            external_ids,
            (
                ExternalId(provider="tmdb", value="1234"),
                ExternalId(provider="tmdb", value="4321"),
                ExternalId(provider="tvdb", value="5678"),
            ),
        )

    def test_media_and_image_reads_use_normalized_records(self) -> None:
        server = FakeMediaServer()

        source = server.get_media_sources("episode-1")[0]
        image = server.get_image_info("show-1", ImageType.PRIMARY)

        self.assertEqual(source.size_bytes, 1024)
        self.assertEqual(source.container, "mkv")
        self.assertIsNotNone(image)
        assert image is not None
        self.assertEqual(image.tag, "image-tag-1")
        self.assertEqual(
            server.get_image("show-1", ImageType.PRIMARY),
            b"image-bytes",
        )

    def test_capability_differences_fail_explicitly(self) -> None:
        server = FakeMediaServer(
            capabilities=frozenset(
                {
                    MediaServerCapability.LIBRARIES,
                    MediaServerCapability.SHOWS,
                }
            )
        )

        self.assertTrue(server.supports(MediaServerCapability.SHOWS))
        self.assertFalse(server.supports(MediaServerCapability.IMAGE_INFO))

        with self.assertRaises(UnsupportedMediaServerCapabilityError) as raised:
            server.get_image_info("show-1", ImageType.PRIMARY)

        self.assertEqual(
            raised.exception.capability,
            MediaServerCapability.IMAGE_INFO,
        )
        self.assertEqual(raised.exception.server_type, "fake")
        self.assertEqual(raised.exception.server_instance, "test-server")
        self.assertEqual(raised.exception.operation, "image_info")

    def test_item_not_found_uses_normalized_error(self) -> None:
        server = FakeMediaServer()

        with self.assertRaises(MediaServerItemNotFoundError) as raised:
            server.get_item("missing")

        self.assertEqual(raised.exception.server_type, "fake")
        self.assertEqual(raised.exception.server_instance, "test-server")
        self.assertEqual(raised.exception.operation, "item_lookup")


if __name__ == "__main__":
    unittest.main()
