# DAKOSYS — Docker App Kometa Overlay System

DAKOSYS is a Docker-based companion for **Plex** and **Kometa** that automates artwork, AnimeFillerList episode classification, TV / Anime status, Next Airing, scheduling, overlays, and related media-management workflows.

**Trakt is optional.** Core Artwork Manager, Anime Episode Type, TV / Anime Status, and Next Airing workflows do not require Trakt.

```text
Artwork Manager
Plex show + movie libraries
        ↓
MediUX curated artwork
        ↓
cohesive selection + safety policy
        ↓
TMDB identity enrichment / gap fallback
        ↓
per-library Kometa metadata item stores

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

> **About this fork**
>
> This repository is a maintained fork of [sahara101/Dakosys](https://github.com/sahara101/Dakosys). The upstream project provides the original DAKOSYS architecture, dashboard, Anime Episode Type Tracker, TV/Anime Status Tracker, Size Overlay, scheduler, notifications, and management tools.
>
> This fork extends that foundation with Plex-aware episode mapping, conservative AnimeFillerList validation, automatic active/future scheduling, local Anime Episode Type generation, hybrid TV metadata providers, provider-derived Next Airing data, autonomous Plex artwork management, safer batch processing, and additional management and diagnostic tools.

---

## What DAKOSYS Does

| Feature | Trakt required | Personal Trakt lists | Main output |
|---|---:|---:|---|
| Artwork Manager | **No** | No | Per-library Kometa artwork metadata |
| Anime Episode Type Tracker | **No** | No | Local Kometa episode collections/overlays |
| Automatic Active/Future Schedule | Yes | No | Generated `scheduled-anime.yaml` |
| TV / Anime Status Tracker | **No** | No | Status overlays + local Next Airing |
| Legacy Episode-List Publishing | Yes | Yes | Filler/canon Trakt lists |
| Size Overlay | No | No | Kometa size overlays |
| Web Dashboard | Depends on enabled features | No by itself | Browser-based management UI |
| Discord Notifications | No | No | Service/update notifications |

Trakt account limits are discovered from the authenticated Trakt API response at runtime for features that actually use Trakt. DAKOSYS does not assume personal-list capacity from account labels such as VIP or non-VIP.

---

# Features

## Artwork Manager

> **Trakt is not required for Artwork Manager.**

Artwork Manager discovers supported Plex **show and movie libraries** from the configured Plex library definitions and maintains Kometa metadata for their artwork. Plex library names are not hard-coded; installation-specific names such as `Movies`, `Films`, `TV`, `Series`, `Anime`, or `Cartoons` are handled according to their configured media type.

The normal provider path is:

```text
Plex inventory
      ↓
MediUX
      ↓
cohesive curated artwork selection
      ↓
TMDB fallback for eligible gaps
      ↓
safety / apply policy
      ↓
per-library Kometa metadata store
```

### Provider behavior

**MediUX is the required primary Artwork Manager provider.**

For shows, DAKOSYS prefers cohesive MediUX artwork sets and can refresh or migrate a managed selection when a better, more complete, or more current set becomes available. This is especially useful for actively airing series where one MediUX set can later fall behind another.

For movies, MediUX provides curated poster and background artwork when available.

TMDB is a fallback rather than a competitor to already usable MediUX artwork:

- show workflows can use TMDB identity enrichment and eligible episode-card fallback;
- movie workflows use TMDB to fill missing poster/background slots;
- existing usable MediUX artwork is preserved when TMDB fills a different missing slot.

The top-level `tmdb_api_key` or the `TMDB_TOKEN` environment override enables TMDB coverage.

Artwork Manager remains usable without TMDB, but coverage then depends entirely on MediUX.

### Safe automatic application

Artwork Manager separates **safety** from **apply mode**.

With:

```yaml
services:
  artwork_manager:
    apply_mode: auto
```

safe plans with changes are applied automatically.

With:

```yaml
services:
  artwork_manager:
    apply_mode: manual
```

safe plans are retained for review instead of being written automatically.

Operational outcomes are:

```text
APPLIED
NO_CHANGES
PENDING_REVIEW
BLOCKED
FAILED
```

`BLOCKED` means the safety layer refused to perform a write. A blocked workflow does not modify the managed item store.

Examples of conditions that can block a write include inconsistent durable state, ownership conflicts, managed-state loss, unsafe identity changes, or provider failures that make the proposed state unreliable.

An individual title being unavailable from a provider is not automatically a library-wide failure. Unsupported or unavailable titles can remain unmanaged while the rest of the library continues safely.

### Durable state and item stores

Artwork Manager writes under:

```yaml
services:
  artwork_manager:
    output_dir: /kometa/metadata
