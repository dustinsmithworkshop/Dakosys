# DAKOSYS — Docker App Kometa Overlay System

DAKOSYS is a Docker-based companion for **Plex**, **Trakt**, and **Kometa**. It can classify anime episodes, create and maintain Trakt lists, generate Kometa collections and overlays, track TV/anime airing status, show media file sizes, and provide a web dashboard for management and troubleshooting.

> **About this fork**
>
> This repository is a maintained fork of [sahara101/Dakosys](https://github.com/sahara101/Dakosys). The upstream project provides the original DAKOSYS architecture, web dashboard, Anime Episode Type Tracker, TV/Anime Status Tracker, Size Overlay, scheduler, notifications, and management tools.
>
> This fork extends that foundation with Plex-aware anime episode mapping, conservative AnimeFillerList validation, TVDb/AFL override controls, automatic Trakt-based anime scheduling, safer batch processing, and release/versioning improvements.

![DAKOSYS dashboard](https://github.com/user-attachments/assets/03af3c98-39f2-4121-99e2-74390d90f87b)

---

## What DAKOSYS Does

| Feature | Trakt required | Trakt VIP required | Main output |
|---|---:|---:|---|
| Anime Episode Type Tracker | Yes | **Yes** | Trakt lists + Kometa episode collections/overlays |
| Automatic Anime Scheduling | Yes | Uses Anime Episode Type workflow | Generated `scheduled-anime.yaml` |
| TV / Anime Status Tracker | Yes | No | Status overlays + Next Airing list |
| Size Overlay | No | No | Kometa size overlays |
| Web Dashboard | Depends on enabled services | No | Browser-based management UI |
| Discord Notifications | No | No | Service/update notifications |

---

# Features

## Anime Episode Type Tracker

> **Trakt VIP is required** because this feature creates multiple Trakt lists.

DAKOSYS reads episode classifications from [AnimeFillerList](https://www.animefillerlist.com/) and creates Trakt lists for:

- Filler
- Manga Canon
- Anime Canon
- Mixed Canon/Filler

Those lists are then used to generate Kometa collections and episode overlays.

![Anime episode type example](https://github.com/user-attachments/assets/5d90e452-173c-4665-b020-add2625ed261)

### Plex-aware episode mapping

AnimeFillerList generally describes anime as one **absolute episode sequence**, while Plex/TVDb may split the same show into seasons, specials, or a different aired-order layout.

This fork does not assume that:

```text
AFL episode 123 == Plex S01E123
```

Instead, DAKOSYS resolves the Plex series and builds a Plex-aware mapping so generated Kometa collections can target real Plex coordinates such as:

```text
tvdb_episode: <tvdb_id>_<season>_<episode>
```

The mapper follows a conservative sequence:

1. Resolve the intended Plex show using configured mappings and, when needed, an explicit TVDb override.
2. Validate that the AnimeFillerList page actually belongs to the requested show.
3. Compare AnimeFillerList episode order with Plex aired order.
4. Keep direct positional mapping when the evidence supports it, even when translated episode titles differ.
5. Use one-to-one title-based mapping only when there is strong evidence that the episode order differs.
6. Reconcile short internal gaps only when trusted surrounding matches make the result structurally safe.
7. Handle compatible Season 0 / special-episode cases conservatively.
8. Leave episodes unmapped when a safe result cannot be established.

The goal is **fail closed rather than guess**. A missing overlay is preferable to applying the wrong episode classification to Plex.

### AnimeFillerList page validation

AnimeFillerList can sometimes return HTTP 200 for a slug that resolves to an unrelated show's page. DAKOSYS validates the returned page identity before trusting the episode data.

A suspicious page is rejected instead of being used to generate Trakt or Kometa data.

Legitimate naming differences can be handled explicitly through `mappings.yaml`; see [Anime Mapping and AFL Controls](#anime-mapping-and-afl-controls).

---

## Automatic Anime Scheduling

DAKOSYS can automatically determine which anime should remain in the scheduled Anime Episode Type update batch.

The schedule is based on:

```text
Plex ownership
    ∩
AnimeFillerList support
    ∩
validated AnimeFillerList identity
    ∩
active/future Trakt status
```

In practical terms:

- the show must exist in one of the configured Plex anime libraries;
- DAKOSYS must have a trustworthy AnimeFillerList source for it;
- the AFL page must pass identity validation;
- Trakt must indicate that the series can still produce future episodes.

Shows explicitly reported as ended or canceled are removed from the generated schedule. Ambiguous or temporarily unavailable source data is handled conservatively rather than causing a mass deletion.

The generated schedule is stored at:

```text
config/scheduled-anime.yaml
```

A hard-coded `scheduler.scheduled_anime` list is **not required** when automatic scheduling is enabled.

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

### Generated schedule state

`scheduled-anime.yaml` is runtime state and should not be edited manually or committed to Git.

It records:

- the generated scheduled anime list;
- Plex and Trakt titles;
- Trakt status and scheduling decision;
- unresolved entries under `review:`;
- explicitly acknowledged AFL exceptions under `ignored:`;
- discovery statistics;
- Trakt request and retry statistics.

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

Normal:

```bash
docker compose run --rm dakosys run-update anime_episode_type
```

refreshes the automatic schedule first, subject to `refresh_hours`, and then processes the resulting anime batch.

`always_include` and `always_exclude` are intended as explicit scheduling overrides. They do not turn an untrusted AFL page into trusted episode data.

---

## TV / Anime Status Tracker

> **Trakt VIP is not required** for this feature.

Creates Kometa overlays showing TV and anime status, including:

- Currently airing
- Ended
- Canceled
- Returning
- Season premiere
- Season finale
- Mid-season finale
- Final episode
- Upcoming air dates

It also maintains a Trakt list of shows with upcoming episodes.

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

The upstream dashboard provides:

- service status and next scheduled runs;
- media statistics;
- configuration management;
- built-in configuration reference;
- service log viewing;
- anime management and mapping tools;
- Trakt-list browsing;
- TV status and Next Airing views;
- library-size browsing;
- first-run setup.

---

## Discord Notifications

DAKOSYS supports Discord webhook notifications.

Automatic anime scheduling can also send a notification when generated schedule membership changes:

- shows added;
- shows removed;
- new scheduled total.

No schedule-change notification is sent when membership is unchanged.

---

# Requirements

Core requirements depend on which services you enable:

- Plex Media Server
- Docker with Docker Compose
- Kometa
- Trakt.tv account
- Trakt API application
- AnimeFillerList access for Anime Episode Type features
- Trakt VIP for Anime Episode Type list generation
- TMDB API configuration for dashboard features that use TMDB artwork/metadata

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

The interactive setup wizard remains the recommended way to complete service configuration and Trakt authentication:

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

Recommended release tags:

```text
ghcr.io/dustinsmithworkshop/dakosys:1.1.0   # exact release
ghcr.io/dustinsmithworkshop/dakosys:1.1     # latest 1.1.x
ghcr.io/dustinsmithworkshop/dakosys:1       # latest 1.x
ghcr.io/dustinsmithworkshop/dakosys:latest  # default-branch/latest build
```

For the most reproducible installation, pin the exact version.

Use `:1` if you want compatible v1 updates without manually changing the image tag for each v1 release.

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
- Trakt configuration
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
| `title_mappings` | Advanced episode-title adjustments |
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

  tv_status_tracker:
    type: hourly
    minute: 30

  size_overlay:
    type: weekly
    days:
      - sunday
    time: "04:00"
```

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

The upstream notification configuration uses:

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

For automatic schedule membership notifications, the scheduler also supports resolving the webhook from environment configuration such as:

```text
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

Keeping secrets outside committed configuration is recommended.

---

# Manual Commands

List all available commands:

```bash
docker compose run --rm dakosys --help
```

You can also append `--help` to individual commands.

Current CLI commands include:

| Command | Purpose |
|---|---|
| `create` | Create a Trakt list for one anime/episode type |
| `create-all` | Create all available episode-type lists for one anime |
| `delete-list` | Delete a Trakt list |
| `delete-piped` | Delete a list from piped input |
| `fix-mappings` | Interactively resolve mapping errors from previous runs |
| `ignore-mapping` | Ignore a specific mapping-error entry |
| `unignore-mapping` | Remove a mapping-error ignore |
| `list-anime` | List AnimeFillerList shows known to DAKOSYS |
| `list-lists` | List Trakt lists |
| `refresh-schedule` | Refresh generated `scheduled-anime.yaml` |
| `run-update` | Run one or all enabled services immediately |
| `schedule` | Manage the legacy hard-coded `scheduler.scheduled_anime` list |
| `setup` | Run full or service-specific interactive setup |
| `show-episodes` | Show AFL episodes and classifications for one anime |
| `sync-collections` | Synchronize the Kometa anime episode collection file |
| `test-logging` | Test logging |
| `test-notification` | Test Discord notifications |
| `test-scheduler` | Validate scheduler configuration |
| `test-trakt` | Diagnose Trakt authentication and list access |

> **Legacy scheduling command**
>
> `schedule` remains available for installations that still use a manually maintained
> `scheduler.scheduled_anime` list. When `scheduler.auto_schedule.enabled: true`,
> the generated automatic schedule is the recommended workflow, so `schedule add/remove`
> should normally not be used to manage that generated membership.

## Anime Episode Type

Create all available episode-type lists for one anime:

```bash
docker compose run --rm dakosys create-all "one-piece"
```

Create one specific list:

```bash
docker compose run --rm dakosys create "naruto-shippuden" FILLER
```

List AnimeFillerList entries:

```bash
docker compose run --rm dakosys list-anime
```

Show episode classifications:

```bash
docker compose run --rm dakosys show-episodes "demon-slayer-kimetsu-no-yaiba"
```

Fix episode/title mapping errors:

```bash
docker compose run --rm dakosys fix-mappings
```

Delete a list:

```bash
docker compose run --rm dakosys delete-list bleach FILLER
```

## Automatic Schedule

Refresh automatic scheduling:

```bash
docker compose run --rm dakosys refresh-schedule --force --no-notify
```

Run the Anime Episode Type batch:

```bash
docker compose run --rm dakosys run-update anime_episode_type
```

When `scheduler.auto_schedule.enabled` is true, the generated schedule is the normal source of truth for that batch. The older `schedule` command still manages the legacy hard-coded `scheduler.scheduled_anime` list and is retained for compatibility/manual workflows.

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

## Trakt List Management

List DAKOSYS-created lists:

```bash
docker compose run --rm dakosys list-lists
```

Filter lists to one anime:

```bash
docker compose run --rm dakosys list-lists --anime "Attack on Titan"
```

Synchronize the generated Kometa collection file:

```bash
docker compose run --rm dakosys sync-collections
```

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

Run:

```bash
docker compose run --rm dakosys test-trakt
```

This checks the configured Trakt user/client configuration, stored token state, token refresh, authenticated account, and Trakt list access.

If no valid token is available, run setup again or reconnect through the web UI.

---

## Scheduler configuration

```bash
docker compose run --rm dakosys test-scheduler
```

---

## AnimeFillerList identity errors

If DAKOSYS reports that an AFL page belongs to a different show, do **not** disable the safety check globally.

First determine which case applies:

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
- `stats:` makes it easier to verify that the complete Plex/AFL candidate set was accounted for.

---

## Missing or incorrectly mapped episodes

Run:

```bash
docker compose run --rm dakosys fix-mappings
```

The Plex-aware mapper intentionally leaves unsafe matches unresolved rather than guessing.

---

## Run setup for one service

```bash
docker compose run --rm dakosys setup anime_episode_type
docker compose run --rm dakosys setup tv_status_tracker
docker compose run --rm dakosys setup size_overlay
```

---

# Development Validation

For source changes to the Anime Episode Type / scheduler path:

```bash
python3 -m py_compile \
  anime_trakt_manager.py \
  scheduled_anime_manager.py

git diff --check
```

The release changelog contains release-specific validation notes and regression summaries.

---

# Upstream Project and Credits

DAKOSYS was originally created by **sahara101**.

Upstream repository:

[https://github.com/sahara101/Dakosys](https://github.com/sahara101/Dakosys)

This fork intentionally preserves the upstream project's core services and dashboard while extending the anime/Plex mapping and scheduling paths.

---

# Releases

See [`CHANGELOG.md`](CHANGELOG.md) for release history, upgrade notes, fixes, and release-specific validation.
