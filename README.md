# DAKOSYS — Docker App Kometa Overlay System

DAKOSYS is a Docker-based companion for **Plex**, **AnimeFillerList**, and **Kometa**, with optional **Trakt** integration for features that require current show metadata or personal Trakt lists.

DAKOSYS 2.0 separates core Anime Episode Type generation from Trakt personal-list publishing.

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
Plex + Trakt metadata
        ↓
Status overlays + one Next Airing list

Legacy Episode-List Publishing
Anime classifications + Trakt personal lists
        ↓
Explicit opt-in compatibility mode
```

> **About this fork**
>
> This repository is a maintained fork of [sahara101/Dakosys](https://github.com/sahara101/Dakosys). The upstream project provides the original DAKOSYS architecture, dashboard, Anime Episode Type Tracker, TV/Anime Status Tracker, Size Overlay, scheduler, notifications, and management tools.
>
> This fork extends that foundation with Plex-aware episode mapping, conservative AnimeFillerList validation, automatic active/future scheduling, local Anime Episode Type generation, Trakt capability-aware behavior, safer batch processing, and additional management and diagnostic tools.

![DAKOSYS dashboard](https://github.com/user-attachments/assets/03af3c98-39f2-4121-99e2-74390d90f87b)

---

## What DAKOSYS Does

| Feature | Trakt required | Personal Trakt lists | Main output |
|---|---:|---:|---|
| Anime Episode Type Tracker | **No** | No | Local Kometa episode collections/overlays |
| Automatic Active/Future Schedule | Yes | No | Generated `scheduled-anime.yaml` |
| TV / Anime Status Tracker | Yes | One `Next Airing` list | Status overlays + Next Airing |
| Legacy Episode-List Publishing | Yes | Yes | Filler/canon Trakt lists |
| Size Overlay | No | No | Kometa size overlays |
| Web Dashboard | Depends on enabled features | No by itself | Browser-based management UI |
| Discord Notifications | No | No | Service/update notifications |

Trakt account limits are discovered from the authenticated Trakt API response at runtime. DAKOSYS does not assume personal-list capacity from account labels such as VIP or non-VIP.

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

The TV / Anime Status Tracker requires Trakt metadata.

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

It also maintains **one** personal Trakt list named `Next Airing` for shows with upcoming episodes.

That single Next Airing list is separate from legacy Anime Episode Type episode-list publishing.

DAKOSYS uses Trakt's reported account capabilities and limits at runtime instead of assuming that a particular account tier is required.

![TV status example](https://github.com/user-attachments/assets/ce2e31fe-aeee-467f-b498-6ea36ac0139b)

---

## Size Overlay

> **Trakt is not required** for this feature.

Creates Kometa overlays showing media file sizes for movies and TV shows. Size history can be tracked over time and episode counts can optionally be displayed.

![Size overlay example](https://github.com/user-attachments/assets/829cd5b1-2d67-456b-b41a-4a930b7a2b9a)

---

## Web Dashboard

The DAKOSYS web UI is normally available at:

```text
http://your-host:3000
```

The 2.0 dashboard provides:

- service status and next scheduled runs;
- local Anime Episode Type management;
- automatic active/future schedule visibility and overrides;
- media statistics;
- configuration management;
- built-in configuration reference;
- service log viewing;
- anime identity and episode-title mapping tools;
- TV status and Next Airing views;
- Trakt connection, feature, capability, and list-usage status;
- library-size browsing;
- first-run setup.

The dashboard does not require a live Trakt request simply to render the main status page.

The Trakt page is capability-focused rather than a bulk personal-list manager.

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

Additionally requires:

- Trakt account
- Trakt API application / authentication
- capacity for the single `Next Airing` personal list

### Legacy Episode-List Publishing

Additionally requires:

- explicit `trakt.episode_list_publishing.enabled: true`;
- Trakt authentication;
- sufficient runtime-reported personal-list and per-list capacity.

Legacy publishing is disabled by default.

### Other

- TMDB API configuration is used by dashboard features that display TMDB artwork/metadata.

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

Trakt authentication is requested only when an enabled feature requires it.

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

For a 2.0 release, semantic tags use:

```text
ghcr.io/dustinsmithworkshop/dakosys:2.0.0   # exact release
ghcr.io/dustinsmithworkshop/dakosys:2.0     # latest 2.0.x
ghcr.io/dustinsmithworkshop/dakosys:2       # latest compatible 2.x
ghcr.io/dustinsmithworkshop/dakosys:latest  # default latest release/build
```

For the most reproducible installation, pin the exact version.

Use `:2` only if you want compatible 2.x updates without manually changing the image tag for each release.

> DAKOSYS 2.0 remains unreleased until the candidate Docker image passes the release validation gate documented below.

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

# Upgrading from 1.x to 2.0

DAKOSYS 2.0 intentionally changes the Anime Episode Type and scheduling architecture.

Before upgrading, back up:

```text
config/config.yaml
config/mappings.yaml
data/
```

## 1. Anime Episode Type no longer requires Trakt lists

In 1.x, Anime Episode Type classifications were commonly published to many personal Trakt lists and Kometa consumed that workflow.

In 2.0, the normal path is local:

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

Leave it disabled for normal 2.0 Anime Episode Type operation.

Enable it only if you intentionally want DAKOSYS to continue creating/updating personal Trakt filler/canon lists.

## 4. Trakt configuration is feature-dependent

You may omit Trakt credentials when using only features that do not require Trakt, such as core Anime Episode Type and Size Overlay.

Trakt is still required for:

- Automatic Active/Future Schedule;
- TV / Anime Status Tracker;
- Next Airing;
- legacy episode-list publishing.

## 5. Next Airing is separate from legacy publishing

TV Status maintains one `Next Airing` list.

Disabling legacy Anime Episode Type list publishing does not disable Next Airing.

## 6. Remove old episode-type lists if desired

Preview legacy DAKOSYS episode lists:

```bash
docker compose run --rm dakosys prune-legacy-lists
```

Apply the cleanup:

```bash
docker compose run --rm dakosys prune-legacy-lists --apply
```

The cleanup classifier protects `Next Airing` and unrelated personal lists.

Always review the dry run before using `--apply`.

## 7. Re-run setup when changing enabled features

The setup wizard is feature-aware in 2.0.

For example, Anime Episode Type by itself will not request Trakt credentials, while enabling Automatic Schedule or TV Status will.

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

---

# Configuration Files

## `config/config.yaml`

Contains service and deployment configuration such as:

- Plex URL and token
- Plex library names
- optional Trakt configuration for Trakt-backed features
- Kometa output paths
- enabled services
- scheduler configuration
- notification configuration

Starter:

```text
config.example.yaml
```

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

Inspect current list usage and the `Next Airing` list:

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

Trakt authentication is only required when at least one Trakt-backed feature is enabled.

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

If you use only core Anime Episode Type and other non-Trakt services, missing Trakt credentials should not prevent those services from running.

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

For source changes to the Anime Episode Type, scheduler, or web path:

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
  web_server.py

git diff --check
```

