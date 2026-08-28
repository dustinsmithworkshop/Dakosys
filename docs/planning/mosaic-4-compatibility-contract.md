# MOSAIC 4.0 Compatibility Contract

**Status:** Proposed compatibility baseline for MOSAIC 4.x  
**Tracking:** M4-02 / #6  
**Version boundary:** DAKOSYS 3.1 → MOSAIC 4.0

## 1. Purpose

MOSAIC 4.0 is an architectural evolution of DAKOSYS 3.x, not a clean-slate rewrite.

This contract defines what existing DAKOSYS users can rely on while the project adopts the MOSAIC identity and introduces media-server-neutral architecture.

The central compatibility promise is:

> **A valid DAKOSYS 3.1 installation must remain a valid starting point for MOSAIC 4.0. Upgrading must not require users to discard working configuration, persistent state, Plex support, or Kometa output merely because the project has been renamed.**

MOSAIC may introduce new configuration, state, adapters, output targets, and preferred names. Existing supported 3.1 behavior must either continue to work or pass through an explicit, documented migration.

---

## 2. Project identity

### 2.1 Name

Beginning with the 4.x generation, the project identity is:

> **MOSAIC — Media Orchestration, Synchronization, Artwork, Identity & Collections**

Tagline:

> **Your media library, orchestrated.**

### 2.2 Historical continuity

The public transition language should remain explicit:

> **MOSAIC is the successor to DAKOSYS. The project began as a heavily extended fork of `sahara101/Dakosys`. DAKOSYS 3.x focused on Plex and Kometa; MOSAIC 4.x evolves that work into a media-server-neutral orchestration platform.**

The rename does not erase repository or implementation history.

### 2.3 Major-version boundary

```text
DAKOSYS 3.1
    |
    | architectural evolution
    v
MOSAIC 4.0
```

The 4.0 major version marks a real architectural boundary:

- Plex becomes a media-server adapter rather than a core assumption.
- Jellyfin becomes a first-class media-server target.
- Kometa becomes one output type rather than the definition of the system.
- normalized identities replace Plex-specific core identity assumptions.
- feature decision engines are shared across media servers and outputs.

---

## 3. Compatibility principles

### 3.1 Compatibility before cleanup

MOSAIC must not remove a working 3.x name, key, state shape, or path solely because a cleaner 4.x equivalent exists.

Introduce the replacement first, migrate safely, emit actionable deprecation information where appropriate, and remove only at a later documented compatibility boundary.

### 3.2 No silent data loss

Configuration or durable state that MOSAIC does not understand must not be silently ignored, reset, overwritten, or deleted if doing so could change managed media state.

When a safe migration cannot be completed, fail closed and tell the user what requires attention.

### 3.3 Plex-only remains supported

MOSAIC 4.x must not require Jellyfin.

A user may continue to run Plex + Kometa without configuring Jellyfin.

### 3.4 Kometa remains supported

MOSAIC 4.x must not require native Jellyfin output.

Kometa remains a valid output adapter while native outputs are added.

### 3.5 Migration is additive before destructive

Where old and new representations can coexist safely, 4.x should prefer an additive compatibility period before removing the legacy representation.

---

## 4. Configuration compatibility

### 4.1 Existing `config.yaml`

A valid DAKOSYS 3.1 `config.yaml` must be accepted as a valid MOSAIC 4.0 starting configuration.

The 4.0 architecture may introduce new top-level concepts such as media servers and outputs, but initial migration must not require users to rewrite a working configuration by hand before MOSAIC can start.

For example, existing 3.1 configuration currently includes concepts such as:

```yaml
plex:
  url: ...
  token: ...
  libraries: ...

kometa_config:
  asset_directory: ...
  collections_dir: ...
  yaml_output_dir: ...

services:
  artwork_manager: ...
  anime_episode_type: ...
  tv_status_tracker: ...
  size_overlay: ...
```

MOSAIC may internally normalize those values into future server/output models while continuing to accept the existing external schema.

### 4.2 New preferred schema

A future 4.x schema may prefer concepts such as:

```yaml
media_servers:
  plex:
    type: plex
    ...
  jellyfin:
    type: jellyfin
    ...

outputs:
  kometa:
    ...
  jellyfin:
    ...
```

This example is architectural direction, **not a frozen configuration schema**.

The final schema belongs to the implementation stories that define media-server and output abstractions.

### 4.3 Precedence during compatibility

If MOSAIC temporarily supports both a legacy setting and its new equivalent, precedence must be deterministic and documented.

The preferred pattern is:

1. explicit new MOSAIC setting;
2. legacy DAKOSYS setting;
3. built-in default.

When both old and new settings are present with conflicting values, MOSAIC should surface a warning rather than silently create ambiguity.

### 4.4 Unknown legacy keys

MOSAIC must not opportunistically delete unknown legacy keys when rewriting configuration.

