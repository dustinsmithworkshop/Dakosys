# MOSAIC Repository Strategy

## Recommendation

**Use the existing `dustinsmithworkshop/Dakosys` fork for MOSAIC 4.0 planning and early architecture work. Do not create a standalone MOSAIC code repository yet.**

The current repository contains the implementation history that led to DAKOSYS 3.1 and is the natural place to track the architectural transition.

A standalone MOSAIC repository should be considered only after the licensing/permission status of the inherited upstream DAKOSYS code is resolved.

## Compatibility contract

The repository decision is part of the broader MOSAIC 4.x compatibility promise.

See [`mosaic-4-compatibility-contract.md`](mosaic-4-compatibility-contract.md) for the canonical policy covering DAKOSYS 3.1 configuration, environment variables, durable state, filesystem/runtime names, Plex and Kometa continuity, attribution, and deprecation boundaries.

## Why this path

### Preserve history

The existing repository contains the real evolution of the project. MOSAIC should preserve that history rather than imply the system was created from scratch.

### Avoid premature fragmentation

Creating a second repository now would split architecture discussion, issues, implementation work, tests, releases, and migration context before the new architecture is implemented.

### Keep the fork relationship visible while licensing is unresolved

The project originated as a fork of `sahara101/Dakosys`. At the time this document was prepared, the inherited repository did not contain an obvious root `LICENSE` file.

That does **not** establish what rights or permissions may exist elsewhere, and this document is not legal advice. It does mean the project should avoid assuming a license that has not been confirmed.

Before moving inherited source into a new independent repository, clarify the license/permission governing the original code.

## Near-term plan

Continue using:

```text
dustinsmithworkshop/Dakosys
```

for MOSAIC architecture documentation, 4.0 epic/story issues, design discussions, compatibility planning, and early refactoring.

Use the long-lived branch:

```text
mosaic-4
```

for architecture-changing implementation work while `main` remains the stable DAKOSYS 3.x line.

## Later decision point

Once licensing/permission is resolved and the MOSAIC 4.0 foundation is stable, choose one of two paths.

### Option A — Rename the existing fork

Example:

```text
dustinsmithworkshop/mosaic-media
```

Advantages:
- preserves issues, releases, stars, watchers, and Git history in place;
- existing GitHub links redirect after a rename;
- least operational migration.

Tradeoff:
- GitHub continues to identify the repository as part of the original fork network.

### Option B — Create a standalone MOSAIC repository

Example:

```text
dustinsmithworkshop/mosaic-media
```

with Git history intentionally migrated from the current repository.

Advantages:
- clean standalone project identity;
- no fork-network presentation;
- clearer long-term branding.

Tradeoffs:
- requires explicit care around inherited-code licensing/permission;
- GitHub issues, releases, stars, and other metadata do not migrate with Git history automatically;
- requires a redirect/archive plan for the old repository.

## Recommended public transition story

> MOSAIC is the successor to DAKOSYS. The project began as a heavily extended fork of `sahara101/Dakosys`. DAKOSYS 3.x focused on Plex and Kometa; MOSAIC 4.x evolves that work into a media-server-neutral orchestration platform.

Exact attribution and license notices should follow the requirements of the confirmed upstream license or permission.

## Version boundary

```text
DAKOSYS 3.1  ->  MOSAIC 4.0
```

MOSAIC 4.0 marks the transition from Plex + Kometa assumptions to a normalized core with media-server adapters, provider integrations, feature engines, and output adapters.

## Working names

```text
Project:      MOSAIC
Repository:   mosaic-media
CLI:          mosaic
Container:    mosaic
```

Do not remove existing `DAKOSYS_*` environment variables or 3.x config keys until a backward-compatible migration/deprecation policy exists.

## Decision record

**Current decision:** Keep planning and early MOSAIC 4.0 development in the existing DAKOSYS fork.

**Revisit when:**
1. upstream licensing/permission is clarified;
2. the media-server abstraction is proven;
3. the desired fork/non-fork GitHub identity is clear; and
4. the DAKOSYS 3.x support strategy is decided.