```

Each Plex library receives an independent item-store directory, for example:

```text
/kometa/metadata/artwork-movies/
/kometa/metadata/artwork-tv/
/kometa/metadata/artwork-anime/
/kometa/metadata/artwork-cartoons/
```

Directory names are derived from the Plex library name.

Each managed movie or show is rendered to its own YAML file. DAKOSYS also maintains ownership and durable-state information used to detect unsafe changes and preserve provider selections between runs.

Treat these directories as **generated state**. Do not manually edit their ownership/state files.

### Kometa integration

The generated directories are Kometa **Metadata Files**.

If DAKOSYS sees the Kometa host directory as `/kometa` and Kometa sees the same host directory as `/config`, a generated DAKOSYS path such as:

```text
/kometa/metadata/artwork-movies
```

can be referenced by Kometa as:

```yaml
libraries:
  Movies:
    metadata_files:
      - folder: config/metadata/artwork-movies
```

Add the corresponding Artwork Manager folder to every Kometa library that should consume managed artwork.

### Scheduler

Artwork Manager can run autonomously through the normal DAKOSYS scheduler:

```yaml
scheduler:
  artwork_manager:
    type: daily
    times:
      - "04:00"
```

The scheduler uses the same safety and apply policy as an explicit CLI run.

### Artwork Manager CLI

Show configuration and discovered Plex libraries:

```bash
docker compose run --rm dakosys artwork status
```

Build a read-only preview of all supported libraries:

```bash
docker compose run --rm dakosys artwork scan
```

Preview one exact Plex library:

```bash
docker compose run --rm dakosys artwork scan --library Movies
```

JSON output is available for automation:

```bash
docker compose run --rm dakosys artwork scan --library Movies --json
```

Execute using the configured `apply_mode`:

```bash
docker compose run --rm dakosys artwork run
```

Run one exact Plex library:

```bash
docker compose run --rm dakosys artwork run --library Movies
```

> `artwork run` can write when `apply_mode: auto`. Use `artwork scan` when a read-only operation is required.

Show recent persisted run history:

```bash
docker compose run --rm dakosys artwork history
```

Long-running `scan` and `run` operations report progress to stderr so JSON output can remain machine-readable on stdout.

---

## Anime Episode Type Tracker

> **Trakt is not required for core Anime Episode Type generation.**

DAKOSYS reads episode classifications from [AnimeFillerList](https://www.animefillerlist.com/), resolves the corresponding series in Plex, and generates local Kometa data for:

- Filler
- Manga Canon
- Anime Canon
- Mixed Canon/Filler

The core path is:

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

### Plex-aware episode mapping

AnimeFillerList generally describes anime as one **absolute episode sequence**, while Plex/TVDb may split the same show into seasons, specials, or a different aired-order layout.

DAKOSYS does not assume:

```text
AFL episode 123 == Plex S01E123
```

Instead, DAKOSYS resolves the intended Plex series and builds a Plex-aware mapping so generated Kometa collections can target real Plex coordinates such as:

```text
tvdb_episode: <tvdb_id>_<season>_<episode>
```

The mapper follows a conservative sequence:

1. Resolve the intended Plex show using configured mappings and, when needed, an explicit TVDb override.
2. Validate that the AnimeFillerList page actually belongs to the requested show.
3. Compare AnimeFillerList episode order with Plex aired order.
4. Keep direct positional mapping when the evidence supports it, even when translated episode titles differ.
5. Use one-to-one title-based mapping only when there is strong evidence that episode order differs.
6. Reconcile short internal gaps only when trusted surrounding matches make the result structurally safe.
7. Handle compatible Season 0 / special-episode cases conservatively.
8. Leave episodes unmapped when a safe result cannot be established.

The goal is **fail closed rather than guess**. A missing overlay is preferable to assigning the wrong classification to a Plex episode.

### AnimeFillerList page validation

AnimeFillerList can sometimes return HTTP 200 for a slug that resolves to an unrelated show's page. DAKOSYS validates page identity before trusting the returned episode data.

A suspicious page is rejected instead of being used by the local mapper.

Legitimate naming differences can be handled explicitly through `mappings.yaml`; see [Anime Mapping and AFL Controls](#anime-mapping-and-afl-controls).

---

## Automatic Anime Scheduling

Automatic scheduling is an **optional Trakt-backed feature** that tracks which owned anime may still produce future episodes.

It is separate from core Anime Episode Type generation.

The generated schedule is based on:

```text
Plex ownership
    ∩
