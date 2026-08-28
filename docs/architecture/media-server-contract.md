# MOSAIC Media Server Contract

**Tracking:** M4-03 / #7

## Purpose

This document defines the first executable boundary between MOSAIC core logic and media-server-specific APIs.

The contract is intentionally **read-only**. Plex, Jellyfin, and future adapters translate their native API objects into normalized MOSAIC inventory records. Mutations belong to output adapters and are not part of this interface.

## Dependency rule

```text
platform API / SDK
      |
      v
mosaic/servers/<platform>/
      |
      v
mosaic/servers/base.py
      |
      v
mosaic/core/
      |
      v
feature engines
```

The allowed dependency direction is:

- `mosaic/core/` depends only on platform-neutral Python/domain concepts.
- `mosaic/servers/base.py` depends on `mosaic/core/` normalized records.
- platform adapters may depend on Plex/Jellyfin SDKs or HTTP clients.
- feature engines may depend on `mosaic/core/` and abstract server contracts.
- `mosaic/core/` must **not** import Plex, Jellyfin, or Kometa APIs.
- feature engines using the new pathway must not receive raw Plex/Jellyfin objects.

## Contract

`mosaic.servers.MediaServer` exposes normalized read operations for:

- library enumeration;
- movie enumeration;
- show enumeration;
- season enumeration;
- episode enumeration;
- item detail lookup;
- exact external-provider ID evidence;
- media sources and byte sizes;
- current image metadata;
- current image content.

The interface does not contain collection writes, metadata writes, image uploads, Kometa YAML emission, or other mutation methods.

## Capability model

Not every media server exposes every useful read in the same way. Adapters therefore advertise a set of `MediaServerCapability` values.

Callers may use:

```python
server.supports(MediaServerCapability.IMAGE_INFO)
```

or require a capability explicitly:

```python
server.require_capability(MediaServerCapability.IMAGE_INFO)
```

Unsupported operations raise `UnsupportedMediaServerCapabilityError` with normalized server and operation context instead of relying on platform-specific exception types.

## Normalized inventory records

The initial inventory layer defines:

- `MediaLibrary`
- `MediaItem`
- `MediaSource`
- `ImageInfo`
- `ExternalId`
- `LibraryKind`
- `MediaItemKind`
- `ImageType`

These models intentionally describe **inventory**, not durable cross-server identity.

### Server-local IDs are not universal identity

`MediaItem.server_item_id` is only the stable ID supplied by the adapter's source server.

For example:

```text
Plex ratingKey      -> server_item_id
Jellyfin item UUID  -> server_item_id
```

This story does not claim those values are interchangeable or globally unique.

M4-04 / #8 owns the durable identity model that will combine server type, server instance, server-local ID, and external-provider evidence.

## External IDs preserve ambiguity

`get_external_ids()` returns a **sequence** of `ExternalId(provider, value)` records rather than a `provider -> value` dictionary.

That is deliberate. A media server can expose multiple exact candidates for the same provider, and the adapter boundary must not silently throw evidence away by choosing the first one.

Example:

```python
(
    ExternalId(provider="tmdb", value="100"),
    ExternalId(provider="tmdb", value="101"),
    ExternalId(provider="tvdb", value="200"),
)
```

Candidate selection and ambiguity handling belong to the identity layer rather than the server adapter.

## Error boundary

Adapters should translate expected platform errors into MOSAIC errors where the distinction is meaningful:

- `MediaServerConnectionError`
- `MediaServerAuthenticationError`
- `MediaServerItemNotFoundError`
- `UnsupportedMediaServerCapabilityError`

All derive from `MediaServerError` and may carry:

- `server_type`
- `server_instance`
- `operation`

Platform exception objects may be retained as Python exception causes for diagnostics, but should not become the interface consumed by feature logic.

## Adapter implementation guidance

A platform adapter should:

1. perform platform-specific API calls inside the adapter package;
2. preserve exact server-local IDs;
3. normalize provider IDs without fuzzy title matching;
4. preserve multiple exact external-ID candidates;
5. normalize byte sizes as integer bytes;
6. map platform-specific image roles into MOSAIC `ImageType` values;
7. fail explicitly when an advertised operation is unsupported;
8. avoid performing mutations through this read interface.

## Scope boundary with follow-up stories

This contract deliberately leaves several concerns to later stories:

- **M4-04 / #8:** durable media-server-neutral identity and migration from `plex_rating_key` state.
- **M4-05 / #9:** output/mutation abstraction.
- **M4-06 / #10:** Plex implementation of this read contract.
- **M4-07 / #11:** Jellyfin implementation of this read contract.

No current Plex production pathway is routed through this interface by M4-03.

## Contract testing

`tests/test_mosaic_media_server_contract.py` provides an in-memory fake adapter that verifies:

- normalized model usage;
- preservation of multiple external-ID candidates;
- capability checks;
- normalized unsupported-capability errors;
- normalized item-not-found errors;
- media-source/image read shapes.

The fake adapter is test-only. It does not introduce a production media-server implementation.
