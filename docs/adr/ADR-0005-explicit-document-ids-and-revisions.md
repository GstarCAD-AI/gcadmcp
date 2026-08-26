# ADR-0005: Explicit document IDs and revisions

## Status

Accepted.

## Context

GstarCAD documents are identified by COM pointers that must never leave the
actor thread, and silently mutating "the active document" is unsafe with
multiple open drawings. Retries must not duplicate geometry.

## Decision

The server assigns UUID `document_id` values per runtime and maintains a
monotonic per-document `revision`. Mutating tools require `document_id`;
they accept `expected_revision` and reject stale writes with
`DOCUMENT_CONFLICT`. Mutating tools also take client-generated
`operation_id` values recorded in an idempotency store. A `runtime_id`
exposes restart invalidation.

## Alternatives

- Path-based identity: rejected; unsaved documents have no path, and paths
  change on save-as.
- Implicit active-document mutation: rejected; ambiguous and dangerous.

## Consequences

- Clients must list documents and track revisions; tools report the selected
  document in every result.
- Server revisions detect server-mediated conflicts only; human edits outside
  the server are reported as a limitation until reactor-based detection
  exists.