AnimeFillerList support
    ∩
validated AnimeFillerList identity
    ∩
active/future Trakt show status
```

The schedule is written to:

```text
config/scheduled-anime.yaml
```

This generated file is the authoritative automatic schedule source. The old manually maintained `scheduler.scheduled_anime` configuration has been retired.

Example:

```yaml
scheduler:
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

  tv_status_tracker:
    type: daily
    times:
      - "02:00"
```

### Important scope distinction

The automatic schedule does **not** filter the core local Anime Episode Type files.

Core Anime Episode Type generation processes the complete valid Plex + AnimeFillerList universe.

The generated active/future schedule is used for active/future state, UI visibility, scheduling metadata, and workflows such as optional legacy publishing that intentionally operate on the active/future set.

A Trakt scheduling failure therefore cannot prevent the local Anime Episode Type generator from running.

### Generated schedule state

`scheduled-anime.yaml` is runtime state and should not be edited manually or committed to Git.

It records scheduled anime, Plex/Trakt titles, Trakt status and scheduling decisions, unresolved review entries, ignored AFL entries, and discovery/request statistics.

If discovery fails fatally, DAKOSYS preserves the previous generated schedule instead of replacing it with an empty result.

### Manual refresh

```bash
docker compose run --rm dakosys refresh-schedule --force --no-notify
```

To allow a Discord notification when membership changes:

```bash
docker compose run --rm dakosys refresh-schedule --force --notify
```

---

## TV / Anime Status Tracker

> **Trakt is not required for TV Status or Next Airing.**

The TV / Anime Status Tracker resolves Plex shows through a provider-independent metadata layer using stable external IDs from Plex.

Lifecycle precedence is:

```text
TMDB -> Sonarr -> TVmaze
```

Upcoming-episode precedence is:

```text
Sonarr -> TMDB -> TVmaze
```

Sonarr is especially useful for concrete upcoming episodes already known to the local automation stack. TMDB is the primary lifecycle source. TVmaze provides a credential-free fallback when a supported external ID is available.

It creates Kometa overlays showing TV and anime state, including:

- Currently airing
- Ended
- Canceled
- Returning
- Season premiere
- Season finale
- Mid-season finale
- Final episode
- Upcoming air dates

Next Airing is generated locally from the same resolved metadata. DAKOSYS writes ordered Kometa collection files and a provider-independent `data/next_airing.json` snapshot used by the web dashboard.

The normal path does **not** create, update, fetch, or title-match against a personal Trakt `Next Airing` list.

At least one primary TV metadata provider must be usable:

- **Sonarr** with URL + API key; or
- **TMDB** with the top-level v3 API key or the advanced `TMDB_TOKEN` environment override.

TVmaze does not require credentials, but it is used as a fallback rather than as the only primary provider.

---

## Size Overlay

> **Trakt is not required** for this feature.

Creates Kometa overlays showing media file sizes for movies and TV shows. Size history can be tracked over time and episode counts can optionally be displayed.

---

## Web Dashboard

The DAKOSYS web UI is normally available at:

```text
http://your-host:3000
```

The dashboard provides:

- service status and next scheduled runs;
- Artwork Manager current state, automation status, run history, and progress;
- local Anime Episode Type management;
- automatic active/future schedule visibility and overrides;
- media statistics;
- configuration management;
- built-in configuration reference;
- service log viewing;
- anime identity and episode-title mapping tools;
- TV status and provider-derived Next Airing views;
- Trakt connection, feature, capability, and list-capacity status;
- library-size browsing;
- first-run setup.

The main dashboard does not perform a live Trakt request simply to render normal status.

The Next Airing dashboard reads local provider-derived data and does not require Trakt.

---

## Discord Notifications

DAKOSYS supports Discord webhook notifications.

Automatic anime scheduling can send a notification when generated schedule membership changes. No schedule-change notification is sent when membership is unchanged.

---

# Requirements

Core requirements depend on which features you enable.

### Artwork Manager

Requires:

- Plex Media Server
- Docker with Docker Compose
- Kometa
- write access to the Kometa configuration directory
- MediUX API token

TMDB is optional but strongly recommended for fallback coverage and identity enrichment.

Trakt is **not** required.

### Core Anime Episode Type

Requires:

- Plex Media Server
- Docker with Docker Compose
- Kometa
- AnimeFillerList access

Trakt is **not** required.

### Automatic Active/Future Schedule

Additionally requires:

- Trakt account
- Trakt API application / authentication

This feature reads show metadata and does not require Anime Episode Type personal-list publishing.

### TV / Anime Status Tracker

Additionally requires at least one usable primary TV metadata provider:

- Sonarr URL + API key; or
- TMDB v3 API key / `TMDB_TOKEN`.

TVmaze is an optional credential-free fallback.

Trakt is **not** required for TV Status or Next Airing.

### Legacy Episode-List Publishing

Additionally requires:

- explicit `trakt.episode_list_publishing.enabled: true`;
- Trakt authentication;
- sufficient runtime-reported personal-list and per-list capacity.

Legacy publishing is disabled by default.

### Other

- TMDB configuration is used by TV Status when the TMDB provider is enabled.
- Artwork Manager can use the same top-level `tmdb_api_key` for identity enrichment and artwork fallback.
- The top-level `tmdb_api_key` can also enrich dashboard poster artwork.
- Missing TMDB poster credentials do not prevent local Next Airing data from displaying.

---

# Installation

## Docker Compose

Clone this fork:

```bash
git clone https://github.com/dustinsmithworkshop/Dakosys.git
cd Dakosys
```

Create local runtime directories if they do not already exist:

```bash
mkdir -p config data
```

Starter files are included at the repository root:

```text
config.example.yaml
mappings.example.yaml
```

Copy them into the runtime configuration directory:

```bash
cp config.example.yaml config/config.yaml
cp mappings.example.yaml config/mappings.yaml
```

The examples are intended as safe starter/reference files. Replace placeholders and customize them for your Plex libraries and deployment.

The interactive setup wizard is the recommended way to complete service configuration:

```bash
docker compose run --rm dakosys setup
```

Start the updater/web service:

```bash
docker compose up -d dakosys-updater
```

The web dashboard should then be available at:

```text
http://your-host:3000
```

---

## Docker Images and Versioning

This fork publishes images to GitHub Container Registry:

```text
ghcr.io/dustinsmithworkshop/dakosys
```

Semantic 3.x tags include:

```text
ghcr.io/dustinsmithworkshop/dakosys:3.0.0   # exact 3.0.0 release
ghcr.io/dustinsmithworkshop/dakosys:3.0     # latest 3.0.x
ghcr.io/dustinsmithworkshop/dakosys:3       # latest compatible 3.x
ghcr.io/dustinsmithworkshop/dakosys:latest  # default latest release/build
```

For the most reproducible installation, pin the exact version.

Use `:3` only if you want compatible 3.x updates without manually changing the image tag for each release.

---

## Kometa Volume Mount

DAKOSYS must be able to write into the same **host directory** used by Kometa for its configuration.

For example, on Unraid:

```text
Host:      /mnt/user/appdata/kometa
Container: /kometa
```

The DAKOSYS Docker services should therefore have a volume mapping equivalent to:

```yaml
volumes:
  - ./config:/app/config
  - ./data:/app/data
  - /mnt/user/appdata/kometa:/kometa
