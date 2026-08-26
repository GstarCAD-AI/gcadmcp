# ADR-0008: Evidence contract from gcadclaw

## Status

Accepted.

## Context

`gcadclaw` established that a drawing task is not complete without a brief,
an action log, before/after entity inventories, a nonblank screenshot, and a
feedback/validation report. The MCP server should make this contract
enforceable rather than advisory.

## Decision

Adopt the gcadclaw evidence contract as the server's run contract:
`gcad_begin_run`, `gcad_capture_before_state`, `gcad_collect_evidence`,
`gcad_validate_run`, and `gcad_finalize_run` produce a durable run directory
(manifest, brief, `actions.jsonl`, inventories, screenshots, validation,
feedback). Missing evidence yields `partial`, never full success. Canonical
prompts are loaded from the `gcadclaw-assets` package, not duplicated.

## Alternatives

- Leave evidence to host discipline: rejected; unenforced contracts drift.
- Copy prompt text into the server: rejected; two sources of truth.

## Consequences

- Runs are auditable artifacts; finalization is idempotent by operation ID.
- The server performs only technical screenshot validation; semantic visual
  review stays with the host model.
