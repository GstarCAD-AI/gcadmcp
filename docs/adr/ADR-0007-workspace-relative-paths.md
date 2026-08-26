# ADR-0007: Workspace-relative filesystem policy

## Status

Accepted.

## Context

An MCP-exposed automation server must not accept arbitrary filesystem paths:
traversal, UNC, device names, alternate data streams, and symlink escape are
all realistic attack classes on Windows.

## Decision

All client-provided paths are relative to a single workspace root (default
`%USERPROFILE%\Documents\GstarCAD-MCP`) and resolved through one
canonicalizer. Absolute paths, `..`, UNC, device names, ADS, reserved names,
disallowed extensions, and symlink/junction escape are rejected. Results
return workspace-relative paths and `gcad://` resource URIs, never absolute
paths.

## Alternatives

- Allow absolute paths with an allow-list: rejected; harder to audit and
  more failure modes.

## Consequences

- Inputs live under `inputs/`, outputs under `outputs/` or the active run.
- Overwrite is denied unless explicitly requested and permitted by policy.
