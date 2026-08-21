# Dakosys

```{=html}
<p align="center">
```
`<img src="docs/images/dakosys-logo.png" alt="Dakosys Logo" width="300">`{=html}
```{=html}
</p>
```
```{=html}
<p align="center">
```
Automated Plex metadata management, Kometa integration, Trakt list
generation, anime tracking, and artwork intelligence.
```{=html}
</p>
```

------------------------------------------------------------------------

## About

Dakosys is an automation platform built around Plex libraries and Kometa
workflows. It manages metadata generation, Trakt automation, anime
tracking, TV status tracking, and artwork selection while keeping
generated assets organized and reproducible.

Dakosys 3.0 introduces the Artwork Manager, a complete artwork
discovery, reconciliation, and application system designed to
intelligently maintain Plex posters and backgrounds.

## Features

### Artwork Manager (3.0)

The Artwork Manager provides automated artwork lifecycle management:

-   Plex library inventory and artwork analysis
-   Provider-based artwork discovery
-   MediUX-first artwork selection
-   TMDB fallback support
-   Movie and TV/show artwork management
-   Safe reconciliation before applying changes
-   Persistent artwork state tracking
-   Migration of legacy metadata

Artwork selection follows a quality-first approach:

1.  MediUX artwork when available
2.  TMDB artwork fallback
3.  Existing artwork preserved when no better source exists

Dakosys avoids destructive changes. Unknown or unresolved items remain
unresolved instead of being guessed.

## Installation

### Docker Compose

Use a semantic release tag:

``` yaml
image: ghcr.io/dustinsmithworkshop/dakosys:3.0.0
```

For reproducible deployments, pin to an exact version.

Example:

``` bash
docker compose pull
docker compose up -d
```

## Configuration

Dakosys uses `config.yaml` for service configuration.

Major services include:

-   Anime Episode Type generation
-   TV Status Tracker
-   Artwork Manager
-   Trakt automation
-   Kometa metadata generation

## Artwork Manager

Enable artwork management:

``` yaml
artwork:
  enabled: true
```

The default schedule:

``` yaml
schedule:
  type: daily
  times:
    - "04:00"
```

Manual runs are supported for testing and maintenance.

## Artwork Commands

Check status:

``` bash
python -m artwork.cli --config /app/config/config.yaml status
```

View recent runs:

``` bash
python -m artwork.cli --config /app/config/config.yaml history
```

Preview changes before applying:

``` bash
python -m artwork.cli --config /app/config/config.yaml scan
```

## Safety Model

Dakosys uses a plan-first workflow:

1.  Discover Plex inventory
2.  Resolve identities
3.  Evaluate available artwork
4.  Generate a change plan
5.  Apply only approved safe changes

Blocked and unresolved items remain visible for review.

## Kometa Integration

Dakosys works with Kometa metadata workflows.

Recommended mappings:

-   Dakosys generated metadata → Kometa overlays
-   Persistent artwork state → stable library management
-   Shared volumes for metadata and assets

Typical volume layout:

    /app/config
    /app/data
    /kometa

## Scheduling

Default scheduled services:

  Service              Schedule
  -------------------- -------------
  Anime Episode Type   Daily 03:00
  TV Status Tracker    Daily 02:00
  Artwork Manager      Daily 04:00

## Upgrading from 2.x

Dakosys 3.0 introduces a major artwork subsystem while preserving
existing automation workflows.

Before upgrading:

-   Backup your config directory
-   Preserve Kometa metadata paths
-   Review generated artwork state
-   Update Docker image tags

## Release Notes

See:

-   `CHANGELOG.md`
-   GitHub Releases

## Validation

Dakosys 3.0 release validation:

-   542 Python tests passed
-   Web production build completed successfully
-   Docker image smoke test completed
-   Artwork Manager production migration verified

## Development

Run tests:

``` bash
python -m pytest -q
```

Build web interface:

``` bash
cd web
npm ci
npm run build
```

## Credits

Dakosys builds on the Plex, Kometa, Trakt, TMDB, MediUX, and open source
communities.
