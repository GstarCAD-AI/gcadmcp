# ADR-0006: Typed action registry in pygcadwin

## Status

Accepted.

## Context

`pygcadwin/tools.py` manually duplicated JSON schemas, performed limited
argument validation, and dispatched through `getattr`. The MCP server needs
one authoritative source of operations, schemas, permissions, and mutation
metadata.

## Decision

Introduce `pygcadwin/operations/registry.py` as the single source for input
validation, schema generation, legacy `tool_schemas()`/`execute_tool()`/
`run_actions()`, MCP adapters, permission metadata, and mutation/destructive
annotations. Legacy entry points remain and are reimplemented on the
registry.

## Alternatives

- Duplicate validation in the MCP server: rejected; two drifting copies of
  the operation surface.
- Keep the `getattr` dispatcher: rejected; unsafe and untyped.

## Consequences

- `pygcadwin` 0.2.0 gains a `pydantic` dependency.
- Every new operation is added once, in the registry, and automatically
  becomes available to legacy callers and MCP tools.
