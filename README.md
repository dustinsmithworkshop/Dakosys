# DAKOSYS — Docker App Kometa Overlay System

DAKOSYS is a Docker-based companion for **Plex**, **AnimeFillerList**, and **Kometa**, with optional **Trakt** integration for automatic anime scheduling and legacy episode-list publishing.

The current architecture keeps core Anime Episode Type, TV / Anime Status, and Next Airing generation independent of Trakt.

```text
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
> This fork extends that foundation with Plex-aware episode mapping, conservative AnimeFillerList validation, automatic active/future scheduling, local Anime Episode Type generation, hybrid TV metadata providers, provider-derived Next Airing data, Trakt capability-aware behavior, safer batch processing, and additional management and diagnostic tools.

![DAKOSYS dashboard](https://github.com/user-attachments/assets/03af3c98-39f2-4121-99e2-74390d90f87b)

---

## What DAKOSYS Does

| Feature | Trakt required | Personal Trakt lists | Main output |
|---|---:|---:|---|
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

## Anime Episode Type Tracker

> **Trakt is not required for core Anime Episode Type generation.**

DAKOSYS reads episode classifications from [AnimeFillerList](https://www.animefillerlist.com/), resolves the corresponding series in Plex, and generates local Kometa data for:

- Filler
- Manga Canon
- Anime Canon
- Mixed Canon/Filler

The core 2.0 path is:

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

In DAKOSYS 2.0 this generated file is the authoritative automatic schedule source.

The old manually maintained `scheduler.scheduled_anime` configuration has been retired.

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

It records:

- scheduled anime;
- Plex and Trakt titles;
- Trakt status and scheduling decisions;
- unresolved entries under `review:`;
- explicitly acknowledged AFL exceptions under `ignored:`;
- discovery statistics;
- Trakt request and retry statistics.

If discovery fails fatally, DAKOSYS preserves the previous generated schedule instead of replacing it with an empty result.

### Manual refresh

With Docker Compose:

```bash
docker compose run --rm dakosys refresh-schedule --force --no-notify
```

To allow a Discord notification when membership changes:

```bash
docker compose run --rm dakosys refresh-schedule --force --notify
```

Inside an already-running container:

```bash
python3 anime_trakt_manager.py refresh-schedule --force --no-notify
```

Inspect the result:

```bash
cat config/scheduled-anime.yaml
```

`always_include` and `always_exclude` are explicit scheduling overrides. They do not bypass Plex ownership or AnimeFillerList identity validation.

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

![TV status example](https://github.com/user-attachments/assets/ce2e31fe-aeee-467f-b498-6ea36ac0139b)

---

## Size Overlay

> **Trakt is not required** for this feature.

Creates Kometa overlays showing media file sizes for movies and TV shows. Size history can be tracked over time and episode counts can optionally be displayed.

![Size overlay example](https://github.com/user-attachments/assets/829cd5b1-2d67-456b-b41a-4a930b7a2b9a)

---

Artwork Manager

Artwork Manager is the DAKOSYS service for managing Plex artwork through Kometa metadata.

It discovers configured Plex show and movie libraries automatically and maintains an independent metadata item store for each library.

Artwork Priority

For episode artwork, DAKOSYS uses this priority:

MediUX curated
    ↓
Dakosys Generated
    ↓
TMDB / existing fallback

MediUX remains the preferred artwork source. Generated artwork is used only when a higher-priority curated episode card is unavailable and generation is enabled.

Manual or locked artwork is protected from automatic replacement.

Generated artwork remains upgradeable. If a better supported MediUX set becomes available later, DAKOSYS can replace generated artwork with the curated set.

Library Support

Artwork Manager supports Plex show and movie libraries. Library names are discovered from Plex and are not hard-coded by DAKOSYS.

Each managed library receives its own Kometa metadata item store. Default output layout:

<output_dir>/
  artwork-<plex-library>/

Each managed show or movie is rendered to its own YAML file. DAKOSYS also maintains ownership and durable state so later runs can safely preserve, refresh, or migrate artwork selections.

Apply Modes

Artwork Manager supports two Apply modes:

auto — safe scheduled plans may be applied automatically.

manual — safe plans are retained for review and can be applied from the Artwork Manager web interface.

Apply mode does not weaken Artwork Manager safety rules. Unsafe plans are blocked regardless of Apply mode.

services:
  artwork_manager:
    enabled: true
    apply_mode: manual
    output_dir: /kometa/metadata

Web Interface

The Artwork Manager page provides service Enabled/Disabled control, current resolved configuration, current-state scans, per-library status, file-change counts, provider activity, generated-card activity, coverage information for show libraries, reviewed Apply, persistent per-library collapse/expand state, run history, and live scan/Apply progress.

Read-only scans for different libraries may run concurrently. Reviewed Applies are globally serialized so only one library can mutate Artwork Manager state at a time.

Current-State Refresh

Refresh Current State performs a new read-only scan. A failed or unsafe current state is presented as Retry Scan.

Refreshing does not mutate metadata, durable artwork state, or generated-card files.

Service Toggle

The Artwork Manager Enabled switch controls:

services:
  artwork_manager:
    enabled: true

Disabling the service stops new Artwork Manager work. It does not delete generated artwork, Kometa metadata already written, Artwork Manager durable state, or cached current-state history.

Artwork Manager is intentionally not exposed through the generic service-run API because its reviewed scan/Apply workflow has stronger safety semantics.

---

Dakosys Episode Artwork Generator

The DAKOSYS episode artwork generator creates deterministic local episode title cards when suitable curated artwork is unavailable.

The generator is a transformation stage, not an artwork provider.

Default State

Generated episode cards are disabled by default.

services:
  artwork_manager:
    generated_episode_cards:
      enabled: true
      kometa_asset_directory: /config/assets
      config_file: config/artwork-generator.yaml

Disabling the generator prevents new generation. It does not remove artwork that was already generated and activated.

Source Priority

MediUX curated
    >
Dakosys generated
    >
TMDB / existing fallback

Generated cards never override manual or locked artwork. Generated cards may later be replaced by better curated MediUX artwork.

Episode Title Source

Plex episode title
    >
TMDB episode name

Image Source

usable TMDB still
    >
usable Plex thumbnail

If no valid source image is available, DAKOSYS preserves the fallback artwork instead of fabricating a card from an unsuitable source.

Rendering

Rendering is deterministic and local using Pillow. No AI image generation, face detection, ImageMagick, or FFmpeg is required.

Output is a 1920×1080 JPEG. The card contains the episode title with restrained lower-screen styling and a subtle gradient for readability. Titles are constrained to avoid oversized or invalid layouts.

Fonts

Bundled font choices:

Marcellus

Prata

Cormorant Garamond

Syne

Libre Baskerville

Cinzel

Japanese/CJK text automatically falls back to bundled Noto Sans JP when needed.

Creative Configuration

Creative settings live separately from the main DAKOSYS configuration:

config/artwork-generator.yaml

Start from:

artwork-generator.example.yaml

Creative inheritance is:

Show > Library > Global

Example:

version: 1

defaults:
  font: marcellus

libraries:
  Anime:
    font: cormorant_garamond

shows:
  "tmdb:1398":
    font: prata

Show overrides use stable artwork identities such as tmdb:1398, not display titles.

Generated Cache

Generated artwork is stored below the configured Kometa asset directory.

generated-artwork/
  tv/
    tmdb-1398/
      season-01/
        S01E01-<fingerprint>.jpg

The filename fingerprint is stable for the rendering inputs. Cached generated files are reused when possible.

DAKOSYS emits generated local artwork to Kometa using file_poster paths rather than file:// URLs.

Preview vs Apply

Preview/build is read-only. During preview DAKOSYS may resolve titles, resolve source images, calculate fingerprints, calculate cache paths, inspect whether a cached file exists, and build generated-card plans.

Preview does not download source images, render JPEGs, write cache files, activate metadata, or activate durable state.

Materialization occurs during Apply only.

If durable Generated state refers to a missing cache JPEG, the library is considered to need Apply so the missing file can be materialized safely.

Invalid Source Images

DAKOSYS fully decodes generator source images before using them. Invalid or corrupt exact sources are quarantined temporarily.

The quarantine identity uses the exact image source and provider/source asset identity. A changed source identity is reconsidered immediately, allowing recovery when Plex or a provider repairs the image.

A known bad source is treated as unavailable on later scans rather than repeatedly causing destructive retries.

---

## Web Dashboard

The DAKOSYS web UI is normally available at:

```text
http://your-host:3000
```

The dashboard provides:

- service status and next scheduled runs;
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

The Trakt page is capability-focused rather than a bulk personal-list manager and reports only features that actually depend on Trakt.

---

## Discord Notifications

DAKOSYS supports Discord webhook notifications.

Automatic anime scheduling can send a notification when generated schedule membership changes:

- shows added;
- shows removed;
- new scheduled total.

No schedule-change notification is sent when membership is unchanged.

---

# Requirements

Core requirements depend on which features you enable.

### Core Anime Episode Type

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

When TV Status is enabled, setup can configure Sonarr, TMDB, and TVmaze metadata providers.

Trakt authentication is requested only when Automatic Active/Future Schedule or legacy episode-list publishing is enabled.

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

Semantic 2.x tags include:

```text
ghcr.io/dustinsmithworkshop/dakosys:2.0.0   # exact 2.0.0 release
ghcr.io/dustinsmithworkshop/dakosys:2.0     # latest 2.0.x
ghcr.io/dustinsmithworkshop/dakosys:2       # latest compatible 2.x
ghcr.io/dustinsmithworkshop/dakosys:latest  # default latest release/build
```

For the most reproducible installation, pin the exact version.

Use `:2` only if you want compatible 2.x updates without manually changing the image tag for each release.

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
Overlays:    /kometa/overlays
```

