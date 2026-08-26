# Operations

## Requirements

- Windows x64 with an interactive desktop session (Session 0 services cannot
  capture screenshots).
- GstarCAD installed and registered as a COM server
  (`GStarCAD.Application.*` ProgIDs).
- Python 3.10–3.13 with `pywin32`.

Verify with:

```powershell
gstarcad-mcp validate-env --json
```

## Running

```powershell
gstarcad-mcp serve            # stdio; used by MCP hosts
gstarcad-mcp status           # quick diagnostic
gstarcad-mcp print-config     # effective non-secret configuration
gstarcad-mcp list-tools       # tool catalog without starting CAD
```

## Workspace layout

Default root `%USERPROFILE%\Documents\GstarCAD-MCP`:

```text
inputs/   drawings/templates supplied by the user
outputs/  delivered drawings and exports
runs/     evidence directories per run
cache/    screenshots not attached to a run
state/    idempotency journal
logs/     server + audit logs
```

## Configuration

TOML via `GSTARCAD_MCP_CONFIG`, environment overrides `GSTARCAD_MCP_*`
(see `examples/server.example.toml`). The MCP client cannot change
permissions or the workspace root.

## Degraded mode

If GstarCAD cannot start, the server stays up: `gcad_get_status` reports the
diagnosis and mutation tools fail with clear errors instead of crashing the
session.

## Crash/disconnect behavior

COM disconnect marks the runtime degraded, rejects new mutations, preserves
journals, and marks in-flight operations `uncertain`. Uncertain mutations
are never auto-replayed; clients use idempotency keys and document queries
to reconcile.

## Operational cautions

- Run only one controlling server per GstarCAD instance.
- Screenshot capture may briefly restore/bring the GstarCAD window forward.
- Server-owned documents are closed/quit according to policy; external
  documents are never closed or overwritten by default.
