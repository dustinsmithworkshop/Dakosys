# GitHub Publishing Checklist — MOSAIC 4.0

## Repository

Use `dustinsmithworkshop/Dakosys` for the initial MOSAIC 4.0 planning and implementation work.

## Branch

Use:

```text
mosaic-4
```

for architecture-changing development while `main` remains the stable DAKOSYS 3.x line.

## Project board

Create a GitHub Project named:

```text
MOSAIC 4.0
```

Suggested workflow columns/status values:

```text
Backlog
Ready
In Progress
Review
Blocked
Done
```

Useful custom fields:

```text
Phase
Feature Area
Risk
Target Release
```

## Suggested labels

```text
epic
story
architecture
mosaic-4
foundation
rebrand
plex
jellyfin
kometa
artwork
tv-status
next-airing
anime-episode-type
dashboard
migration
technical-debt
safety
```

## Phases

### Phase 1 — Foundation
- M4-01 Publish architecture
- M4-02 Establish MOSAIC identity and compatibility policy
- M4-03 Introduce media-server-neutral core interfaces
- M4-04 Refactor normalized identity model
- M4-05 Introduce output abstraction
- M4-06 Adapt Plex to the new server boundary

### Phase 2 — Jellyfin read path
- M4-07 Implement read-only Jellyfin adapter
- M4-08 Build Plex ↔ Jellyfin parity audit
- M4-09 Preserve dashboard compatibility

### Phase 3 — First native Jellyfin feature
- M4-10 Implement Jellyfin collection output
- M4-11 Port TV Status to normalized core
- M4-12 Implement native Jellyfin Next Airing

### Phase 4 — Artwork Manager
- M4-13 Validate Jellyfin artwork ownership strategy
- M4-14 Implement Jellyfin Artwork Manager output

### Phase 5 — Native presentation engine
- M4-15 Build native compositor foundation

### Phase 6 — Anime and migration
- M4-16 Design Jellyfin Anime Episode Type representation
- M4-17 Publish DAKOSYS 3.x → MOSAIC 4.x migration guide

## Repository rename

Do not make the repository rename the first implementation task.

First:
1. clarify upstream licensing/permission;
2. publish and accept the architecture;
3. establish the epic/backlog;
4. prove the adapter boundaries.

Then decide whether to rename the existing fork or migrate Git history to a new standalone `mosaic-media` repository.