```

With that layout, common DAKOSYS paths are:

```text
Assets:      /kometa/assets
Collections: /kometa/collections
Metadata:    /kometa/metadata
Overlays:    /kometa/overlays
```

Kometa may see the exact same host directory as `/config` inside the Kometa container. That is normal.

---

# Upgrading from 2.x

DAKOSYS 3.0 adds Artwork Manager as a major new automation subsystem while retaining the 2.x Anime Episode Type and TV metadata architecture.

Before upgrading, back up:

```text
config/config.yaml
config/mappings.yaml
data/
your Kometa configuration directory
```

## 1. Configure Artwork Manager deliberately

The starter configuration keeps Artwork Manager disabled until explicitly configured:

```yaml
services:
  artwork_manager:
    enabled: false
```

To enable it:

```yaml
services:
  artwork_manager:
    enabled: true
    apply_mode: auto
    output_dir: /kometa/metadata

    providers:
      mediux:
        api_token: REPLACE_WITH_MEDIUX_API_TOKEN
```

`MEDIUX_API_TOKEN` may be supplied through the container environment instead of YAML and takes precedence over the configured token.

## 2. Reuse the existing TMDB credential

Artwork Manager reuses the top-level TMDB configuration:

```yaml
tmdb_api_key: REPLACE_WITH_TMDB_API_KEY
```

or the advanced environment override:

```text
TMDB_TOKEN
```

No separate Artwork Manager TMDB credential is required.

## 3. Preview before the first write

Check discovered libraries:

```bash
docker compose run --rm dakosys artwork status
```

Build a read-only preview:

```bash
docker compose run --rm dakosys artwork scan
```

A specific Plex library can be selected exactly:

```bash
docker compose run --rm dakosys artwork scan --library Movies
```

`scan` never applies the proposed Artwork Manager changes.

## 4. Choose automatic or manual application

The normal 3.0 mode is:

```yaml
apply_mode: auto
```

Safe changes are written automatically. Unsafe changes remain blocked.

For explicit review-first operation:

```yaml
apply_mode: manual
```

Safe changes become `PENDING_REVIEW` instead of being written automatically.

## 5. Add generated metadata folders to Kometa

Artwork Manager creates one generated metadata directory per configured Plex library.

For example, if DAKOSYS writes:

```text
/kometa/metadata/artwork-movies
```

and Kometa sees that same host directory as `/config`, configure:

```yaml
libraries:
  Movies:
    metadata_files:
      - folder: config/metadata/artwork-movies