Kometa may see the exact same host directory as `/config` inside the Kometa container. That is normal.

For example, DAKOSYS may write:

```text
/kometa/collections/anime_episode_type.yml
```

while Kometa references the same file as:

```text
config/collections/anime_episode_type.yml
```

---

# Upgrading from 1.x

DAKOSYS 2.x intentionally changes the Anime Episode Type, scheduling, TV Status, and Next Airing architecture.

Before upgrading, back up:

```text
config/config.yaml
config/mappings.yaml
data/
```

## 1. Anime Episode Type no longer requires Trakt lists

In 1.x, Anime Episode Type classifications were commonly published to many personal Trakt lists and Kometa consumed that workflow.

In 2.x, the normal path is local:

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

If automatic active/future scheduling is desired, configure:

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

`config/scheduled-anime.yaml` is generated runtime state and should not be committed.

## 3. Legacy episode-list publishing is opt-in

The compatibility publisher is disabled by default:

```yaml
trakt:
  episode_list_publishing:
    enabled: false
```

Leave it disabled for normal local Anime Episode Type operation.

Enable it only if you intentionally want DAKOSYS to continue creating/updating personal Trakt filler/canon lists.

## 4. Trakt configuration is feature-dependent

You may omit Trakt credentials when using:

- core Anime Episode Type;
- TV / Anime Status Tracker;
- Next Airing;
- Size Overlay.

