# DAKOSYS — Docker App Kometa Overlay System

DAKOSYS is a Docker-based companion for **Plex**, **Kometa**, and **AnimeFillerList** that automates artwork, anime episode classifications, TV status overlays, Next Airing data, scheduling, and related media-management workflows.

Trakt is optional and is used only by features that actually need it, such as Automatic Active/Future Anime Scheduling and legacy episode-list publishing.

![DAKOSYS dashboard](https://github.com/user-attachments/assets/03af3c98-39f2-4121-99e2-74390d90f87b)

> **About this fork**
>
> This repository is a maintained fork of [sahara101/Dakosys](https://github.com/sahara101/Dakosys). The upstream project established the original DAKOSYS architecture, dashboard, Anime Episode Type Tracker, TV/Anime Status Tracker, Size Overlay, scheduler, notifications, and management tools.
>
> This fork extends that foundation with Plex-aware anime episode mapping, automatic active/future scheduling, local TV metadata providers, provider-derived Next Airing data, autonomous artwork management, generated episode title cards, safer reviewed-apply workflows, and additional diagnostics and web tooling.

---

## Contents

- [What DAKOSYS Does](#what-dakosys-does)
- [Architecture at a Glance](#architecture-at-a-glance)
- [Artwork Manager](#artwork-manager)
- [Anime Episode Type Tracker](#anime-episode-type-tracker)
- [Automatic Anime Scheduling](#automatic-anime-scheduling)
- [TV / Anime Status Tracker](#tv--anime-status-tracker)
- [Size Overlay](#size-overlay)
- [Web Dashboard](#web-dashboard)
- [Requirements](#requirements)
- [Installation](#installation)
- [Docker Images and Versioning](#docker-images-and-versioning)
- [Kometa Volume Mount](#kometa-volume-mount)
- [Configuration](#configuration)
- [Kometa Integration](#kometa-integration)
- [Scheduler Configuration](#scheduler-configuration)
- [Anime Mapping and AFL Controls](#anime-mapping-and-afl-controls)
- [Manual Commands](#manual-commands)
- [Logs](#logs)
- [Troubleshooting](#troubleshooting)
- [Upgrading to 3.1](#upgrading-to-31)
- [Development and Release Validation](#development-and-release-validation)
- [Upstream Project and Credits](#upstream-project-and-credits)
- [Releases](#releases)

---

## What DAKOSYS Does

| Feature | Trakt required | Personal Trakt lists | Main output |
|---|---:|---:|---|
| Artwork Manager | **No** | No | Kometa artwork metadata + optional generated episode cards |
| Anime Episode Type Tracker | **No** | No | Local Kometa episode collections/overlays |
| Automatic Active/Future Schedule | Yes | No | Generated `scheduled-anime.yaml` |
| TV / Anime Status Tracker | **No** | No | Status overlays + local Next Airing |
| Size Overlay | **No** | No | Kometa size overlays |
| Legacy Episode-List Publishing | Yes | Yes | Optional filler/canon Trakt lists |
| Web Dashboard | Depends on enabled features | No by itself | Browser-based management UI |
| Discord Notifications | **No** | No | Service and schedule-change notifications |

Trakt account limits are discovered from the authenticated Trakt API response at runtime for features that use Trakt. DAKOSYS does not infer personal-list capacity from account labels such as VIP or non-VIP.

---

## Architecture at a Glance

```text
Artwork Manager
Plex libraries + MediUX + TMDB
        ↓
safe per-library artwork plans
        ↓
MediUX curated
        ↓
Dakosys Generated
        ↓
TMDB / existing fallback
        ↓
Kometa metadata + generated asset cache


Anime Episode Type
Plex + AnimeFillerList
        ↓
Plex-aware local mapper
        ↓
Kometa collections / overlays


Automatic Active/Future Schedule
Plex + AnimeFillerList + Trakt show metadata
        ↓
config/scheduled-anime.yaml


TV / Anime Status Tracker
Plex show IDs
        ↓
Sonarr + TMDB + TVmaze
        ↓
normalized TV metadata
        ↓
Status overlays + local Next Airing data
        ├── Kometa collections
        └── DAKOSYS dashboard


Legacy Episode-List Publishing
Anime classifications + Trakt personal lists
        ↓
Explicit opt-in compatibility mode
```

---

# Features

## Artwork Manager

> **Trakt is not required for Artwork Manager.**

Artwork Manager discovers configured Plex **show and movie libraries** and maintains independent Kometa metadata item stores for their artwork.

Plex library names are discovered dynamically and are not hard-coded by DAKOSYS.

Typical output:

```text
<output_dir>/
  artwork-<plex-library>/
```

Each managed show or movie is rendered to its own YAML file. DAKOSYS also maintains ownership and durable state so later runs can safely preserve, refresh, or migrate previous selections.

### Artwork priority

For episode artwork, DAKOSYS uses:

```text
MediUX curated
    >
Dakosys Generated
    >
TMDB / existing fallback
```

MediUX remains the preferred source.

Generated artwork:

- is used only when a higher-priority curated card is unavailable;
- never overrides manual/locked artwork;
- remains upgradeable if better MediUX artwork becomes available later.

### Automatic vs manual Apply

Artwork Manager supports two Apply modes:

| Mode | Behavior |
|---|---|
| `auto` | Safe scheduled plans are applied automatically |
| `manual` | Safe plans remain pending until reviewed and explicitly applied |

Apply mode does **not** weaken safety checks. Unsafe plans are blocked in both modes.

Example:

```yaml
services:
  artwork_manager:
    enabled: true
    apply_mode: auto
    output_dir: /kometa/metadata
```

### Reviewed Apply safety

The web UI separates planning from mutation.

```text
Current-State Scan / Preview
resolve Plex + provider state
        ↓
build desired metadata
        ↓
build generator plans
        ↓
calculate file changes + safety
        ↓
calculate exact review fingerprint
        ↓
NO WRITES
```

When `Apply Reviewed Plan` is selected, DAKOSYS rebuilds the plan against fresh state and verifies that it still matches the reviewed fingerprint.

If the plan changed, Apply is rejected as stale and **no writes occur**.

```text
Reviewed Apply
rebuild fresh plan
        ↓
verify exact fingerprint
        ↓
materialize required generated images
        ↓
verify generated files
        ↓
transactionally write metadata/state
        ↓
refresh current state
```

Only one reviewed Artwork Apply can run globally at a time. Read-only scans for different libraries may still run concurrently.

### Generated episode title cards

Generated episode cards are disabled by default.

Enable them explicitly:

```yaml
services:
  artwork_manager:
    generated_episode_cards:
      enabled: true
      kometa_asset_directory: /config/assets
      config_file: config/artwork-generator.yaml
```

The generator is a transformation stage, not an artwork provider.

Preferred title source:

```text
Plex episode title
    >
TMDB episode name
```

Preferred image source:

```text
usable TMDB still
    >
usable Plex thumbnail
```

If no valid source image is available, DAKOSYS keeps the lower-tier fallback instead of fabricating a card from an unsuitable image.

Generated cards are deterministic local **1920×1080 JPEGs** rendered with Pillow. No AI generation, face detection, ImageMagick, or FFmpeg is required.

Bundled fonts include:

- Marcellus
- Prata
- Cormorant Garamond
- Syne
- Libre Baskerville
- Cinzel

Japanese/CJK titles automatically use the bundled Noto Sans JP fallback when needed.

### Creative configuration

Creative settings live separately from the main service configuration:

```text
config/artwork-generator.yaml
```

Start from:

```text
artwork-generator.example.yaml
```

Creative inheritance:

```text
Show > Library > Global
```

Example:

```yaml
version: 1

defaults:
  font: marcellus

libraries:
  Anime:
    font: cormorant_garamond

shows:
  "tmdb:1398":
    font: prata
```

Show overrides use stable identities such as `tmdb:1398`, not display titles.

### Generated artwork cache

Generated files are stored beneath the configured Kometa asset directory.

Typical layout:

```text
generated-artwork/
  tv/
    tmdb-1398/
      season-01/
        S01E01-<fingerprint>.jpg
```

Cached files are reused when possible.

DAKOSYS references generated local artwork from Kometa metadata with `file_poster`.

### Invalid source images

Generator source images are fully decoded before use.

An exact corrupt or invalid Plex/TMDB source is quarantined temporarily so later scans fail safely instead of repeatedly retrying the same bad image.

If the source identity changes, the repaired source is reconsidered immediately.

### Artwork Manager web controls

The Artwork page provides:

- Enabled / Disabled service control
- current resolved configuration
- current-state scans
- `Refresh Current State`
- `Retry Scan` for failed/unsafe states
- per-library status
- provider and generator counts
- file-change counts
- coverage metrics for show libraries
- reviewed Apply
- live scan / Apply progress
- run history
- persistent collapsible library cards

Disabling Artwork Manager stops new work. It does not delete previously generated images, metadata, or durable Artwork Manager state.

---

## Anime Episode Type Tracker

> **Trakt is not required for core Anime Episode Type generation.**

DAKOSYS reads episode classifications from [AnimeFillerList](https://www.animefillerlist.com/), resolves the corresponding series in Plex, and generates local Kometa data for:

- Filler
- Manga Canon
- Anime Canon
- Mixed Canon/Filler

```text
Plex library
    ∩
AnimeFillerList catalog / configured mappings
    ∩
validated AnimeFillerList identity
        ↓
Plex-aware local episode mapper
        ↓
Kometa episode collections and overlays
```

No Trakt OAuth session, personal Trakt list, or Trakt account is required for this workflow.

![Anime episode type example](https://github.com/user-attachments/assets/5d90e452-173c-4665-b020-add2625ed261)

### Plex-aware episode mapping

AnimeFillerList generally describes anime as one absolute episode sequence, while Plex/TVDb may split the same show into seasons, specials, or another aired-order layout.

DAKOSYS does not assume:

```text
AFL episode 123 == Plex S01E123
```

Instead it resolves the intended Plex series, validates source identity, compares episode order, and maps classifications to real Plex coordinates such as:

```text
tvdb_episode: <tvdb_id>_<season>_<episode>
```

The mapper is deliberately conservative. If a safe result cannot be established, DAKOSYS leaves the episode unresolved rather than assigning the wrong classification.

### AnimeFillerList page validation

AnimeFillerList can sometimes return HTTP 200 for a slug that resolves to a different show's page.

DAKOSYS validates page identity before trusting episode data.

Legitimate exceptions can be handled explicitly through `mappings.yaml`; see [Anime Mapping and AFL Controls](#anime-mapping-and-afl-controls).

---

## Automatic Anime Scheduling

Automatic scheduling is an optional **Trakt-backed** feature that tracks owned anime that may still produce future episodes.

It is separate from core Anime Episode Type generation.

```text
Plex ownership
    ∩
AnimeFillerList support
    ∩
validated AnimeFillerList identity
    ∩
active/future Trakt show status
        ↓
config/scheduled-anime.yaml
```

The generated file is the authoritative automatic schedule source.

The old manually maintained `scheduler.scheduled_anime` workflow is retired.

Example:

```yaml
scheduler:
  auto_schedule:
    enabled: true
    file: config/scheduled-anime.yaml
    refresh_hours: 24
    notify_on_change: true
    always_include: []
    always_exclude: []
```

The automatic schedule does **not** filter the core local Anime Episode Type files. A Trakt scheduling failure therefore cannot prevent Anime Episode Type generation.

### Generated schedule state

`config/scheduled-anime.yaml` is runtime state and should not be edited manually or committed.

It records:

- scheduled anime;
- Plex and Trakt titles;
- Trakt status and scheduling decisions;
- unresolved candidates under `review:`;
- acknowledged AFL exceptions under `ignored:`;
- discovery statistics;
- Trakt request/retry statistics.

If discovery fails fatally, DAKOSYS preserves the previous generated schedule rather than replacing it with an empty result.

---

## TV / Anime Status Tracker

> **Trakt is not required for TV Status or Next Airing.**

The TV / Anime Status Tracker resolves Plex shows through a provider-independent metadata layer using stable external IDs from Plex.

Lifecycle precedence:

```text
TMDB -> Sonarr -> TVmaze
```

Upcoming-episode precedence:

```text
Sonarr -> TMDB -> TVmaze
```

It creates Kometa overlays for states including:

- Currently airing
- Ended
- Canceled
- Returning
- Season premiere
- Season finale
- Mid-season finale
- Final episode
- Upcoming air dates

Next Airing is generated locally from the same resolved metadata.

DAKOSYS writes ordered Kometa collection files and a provider-independent:

```text
data/next_airing.json
```

The normal path does **not** create, update, fetch, or title-match against a personal Trakt `Next Airing` list.

At least one primary metadata provider must be usable:

- **Sonarr** with URL + API key; or
- **TMDB** using the top-level v3 API key or `TMDB_TOKEN`.

TVmaze is a credential-free fallback.

![TV status example](https://github.com/user-attachments/assets/ce2e31fe-aeee-467f-b498-6ea36ac0139b)

---

## Size Overlay

> **Trakt is not required for Size Overlay.**

Creates Kometa overlays showing media file sizes for movies and TV shows. Size history can be tracked over time and episode counts can optionally be displayed.

![Size overlay example](https://github.com/user-attachments/assets/829cd5b1-2d67-456b-b41a-4a930b7a2b9a)

---

## Web Dashboard

The DAKOSYS web interface provides:

- service status and next scheduled runs;
- Artwork Manager current-state, Apply, history, progress, and service controls;
- local Anime Episode Type management;
- automatic active/future schedule visibility and overrides;
- TV Status and provider-derived Next Airing views;
- configuration management;
- built-in configuration reference;
- dedicated service logs, including Artwork Manager;
- anime identity and episode-title mapping tools;
- Trakt connection, feature, capability, and list-capacity status;
- library-size browsing;
- first-run setup.

The main dashboard does not require a live Trakt request simply to render normal status.

---

## Discord Notifications

DAKOSYS supports Discord webhook notifications.

Automatic anime scheduling can notify when generated schedule membership changes, including:

- shows added;
- shows removed;
- new scheduled total.

Keeping webhook URLs outside committed configuration is recommended.

---

# Requirements

Core requirements depend on which features you enable.

### Core Anime Episode Type

- Plex Media Server
- Docker / Docker Compose
- Kometa
- AnimeFillerList access

Trakt is **not** required.

### Artwork Manager

- Plex Media Server
- Kometa
- writable Kometa metadata directory
- MediUX API access for the primary curated provider
- TMDB recommended for identity enrichment and fallback artwork

Generated episode cards additionally require a writable Kometa asset directory.

Trakt is **not** required.

### Automatic Active/Future Schedule

- Trakt account
- Trakt API application/authentication

This feature reads show metadata and does not require Anime Episode Type personal-list publishing.

### TV / Anime Status Tracker

At least one usable primary metadata provider:

- Sonarr URL + API key; or
- TMDB v3 API key / `TMDB_TOKEN`.

TVmaze is an optional credential-free fallback.

Trakt is **not** required.

### Legacy Episode-List Publishing

Additionally requires:

- `trakt.episode_list_publishing.enabled: true`;
- Trakt authentication;
- sufficient runtime-reported personal-list and per-list capacity.

Legacy publishing is disabled by default.

---

# Installation

## Docker Compose

Clone the repository:

```bash
git clone https://github.com/dustinsmithworkshop/Dakosys.git
cd Dakosys
```

Create local runtime directories:

```bash
mkdir -p config data
```

Starter files at the repository root include:

```text
config.example.yaml
mappings.example.yaml
artwork-generator.example.yaml
```

Copy the primary runtime files:

```bash
cp config.example.yaml config/config.yaml
cp mappings.example.yaml config/mappings.yaml
```

If you want custom generated episode-card styling:

```bash
cp artwork-generator.example.yaml config/artwork-generator.yaml
```

Replace all credential placeholders before use.

The interactive setup wizard is the recommended way to complete service configuration:

```bash
docker compose run --rm dakosys setup
```

Start the updater/web service:

```bash
docker compose up -d dakosys-updater
```

---

## Docker Images and Versioning

Images are published to GitHub Container Registry:

```text
ghcr.io/dustinsmithworkshop/dakosys
```

DAKOSYS 3.1 tags:

```text
ghcr.io/dustinsmithworkshop/dakosys:3.1.0   # exact release
ghcr.io/dustinsmithworkshop/dakosys:3.1     # latest compatible 3.1.x
ghcr.io/dustinsmithworkshop/dakosys:3       # latest compatible 3.x
ghcr.io/dustinsmithworkshop/dakosys:latest  # latest release/default branch build
```

For reproducible deployments, pin the exact release.

---

## Kometa Volume Mount

DAKOSYS must be able to write to the same host directory used by Kometa.

Example on Unraid:

```text
Host:      /mnt/user/appdata/kometa
DAKOSYS:   /kometa
```

Example Compose mapping:

```yaml
volumes:
  - ./config:/app/config
  - ./data:/app/data
  - /mnt/user/appdata/kometa:/kometa
```

Typical DAKOSYS paths:

```text
Assets:      /kometa/assets
Metadata:    /kometa/metadata
Collections: /kometa/collections
Overlays:    /kometa/overlays
```

Kometa may see the same host directory as `/config` inside the Kometa container. That is normal.

For generated episode cards, a common mapping is:

```text
DAKOSYS: /kometa/assets/generated-artwork/
Kometa:  /config/assets/generated-artwork/
```

Configure the Kometa-visible asset path:

```yaml
services:
  artwork_manager:
    generated_episode_cards:
      kometa_asset_directory: /config/assets
```

---

# Configuration

## `config/config.yaml`

The main configuration contains:

- Plex URL/token and configured libraries
- Artwork Manager providers and Apply mode
- generated-card configuration
- optional Trakt configuration
- Sonarr / TMDB / TVmaze TV metadata configuration
- top-level TMDB API key
- Kometa output paths
- enabled services
- scheduler configuration
- notifications

Start from:

```text
config.example.yaml
```

### Artwork Manager example

```yaml
services:
  artwork_manager:
    enabled: true
    apply_mode: auto
    output_dir: /kometa/metadata

    generated_episode_cards:
      enabled: true
      kometa_asset_directory: /config/assets
      config_file: config/artwork-generator.yaml

    providers:
      mediux:
        api_token: REPLACE_WITH_MEDIUX_API_TOKEN
```

`MEDIUX_API_TOKEN` may be supplied through the container environment and takes precedence over the YAML token.

Never commit real provider credentials.

### TV metadata provider example

```yaml
tmdb_api_key: REPLACE_WITH_TMDB_API_KEY

services:
  tv_status_tracker:
    enabled: true
    collections_dir: /kometa/collections

    metadata:
      sonarr:
        enabled: true
        url: http://192.168.1.100:8989
        api_key: REPLACE_WITH_SONARR_API_KEY

      tmdb:
        enabled: true

      tvmaze:
        enabled: true
```

Provider precedence is intentionally internal:

```text
Lifecycle:     TMDB -> Sonarr -> TVmaze
Next episode:  Sonarr -> TMDB -> TVmaze
```

Environment overrides:

```text
SONARR_URL
SONARR_API_KEY
TMDB_TOKEN
```

## `config/artwork-generator.yaml`

Optional creative settings for generated episode cards.

Start from:

```text
artwork-generator.example.yaml
```

This file controls rendering style only. It does not enable the generator by itself.

## `config/mappings.yaml`

Contains installation-specific anime identity and mapping exceptions.

Start from:

```text
mappings.example.yaml
```

Do not blindly copy another installation's mappings. Plex titles, TVDb IDs, metadata agents, ordering, and library contents can differ.

## Runtime / generated files

These should stay local and should not be committed:

```text
config/config.yaml
config/mappings.yaml
config/artwork-generator.yaml
config/scheduled-anime.yaml
data/next_airing.json
data/artwork-manager/
data/artwork_manager.log
```

Generated Artwork Manager image assets under the Kometa asset directory are also runtime data.

---

# Kometa Integration

Add DAKOSYS-generated files to the appropriate Kometa libraries.

Example:

```yaml
TV:
  collection_files:
    - file: config/collections/tv-next-airing.yml

  overlay_files:
    - file: config/overlays/size-overlays-tv.yml
    - file: config/overlays/overlay_tv_status_tv.yml

Anime:
  collection_files:
    - file: config/collections/anime-next-airing.yml
    - file: config/collections/anime_episode_type.yml

  overlay_files:
    - file: config/overlays/size-overlays-anime.yml
    - file: config/overlays/fillers.yml
    - file: config/overlays/manga_canon.yml
    - file: config/overlays/anime_canon.yml
    - file: config/overlays/mixed.yml
    - file: config/overlays/overlay_tv_status_anime.yml
```

Library names and filenames vary with configuration. Use the files generated by your installation.

Next Airing collection YAML uses Kometa `text_file` membership with `collection_order: custom`, preserving provider-derived air-date ordering.

Artwork Manager writes metadata separately under its configured `output_dir`.

---

# Scheduler Configuration

Each service has its own schedule block.

Supported scheduler styles include:

| Type | Fields |
|---|---|
| `daily` | `times: ["HH:MM", ...]` |
| `hourly` | `minute: N` |
| `weekly` | `days: ["monday", ...]`, `time: "HH:MM"` |
| `monthly` | `dates: [1, 15]`, `time: "HH:MM"` |
| `cron` | `expression: "0 3 * * *"` |
| `run` | Runs once at startup |

Example:

```yaml
scheduler:
  artwork_manager:
    type: daily
    times:
      - "01:00"

  tv_status_tracker:
    type: daily
    times:
      - "02:00"

  anime_episode_type:
    type: daily
    times:
      - "03:00"

  auto_schedule:
    enabled: true
    file: config/scheduled-anime.yaml
    refresh_hours: 24
    notify_on_change: true
    always_include: []
    always_exclude: []

  size_overlay:
    type: weekly
    days:
      - sunday
    time: "00:30"
```

A useful deployment pattern is to schedule Artwork Manager **before** the normal Kometa run so Kometa can consume newly written metadata during its next cycle.

---

# Anime Mapping and AFL Controls

DAKOSYS provides several mapping mechanisms for different kinds of identity exceptions.

| Key | Purpose |
|---|---|
| `mappings` | Map a DAKOSYS/AFL slug to an exact Plex show title |
| `afl_mappings` | Use a different AnimeFillerList URL slug |
| `afl_identity_aliases` | Trust another legitimate AFL display title |
| `afl_ignored` | Explicitly skip a known unusable AFL entry |
| `tvdb_mappings` | Resolve an ambiguous Plex show by TVDb series ID |
| `title_mappings` | Advanced episode-title overrides |
| `ignored_mappings` | Legacy/advanced mapping workflow |

### Plex title mappings

```yaml
mappings:
  code-geass: "Code Geass: Lelouch of the Rebellion"
  dr-stone: "Dr. STONE"
  haikyuu: "Haikyu!!"
```

The value should be the exact Plex title for the same series.

Do not map a slug to a different reboot, sequel, remake, or adaptation simply to make validation pass.

### AnimeFillerList slug overrides

```yaml
afl_mappings:
  blue-lock: blue-lock-0
  shaman-king: shaman-king-2021
  your-eternity-0: your-eternity
```

### AnimeFillerList identity aliases

```yaml
afl_identity_aliases:
  fighting-spirit:
    - "Hajime no Ippo: The Fighting!"
```

Identity aliases add an explicitly trusted identity. They do not disable identity validation.

### Ignoring known AFL failures

```yaml
afl_ignored:
  - city-hunter
  - mobile-suit-gundam-zz
  - mobile-suit-zeta-gundam
```

Use `afl_ignored` for known source limitations, not to hide a mapping problem that can be repaired.

### TVDb overrides

```yaml
tvdb_mappings:
  rurouni-kenshin: 70863
  urusei-yatsura: 75113
```

TVDb overrides are authoritative. DAKOSYS will not silently fall back to an unrelated Plex title when the requested series cannot be found.

### Episode-title overrides

`title_mappings.special_matches` remains as a compatibility schema name, but the values are used as generic episode-title overrides by the local mapper as well as the optional legacy Trakt publishing path.

---

# Manual Commands

List commands supported by the exact image you are running:

```bash
docker compose run --rm dakosys --help
```

## Artwork Manager CLI

Check configuration/status:

```bash
python -m artwork.cli --config /app/config/config.yaml status
```

Run a read-only scan:

```bash
python -m artwork.cli --config /app/config/config.yaml scan
```

Review previous runs:

```bash
python -m artwork.cli --config /app/config/config.yaml history
```

## Anime Episode Type

Regenerate local Anime Episode Type data and Kometa collections:

```bash
docker compose run --rm dakosys sync-collections
```

Run the enabled Anime Episode Type service:

```bash
docker compose run --rm dakosys run-update anime_episode_type
```

List AnimeFillerList entries:

```bash
docker compose run --rm dakosys list-anime
```

Show classifications:

```bash
docker compose run --rm dakosys show-episodes "demon-slayer-kimetsu-no-yaiba"
```

## Automatic Schedule

```bash
docker compose run --rm dakosys refresh-schedule --force --no-notify
```

## Service Updates

Run all generic enabled services:

```bash
docker compose run --rm dakosys run-update all
```

Run TV Status:

```bash
docker compose run --rm dakosys run-update tv_status_tracker
```

Run Size Overlay:

```bash
docker compose run --rm dakosys run-update size_overlay
```

Artwork Manager intentionally uses its own scan/Apply workflow rather than the generic service-run API.

## Trakt diagnostics

```bash
docker compose run --rm dakosys trakt-capabilities --json
docker compose run --rm dakosys trakt-list-capacity --json
docker compose run --rm dakosys trakt-list-usage --json
docker compose run --rm dakosys test-trakt
```

## Legacy episode-list publishing

This compatibility path requires:

```yaml
trakt:
  episode_list_publishing:
    enabled: true
```

Examples:

```bash
docker compose run --rm dakosys create "naruto-shippuden" FILLER
docker compose run --rm dakosys create-all "one-piece"
docker compose run --rm dakosys prune-legacy-lists
docker compose run --rm dakosys prune-legacy-lists --apply
```

---

# Logs

Service logs are stored under `data/`.

Common logs include:

```text
data/anime_trakt_manager.log
data/tv_status_tracker.log
data/size_overlay.log
data/artwork_manager.log
data/notifications.log
data/auto_update.log
data/scheduler.log
data/failed_episodes.log
```

The web Logs page includes:

- All Logs
- Anime Episodes
- TV Status
- Size Overlay
- Artwork

Artwork Manager logs current-state scans, reviewed Apply activity, scheduled runs, blocked/stale outcomes, and failures.

Follow the updater/web container:

```bash
docker compose logs -f dakosys-updater
```

---

# Troubleshooting

## Artwork Manager plan is blocked

A blocked plan is intentionally not applied, even when:

```yaml
apply_mode: auto
```

Refresh Current State and review the safety/issues section in the Artwork page.

Automatic mode applies **safe** plans automatically; it does not bypass safety rules.

## Artwork Manager plan became stale

A reviewed Apply uses an exact fingerprint.

If Plex/provider state changes after review, DAKOSYS rejects the Apply as stale.

Refresh Current State and review the new plan.

## Generated card source image fails

DAKOSYS fully decodes generated-card source images.

Known corrupt exact sources are temporarily quarantined. If Plex or the provider later supplies a new source identity, DAKOSYS automatically reconsiders it.

## Trakt authentication

Trakt authentication is required only when a Trakt-backed feature is enabled:

- Automatic Active/Future Schedule;
- legacy episode-list publishing.

Missing Trakt credentials should not prevent Artwork Manager, Anime Episode Type, TV Status, Next Airing, or Size Overlay from running.

## TV metadata providers

For Sonarr:

```yaml
services:
  tv_status_tracker:
    metadata:
      sonarr:
        enabled: true
        url: http://sonarr:8989
        api_key: YOUR_SONARR_API_KEY
```

Or:

```text
SONARR_URL
SONARR_API_KEY
```

For TMDB:

```yaml
tmdb_api_key: YOUR_TMDB_API_KEY

services:
  tv_status_tracker:
    metadata:
      tmdb:
        enabled: true
```

Or:

```text
TMDB_TOKEN
```

## Next Airing

TV Status writes:

```text
data/next_airing.json
<collections_dir>/*-next-airing.txt
<collections_dir>/*-next-airing.yml
```

If Next Airing data is missing, run TV Status and verify these files are created.

## AnimeFillerList identity errors

Do not disable the safety check globally.

Use the appropriate explicit mechanism:

- wrong AFL URL slug → `afl_mappings`;
- legitimate alternate AFL display title → `afl_identity_aliases`;
- ambiguous Plex title → `mappings` or `tvdb_mappings`;
- intentionally accepted unusable AFL source → `afl_ignored`.

## Scheduler

Test scheduler configuration:

```bash
docker compose run --rm dakosys test-scheduler
```

---

# Upgrading to 3.1

DAKOSYS 3.1 expands Artwork Manager with generated episode title cards, reviewed web Apply, movie support, current-state controls, source-image hardening, service controls, collapsible library cards, and dedicated activity logging.

Before upgrading, back up:

```text
config/config.yaml
config/mappings.yaml
config/artwork-generator.yaml
data/
```

Also back up the Kometa metadata and asset directories written by DAKOSYS.

### Recommended first 3.1 Artwork run

For an existing installation, use manual review first:

```yaml
services:
  artwork_manager:
    enabled: true
    apply_mode: manual
```

For each library:

1. Refresh Current State.
2. Review safety and file changes.
3. Apply the reviewed plan.
4. Wait for the post-Apply refresh.
5. Confirm the library reports Current.
6. Run Kometa.
7. Verify the resulting artwork in Plex.

Once the environment is validated, switch to:

```yaml
services:
  artwork_manager:
    apply_mode: auto
```

Safe scheduled plans will then be applied automatically. Unsafe plans remain blocked.

### Generated episode cards

Generated cards remain disabled unless explicitly enabled:

```yaml
services:
  artwork_manager:
    generated_episode_cards:
      enabled: true
```

Disabling Artwork Manager or disabling generated cards stops new work. It does not delete previously generated artwork, Kometa metadata, or durable state.

### Upgrading from older 1.x / 2.x installations

Key architecture changes retained in current DAKOSYS include:

- core Anime Episode Type generation is local and no longer requires Trakt personal lists;
- the manually maintained `scheduler.scheduled_anime` workflow is retired;
- legacy Trakt episode-list publishing is explicit opt-in;
- TV Status resolves metadata through Sonarr/TMDB/TVmaze rather than requiring Trakt;
- Next Airing is generated locally.

See [`CHANGELOG.md`](CHANGELOG.md) for historical release-specific migration notes.

---

# Development and Release Validation

For source changes:

```bash
python3 -m py_compile \
  anime_trakt_manager.py \
  asset_manager.py \
  auto_update.py \
  mappings_manager.py \
  scheduled_anime_manager.py \
  scheduler.py \
  setup.py \
  shared_utils.py \
  tv_status_tracker.py \
  web_server.py

git diff --check
```

Run the Python test suite with:

```bash
python -m pytest -q
```

Frontend validation:

```bash
cd web
npm run build
cd ..
```

A release should also be tested using the exact Docker image intended for publication.

For Artwork Manager changes, validate at minimum:

- daemon/container startup;
- current-state scans;
- reviewed Apply;
- automatic Apply behavior when enabled;
- show and movie libraries;
- MediUX selection;
- TMDB fallback/enrichment;
- generated-card planning/materialization when enabled;
- Kometa metadata ingestion;
- Plex artwork results;
- cache reuse and idempotent follow-up scans;
- dedicated Artwork logs;
- scheduler behavior.

Do not infer Docker correctness solely from local Python/TypeScript tests.

---

# Upstream Project and Credits

DAKOSYS was originally created by **sahara101**.

Upstream repository:

[https://github.com/sahara101/Dakosys](https://github.com/sahara101/Dakosys)

This fork preserves the upstream project's major service concepts while substantially extending the anime/Plex mapping, scheduling, TV metadata, Next Airing, Artwork Manager, generated artwork, Trakt integration, and dashboard paths.

---

# Releases

See [`CHANGELOG.md`](CHANGELOG.md) for release history, upgrade notes, fixes, and release-specific validation.
