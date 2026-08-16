"""TMDB artwork access for Artwork Manager.

This module extends Dakosys's existing read-only TMDB transport with
artwork-specific episode-still parsing.
"""

from __future__ import annotations

from artwork.models import (
    ArtworkAsset,
    ArtworkKind,
    ArtworkQuality,
    ArtworkSource,
)
from tv_metadata.providers.tmdb import (
    TMDBProvider as MetadataTMDBProvider,
)


TMDB_IMAGE_BASE_URL = (
    "https://image.tmdb.org/t/p"
)

TMDB_DEFAULT_IMAGE_SIZE = "original"


class TMDBArtworkClient(
    MetadataTMDBProvider
):
    """Read-only TMDB artwork client."""

    name = "tmdb"

    def __init__(
        self,
        access_token: str | None = None,
        *,
        api_key: str | None = None,
        base_url: str = (
            "https://api.themoviedb.org/3"
        ),
        image_base_url: str = (
            TMDB_IMAGE_BASE_URL
        ),
        image_size: str = (
            TMDB_DEFAULT_IMAGE_SIZE
        ),
        session=None,
        timeout: float = 30.0,
    ) -> None:
        super().__init__(
            access_token=access_token,
            api_key=api_key,
            base_url=base_url,
            session=session,
            timeout=timeout,
        )

        self.image_base_url = (
            image_base_url.rstrip("/")
        )

        self.image_size = (
            image_size.strip("/")
        )

        if not self.image_size:
            raise ValueError(
                "TMDB image size cannot be empty"
            )

    def _image_url(
        self,
        file_path: str,
    ) -> str:
        normalized = (
            "/"
            + file_path.strip().lstrip("/")
        )

        return (
            f"{self.image_base_url}"
            f"/{self.image_size}"
            f"{normalized}"
        )

    def get_season_episode_cards(
        self,
        *,
        tmdb_id: int,
        season_number: int,
    ) -> dict[int, ArtworkAsset]:
        """Return available episode stills for one TMDB season.

        One season request can resolve many missing episode cards.
        Missing stills are omitted from the result.
        """

        response = self._get(
            (
                f"/tv/{tmdb_id}"
                f"/season/{season_number}"
            )
        )

        if response.status_code == 404:
            return {}

        response.raise_for_status()

        payload = response.json()

        episodes = (
            payload.get("episodes")
            or []
        )

        cards: dict[
            int,
            ArtworkAsset,
        ] = {}

        for raw_episode in episodes:
            if not isinstance(
                raw_episode,
                dict,
            ):
                continue

            episode_number = (
                raw_episode.get(
                    "episode_number"
                )
            )

            still_path = (
                raw_episode.get(
                    "still_path"
                )
            )

            if not isinstance(
                episode_number,
                int,
            ):
                continue

            if not isinstance(
                still_path,
                str,
            ):
                continue

            still_path = (
                still_path.strip()
            )

            if not still_path:
                continue

            cards[
                episode_number
            ] = ArtworkAsset(
                kind=(
                    ArtworkKind
                    .EPISODE_CARD
                ),
                source=(
                    ArtworkSource.TMDB
                ),
                url=self._image_url(
                    still_path
                ),
                provider_asset_id=(
                    still_path
                ),
                quality=(
                    ArtworkQuality
                    .RAW_STILL
                ),
            )

        return cards
