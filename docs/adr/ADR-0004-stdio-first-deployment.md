# ADR-0004: STDIO-first deployment

## Status

Accepted.

## Context

The MVP controls a desktop application on the operator's machine. Network
exposure would require authentication, leases, and transport security that
are out of scope for the first release.

## Decision

Ship `stdio` transport first. Streamable HTTP is a later, separately
authorized deployment mode (localhost bind, authentication, rate limiting).
Logging goes to stderr or a rotating file; stdout is reserved for the
protocol.

## Alternatives

- Streamable HTTP first: rejected; enlarges the attack surface before the
  core safety mechanisms exist.

## Consequences

- Host configuration examples are the primary integration surface.
- No listening port, no outbound network dependency in the MVP.
