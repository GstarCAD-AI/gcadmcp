# ADR-0003: Single-threaded COM actor

## Status

Accepted.

## Context

`pygcadwin.Gcad` initializes COM on the calling thread and retains GstarCAD
application/document references. MCP tool handlers may run on arbitrary
worker threads. COM apartment objects must not be called cross-thread.

## Decision

All COM initialization, references, and calls live on one dedicated Windows
thread (the COM actor). Tools enqueue serializable `CadCommand` objects and
await futures. Only Pydantic models, dicts, lists, primitives, and bytes
cross the thread boundary. Owner-thread guards in `pygcadwin` enforce this.

## Alternatives

- Per-request COM initialization: rejected; unstable attach/detach churn and
  no shared document registry.
- COM MTA with cross-thread marshaling: rejected; GstarCAD automation
  objects are apartment-threaded in practice.

## Consequences

- CAD operations serialize; throughput is bounded by one thread, which is
  appropriate for one interactive GstarCAD instance.
- Cancellation cannot kill a running COM call; queued work is cancellable,
  running work completes, and idempotency keys make retries safe.