Trakt is required only for:

- Automatic Active/Future Schedule;
- legacy episode-list publishing.

## 5. TV Status uses local metadata providers

TV Status no longer requires Trakt metadata.

A typical provider configuration is:

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

Environment values take precedence over their YAML credential equivalents.

## 6. Next Airing is local

TV Status resolves upcoming episodes through Sonarr, TMDB, and TVmaze and generates Next Airing locally.

The normal workflow writes:

```text
data/next_airing.json
<collections_dir>/*-next-airing.txt
<collections_dir>/*-next-airing.yml
```

Kometa consumes the ordered local text files, while the DAKOSYS dashboard consumes `data/next_airing.json`.

A personal Trakt `Next Airing` list is no longer part of the normal TV Status workflow.

## 7. Remove old episode-type lists if desired

Preview legacy DAKOSYS episode lists:

```bash
docker compose run --rm dakosys prune-legacy-lists
```

Apply the cleanup:

```bash
docker compose run --rm dakosys prune-legacy-lists --apply
```

The cleanup classifier protects `Next Airing` and unrelated personal lists. This protection is useful for installations that still have an old Next Airing list from a previous DAKOSYS version.

Always review the dry run before using `--apply`.

## 8. Re-run setup when changing enabled features

The setup wizard is feature-aware.

