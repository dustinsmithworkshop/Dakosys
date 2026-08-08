# DAKOSYS - Docker App Kometa Overlay System

DAKOSYS is a tool for Plex users that creates and manages Trakt.tv lists and Kometa overlays. It categorizes anime episodes by type, tracks TV show statuses, and displays media file sizes — all running in Docker with automatic scheduling.

A built-in web dashboard lets you manage configuration, monitor services, browse logs, and handle anime mappings without touching the command line.

---

## Enhancements in This Fork

This fork includes substantial improvements to anime episode mapping and Kometa integration, with a focus on correctly mapping AnimeFillerList episode data to the episode structure used by Plex.

### Plex-Aware Episode Mapping

AnimeFillerList frequently represents a series as one continuous absolute episode sequence, while Plex may organize the same show across multiple seasons.

DAKOSYS now builds a Plex-aware absolute episode map and converts AnimeFillerList episode numbers into the actual Plex/TVDb season and episode coordinates used by Kometa.

For example, an absolute episode may be converted into a Kometa ID such as:

```text
tvdb_episode:74796_3_1
```

This allows episode-type overlays to work correctly across multi-season anime instead of assuming that every episode belongs to season 1.

### Automatic Episode Ordering Detection

DAKOSYS now analyzes the relationship between AnimeFillerList and Plex episode ordering before generating Kometa episode IDs.

Three strategies are supported:

1. **Direct aired-order mapping**

   Used when AnimeFillerList and Plex follow the same episode sequence.

2. **Title-based mapping**

   Used when the same episodes exist in both sources but are intentionally arranged in a different order.

3. **Fail-closed rejection**

   Used when the two episode schemes differ too much to map safely.

DAKOSYS favors skipping a questionable show over generating incorrect Kometa episode IDs.

### Translation-Aware Matching

Different metadata providers sometimes use substantially different English translations for the same episode title.

Low title similarity alone is therefore no longer treated as proof that episode ordering differs.

DAKOSYS checks whether mismatched titles strongly correspond to episodes at different Plex positions:

* Few or no off-position matches usually indicate translation or naming differences, so direct episode numbering is retained.
* A significant number of strong off-position matches indicates that the show is actually reordered, allowing title-based mapping to take over.

This allows shows with alternate English titles to remain correctly mapped without requiring manual episode mappings.

### Reordered Series Support

Some series use substantially different broadcast, production, DVD, or metadata-provider episode orders.

When DAKOSYS detects strong evidence that episodes exist at different positions, it can build a one-to-one title-based mapping between AnimeFillerList and Plex.

Exact normalized-title matches are preferred before fuzzy matching.

Multipart episode names are normalized so equivalent forms such as:

```text
Endless Eight II
Endless Eight (2)
```

can be recognized as the same episode.

### Conservative Sequence Realignment

DAKOSYS can detect cases where an episode exists in AnimeFillerList but is absent from Plex's regular aired-order sequence, or vice versa.

A sequence offset is only applied after multiple subsequent episodes confirm the realignment.

This prevents a single title mismatch from shifting every remaining episode in a series.

### AnimeFillerList Page Validation

AnimeFillerList can occasionally return an unrelated show's page for a valid-looking URL.

DAKOSYS now validates the identity of the returned AnimeFillerList page before accepting episode data.

If the page does not sufficiently match the requested anime, the show is skipped rather than generating lists from incorrect episode data.

### Mapping Diagnostics

Episode generation now reports how each show was handled, including:

* Direct Plex aired-order mapping
* Title-based episode mapping
* Ordering incompatibility
* Confirmed sequence realignments
* AnimeFillerList-only episodes
* Unmapped episodes
* Title mismatches
* Mapping confidence

These diagnostics make it easier to identify metadata-provider differences without silently producing incorrect overlays.

---

## Features

### Anime Episode Type Tracker

Trakt VIP required.

Creates Trakt lists and Kometa overlays categorizing anime episodes by type: filler, manga canon, anime canon, and mixed.

Supports:

* Automatic scheduling
* Custom anime title mappings
* Custom episode title mappings
* Plex-aware multi-season episode mapping
* Automatic episode ordering detection
* Title-based fallback for reordered series
* Translation-aware title comparison
* Conservative episode sequence realignment
* AnimeFillerList page validation

### TV / Anime Status Tracker

No Trakt VIP required (uses one list).

Creates overlays showing the airing status of TV shows and anime: currently airing, ended, cancelled, returning, season finale, mid-season finale, final episode, and season premiere. Displays upcoming air dates. Generates a Trakt list of shows with upcoming episodes.

### Size Overlay

No Trakt required.

Creates overlays showing file sizes for movies and TV shows. Tracks size changes over time and optionally displays episode counts.

### Web Dashboard

A web UI accessible at `http://your-host:3000`.

Features:

* Dashboard with service status, next scheduled runs, and media stats
* Configuration editor with built-in config reference documenting all options
* Log viewer for all services
* Anime management: add anime, view Trakt lists, resolve mapping errors
* TV status browser and Next Airing list with posters
* Library size browser
* Setup wizard for first-time configuration

### Notifications

Discord webhook integration.

---

## Requirements

* Plex Media Server
* Trakt.tv account and API application
* TMDB API for UI posters
* Docker
* Kometa / Plex Meta Manager

---

## Quick Start

Create the directory structure:

```bash
mkdir -p dakosys/{config,data}
cd dakosys
```

Download `docker-compose.yml` from this fork:

```bash
curl -O https://raw.githubusercontent.com/dustinsmithworkshop/Dakosys/main/docker-compose.yml
```

This fork publishes Docker images to GitHub Container Registry:

```text
ghcr.io/dustinsmithworkshop/dakosys:latest
```

If you are adapting an existing DAKOSYS installation from upstream, make sure the `image:` entry in your Docker Compose or Unraid configuration points to:

```yaml
image: ghcr.io/dustinsmithworkshop/dakosys:latest
```

Run the setup wizard:

```bash
docker compose run --rm dakosys setup
```

Start the daemon:

```bash
docker compose up -d dakosys-updater
```

The web dashboard will be available at `http://your-host:3000`.


Add the generated YAML files to your Kometa config:

```yaml
Seriale:
  collection_files:
    - file: config/collections/seriale-next-airing.yml
  overlay_files:
    - file: config/overlays/size-overlays-seriale.yml
    - file: config/overlays/overlay_tv_status_seriale.yml

Anime:
  collection_files:
    - file: config/collections/anime-next-airing.yml
    - file: config/collections/anime_episode_type.yml
      schedule: weekly(monday)
  overlay_files:
    - file: config/overlays/size-overlays-anime.yml
    - file: config/overlays/fillers.yml
    - file: config/overlays/manga_canon.yml
    - file: config/overlays/anime_canon.yml
    - file: config/overlays/mixed.yml
    - file: config/overlays/overlay_tv_status_anime.yml
```

---

## Service Notes

### Anime Episode Type Tracker

The Anime Episode Type Tracker requires Trakt VIP because it creates multiple lists — one per episode type per anime.

AnimeFillerList uses absolute episode numbering, while Plex may divide the same series into multiple aired-order seasons. DAKOSYS automatically converts absolute episode numbers into Plex/TVDb season and episode coordinates before generating Kometa collections.

DAKOSYS also checks whether the AnimeFillerList sequence corresponds to Plex's aired order.

If episode titles differ because of translation or metadata-provider naming differences but there is no strong evidence of reordering, Plex numbering is retained.

If strong evidence of a different episode order is found, DAKOSYS attempts a one-to-one title-based mapping.

If a sufficiently reliable mapping cannot be constructed, the show is skipped rather than generating potentially incorrect Kometa episode IDs.

Individual episodes that cannot be safely mapped are reported in the logs.

### TV / Anime Status Tracker

The TV / Anime Status Tracker uses a single Trakt list and does not require Trakt VIP.

Once configured, scheduled updates can run automatically.

### Size Overlay

The Size Overlay does not require Trakt.

Once configured, scheduled updates can run automatically.

---

## Manual Commands

You can always run:

```bash
docker compose run --rm dakosys --help
```

to list all commands, and `--help` on any command for usage details.

### Anime Episode Type

Create all list types for an anime:

```bash
docker compose run --rm dakosys create-all "One-Piece"
```

Create a specific list type:

```bash
docker compose run --rm dakosys create-list "Naruto-Shippuden" FILLER
```

Fix mapping errors for episodes:

```bash
docker compose run --rm dakosys fix-mappings
```

List all available anime on AnimeFillerList:

```bash
docker compose run --rm dakosys list-anime
```

Show all episodes and their types:

```bash
docker compose run --rm dakosys show-episodes "Demon Slayer Kimetsu No Yaiba"
```

Delete a list:

```bash
docker compose run --rm dakosys delete-list bleach FILLER
```

Delete multiple lists at once:

```bash
docker compose run --rm dakosys list-lists --format plain --anime "One Punch Man" | xargs -n2 docker compose run --rm --no-TTY dakosys delete-piped --force
```

### Scheduled Updates

Add an anime to the automatic update schedule:

```bash
docker compose run --rm dakosys schedule add "Jujutsu Kaisen"
```

Remove an anime from the schedule:

```bash
docker compose run --rm dakosys schedule remove "Dragon Ball"
```

List all scheduled anime:

```bash
docker compose run --rm dakosys schedule list
```

Run an immediate update of all services:

```bash
docker compose run --rm dakosys run-update all
```

Run an immediate update of a specific service:

```bash
docker compose run --rm dakosys run-update tv_status_tracker
```

### List Management

List all Trakt lists created by DAKOSYS:

```bash
docker compose run --rm dakosys list-lists
```

List Trakt lists for a specific anime:

```bash
docker compose run --rm dakosys list-lists --anime "Attack on Titan"
```

