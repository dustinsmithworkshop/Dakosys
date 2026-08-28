# MOSAIC 4.0 Epic and Story Backlog

## Epic

**MOSAIC 4.0 — Media-server-neutral foundation and Jellyfin support**

MOSAIC 4.0 evolves DAKOSYS from a Plex/Kometa-oriented utility into a media-server-neutral orchestration platform while preserving deterministic planning, reviewed apply workflows, fail-closed safety, durable state, artwork cohesion, conservative matching, scheduling, automation, and the dashboard.

> **Core code knows about media, not Plex, Jellyfin, or Kometa. Platform-specific behavior belongs behind adapters.**

## Phase 1 — Foundation

### M4-01 — Publish MOSAIC 4.0 architecture
**Goal:** Establish the architecture document as the shared source of truth.

**Acceptance criteria:** Architecture and runtime diagrams are published; server/provider/feature/presentation/output boundaries and non-goals are documented.

### M4-02 — Establish MOSAIC identity and compatibility policy
**Goal:** Define the DAKOSYS 3.1 → MOSAIC 4.0 transition without turning the rebrand into a breaking change.

**Acceptance criteria:** MOSAIC identity/tagline, attribution language, compatibility policy for `DAKOSYS_*` names/state, and repository/licensing decision record are documented.

### M4-03 — Introduce media-server-neutral core interfaces
**Goal:** Allow feature engines to operate without Plex/Jellyfin object types.

**Acceptance criteria:** Normalized media-server interface and models exist; core code does not import platform APIs; fake-adapter contract tests exist.

### M4-04 — Refactor normalized identity model away from Plex-specific keys
**Goal:** Replace `plex_rating_key` as a universal core identity.

**Acceptance criteria:** Server type, configured server instance, and server-local item ID are represented separately from TMDB/TVDB/IMDb IDs; legacy state has a migration path.

### M4-05 — Introduce output abstraction
**Goal:** Separate desired-state application from library reads.

**Acceptance criteria:** Kometa becomes an output implementation; desired-state models are transport-neutral; unsupported capabilities fail explicitly.

### M4-06 — Adapt Plex inventory to the new server boundary
**Goal:** Preserve existing production Plex behavior through normalized adapters.

**Acceptance criteria:** Plex libraries/items/provider IDs/images/media sizes map to normalized models; regression tests protect the existing path.

## Phase 2 — Jellyfin read path

### M4-07 — Implement read-only Jellyfin adapter
**Goal:** Read Jellyfin through the same normalized boundary used for Plex.

**Acceptance criteria:** Libraries, movies, shows, seasons, episodes, Jellyfin item IDs, provider IDs, image state, media sources, and size data can be inventoried without mutation.

### M4-08 — Build Plex ↔ Jellyfin parity audit
**Goal:** Measure migration parity before native writes are enabled.

**Acceptance criteria:** Matched/unmatched items, season/episode parity, missing/conflicting provider IDs, ambiguous matches, and useful path evidence are reported non-destructively.

### M4-09 — Preserve dashboard compatibility during core refactor
**Goal:** Keep the existing UI useful as the backend becomes server-neutral.

**Acceptance criteria:** Existing critical pages build and run; server identity is no longer globally Plex-specific; Jellyfin inventory/status can be surfaced where available.

## Phase 3 — First native Jellyfin feature

### M4-10 — Implement Jellyfin collection output
**Goal:** Create and reconcile MOSAIC-managed Jellyfin collections without Kometa.

**Acceptance criteria:** Create/add/remove/no-op flows are idempotent, auditable, and do not modify unrelated manual collections.

### M4-11 — Port TV Status to normalized core
**Goal:** Run the existing TV Status resolver from normalized identities.

**Acceptance criteria:** Equivalent Plex and Jellyfin normalized inputs produce equivalent decisions; provider precedence/fallback behavior is preserved.

### M4-12 — Implement native Jellyfin Next Airing
**Goal:** Maintain a Jellyfin-native Next Airing collection.

**Acceptance criteria:** Jellyfin inventory feeds the existing next-airing logic, membership is reconciled safely, ordering is represented as faithfully as supported, and the dashboard surfaces the result.

## Phase 4 — Artwork Manager

### M4-13 — Validate Jellyfin artwork ownership and manual-change detection
**Goal:** Prove a conservative ownership witness before MOSAIC writes artwork natively.

**Acceptance criteria:** Real-server experiments establish how image tags/ETags or equivalent evidence behave; unchanged MOSAIC-owned images can be distinguished from external/manual changes; unknown ownership fails closed.

### M4-14 — Implement native Jellyfin Artwork Manager output
**Goal:** Reuse existing Artwork Manager decision logic while replacing the final Kometa path with Jellyfin image writes.

**Acceptance criteria:** MediUX/TMDB/generated-card selection and cohesion logic are reused; reviewed apply, stale-plan detection, quarantine, and ownership safety remain enforced; Plex/Kometa remains functional.

## Phase 5 — Native presentation engine

### M4-15 — Build native compositor foundation for derived visuals
**Goal:** Render deterministic visual derivatives without recursively baking overlays.

**Acceptance criteria:** Base art, transform specification, derivative, and applied state are separate; unchanged renders are deterministic/cacheable; transform changes always render from authoritative base; TV Status and Size can share the compositor foundation.

## Phase 6 — Anime and migration

### M4-16 — Design Jellyfin Anime Episode Type representation
**Goal:** Define how AFL filler/canon classifications map to Jellyfin-native episode identities and presentation.

**Acceptance criteria:** Existing AFL classification/mapping logic is inventoried for reuse; Jellyfin episode targeting is demonstrated; visual/metadata/collection approaches are compared; a preferred initial representation is selected without ambiguous auto-application.

### M4-17 — Publish DAKOSYS 3.x → MOSAIC 4.x migration guide
**Goal:** Let current users upgrade without losing configuration, state, or Plex/Kometa behavior.

**Acceptance criteria:** Config/environment/state migration, deprecation windows, rollback considerations, dual Plex/Jellyfin mode, and eventual container/repository naming changes are documented.

## Epic success criteria

- Feature engines consume normalized media models without importing Plex/Jellyfin/Kometa APIs.
- Plex and Jellyfin can independently produce equivalent normalized domain models.
- Cross-server identity can be audited conservatively using provider IDs.
- At least one desired result is emitted natively to Jellyfin.
- TV Status + Next Airing work end-to-end on Jellyfin.
- Existing Plex/Kometa workflows continue to function.
- Artwork Manager safety is preserved before native Jellyfin artwork writes are enabled.
- A documented DAKOSYS 3.x → MOSAIC 4.x migration path exists.