Anime Episode Type, TV Status, Next Airing, and Size Overlay do not require Trakt credentials.

Enabling Automatic Active/Future Schedule or legacy episode-list publishing does.

When TV Status is enabled, setup can configure Sonarr, TMDB, and TVmaze metadata providers instead.

---

# Kometa Integration

Add the files generated by DAKOSYS to the appropriate Kometa libraries.

A typical configuration looks like:

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

Library names and generated filenames can vary with configuration. Use the files produced by your installation.

Next Airing collection YAML uses Kometa `text_file` membership with `collection_order: custom`, so provider-derived air-date order is preserved.

---

# Configuration Files

## `config/config.yaml`

Contains service and deployment configuration such as:

- Plex URL and token
- Plex library names
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

      # Uses the top-level tmdb_api_key.
      tmdb:
        enabled: true

      # Public credential-free fallback.
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

Explicit `enabled: false` still disables a provider even when its credentials are present.

## `config/mappings.yaml`

Contains installation-specific anime identity and mapping exceptions.

Starter:

```text
mappings.example.yaml
```

Do not blindly copy another user's `mappings.yaml`. Plex titles, TVDb IDs, metadata agents, ordering, and library contents can differ.

## Local / Generated Files

These should remain local/runtime files and should not be committed:

```text
config/config.yaml
config/mappings.yaml
config/scheduled-anime.yaml
data/next_airing.json
```

---

# Anime Mapping and AFL Controls

DAKOSYS provides several different mapping mechanisms. They solve different problems and should not be treated as interchangeable.

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

---

## AnimeFillerList slug overrides

Sometimes the correct AFL page exists under a different URL slug:

```yaml
afl_mappings:
  blue-lock: blue-lock-0
  shaman-king: shaman-king-2021
  your-eternity-0: your-eternity
```

This changes only the AnimeFillerList source URL. The original DAKOSYS/Plex key continues to be used elsewhere.

---

## AnimeFillerList identity aliases

Sometimes the correct AFL page has a substantially different display title:

```yaml
afl_identity_aliases:
  fighting-spirit:
    - "Hajime no Ippo: The Fighting!"
```

Identity aliases add another explicitly trusted identity to the existing validator.

They do **not** lower or bypass the AFL identity threshold.

---

## Ignoring known AFL failures

If an AFL catalog entry is known to be permanently unsupported or consistently resolves to unusable data, it can be explicitly ignored:

```yaml
afl_ignored:
  - city-hunter
  - mobile-suit-gundam-zz
  - mobile-suit-zeta-gundam
```

Ignored entries:

- are not fetched from AnimeFillerList during automatic schedule discovery;
- do not repeatedly flood the identity-error log;
- do not consume Trakt schedule lookups;
- are not automatically scheduled;
- appear under `ignored:` instead of `review:` in `scheduled-anime.yaml`.