Configuration editors and migrations should preserve keys they do not own unless a documented migration intentionally replaces them.

---

## 5. Environment-variable compatibility

### 5.1 Provider variables are not renamed for branding

Environment variables that describe external providers rather than the project itself should remain stable unless there is a technical reason to change them.

Examples include current names such as:

```text
TMDB_TOKEN
MEDIUX_API_TOKEN
DISCORD_WEBHOOK_URL
```

There is no value in changing these merely to include `MOSAIC` in the name.

### 5.2 `DAKOSYS_*` variables

Any supported `DAKOSYS_*` environment variable present in 3.x must continue to be accepted throughout the MOSAIC 4.x major line unless a security or correctness issue makes that impossible.

When a `MOSAIC_*` replacement is introduced:

1. `MOSAIC_*` becomes the preferred documented name;
2. the equivalent `DAKOSYS_*` name remains an accepted compatibility alias;
3. if both are set, the `MOSAIC_*` value wins;
4. a conflict should produce a clear warning;
5. removal of the `DAKOSYS_*` alias is not eligible before a future major-version boundary.

### 5.3 Deprecation window

DAKOSYS-branded environment-variable aliases introduced into the compatibility layer are supported for the entire MOSAIC 4.x major line.

They may be considered for removal in MOSAIC 5.0 or later only after:

- the MOSAIC replacement has existed for at least one stable major line;
- release notes have documented the deprecation;
- startup warnings identify the replacement;
- migration documentation exists.

---

## 6. Persistent state compatibility

### 6.1 State is user data

MOSAIC must treat DAKOSYS durable state as user data, not disposable cache.

This includes state used for:

- Artwork Manager ownership and selections;
- reviewed/apply workflows;
- generated-artwork fingerprints;
- run history;
- TV metadata/status state where persisted;
- size history;
- anime mappings and schedules;
- other durable service state.

Disposable caches may be rebuilt only when they are explicitly classified as caches and rebuilding them cannot change ownership or management decisions unsafely.

### 6.2 Versioned migrations

Any persisted-state shape changed by MOSAIC 4.x must have an explicit migration path.

A state migration should:

1. identify the source schema/version;
2. validate required source fields;
3. produce the new representation deterministically;
4. preserve enough information for rollback or diagnosis;
5. write atomically where practical;
6. fail closed on ambiguity;
7. record the migration in logs or audit history.

### 6.3 Plex identity migration

Replacing `plex_rating_key` with a neutral media-server identity must not orphan existing state.

Existing Plex state should be translated conceptually from:

```text
plex_rating_key = 12345
```

to something equivalent to:

```text
server_type = plex
server_instance_id = <configured Plex instance>
server_item_id = 12345
```

The exact schema is owned by M4-04, but the compatibility requirement is fixed here: **existing Plex-backed state must remain addressable after the identity refactor.**

### 6.4 Manual/locked artwork protection survives migration

State migration must not downgrade manual-change, lock, ownership, stale-plan, or reviewed-apply protections.

If ownership cannot be established safely after migration, MOSAIC must treat ownership as unknown and fail closed rather than assuming permission to overwrite artwork.

---

## 7. Filesystem and volume compatibility

### 7.1 Persistent mounts

MOSAIC 4.x should not require users to rename persistent Docker mounts merely for branding.

Existing mounted configuration/data locations remain valid unless a technical migration explicitly requires otherwise.

### 7.2 Generated Kometa output

Existing Kometa output locations remain supported while Kometa is enabled, including configured asset, metadata, collection, and overlay directories.

Adding native Jellyfin output must not silently repurpose or delete Kometa-managed files.

### 7.3 Generated artwork

Generated artwork already referenced by durable Artwork Manager state should remain usable after the rename when its source inputs and fingerprints are still valid.

A branding change alone must not force regeneration of every image.

---

## 8. Docker, CLI, and runtime naming

### 8.1 Preferred 4.x names

Working preferred names are:

```text
Project:    MOSAIC
CLI:        mosaic
Container:  mosaic
Repository: mosaic-media   # subject to repository/licensing decision
```

### 8.2 Existing runtime names

Existing DAKOSYS 3.x container/service naming must not be used as a reason to make an otherwise valid upgrade fail.

Where Docker Compose service names, commands, or scripts are renamed, migration documentation must show both old and new forms during the compatibility period where practical.

### 8.3 Image transition

The final MOSAIC container registry/repository identity is deferred until the repository strategy and upstream licensing/permission question are resolved.

No current DAKOSYS image/tag should be silently retargeted to materially different software without explicit release/version documentation.

Existing 3.x releases should remain identifiable as DAKOSYS releases.

---

## 9. UI and documentation compatibility

### 9.1 Branding may change before runtime names

The web UI, docs, issue tracker, and release notes may adopt MOSAIC branding before every compatibility alias is removed internally.

This is expected.

### 9.2 Legacy terminology

