"""Configuration policy for Dakosys Artwork Generator."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


ARTWORK_GENERATOR_CONFIG_VERSION = 1

DEFAULT_GENERATOR_FONT = "marcellus"

SUPPORTED_GENERATOR_FONTS = frozenset(
    {
        "marcellus",
        "prata",
        "cormorant_garamond",
        "syne",
        "libre_baskerville",
        "cinzel",
    }
)


class ArtworkGeneratorConfigError(
    ValueError
):
    """Artwork Generator configuration is invalid."""


@dataclass(frozen=True)
class ArtworkGeneratorStyle:
    """Resolved creative policy for generated episode artwork."""

    font: str = DEFAULT_GENERATOR_FONT


@dataclass(frozen=True)
class ArtworkGeneratorConfig:
    """Versioned Artwork Generator creative policy."""

    version: int = (
        ARTWORK_GENERATOR_CONFIG_VERSION
    )

    defaults: ArtworkGeneratorStyle = field(
        default_factory=ArtworkGeneratorStyle
    )

    libraries: dict[
        str,
        ArtworkGeneratorStyle,
    ] = field(
        default_factory=dict
    )

    shows: dict[
        str,
        ArtworkGeneratorStyle,
    ] = field(
        default_factory=dict
    )

    def resolve_style(
        self,
        *,
        library: str | None = None,
        show_id: str | None = None,
    ) -> ArtworkGeneratorStyle:
        """Resolve Show > Library > Global creative inheritance."""

        font = self.defaults.font

        if library:
            library_style = (
                self.libraries.get(
                    library
                )
            )

            if library_style is not None:
                font = library_style.font

        if show_id:
            show_style = (
                self.shows.get(
                    show_id
                )
            )

            if show_style is not None:
                font = show_style.font

        return ArtworkGeneratorStyle(
            font=font
        )


def _mapping(
    value,
    *,
    label: str,
) -> dict:
    if value is None:
        return {}

    if not isinstance(
        value,
        dict,
    ):
        raise ArtworkGeneratorConfigError(
            f"{label} must be a YAML mapping"
        )

    return value


def _normalize_font(
    value,
    *,
    label: str,
) -> str:
    if not isinstance(
        value,
        str,
    ):
        raise ArtworkGeneratorConfigError(
            f"{label}.font must be a string"
        )

    font = (
        value
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )

    if (
        font
        not in SUPPORTED_GENERATOR_FONTS
    ):
        supported = ", ".join(
            sorted(
                SUPPORTED_GENERATOR_FONTS
            )
        )

        raise ArtworkGeneratorConfigError(
            f"{label}.font has unsupported "
            f"value {value!r}; supported fonts: "
            f"{supported}"
        )

    return font


def _parse_style(
    value,
    *,
    label: str,
    inherited: ArtworkGeneratorStyle,
) -> ArtworkGeneratorStyle:
    payload = _mapping(
        value,
        label=label,
    )

    unknown = (
        set(payload)
        - {"font"}
    )

    if unknown:
        names = ", ".join(
            sorted(
                str(item)
                for item in unknown
            )
        )

        raise ArtworkGeneratorConfigError(
            f"{label} contains unsupported "
            f"setting(s): {names}"
        )

    font = inherited.font

    if "font" in payload:
        font = _normalize_font(
            payload["font"],
            label=label,
        )

    return ArtworkGeneratorStyle(
        font=font
    )


def _parse_overrides(
    value,
    *,
    label: str,
    inherited: ArtworkGeneratorStyle,
) -> dict[str, ArtworkGeneratorStyle]:
    payload = _mapping(
        value,
        label=label,
    )

    parsed: dict[
        str,
        ArtworkGeneratorStyle,
    ] = {}

    for raw_key, raw_style in payload.items():
        if not isinstance(
            raw_key,
            str,
        ):
            raise ArtworkGeneratorConfigError(
                f"{label} keys must be strings"
            )

        key = raw_key.strip()

        if not key:
            raise ArtworkGeneratorConfigError(
                f"{label} keys cannot be empty"
            )

        parsed[key] = _parse_style(
            raw_style,
            label=f"{label}.{key}",
            inherited=inherited,
        )

    return parsed


def parse_artwork_generator_config(
    payload,
) -> ArtworkGeneratorConfig:
    """Parse one Artwork Generator YAML document."""

    document = _mapping(
        payload,
        label="artwork-generator",
    )

    unknown = (
        set(document)
        - {
            "version",
            "defaults",
            "libraries",
            "shows",
        }
    )

    if unknown:
        names = ", ".join(
            sorted(
                str(item)
                for item in unknown
            )
        )

        raise ArtworkGeneratorConfigError(
            "artwork-generator contains "
            f"unsupported setting(s): {names}"
        )

    version = document.get(
        "version",
        ARTWORK_GENERATOR_CONFIG_VERSION,
    )

    if (
        not isinstance(
            version,
            int,
        )
        or isinstance(
            version,
            bool,
        )
    ):
        raise ArtworkGeneratorConfigError(
            "artwork-generator.version "
            "must be an integer"
        )

    if (
        version
        != ARTWORK_GENERATOR_CONFIG_VERSION
    ):
        raise ArtworkGeneratorConfigError(
            "unsupported artwork-generator "
            f"config version: {version}"
        )

    base_style = (
        ArtworkGeneratorStyle()
    )

    defaults = _parse_style(
        document.get(
            "defaults"
        ),
        label="defaults",
        inherited=base_style,
    )

    libraries = _parse_overrides(
        document.get(
            "libraries"
        ),
        label="libraries",
        inherited=defaults,
    )

    shows = _parse_overrides(
        document.get(
            "shows"
        ),
        label="shows",
        inherited=defaults,
    )

    return ArtworkGeneratorConfig(
        version=version,
        defaults=defaults,
        libraries=libraries,
        shows=shows,
    )


def load_artwork_generator_config(
    path: Path,
) -> ArtworkGeneratorConfig:
    """Load creative policy, using defaults when no file exists."""

    if not path.exists():
        return ArtworkGeneratorConfig()

    try:
        payload = yaml.safe_load(
            path.read_text(
                encoding="utf-8"
            )
        )

    except Exception as exc:
        raise ArtworkGeneratorConfigError(
            "could not load Artwork Generator "
            f"config: {path}"
        ) from exc

    return parse_artwork_generator_config(
        payload
    )