```

Use the folder corresponding to each Plex library.

---

# Upgrading from 1.x

DAKOSYS 2.x and later intentionally changed the Anime Episode Type, scheduling, TV Status, and Next Airing architecture.

Before upgrading, back up:

```text
config/config.yaml
config/mappings.yaml
data/
```

## 1. Anime Episode Type no longer requires Trakt lists

In 1.x, Anime Episode Type classifications were commonly published to many personal Trakt lists and Kometa consumed that workflow.

The normal path is now local:

```text
Plex + AnimeFillerList
        ↓
local Plex-aware mapper
        ↓
Kometa
```

Existing Plex, AFL, TVDb, and episode-title mappings remain useful.

## 2. Remove the old hard-coded anime schedule

The old configuration:

```yaml
scheduler:
  scheduled_anime:
    - some-show
```

is no longer used.

Use `scheduler.auto_schedule` instead.

## 3. Legacy episode-list publishing is opt-in

The compatibility publisher is disabled by default:

```yaml
trakt:
  episode_list_publishing:
    enabled: false
```

Leave it disabled for normal local Anime Episode Type operation.

## 4. Trakt configuration is feature-dependent

Trakt may be omitted when using:

- Artwork Manager;
- core Anime Episode Type;
- TV / Anime Status Tracker;
- Next Airing;
- Size Overlay.

Trakt is required only for Automatic Active/Future Schedule and optional legacy episode-list publishing.

## 5. TV Status uses local metadata providers

TV Status no longer requires Trakt metadata. A typical provider configuration is:

```yaml
tmdb_api_key: REPLACE_WITH_TMDB_API_KEY

services:
  tv_status_tracker:
    enabled: true

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

Environment overrides are also supported:

```text
SONARR_URL
SONARR_API_KEY
TMDB_TOKEN
```

## 6. Next Airing is local

TV Status resolves upcoming episodes through Sonarr, TMDB, and TVmaze and generates Next Airing locally.

The normal workflow writes:

```text
data/next_airing.json
<collections_dir>/*-next-airing.txt
<collections_dir>/*-next-airing.yml
```

A personal Trakt `Next Airing` list is no longer part of the normal TV Status workflow.

---

# Kometa Integration

Artwork Manager item stores belong under `metadata_files`. For example:

```yaml
libraries:
  Movies:
    metadata_files:
      - folder: config/metadata/artwork-movies

  TV:
    metadata_files:
      - folder: config/metadata/artwork-tv
```

Other DAKOSYS collection and overlay outputs remain configured through `collection_files` and `overlay_files`.

