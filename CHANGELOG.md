# Changelog

All notable changes to this fork are documented here.

## [Unreleased]

### Added

- Autonomous Artwork Manager for configured Plex show and movie libraries.
- MediUX primary artwork provider with cohesive show-set selection, refresh, and migration behavior.
- TMDB artwork fallback and identity enrichment for show and movie coverage gaps.
- Per-library Kometa metadata item stores with one generated YAML file per managed movie/show.
- Durable Artwork Manager ownership/state tracking with transactional application.
- Independent Artwork Manager safety policy with APPLIED, NO_CHANGES, PENDING_REVIEW, BLOCKED, and FAILED outcomes.
- Automatic and manual Artwork Manager apply modes.
- Artwork Manager CLI commands for status, read-only scan, run, and persistent history.
- Live progress reporting for long-running Artwork Manager scans and runs.
- Artwork Manager scheduler integration and web dashboard/current-state/history/progress support.

- Hybrid TV metadata provider architecture using stable Plex external IDs with Sonarr, TMDB, and TVmaze providers.
- Provider-independent normalization for TV lifecycle state and upcoming episodes.
- Field-specific provider precedence:
  - lifecycle: TMDB -> Sonarr -> TVmaze;
  - next episode: Sonarr -> TMDB -> TVmaze.
- Provider provenance and warning reporting for conflicting or suspicious metadata.
- Conservative validation for future episodes reported by providers that also consider a series ended.
- Local provider-derived Next Airing generation for Kometa using ordered `text_file` collections.
- Provider-independent `data/next_airing.json` snapshot used by the DAKOSYS web dashboard.
- TV metadata provider configuration in both web and CLI setup.
- Sonarr credential support through `services.tv_status_tracker.metadata.sonarr` or `SONARR_URL` / `SONARR_API_KEY`.
- TMDB v3 API-key support through the existing top-level `tmdb_api_key`, with `TMDB_TOKEN` bearer authentication available as an environment override.
- Credential-free TVmaze fallback provider.
- Regression coverage for provider identity, Sonarr, TMDB, TVmaze, resolver behavior, presentation, shadow comparison, local Next Airing, web Next Airing, Trakt dependency reporting, TV Status integration, and CLI provider setup.

### Changed

- Artwork Manager discovers configured Plex libraries by media type instead of requiring hard-coded library names.
- Artwork Manager prioritizes curated MediUX artwork and uses TMDB to fill eligible gaps without replacing usable MediUX assets.
- Safe Artwork Manager plans default to automatic application; manual mode remains available for review-first operation.
- Artwork Manager persists provider selection and ownership so later runs can safely refresh or migrate cohesive artwork sets.

- TV / Anime Status Tracker now resolves normal metadata locally instead of requiring Trakt.
- TV Status uses stable Plex external IDs rather than fuzzy title matching between providers.
- Lifecycle and upcoming-episode resolution are independent so a concrete future episode can remain valid even when lifecycle metadata disagrees.
- Next Airing membership now comes directly from the normalized TV metadata resolver.
- Kometa Next Airing collections and the DAKOSYS Next Airing dashboard now consume the same provider-derived data model.
- Next Airing dashboard data is read from `data/next_airing.json` instead of retrieving a personal Trakt list and matching titles back to the TV Status cache.
- TMDB poster artwork on the Next Airing dashboard is optional enrichment and no longer blocks the page when a TMDB key is absent.
- Trakt is now required only for Automatic Active/Future Schedule and optional legacy episode-list publishing.
- The main dashboard and Trakt page now report only features that actually depend on Trakt.
- The Trakt dashboard no longer treats TV Status or Next Airing as Trakt-backed features.
- CLI setup can configure Sonarr, TMDB, and TVmaze for TV Status.
- CLI setup no longer requests Trakt list settings or starts Trakt authentication when TV Status is the only enabled feature.
- Web setup exposes TV metadata provider configuration and no longer presents TV Status / Next Airing as Trakt-dependent.
- TV Status can initialize and run without a `trakt:` configuration section when no Trakt-backed feature is enabled.
- Next Airing air dates retain provider broadcast/calendar semantics while exact timestamps are converted to the configured DAKOSYS timezone for display.

