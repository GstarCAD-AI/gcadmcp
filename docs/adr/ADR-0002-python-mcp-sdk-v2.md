# ADR-0002: Python MCP SDK v2

## Status

Accepted.

## Context

The server needs typed tools, resources, prompts, structured output,
lifespan management, and `stdio` transport. `pygcadwin` is Python.

## Decision

Use the official MCP Python SDK v2, pinned `mcp>=2,<3`. Use `MCPServer` from
`mcp.server.mcpserver`, `ToolError`/`ResourceNotFoundError` from
`mcp.server.mcpserver.exceptions`, and `MCPError` from
`mcp.shared.exceptions` for protocol-level failures.

## Alternatives

- TypeScript/Rust/C++ server: rejected; would require reimplementing or
  bridging the entire COM layer.
- SDK v1: rejected; v2 is the stable line for the 2026-07-28 protocol.

## Consequences

- Python 3.10+ runtime dependency.
- The major SDK version must stay pinned and contract-tested; schema
  snapshots guard against unintended drift.