Where a user-facing control still maps to a legacy config key or Kometa-specific mechanism, documentation should explain the relationship rather than pretend the legacy mechanism no longer exists.

### 9.3 Warnings must be actionable

Deprecation warnings should state:

- what legacy setting/name was detected;
- the preferred replacement;
- whether behavior is currently unchanged;
- the earliest release in which removal could occur, if known.

Warnings should not be emitted merely because a supported 3.x configuration is being used unless the user has an actionable migration available.

---

## 10. Feature compatibility guarantees

### 10.1 Plex

Plex remains a supported media-server adapter in MOSAIC 4.x.

The media-server abstraction must preserve enough behavior for existing Plex-backed features to continue functioning.

### 10.2 Kometa

Kometa remains a supported output in MOSAIC 4.x.

Native Jellyfin output is additive, not a replacement requirement.

### 10.3 Jellyfin

Jellyfin support may arrive feature-by-feature.

The presence of a Jellyfin adapter does not imply parity until a feature's story explicitly declares and tests that capability.

Unsupported Jellyfin feature/output combinations must fail explicitly rather than silently fall back to an unsafe behavior.

### 10.4 Dual-server operation

During migration, Plex and Jellyfin may coexist.

MOSAIC must not assume that the primary read server, identity source, and output target are always the same system.

---

## 11. Deprecation policy

A supported 3.x behavior may be deprecated in 4.x when a replacement exists, but deprecation is not removal.

For compatibility-sensitive interfaces such as environment variables, configuration keys, state formats, and filesystem paths:

1. document the replacement;
2. support both forms when technically safe;
3. provide deterministic precedence;
4. warn only when the user can take meaningful action;
5. migrate automatically when the transformation is unambiguous;
6. fail closed when it is not;
7. do not remove the legacy form before the documented major-version boundary.

### 11.1 Default removal boundary

Unless security/correctness requires earlier action, DAKOSYS-branded compatibility aliases are not eligible for removal during MOSAIC 4.x.

The earliest default removal boundary is MOSAIC 5.0.

This is a compatibility floor, not a requirement that 5.0 remove them.

---

## 12. Repository, attribution, and licensing

### 12.1 Current repository

MOSAIC 4.0 planning and early implementation remain in:

```text
dustinsmithworkshop/Dakosys
```

The existing Git history is intentionally preserved.

### 12.2 Upstream attribution

The project must continue to acknowledge that it originated from `sahara101/Dakosys`.

The rebrand must not imply that inherited upstream work was created independently by the MOSAIC project.

### 12.3 Licensing/permission blocker

At the time the MOSAIC architecture baseline was created, no obvious root `LICENSE` file was present in the upstream repository.

This document makes no legal conclusion about the rights governing that code.

Until the upstream licensing/permission basis is clarified:

- do not assume a license that has not been confirmed;
- do not relicense inherited source without authority;
- do not move inherited code into a standalone non-fork repository merely for branding;
- keep the repository-strategy decision explicitly open.

See `docs/planning/repository-strategy.md` for the current repository decision record.

---

## 13. Compatibility matrix

| Surface | DAKOSYS 3.1 | MOSAIC 4.x policy |
|---|---|---|
| Project branding | DAKOSYS | MOSAIC preferred |
| Existing `config.yaml` | Supported | Must remain a valid starting point |
| Legacy config keys | Supported | Compatibility support; migrate deliberately |
| Provider env vars | Supported | Keep stable unless technically necessary |
| `DAKOSYS_*` env vars | Supported where present | Accepted throughout 4.x; `MOSAIC_*` may become preferred |
| Plex | Core assumption | Supported adapter |
| Jellyfin | Not supported | Added feature-by-feature |
| Kometa | Primary output mechanism | Supported output adapter |
| Persistent state | DAKOSYS schema | Versioned migration; no silent reset |
| Manual artwork protections | Supported | Must not be weakened by migration |
| Existing Kometa files | Supported | Preserve while Kometa output is enabled |
| DAKOSYS container/runtime names | Current | Compatible during transition |
| Repository | DAKOSYS fork | Stay in existing fork until repository/license decision |
| Git history/upstream attribution | Existing | Preserve explicitly |

---

## 14. Definition of compatibility success

M4-02 is satisfied when this contract is accepted as the 4.x baseline and subsequent stories treat the following as hard requirements:

1. existing 3.1 config is a supported 4.0 starting point;
2. existing persisted state is migrated rather than discarded;
3. Plex and Kometa remain supported;
4. Jellyfin support is additive and capability-driven;
5. DAKOSYS-branded runtime compatibility aliases survive through 4.x;
6. manual/ownership safety guarantees are not weakened;
7. repository history and upstream attribution remain visible;
8. licensing/permission uncertainty remains an explicit blocker for unsupported relicensing or standalone source migration.

Changes to these guarantees require an explicit architecture/compatibility decision rather than an incidental implementation change.
