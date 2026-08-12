# Changelog

All notable changes to this fork are documented here.

## [2.0.0] - Unreleased

DAKOSYS 2.0 is an intentional architecture change.

The release remains **unreleased** until the exact candidate Docker image has passed validation inside the real container environment and the Trakt-backed paths have also been verified using a fresh non-VIP/free-tier Trakt account.

### Added

- Local Anime Episode Type discovery from Plex + AnimeFillerList without requiring Trakt personal lists.
- Shared AnimeFillerList discovery candidate generation using live catalog entries plus configured mapping-backed identities.
- Automatic Trakt account capability discovery from the authenticated `/users/settings` response.
- Read-only Trakt capability, list-capacity, and list-usage CLI diagnostics.
- Runtime enforcement of Trakt personal-list count and per-list item capacity.
- `prune-legacy-lists` dry-run/apply workflow for removing old DAKOSYS filler/canon personal lists while protecting `Next Airing` and unrelated lists.
- Feature-aware web setup for optional Trakt configuration.
- Automatic schedule management and include/exclude overrides in the web UI.
- Trakt dashboard focused on connection state, enabled Trakt-backed features, live account limits, and Next Airing usage.

### Changed

- Core Anime Episode Type generation now uses the local Plex + AnimeFillerList mapper and does not require Trakt authentication.
- `sync-collections`, scheduled Anime Episode Type execution, immediate Anime Episode Type execution, and mapping-fix regeneration now use the local backend.
- Automatic active/future scheduling remains Trakt-backed but is independent of core Anime Episode Type generation.
- Generated `config/scheduled-anime.yaml` is now the authoritative automatic schedule source.
- TV Status continues to use Trakt metadata and maintains a single `Next Airing` personal list.
- Trakt credentials are requested only when an enabled feature actually requires Trakt.
- Legacy filler/canon personal-list publishing is an explicit compatibility mode and is disabled by default.
- Legacy publishing capacity decisions use account limits reported by Trakt at runtime instead of hard-coded VIP/free assumptions.
- The main dashboard no longer performs live Trakt calls merely to render its normal status view.
- The Trakt web page no longer exposes the configured client secret back to the browser.
- Episode-title overrides are presented as generic mapping overrides because the local mapper also consumes `title_mappings.special_matches`.
- Mapping fixes in the web UI regenerate local Anime Episode Type outputs instead of silently invoking Trakt list publishing.

### Removed

- The manually maintained `scheduler.scheduled_anime` configuration workflow.
- The legacy `schedule` CLI command.
- Obsolete web endpoints and client methods for bulk Trakt-list browsing, deletion, and synchronization.
- The obsolete per-anime web run workflow.
- Core Anime Episode Type dependence on Trakt OAuth and personal-list inventory.

### Safety / Compatibility

- Legacy episode-list publishing fails closed unless `trakt.episode_list_publishing.enabled` is explicitly true.
- Internal legacy publishing and `fix-mappings` check the publishing opt-in before attempting Trakt OAuth.
- Existing `title_mappings.special_matches`, Plex mappings, AFL mappings, AFL aliases, ignored AFL entries, and TVDb mappings remain supported.
- Automatic schedule discovery preserves the previous generated schedule on fatal discovery failure.
- A Trakt scheduling failure cannot block local Anime Episode Type generation.
- Runtime Trakt limits are treated as the source of truth rather than assuming limits from VIP/non-VIP labels.
- `Next Airing` remains independent from legacy Anime Episode Type personal-list publishing.

### Validation Completed Before Docker Release Testing

- Real no-Trakt Anime Episode Type regression reached the production local synchronization path successfully.
- Core Anime Episode Type functions passed direct source assertions for absence of Trakt publishing/OAuth dependencies.
- Generated schedule authority regression confirmed that the retired hard-coded schedule is ignored.
- Legacy publishing disabled-state regression confirmed OAuth is unreachable.
- Mapping-fix regeneration was verified to use the local Anime Episode Type backend.
- Python compilation and `git diff --check` passed during development.
- TypeScript type checking and the Next.js production build passed during development.
- Source-wide 1.x architecture and stale web API sweeps passed.

### Validation Required Before Release