Use `afl_ignored` for acknowledged source limitations, not as a way to suppress a mapping problem that can actually be fixed.

---

## TVDb overrides

When title matching is ambiguous, specify the intended TVDb series directly:

```yaml
tvdb_mappings:
  rurouni-kenshin: 70863
  urusei-yatsura: 75113
```

TVDb overrides are authoritative. If the requested TVDb series cannot be found in the configured Plex anime libraries, DAKOSYS will not silently fall back to an unrelated title.

---

## Episode-title overrides

`title_mappings.special_matches` is retained as a compatibility schema name, but the mapped values are used by the local Anime Episode Type loader as well as the optional legacy Trakt matching path.

Conceptually, treat these entries as:

```text
source episode title → mapped episode title
```

rather than as a Trakt-only mapping.

---

Artwork Manager Reviewed Apply Safety

DAKOSYS separates artwork planning from mutation. This is the core safety model used by the Artwork Manager web interface.

Read-Only Planning

resolve Plex/library state
        ↓
resolve provider artwork
        ↓
resolve generated-card plans
        ↓
render desired Kometa metadata in memory
        ↓
calculate safety + file changes
        ↓
calculate review fingerprint
        ↓
NO WRITES

The resulting current state is cached for the web dashboard.

Review Fingerprint

A safe plan that needs changes receives an exact review fingerprint.

When the user chooses Apply Reviewed Plan, DAKOSYS does not blindly apply the cached result. It rebuilds the plan against fresh library/provider state and verifies that the new plan still matches the exact reviewed fingerprint.

If the plan changed, Apply is rejected as stale. No writes are performed for a stale reviewed plan. The user must refresh current state and review the new plan.

Apply

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

Generated-image materialization occurs before generated artwork is activated in metadata or durable state.

Safety Outcomes

Artwork Manager records outcomes such as applied, no_changes, pending_review, blocked, and failed. Reviewed Apply also uses stale when the exact reviewed plan no longer matches.

Unsafe plans remain blocked regardless of whether configuration uses automatic or manual Apply mode.

Global Apply Serialization

Only one reviewed Artwork Apply can run at a time across all libraries.

Anime Apply running
  ├─ Anime + same fingerprint -> reuse existing Apply
  ├─ Anime + different plan   -> reject
  ├─ TV Apply                 -> reject until Anime finishes
  ├─ Movies Apply             -> reject until Anime finishes
  └─ Cartoons Apply           -> reject until Anime finishes

This serialization is enforced by both the UI and backend API.

Read-only current-state scans are not globally serialized and may run concurrently for different libraries.

Failure Behavior

Apply fails closed. Examples include provider failure, unsafe artwork selection, invalid generated source image, generated-file materialization failure, stale reviewed fingerprint, and transactional write failure.

A failed or stale Apply does not silently submit a different plan.

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

# TV Status Custom Labels

Status text can be customized in `config.yaml`.

```yaml
services:
  tv_status_tracker:
    labels:
      ended: "ENDED"
      cancelled: "CANCELED"
      returning: "RETURNING"
      airing: "AIRING"
      season_finale: "SEASON FINALE"
      mid_season_finale: "MID-SEASON FINALE"
      final_episode: "FINAL EPISODE"
      season_premiere: "SEASON PREMIERE"
```

All label keys are optional.

Air-date-capable labels retain the TV Status Tracker's normal date behavior.

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

You can also append `--help` to individual commands.

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

The generated `config/scheduled-anime.yaml` file is the only automatic schedule source in 2.0.

There is no manually maintained `scheduler.scheduled_anime` workflow.

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

Inspect list-capacity information:

```bash
docker compose run --rm dakosys trakt-list-capacity --json
```

Inspect current personal-list usage:

```bash
docker compose run --rm dakosys trakt-list-usage --json
```

General Trakt diagnostics:

```bash
docker compose run --rm dakosys test-trakt
```

## Legacy Episode-List Publishing

