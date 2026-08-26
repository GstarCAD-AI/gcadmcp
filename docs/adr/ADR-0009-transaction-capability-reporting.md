# ADR-0009: Transaction capability reporting

## Status

Accepted.

## Context

GstarCAD COM automation support for undo grouping/transactions varies by
version and is not guaranteed. Claiming atomicity that cannot be verified
would mislead models into unsafe retry and repair behavior.

## Decision

Detect and report the actual transaction mode per batch: `undo_group`,
`copy_on_write`, `compensating_actions`, or `best_effort`. The MVP executes
prevalidated batches sequentially, stops on first error when requested,
reports exact committed actions and handles, and sets
`rollback_status` honestly. `atomic=True` is a request, not a promise;
results carry a warning when atomicity was unavailable.

## Alternatives

- Always claim undo-group atomicity: rejected; unverifiable.
- Implement copy-on-write by default: rejected; slow and disruptive for the
  MVP; reserved as a later explicit mode.

## Consequences

- Partial commits are first-class results with exact side-effect records.
- Capability probes per GstarCAD version feed the reported mode.