### Removed

- Normal TV Status dependence on Trakt metadata.
- Normal TV Status creation and maintenance of a personal Trakt `Next Airing` list.
- Next Airing dashboard dependence on Trakt list retrieval.
- Next Airing title matching against the local TV Status cache.
- User-visible claims that TV Status or Next Airing require Trakt.

### Validation

- Artwork Manager show and movie workflows were exercised end-to-end against real Plex and Kometa mounts.
- Production-scale Movies processing managed 3,058 of 3,059 Plex movies using MediUX with TMDB fallback.
- A full four-library automatic production run completed with zero blocked and zero failed libraries.
- Production runs exercised provider migrations, set refreshes, TMDB gap filling, transactional writes, durable state, and no-change behavior.

- Full TV metadata regression suite passes with 102 Python tests.
- Next.js production build passes after provider setup and Next Airing UI migration.
- Full no-Trakt TV Status staging run completed against the feature implementation.
- Local Next Airing staging output returned to the expected 81 entries after rejecting an uncorroborated bogus future TMDB episode.
- Staged library totals were:
  - Anime: 42;
  - Cartoons: 4;
  - TV: 35.
- No normal Next Airing Trakt references remain in the web API, page, or TypeScript contract.
- CLI setup regression confirms a TV Status-only installation does not prompt for or authenticate with Trakt.
- Python compilation and `git diff --check` pass for the migrated provider paths.

---

## [2.0.0] - 2026-08-13

DAKOSYS 2.0 is an intentional architecture change that moved core Anime Episode Type generation away from Trakt personal lists while retaining Trakt-backed automatic scheduling and the then-existing TV Status implementation.

### Added

- Local Anime Episode Type discovery from Plex + AnimeFillerList without requiring Trakt personal lists.
- Shared AnimeFillerList discovery candidate generation using live catalog entries plus configured mapping-backed identities.
- Automatic Trakt account capability discovery from the authenticated `/users/settings` response.
- Read-only Trakt capability, list-capacity, and list-usage CLI diagnostics.
- Runtime enforcement of Trakt personal-list count and per-list item capacity.
- `prune-legacy-lists` dry-run/apply workflow for removing old DAKOSYS filler/canon personal lists while protecting `Next Airing` and unrelated lists.
- Feature-aware web setup for optional Trakt configuration.
- Automatic schedule management and include/exclude overrides in the web UI.
- In 2.0, the Trakt dashboard focused on connection state, enabled Trakt-backed features, live account limits, and Next Airing usage.

### Changed

- Core Anime Episode Type generation now uses the local Plex + AnimeFillerList mapper and does not require Trakt authentication.
- `sync-collections`, scheduled Anime Episode Type execution, immediate Anime Episode Type execution, and mapping-fix regeneration now use the local backend.
- Automatic active/future scheduling remains Trakt-backed but is independent of core Anime Episode Type generation.
- Generated `config/scheduled-anime.yaml` is now the authoritative automatic schedule source.
- In 2.0, TV Status continued to use Trakt metadata and maintained a single `Next Airing` personal list.
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
- In 2.0, `Next Airing` was independent from legacy Anime Episode Type personal-list publishing.

### Validation

Before the v2.0.0 release, validation included:

- real no-Trakt Anime Episode Type regression reaching the production local synchronization path successfully;
- direct source assertions confirming core Anime Episode Type functions did not depend on Trakt publishing/OAuth;
- generated schedule authority regression confirming that the retired hard-coded schedule was ignored;
- legacy publishing disabled-state regression confirming OAuth was unreachable;
- mapping-fix regeneration using the local Anime Episode Type backend;
- Python compilation and `git diff --check`;
- TypeScript type checking and the Next.js production build;
- source-wide 1.x architecture and stale web API sweeps;
- candidate Docker image startup with the real Plex/Kometa mounts;
- core Anime Episode Type generation inside Docker without Trakt;
- Kometa collection/overlay generation;
- automatic schedule refresh, failure preservation, and include/exclude overrides;
- TV Status and the 2.0 Trakt-backed Next Airing workflow;
- scheduler execution inside Docker;
- explicit legacy publishing opt-in and runtime account-capacity checks.

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