Sync the Kometa collections file with current Trakt lists:

```bash
docker compose run --rm dakosys sync-collections
```

---

## Scheduler Configuration

Each service has its own schedule block under `scheduler:` in `config.yaml`.

```yaml
scheduler:
  anime_episode_type:
    type: daily
    times: ["03:00"]

  tv_status_tracker:
    type: hourly
    minute: 30

  size_overlay:
    type: weekly
    days: ["sunday"]
    time: "04:00"
```

Schedule types:

| Type      | Fields                                   |
| --------- | ---------------------------------------- |
| `daily`   | `times: ["HH:MM", ...]`                  |
| `hourly`  | `minute: N`                              |
| `weekly`  | `days: ["monday", ...]`, `time: "HH:MM"` |
| `monthly` | `dates: [1, 15]`, `time: "HH:MM"`        |
| `cron`    | `expression: "0 3 * * *"`                |
| `run`     | Runs once at startup only                |

---

## TV Status Custom Labels

Status text displayed on overlays defaults to English. Override any label in `config.yaml`:

```yaml
services:
  tv_status_tracker:
    labels:
      ended: "T E R M I N E E"
      cancelled: "A N N U L E E"
      returning: "R E V I E N T"
      airing: "EN COURS"
      season_finale: "FIN DE SAISON"
      mid_season_finale: "MI-SAISON"
      final_episode: "EPISODE FINAL"
      season_premiere: "PREMIERE SAISON"
```

All keys are optional. Labels for `airing`, `season_finale`, `mid_season_finale`, `final_episode`, and `season_premiere` have the air date appended automatically.

---

## Notifications

Discord webhook notifications.

```yaml
notifications:
  enabled: true
  discord:
    webhook_url: "https://discord.com/api/webhooks/..."
```

Test notifications:

```bash
docker compose run --rm dakosys test-notification
```

---

## Logs

Service logs are written to the `data/` directory:

* `data/anime_trakt_manager.log`
* `data/tv_status_tracker.log`
* `data/size_overlay.log`
* `data/notifications.log`
* `data/auto_update.log`
* `data/scheduler.log`
* `data/failed_episodes.log`

View container logs:

```bash
docker compose logs -f dakosys-updater
```

For Plex-aware episode mapping, the logs also report whether a show used direct aired-order mapping, title-based mapping, sequence realignment, or was rejected because a safe mapping could not be established.

---

## Troubleshooting

### Missing episodes in lists

Use the mapping fix tool:

```bash
docker compose run --rm dakosys fix-mappings
```

### Anime exists in AnimeFillerList but not Plex

DAKOSYS will skip an anime that is scheduled but cannot be found in the configured Plex anime libraries.

Check your anime title mapping if the Plex title differs from the AnimeFillerList title.

Do not map an AnimeFillerList entry to an unrelated Plex show simply to suppress the warning.

### AnimeFillerList page rejected

DAKOSYS validates that the AnimeFillerList page returned for a show actually belongs to the requested anime.

If AnimeFillerList returns an unrelated page, DAKOSYS will reject it and log an identity mismatch rather than generating incorrect episode data.

### Episode ordering rejected

If DAKOSYS reports that episode ordering is incompatible with Plex aired order, it found evidence that the AnimeFillerList and Plex sequences differ and could not construct a sufficiently reliable title-based mapping.

The show is skipped intentionally to prevent incorrect Kometa episode IDs.

### Test scheduler configuration

```bash
docker compose run --rm dakosys test-scheduler
```

### Run setup for a single service

```bash
docker compose run --rm dakosys setup anime_episode_type
docker compose run --rm dakosys setup tv_status_tracker
docker compose run --rm dakosys setup size_overlay
```

---

## Example: create-all output

```text
docker compose run --rm dakosys create-all "Bleach"
Connecting to Plex server...
Connected to Plex server successfully!
Found direct match in Plex: Bleach
Fetching anime list from AnimeFillerList...
Found exact match: bleach
Use this match? [Y/n]: y
Added mapping: bleach → Bleach

Checking for MANGA episodes...
Found 162 MANGA episodes
Trakt list 'bleach_manga canon' created successfully.
Successfully added: 162 episodes

Checking for FILLER episodes...
Found 163 FILLER episodes
Trakt list 'bleach_filler' created successfully.
Successfully added: 163 episodes

Checking for MIXED episodes...
Found 41 MIXED episodes
Trakt list 'bleach_mixed canon/filler' created successfully.
Successfully added: 41 episodes

Created lists:
  MANGA: 162 episodes - https://trakt.tv/users/YOUR_USERNAME/lists/bleach_manga-canon
  FILLER: 163 episodes - https://trakt.tv/users/YOUR_USERNAME/lists/bleach_filler
  MIXED: 41 episodes - https://trakt.tv/users/YOUR_USERNAME/lists/bleach_mixed-canon-filler

Would you like to add 'Bleach' to the automatic update schedule? [Y/n]: n
```