A typical configuration may look like:

```yaml
libraries:
  TV:
    metadata_files:
      - folder: config/metadata/artwork-tv
    collection_files:
      - file: config/collections/tv-next-airing.yml
    overlay_files:
      - file: config/overlays/size-overlays-tv.yml
      - file: config/overlays/overlay_tv_status_tv.yml

  Anime:
    metadata_files:
      - folder: config/metadata/artwork-anime
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

Library names and generated filenames vary with configuration. Use the files produced by your installation.

---

# Configuration Files

## `config/config.yaml`

Contains service and deployment configuration such as:

- Plex URL and token
- configured Plex library names/media types
- Artwork Manager provider, apply-mode, filtering, and output configuration
- optional Trakt configuration for Trakt-backed features
- Sonarr/TMDB/TVmaze TV metadata provider configuration
- top-level TMDB API key
- Kometa output paths
- enabled services
- scheduler configuration
- notification configuration

Starter:

```text
config.example.yaml
```

### Artwork Manager example

```yaml
tmdb_api_key: REPLACE_WITH_TMDB_API_KEY

services:
  artwork_manager:
    enabled: true

    # auto = apply safe plans automatically
    # manual = retain safe plans for review
    apply_mode: auto

    output_dir: /kometa/metadata

    providers:
      mediux:
        api_token: REPLACE_WITH_MEDIUX_API_TOKEN

scheduler:
  artwork_manager:
    type: daily
    times:
      - "04:00"
```

MediUX is the required primary Artwork Manager provider.

Credential precedence is:

```text
MediUX: MEDIUX_API_TOKEN -> services.artwork_manager.providers.mediux.api_token
TMDB:   TMDB_TOKEN       -> top-level tmdb_api_key
```

Optional library filtering is based on configured Plex library names:

```yaml
services:
  artwork_manager:
    libraries:
      include:
        - Movies
        - TV

      exclude:
        - Home Videos

      overrides:
        Movies:
          output: /kometa/metadata/custom-movie-artwork
```

Library names are installation-specific; DAKOSYS does not require `Movies`, `TV`, `Anime`, or `Cartoons` as literal names.

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

Provider precedence is intentionally internal rather than normally user-configurable:

```text
Lifecycle:     TMDB -> Sonarr -> TVmaze
Next episode:  Sonarr -> TMDB -> TVmaze
```

Advanced/container credential overrides:

```text
SONARR_URL
SONARR_API_KEY
TMDB_TOKEN
```

## `config/mappings.yaml`

Contains installation-specific anime identity and mapping exceptions.

Starter:

```text
mappings.example.yaml
```

Do not blindly copy another installation's `mappings.yaml`. Plex titles, TVDb IDs, metadata agents, ordering, and library contents can differ.

## Local / Generated Files

These should remain local/runtime files and should not be committed:

```text
config/config.yaml
config/mappings.yaml
config/scheduled-anime.yaml
data/next_airing.json
data/artwork-manager/
```

Artwork Manager also writes generated per-library item stores under its configured `output_dir`, commonly:

```text
/kometa/metadata/artwork-*/
```

Those item stores contain generated Kometa YAML plus DAKOSYS ownership/durable-state information and should not be edited manually.

---

# Anime Mapping and AFL Controls

DAKOSYS provides several mapping mechanisms. They solve different problems and should not be treated as interchangeable.

| Key | Purpose |
|---|---|
| `mappings` | Map a DAKOSYS/AFL slug to the exact Plex show title |
| `afl_mappings` | Use a different AnimeFillerList URL slug |
| `afl_identity_aliases` | Trust an additional legitimate AFL display title |
| `afl_ignored` | Explicitly skip a known unusable AFL entry |
| `tvdb_mappings` | Resolve an ambiguous Plex show by TVDb series ID |
| `title_mappings` | Advanced episode-title overrides used by local and legacy matching |
| `ignored_mappings` | Legacy/advanced mapping workflow; normally leave empty |

## Plex title mappings

```yaml
mappings:
  code-geass: "Code Geass: Lelouch of the Rebellion"
  dr-stone: "Dr. STONE"
  haikyuu: "Haikyu!!"
  sage-tanya-evil: "Saga of Tanya the Evil"
