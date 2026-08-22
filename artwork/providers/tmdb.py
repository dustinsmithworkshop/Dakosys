"""TMDB artwork access for Artwork Manager.

This module extends Dakosys's existing read-only TMDB transport with
artwork-specific episode-still parsing.
"""

from __future__ import annotations

from dataclasses import dataclass

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


@dataclass(frozen=True)
class TMDBTVExternalIds:
    """Exact external IDs reported by TMDB for one TV series."""

    tvdb_id: int | None = None
    imdb_id: str | None = None


@dataclass(frozen=True)
class TMDBMovieArtwork:
    """Primary TMDB presentation artwork for one movie."""

    tmdb_id: int

    poster: ArtworkAsset | None = None
    background: ArtworkAsset | None = None


@dataclass(frozen=True)
class TMDBEpisodeArtwork:
    """Generation-relevant TMDB metadata for one TV episode."""

    episode_number: int
    title: str | None = None
    card: ArtworkAsset | None = None


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

    def get_tv_external_ids(
        self,
        *,
        tmdb_id: int,
    ) -> TMDBTVExternalIds:
        """Return exact TVDB/IMDb IDs attached to one TMDB TV series."""

        if (
            not isinstance(
                tmdb_id,
                int,
            )
            or isinstance(
                tmdb_id,
                bool,
            )
            or tmdb_id <= 0
        ):
            raise ValueError(
                "TMDB TV ID must be a positive integer"
            )

        response = self._get(
            f"/tv/{tmdb_id}/external_ids"
        )

        if response.status_code == 404:
            return TMDBTVExternalIds()

        response.raise_for_status()

        payload = response.json()

        raw_tvdb_id = payload.get(
            "tvdb_id"
        )

        tvdb_id = (
            raw_tvdb_id
            if (
                isinstance(
                    raw_tvdb_id,
                    int,
                )
                and not isinstance(
                    raw_tvdb_id,
                    bool,
                )
                and raw_tvdb_id > 0
            )
            else None
        )

        raw_imdb_id = payload.get(
            "imdb_id"
        )

        imdb_id = (
            raw_imdb_id.strip()
            if isinstance(
                raw_imdb_id,
                str,
            )
            and raw_imdb_id.strip()
            else None
        )

        return TMDBTVExternalIds(
            tvdb_id=tvdb_id,
            imdb_id=imdb_id,
        )

    def resolve_movie_tmdb_id(
        self,
        identity,
    ) -> tuple[int | None, str | None]:
        """Resolve a movie by direct TMDB or exact IMDb identity."""

        tmdb_id = getattr(
            identity,
            "tmdb_id",
            None,
        )

        if tmdb_id is not None:
            return (
                tmdb_id,
                "tmdb",
            )

        imdb_id = getattr(
            identity,
            "imdb_id",
            None,
        )

        if not imdb_id:
            return None, None

        response = self._get(
            f"/find/{imdb_id}",
            params={
                "external_source":
                    "imdb_id",
            },
        )

        response.raise_for_status()

        raw_results = (
            response.json().get(
                "movie_results"
            )
            or []
        )

        ids = tuple(
            sorted(
                {
                    result.get(
                        "id"
                    )
                    for result
                    in raw_results
                    if (
                        isinstance(
                            result,
                            dict,
                        )
                        and isinstance(
                            result.get(
                                "id"
                            ),
                            int,
                        )
                        and not isinstance(
                            result.get(
                                "id"
                            ),
                            bool,
                        )
                        and result.get(
                            "id"
                        ) > 0
                    )
                }
            )
        )

        if not ids:
            return None, "not_found"

        if len(ids) != 1:
            return (
                None,
                "ambiguous_external_id",
            )

        return ids[0], "imdb"

    def get_movie_artwork(
        self,
        *,
        tmdb_id: int,
    ) -> TMDBMovieArtwork:
        """Return TMDB poster/background artwork for one movie."""

        if (
            not isinstance(
                tmdb_id,
                int,
            )
            or isinstance(
                tmdb_id,
                bool,
            )
            or tmdb_id <= 0
        ):
            raise ValueError(
                "TMDB movie ID must be "
                "a positive integer"
            )

        response = self._get(
            f"/movie/{tmdb_id}"
        )

        if response.status_code == 404:
            return TMDBMovieArtwork(
                tmdb_id=tmdb_id
            )

        response.raise_for_status()

        payload = response.json()

        poster = None
        background = None

        poster_path = payload.get(
            "poster_path"
        )

        if isinstance(
            poster_path,
            str,
        ):
            poster_path = (
                poster_path.strip()
            )

            if poster_path:
                poster = ArtworkAsset(
                    kind=(
                        ArtworkKind
                        .MOVIE_POSTER
                    ),
                    source=(
                        ArtworkSource.TMDB
                    ),
                    url=self._image_url(
                        poster_path
                    ),
                    provider_asset_id=(
                        poster_path
                    ),
                )

        backdrop_path = payload.get(
            "backdrop_path"
        )

        if isinstance(
            backdrop_path,
            str,
        ):
            backdrop_path = (
                backdrop_path.strip()
            )

            if backdrop_path:
                background = ArtworkAsset(
                    kind=(
                        ArtworkKind
                        .MOVIE_BACKGROUND
                    ),
                    source=(
                        ArtworkSource.TMDB
                    ),
                    url=self._image_url(
                        backdrop_path
                    ),
                    provider_asset_id=(
                        backdrop_path
                    ),
                )

        return TMDBMovieArtwork(
            tmdb_id=tmdb_id,
            poster=poster,
            background=background,
        )

    def get_season_episode_artwork(
        self,
        *,
        tmdb_id: int,
        season_number: int,
    ) -> dict[int, TMDBEpisodeArtwork]:
        """Return title/still metadata for one TMDB season.

        Episodes remain present even when TMDB has no usable still so
        Artwork Generator may still use the TMDB title with a Plex
        thumbnail fallback.
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

        artwork: dict[
            int,
            TMDBEpisodeArtwork,
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

            if not isinstance(
                episode_number,
                int,
            ):
                continue

            raw_title = raw_episode.get(
                "name"
            )

            title = None

            if isinstance(
                raw_title,
                str,
            ):
                raw_title = raw_title.strip()

                if raw_title:
                    title = raw_title

            still_path = raw_episode.get(
                "still_path"
            )

            card = None

            if isinstance(
                still_path,
                str,
            ):
                still_path = (
                    still_path.strip()
                )

                if still_path:
                    card = ArtworkAsset(
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

            artwork[
                episode_number
            ] = TMDBEpisodeArtwork(
                episode_number=(
                    episode_number
                ),
                title=title,
                card=card,
            )

        return artwork

    def get_season_episode_cards(
        self,
        *,
        tmdb_id: int,
        season_number: int,
    ) -> dict[int, ArtworkAsset]:
        """Return available episode stills for one TMDB season.

        This compatibility view preserves the Artwork Manager 3.0
        contract while generation consumes the richer episode metadata.
        """

        artwork = (
            self.get_season_episode_artwork(
                tmdb_id=tmdb_id,
                season_number=season_number,
            )
        )

        return {
            episode_number: episode.card
            for (
                episode_number,
                episode,
            ) in artwork.items()
            if episode.card is not None
        }