Frontend validation:

```bash
cd web
npx tsc --noEmit --pretty false
npm run build
cd ..
```

## Release Validation

A release should also be tested using the exact Docker image intended for publication.

The DAKOSYS 2.0 release gate includes:

- container startup;
- Anime Episode Type with no Trakt configuration;
- real Plex + AnimeFillerList local generation;
- Kometa output generation;
- automatic schedule refresh and failure preservation;
- `always_include` / `always_exclude`;
- TV Status and its single Next Airing list;
- legacy publishing disabled before OAuth;
- explicit legacy publishing opt-in and account-capacity checks;
- scheduler execution inside Docker;
- web setup/dashboard/anime/Trakt/mappings/config-reference pages;
- a fresh non-VIP/free-tier Trakt account before final release.

Do not infer Docker correctness solely from local Python/TypeScript tests.

**Do not tag `v2.0.0` until the Docker and fresh free-tier Trakt validation gates pass.**

---

# Upstream Project and Credits

DAKOSYS was originally created by **sahara101**.

Upstream repository:

[https://github.com/sahara101/Dakosys](https://github.com/sahara101/Dakosys)

This fork preserves the upstream project's major service concepts while substantially reworking the anime/Plex mapping, scheduling, Trakt integration, and dashboard paths.

---

# Releases

See [`CHANGELOG.md`](CHANGELOG.md) for release history, upgrade notes, fixes, and release-specific validation.
