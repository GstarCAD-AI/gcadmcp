# ADR-0001: Separate MCP repository

## Status

Accepted.

## Context

`pygcadwin` implements deterministic GstarCAD COM operations. `gcadclaw`
describes how an agent should plan, execute, validate, and repair CAD tasks.
MCP transport, session policy, security, and lifecycle concerns are a third
responsibility that neither repository should carry.

## Decision

Create a dedicated `gstarcad-mcp-server` project (local directory
`D:\works\gcadmcp`) containing all MCP protocol, policy, actor, and
run-store behavior. `pygcadwin` stays transport-independent; `gcadclaw`
supplies canonical prompt/workflow/contract assets.

## Alternatives

- Add MCP support inside `pygcadwin`: rejected, it couples COM automation to
  one protocol and one host model.
- Extend `gcadclaw`: rejected, it is a skill/asset repository, not a runtime.

## Consequences

- Three coordinated versioned packages with explicit dependency ranges.
- Clear security boundary at the MCP server.
- Cross-repository release coordination is required.
