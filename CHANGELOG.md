# Changelog

All notable changes to this fork are documented here.

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
