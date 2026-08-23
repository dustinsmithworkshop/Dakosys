"""Read-only evidence loading for pre-state-store Artwork Manager output.

Artwork Manager 3.0 installations may have a valid per-item ownership
manifest and Kometa YAML files but no durable semantic state sidecar.

This module reads only Dakosys-owned files named by the manifest,
verifies their hashes, and records deterministic artwork provenance.

It deliberately does not infer cohesive-set identity. That requires a
separate provider-backed reconciliation step.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse

import yaml

from artwork.item_store import (
    load_item_store_manifest,
)
from artwork.models import (
    ArtworkKind,
    ArtworkSource,
)


class ArtworkItemStoreBootstrapError(
    RuntimeError
):
    """Existing item-store output cannot be bootstrapped safely."""


@dataclass(frozen=True)
class PersistedArtworkEvidence:
    """One artwork reference recovered from an owned Kometa YAML."""

    kind: ArtworkKind
    source: ArtworkSource
    url: str

    provider_asset_id: str | None = None

    season_number: int | None = None
    episode_number: int | None = None

    @property
    def family(self) -> str:
        if self.kind is ArtworkKind.EPISODE_CARD:
            return "episode"

        return "presentation"


@dataclass(frozen=True)
class ShowItemStoreBootstrapSeed:
    """Read-only evidence for one owned pre-state-store show."""

    plex_rating_key: str
    tvdb_id: int
    filename: str

    assets: tuple[
        PersistedArtworkEvidence,
        ...,
    ]

    @property
    def mediux_episode_asset_ids(
        self,
    ) -> frozenset[str]:
        return frozenset(
            asset.provider_asset_id
            for asset in self.assets
            if (
                asset.family == "episode"
                and asset.source
                is ArtworkSource.MEDIUX
                and asset.provider_asset_id
                is not None
            )
        )

    @property
    def mediux_presentation_asset_ids(
        self,
    ) -> frozenset[str]:
        return frozenset(
            asset.provider_asset_id
            for asset in self.assets
            if (
                asset.family == "presentation"
                and asset.source
                is ArtworkSource.MEDIUX
                and asset.provider_asset_id
                is not None
            )
        )


def _sha256_bytes(
    value: bytes,
) -> str:
    return sha256(
        value
    ).hexdigest()


def _positive_or_zero_int(
    value,
    *,
    field: str,
) -> int:
    try:
        result = int(
            value
        )

    except (
        TypeError,
        ValueError,
    ) as exc:
        raise ArtworkItemStoreBootstrapError(
            f"{field} must be numeric"
        ) from exc

    if result < 0:
        raise ArtworkItemStoreBootstrapError(
            f"{field} must not be negative"
        )

    return result


def _mapping(
    value,
    *,
    field: str,
) -> dict:
    if value is None:
        return {}

    if not isinstance(
        value,
        dict,
    ):
        raise ArtworkItemStoreBootstrapError(
            f"{field} must contain a mapping"
        )

    return value


def _reject_local_file(
    value: dict,
    *,
    field: str,
) -> None:
    raw = value.get(
        "file_poster"
    )

    if raw is None:
        return

    if str(
        raw
    ).strip():
        raise ArtworkItemStoreBootstrapError(
            f"{field} contains file_poster; "
            "pre-state-store bootstrap cannot "
            "safely infer local-file provenance"
        )


def _source_from_url(
    url: str,
) -> tuple[
    ArtworkSource,
    str | None,
]:
    parsed = urlparse(
        url
    )

    if parsed.scheme not in {
        "http",
        "https",
    }:
        raise ArtworkItemStoreBootstrapError(
            "persisted artwork URL must use "
            f"http or https: {url!r}"
        )

    host = (
        parsed.hostname
        or ""
    ).casefold()

    if host == "api.mediux.pro":
        parts = tuple(
            part
            for part in parsed.path.split("/")
            if part
        )

        if (
            len(parts) != 2
            or parts[0].casefold()
            != "assets"
            or not parts[1].strip()
        ):
            raise ArtworkItemStoreBootstrapError(
                "unrecognized MediUX asset URL "
                f"in pre-state-store output: {url!r}"
            )

        return (
            ArtworkSource.MEDIUX,
            parts[1],
        )

    if host == "image.tmdb.org":
        parts = tuple(
            part
            for part in parsed.path.split("/")
            if part
        )

        if (
            len(parts) < 4
            or parts[0].casefold() != "t"
            or parts[1].casefold() != "p"
            or not parts[2].strip()
        ):
            raise ArtworkItemStoreBootstrapError(
                "unrecognized TMDB image URL "
                f"in pre-state-store output: {url!r}"
            )

        file_path = (
            "/"
            + "/".join(
                parts[3:]
            )
        )

        if file_path == "/":
            raise ArtworkItemStoreBootstrapError(
                "TMDB image URL has no "
                f"provider file path: {url!r}"
            )

        return (
            ArtworkSource.TMDB,
            file_path,
        )

    raise ArtworkItemStoreBootstrapError(
        "cannot safely infer artwork provider "
        f"from persisted URL: {url!r}"
    )


def _url_evidence(
    *,
    kind: ArtworkKind,
    url,
    season_number: int | None = None,
    episode_number: int | None = None,
) -> PersistedArtworkEvidence | None:
    if url is None:
        return None

    if not isinstance(
        url,
        str,
    ):
        raise ArtworkItemStoreBootstrapError(
            "persisted artwork URL must be a string"
        )

    normalized = url.strip()

    if not normalized:
        return None

    (
        source,
        provider_asset_id,
    ) = _source_from_url(
        normalized
    )

    return PersistedArtworkEvidence(
        kind=kind,
        source=source,
        url=normalized,
        provider_asset_id=(
            provider_asset_id
        ),
        season_number=season_number,
        episode_number=episode_number,
    )


def _parse_show_file(
    *,
    path: Path,
    plex_rating_key: str,
    tvdb_id: int,
) -> ShowItemStoreBootstrapSeed:
    try:
        raw = yaml.safe_load(
            path.read_text(
                encoding="utf-8"
            )
        )

    except (
        OSError,
        yaml.YAMLError,
    ) as exc:
        raise ArtworkItemStoreBootstrapError(
            "could not read owned Artwork Manager "
            f"item file: {path}"
        ) from exc

    root = _mapping(
        raw,
        field=str(
            path
        ),
    )

    metadata = _mapping(
        root.get(
            "metadata"
        ),
        field=(
            f"{path}.metadata"
        ),
    )

    matching = []

    for raw_key, raw_value in metadata.items():
        try:
            key = int(
                raw_key
            )

        except (
            TypeError,
            ValueError,
        ):
            continue

        if key == tvdb_id:
            matching.append(
                raw_value
            )

    if (
        len(metadata) != 1
        or len(matching) != 1
    ):
        raise ArtworkItemStoreBootstrapError(
            "owned per-item YAML must contain "
            "exactly its manifest TVDB identity: "
            f"{path}"
        )

    show = _mapping(
        matching[0],
        field=(
            f"{path}.metadata[{tvdb_id}]"
        ),
    )

    assets: list[
        PersistedArtworkEvidence
    ] = []

    poster = _url_evidence(
        kind=ArtworkKind.SHOW_POSTER,
        url=show.get(
            "url_poster"
        ),
    )

    if poster is not None:
        assets.append(
            poster
        )

    background = _url_evidence(
        kind=(
            ArtworkKind
            .SHOW_BACKGROUND
        ),
        url=show.get(
            "url_background"
        ),
    )

    if background is not None:
        assets.append(
            background
        )

    seasons = _mapping(
        show.get(
            "seasons"
        ),
        field=(
            f"{path}.seasons"
        ),
    )

    for (
        raw_season_number,
        raw_season,
    ) in seasons.items():
        season_number = (
            _positive_or_zero_int(
                raw_season_number,
                field=(
                    f"{path}.season"
                ),
            )
        )

        season = _mapping(
            raw_season,
            field=(
                f"{path}.season[{season_number}]"
            ),
        )

        _reject_local_file(
            season,
            field=(
                f"{path}.season[{season_number}]"
            ),
        )

        season_poster = (
            _url_evidence(
                kind=(
                    ArtworkKind
                    .SEASON_POSTER
                ),
                url=season.get(
                    "url_poster"
                ),
                season_number=(
                    season_number
                ),
            )
        )

        if season_poster is not None:
            assets.append(
                season_poster
            )

        episodes = _mapping(
            season.get(
                "episodes"
            ),
            field=(
                f"{path}.season"
                f"[{season_number}]"
                ".episodes"
            ),
        )

        for (
            raw_episode_number,
            raw_episode,
        ) in episodes.items():
            episode_number = (
                _positive_or_zero_int(
                    raw_episode_number,
                    field=(
                        f"{path}.season"
                        f"[{season_number}]"
                        ".episode"
                    ),
                )
            )

            episode = _mapping(
                raw_episode,
                field=(
                    f"{path}.season"
                    f"[{season_number}]"
                    f".episode[{episode_number}]"
                ),
            )

            _reject_local_file(
                episode,
                field=(
                    f"{path}.season"
                    f"[{season_number}]"
                    f".episode[{episode_number}]"
                ),
            )

            card = _url_evidence(
                kind=(
                    ArtworkKind
                    .EPISODE_CARD
                ),
                url=episode.get(
                    "url_poster"
                ),
                season_number=(
                    season_number
                ),
                episode_number=(
                    episode_number
                ),
            )

            if card is not None:
                assets.append(
                    card
                )

    return ShowItemStoreBootstrapSeed(
        plex_rating_key=(
            plex_rating_key
        ),
        tvdb_id=tvdb_id,
        filename=path.name,
        assets=tuple(
            assets
        ),
    )


def load_show_item_store_bootstrap_seeds(
    *,
    directory: str | Path,
    expected_library: str,
) -> tuple[
    ShowItemStoreBootstrapSeed,
    ...,
]:
    """Load and verify all manifest-owned pre-state-store show output.

    This function is strictly read-only.
    """

    directory = Path(
        directory
    )

    manifest = (
        load_item_store_manifest(
            directory,
            expected_library=(
                expected_library
            ),
        )
    )

    if manifest is None:
        return ()

    seeds = []

    for item in manifest.items:
        path = (
            directory
            / item.filename
        )

        try:
            contents = (
                path.read_bytes()
            )

        except OSError as exc:
            raise ArtworkItemStoreBootstrapError(
                "manifest-owned Artwork Manager "
                f"item file is missing: {path}"
            ) from exc

        actual_sha256 = (
            _sha256_bytes(
                contents
            )
        )

        if actual_sha256 != item.sha256:
            raise ArtworkItemStoreBootstrapError(
                "manifest-owned Artwork Manager "
                "item file does not match its "
                f"recorded hash: {path}"
            )

        seeds.append(
            _parse_show_file(
                path=path,
                plex_rating_key=(
                    item.plex_rating_key
                ),
                tvdb_id=item.tvdb_id,
            )
        )

    seeds.sort(
        key=lambda seed: (
            seed.plex_rating_key
        )
    )

    return tuple(
        seeds
    )