These commands belong to the optional compatibility publisher and require:

```yaml
trakt:
  episode_list_publishing:
    enabled: true
```

Create one personal Trakt episode-type list:

```bash
docker compose run --rm dakosys create "naruto-shippuden" FILLER
```

Create all available episode-type lists for one anime:

```bash
docker compose run --rm dakosys create-all "one-piece"
```

Interactively repair mapping errors from the legacy Trakt publishing workflow:

```bash
docker compose run --rm dakosys fix-mappings
```

List personal Trakt lists:

```bash
docker compose run --rm dakosys list-lists
```

Delete legacy lists with the dedicated cleanup workflow:

```bash
docker compose run --rm dakosys prune-legacy-lists
docker compose run --rm dakosys prune-legacy-lists --apply
```

DAKOSYS checks Trakt's runtime-reported list and per-list limits before creating or growing legacy personal lists.

---

# Logs

Service logs are written under `data/`.

Common logs include:

```text
data/anime_trakt_manager.log
data/tv_status_tracker.log
data/size_overlay.log
data/notifications.log
data/auto_update.log
data/scheduler.log
data/failed_episodes.log
```

Follow the updater/web container:

```bash
docker compose logs -f dakosys-updater
```

---

# Troubleshooting

## Trakt authentication

Trakt authentication is only required when at least one Trakt-backed feature is enabled:

- Automatic Active/Future Schedule;
- legacy episode-list publishing.

Run:

```bash
docker compose run --rm dakosys test-trakt
```

For account/list capability information:

```bash
docker compose run --rm dakosys trakt-capabilities --json
docker compose run --rm dakosys trakt-list-usage --json
```

If no valid token is available, run setup again or reconnect through the web UI.

Missing Trakt credentials should not prevent Anime Episode Type, TV Status, Next Airing, Size Overlay, or other non-Trakt services from running.

---

## TV metadata providers

If TV Status reports that no metadata resolver is configured, verify that at least one primary provider is usable.

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

Or configure:

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

Or use the advanced bearer override:

```text
TMDB_TOKEN
```

TVmaze is a credential-free fallback and does not replace the requirement for at least one usable Sonarr or TMDB primary provider.

---

## Next Airing

Next Airing is generated when the TV Status Tracker runs.

DAKOSYS writes:

```text
data/next_airing.json
<collections_dir>/*-next-airing.txt
<collections_dir>/*-next-airing.yml
```

If the web page reports that Next Airing data is missing, run the TV Status Tracker and verify that `data/next_airing.json` is created.

Poster artwork is optional enrichment. Missing TMDB artwork credentials do not prevent the underlying Next Airing entries from displaying.

---

## Scheduler configuration

```bash
docker compose run --rm dakosys test-scheduler
```

---

## AnimeFillerList identity errors

If DAKOSYS reports that an AFL page belongs to a different show, do **not** disable the safety check globally.

Determine which case applies:

- wrong AFL URL slug → use `afl_mappings`;
- correct page with a different legitimate display title → use `afl_identity_aliases`;
- ambiguous Plex title → use `mappings` or `tvdb_mappings`;
- known unusable AFL source you intentionally accept → use `afl_ignored`.

---

## Automatic schedule review

Inspect:

```bash
cat config/scheduled-anime.yaml
```

Pay particular attention to:

```yaml
review:
ignored:
stats:
```

- `review:` contains unresolved candidates worth investigating.
- `ignored:` contains explicitly acknowledged AFL exceptions.
- `stats:` helps verify that the complete Plex/AFL candidate set was accounted for.

A scheduling failure should not stop core local Anime Episode Type generation.

---

## Missing or incorrectly mapped local episodes

The Plex-aware mapper intentionally leaves unsafe matches unresolved rather than guessing.

Check:

- the Anime Episode Type / mapping logs;
- `config/mappings.yaml`;
- the web Mappings page;
- `mappings`;
- `tvdb_mappings`;
- `afl_mappings`;
- `afl_identity_aliases`;
- `title_mappings`.

