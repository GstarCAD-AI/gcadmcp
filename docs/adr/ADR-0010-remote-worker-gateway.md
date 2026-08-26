# ADR-0010: Remote worker/gateway architecture (future)

## Status

Proposed; intentionally not implemented in the MVP.

## Context

Future deployments may serve remote MCP clients. COM automation still
requires a per-user interactive Windows desktop.

## Decision

Keep the MVP boundaries compatible with a future architecture:
authenticated Streamable HTTP gateway -> per-user routing -> secure worker
channel -> per-user desktop worker -> local COM actor -> GstarCAD. Leases
(`DocumentLease` interfaces) and principal-aware idempotency keys are
designed now, enabled later.

## Alternatives

- Expose the local stdio server on a port: rejected; no authentication or
  tenant isolation.

## Consequences

- The local MVP keeps interfaces (principal, lease, idempotency key shape)
  remote-ready without implementing network exposure.
- Remote release requires OAuth/MCP authorization, rate limits, request size
  limits, DNS-rebinding protection, and per-user session isolation.