- Build the exact 2.0 candidate Docker image from the final candidate commit.
- Run the candidate with the real Docker mounts and Plex/Kometa environment.
- Verify container startup and runtime paths.
- Run core Anime Episode Type generation from inside the container with no Trakt dependency.
- Verify Kometa collection/overlay output generation from inside Docker.
- Exercise automatic schedule refresh, failure preservation, and include/exclude overrides.
- Exercise TV Status and the single `Next Airing` list from inside Docker.
- Verify legacy publishing remains disabled before OAuth when opt-in is false.
- Verify explicit legacy publishing opt-in and runtime account-capacity enforcement.
- Exercise the migrated web UI against the same candidate container.
- Exercise scheduler jobs from inside the candidate container.
- Validate Trakt-backed behavior with a fresh non-VIP/free-tier Trakt account.
- Do not tag `v2.0.0` until these gates pass.

---

## [1.1.0] - 2026-08-11

### Added

- Automatic anime schedule generation from Plex, AnimeFillerList, and Trakt series status.
- Generated `config/scheduled-anime.yaml` runtime state with scheduled shows, decisions, review entries, ignored entries, and discovery statistics.
- `refresh-schedule` command for manually refreshing the generated anime schedule.
- Discord notifications when automatic schedule membership changes.
- `scheduler.auto_schedule.always_include` and `always_exclude` overrides.
- `afl_mappings` support for alternate AnimeFillerList URL slugs.
- `afl_identity_aliases` for legitimate alternate AnimeFillerList display titles without weakening identity validation.
- `afl_ignored` for explicitly acknowledged unsupported or broken AnimeFillerList entries.
- Root `config.example.yaml` and `mappings.example.yaml` starter configuration files.

### Changed

- Hard-coded `scheduler.scheduled_anime` was no longer required when automatic scheduling was enabled.
- Scheduled anime were discovered from the intersection of Plex ownership, valid AnimeFillerList data, and active/future Trakt status.
- Automatic schedule discovery used a single Trakt lookup per eligible show.
- Trakt requests were paced and included retry/backoff handling for rate limits and transient server errors.
- Automatic anime batches deferred expensive Plex/Kometa collection synchronization until the end of the batch.
- Known `afl_ignored` entries were skipped before AnimeFillerList validation and no longer appeared as repeated errors or unresolved review entries.
- The legacy `schedule` command remained available in 1.1 for manually maintained `scheduler.scheduled_anime` configurations.

### Fixed

- False Plex connection failures caused by `PlexServer` object truthiness checks.
- Configuration handoff when `anime_trakt_manager.py` was executed as `__main__`.
- Automatic schedule refresh preserved the previous generated schedule when discovery failed instead of replacing it with an empty result.
- Automatic schedule discovery handled Trakt HTTP 429 rate limits without turning affected shows into false review results.

### Examples / Compatibility

- Added example AFL slug overrides for cases such as Blue Lock and To Your Eternity.
- Added an example AFL identity alias for Fighting Spirit / Hajime no Ippo.
- Added example ignored AFL entries demonstrating how known unusable sources can be excluded cleanly.

---

## [1.0.0] - 2026-08-10

### Added

- Plex-aware AnimeFillerList episode mapping across Plex/TVDb seasons.
- Automatic detection of direct aired-order vs. reordered episode sequences.
- Conservative title-based fallback for reordered series, including confidence-ordered fuzzy matching.
- Bounded sequence reconciliation for short, structurally safe gaps between trusted episode anchors.
- Season 0 / special-episode handling with conservative sequence realignment.
- TVDb show overrides through `tvdb_mappings` for ambiguous adaptations.
- AnimeFillerList page identity validation to reject incorrect HTTP 200 responses for unrelated shows.
- Batch collection synchronization after scheduled anime updates to avoid rescanning the Plex library after every show.
- Accurate scheduled-update reporting for successful vs. skipped/failed anime.
- Support for Kometa config roots mounted directly at `/kometa` when deriving generated collection paths.

### Changed

- Episode mapping now fails closed when Plex and AnimeFillerList ordering cannot be reconciled safely.
- Translation/title differences alone no longer force episode reordering when positional evidence supports Plex aired order.
- Generated anime episode collections use Plex-aware `tvdb_episode` season/episode coordinates.
- Docker images are published from `dustinsmithworkshop/Dakosys` and v1 releases use semantic version tags.

### Validation

The v1.0 mapper was regression-tested against a Plex anime library with 116 mapped shows. The final v8.4 regression mapped 8,547 episodes with 160 intentionally unmapped episodes and preserved fail-closed behavior for incompatible or invalid sources.