```

The key is the DAKOSYS/AnimeFillerList slug. The value should be the **exact Plex title for the same series**.

Do not map a slug to a different reboot, remake, sequel, or adaptation simply to make validation pass.

## AnimeFillerList slug overrides

```yaml
afl_mappings:
  blue-lock: blue-lock-0
  shaman-king: shaman-king-2021
  your-eternity-0: your-eternity
```

This changes only the AnimeFillerList source URL. The original DAKOSYS/Plex key continues to be used elsewhere.

## AnimeFillerList identity aliases

```yaml
afl_identity_aliases:
  fighting-spirit:
    - "Hajime no Ippo: The Fighting!"
```

Identity aliases add another explicitly trusted identity to the existing validator. They do **not** lower or bypass the AFL identity threshold.

## Ignoring known AFL failures

```yaml
afl_ignored:
  - city-hunter
  - mobile-suit-gundam-zz
  - mobile-suit-zeta-gundam
```

Use `afl_ignored` for acknowledged source limitations, not as a way to suppress a mapping problem that can actually be fixed.

## TVDb overrides

When title matching is ambiguous, specify the intended TVDb series directly:

```yaml
tvdb_mappings:
  rurouni-kenshin: 70863
  urusei-yatsura: 75113
```

TVDb overrides are authoritative. If the requested TVDb series cannot be found in the configured Plex anime libraries, DAKOSYS will not silently fall back to an unrelated title.

---

# Scheduler Configuration

Each service has its own schedule block under `scheduler:`.

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
      - "04:00"

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

  tv_status_tracker:
    type: hourly
    minute: 30

  size_overlay:
    type: weekly
    days:
      - sunday
    time: "04:00"
```

Automatic Schedule refresh is independent of core Anime Episode Type generation.

---

# Discord Notifications

The notification configuration uses:

```yaml
notifications:
  enabled: true
  discord:
    webhook_url: "https://discord.com/api/webhooks/..."
```

Test it with:

```bash
docker compose run --rm dakosys test-notification
```

For automatic schedule membership notifications, the scheduler can also resolve the webhook from environment configuration such as:

```text
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

Keeping secrets outside committed configuration is recommended.

---

# Manual Commands

List available commands from the exact image/version you are running:

```bash
docker compose run --rm dakosys --help
```

## Artwork Manager

```bash
docker compose run --rm dakosys artwork status
docker compose run --rm dakosys artwork scan
docker compose run --rm dakosys artwork scan --library Movies
docker compose run --rm dakosys artwork run
docker compose run --rm dakosys artwork run --library Movies
docker compose run --rm dakosys artwork history
```

## Core Anime Episode Type

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

Show AFL episode classifications:

```bash
docker compose run --rm dakosys show-episodes "demon-slayer-kimetsu-no-yaiba"
```

## Automatic Schedule

Refresh automatic scheduling:

```bash
docker compose run --rm dakosys refresh-schedule --force --no-notify
```

## Service Updates

Run all enabled services:

```bash
docker compose run --rm dakosys run-update all
```

Run TV status tracking:

```bash
docker compose run --rm dakosys run-update tv_status_tracker
```

Run size overlays:

```bash
docker compose run --rm dakosys run-update size_overlay
```

## Trakt Account Diagnostics

These commands are relevant only when using a Trakt-backed feature or inspecting existing legacy Trakt state.

Display normalized Trakt account capabilities:

```bash
docker compose run --rm dakosys trakt-capabilities
```

JSON output:

```bash
docker compose run --rm dakosys trakt-capabilities --json
```

---

# Release Notes — 3.0

DAKOSYS 3.0 introduces Artwork Manager as a first-class production subsystem.

Highlights include:

- dynamic configured Plex show/movie library support;
- MediUX curated artwork discovery;
- cohesive show artwork-set selection and migration;
- TMDB identity enrichment and artwork gap fallback;
- movie poster/background support;
- per-item Kometa metadata stores;
- durable ownership and provider state;
- transactional apply with rollback-aware behavior;
- independent safety and apply-mode policy;
- AUTO and MANUAL operation;
- persistent run history;
- CLI status/scan/run/history commands;
- live progress reporting for long scans/runs;
- scheduler integration;
- Artwork Manager dashboard/current-state/history/progress UI;
- continued Trakt-independent operation for core local workflows.

For release builds, the recommended exact image pin is:

```text
ghcr.io/dustinsmithworkshop/dakosys:3.0.0
```