`title_mappings.special_matches` is retained as a compatibility schema name but is used as a generic episode-title override by the local mapper as well as by legacy Trakt matching.

The CLI `fix-mappings` command is specifically for the optional legacy Trakt episode-list publishing workflow.

---

## Run setup for one service

```bash
docker compose run --rm dakosys setup anime_episode_type
docker compose run --rm dakosys setup tv_status_tracker
docker compose run --rm dakosys setup size_overlay
```

---

# Development Validation

For source changes to the Anime Episode Type, scheduler, TV metadata, or web path:

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

Run the Python tests:

```bash
python -m unittest discover -s tests -v
```

Frontend validation:

```bash
cd web
npm run build
cd ..
```

## Release Validation

A release should also be tested using the exact Docker image intended for publication.

For changes that touch the TV metadata architecture, validate at minimum:

- container startup under the supported Python runtime;
- TV Status initialization without a `trakt:` section when no Trakt-backed feature is enabled;
- Sonarr/TMDB/TVmaze provider configuration and resolver startup;
- a full provider-backed TV Status run against real Plex libraries;
- provider-derived status overlays;
- local Next Airing `.txt` / `.yml` Kometa outputs;
- `data/next_airing.json`;
- Next Airing dashboard operation without Trakt;
- actual Kometa ingestion of the generated Next Airing collection files;
- preservation of expected provider conflict behavior and warnings;
- Automatic Active/Future Schedule when that Trakt-backed path is changed;
- legacy episode-list publishing and Trakt capacity checks when that path is changed;
- CLI and web setup behavior;
- Python test suite;
- frontend production build.

Do not infer Docker correctness solely from local Python/TypeScript tests.

---

# Upstream Project and Credits

DAKOSYS was originally created by **sahara101**.

Upstream repository:

[https://github.com/sahara101/Dakosys](https://github.com/sahara101/Dakosys)

This fork preserves the upstream project's major service concepts while substantially reworking the anime/Plex mapping, scheduling, TV metadata, Next Airing, Trakt integration, and dashboard paths.

---

# Releases

See [`CHANGELOG.md`](CHANGELOG.md) for release history, upgrade notes, fixes, and release-specific validation.



---

# Dakosys 3.0 Release Notes

## Artwork Manager

Dakosys 3.0 introduces the Artwork Manager, a complete artwork discovery, reconciliation, and application system.

New capabilities:

- Plex library artwork inventory
- Artwork coverage analysis
- MediUX-first artwork selection
- TMDB artwork fallback support
- Movie artwork management
- TV/show artwork management
- Persistent artwork state tracking
- Safe preview and reconciliation before applying changes
- Legacy artwork migration support

Artwork provider priority:

1. MediUX artwork when available
2. TMDB artwork fallback
3. Existing artwork preserved when no better source exists

The Artwork Manager is designed to improve artwork quality without destructive replacements. Items that cannot be confidently resolved remain available for review.

## Artwork Manager Commands

Check artwork configuration:

```bash
python -m artwork.cli --config /app/config/config.yaml status
```

Preview artwork changes:

```bash
python -m artwork.cli --config /app/config/config.yaml scan
```

Review previous artwork runs:

```bash
python -m artwork.cli --config /app/config/config.yaml history
```

## 3.0 Release Validation

Dakosys 3.0 was validated with:

- 542 Python tests passing
- Web production build completed successfully
- Docker image smoke testing completed
- Artwork Manager production migration verified

## Upgrading to 3.0

Before upgrading:

- Backup your Dakosys configuration
- Preserve existing Kometa paths
- Update your Docker image tag to `3.0.0`
- Allow the Artwork Manager to complete its initial inventory scan

Example:

```yaml
image: ghcr.io/dustinsmithworkshop/dakosys:3.0.0
```
