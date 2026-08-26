# Architecture

This document explains how the GstarCAD MCP server fits together. Read it before changing the codebase, and keep it updated as the design evolves — an out-of-date architecture doc is worse than none.

This repository is the `gstarcad-mcp-server` project (local directory `gcadmcp`). The full implementation specification is `GSTARCAD_MCP_SERVER_IMPLEMENTATION_GUIDELINE.md`; decision records live in `docs/adr/`.

## Overview

The server is a **secure protocol adapter and workflow runtime** around `pygcadwin`, not a second CAD library. Three layers, three repositories:

```text
gcadclaw            = how an agent should plan, execute, validate, and repair a CAD task
gstarcad-mcp-server = how MCP clients securely and reliably invoke those capabilities
pygcadwin           = how deterministic GstarCAD operations are implemented through COM
```

```text
MCP hosts (Codex / Claude / VS Code / opencode / other)
        │  MCP over stdio
        ▼
gstarcad-mcp-server (this repo)
  MCP layer            tools, resources, prompts, typed errors, structured outputs
  policy/session layer permissions, workspace sandbox, idempotency, revisions, audit
  dedicated COM actor  one Windows thread, command queue, document registry
        │  pygcadwin operation registry + services (explicit Context)
        ▼  pywin32 / COM (GStarCAD.Application.*)
GstarCAD process (live DWG session, interactive desktop)
```

Practical consequence: a drawing-behavior bug belongs in `pygcadwin`, a drafting-convention bug belongs in `gcadclaw`, and this repo only fixes protocol, session, policy, and plumbing issues.

## Components

### pygcadwin — the engine (`../pygcadwin`, v0.2.x)

- Transport-independent; **no MCP dependency**.
- Typed operation registry (`pygcadwin/operations/registry.py`) is the single source for input validation, schemas, permission metadata, and mutation annotations.
- Services (`DocumentService`, `EntityService`, `LayerService`, `LayoutService`, `ViewService`, `EvidenceService`) take explicit wrappers and never discover global state.
- `Gcad` exposes connection observability (`connection_mode`, `owner_thread_id`, `is_connected`) and owner-thread guards (`CadThreadAffinityError`).
- Legacy entry points `tool_schemas()`, `execute_tool()`, `run_actions()` remain, reimplemented on the registry.

### gcadclaw — the workflow contract (`../gcadclaw`, package `gcadclaw-assets`)

- Codex skill plus installable asset package: canonical prompts, workflow YAML, JSON-schema contracts, evaluation fixtures.
- This server loads prompts/contracts with `importlib.resources` — never a second copy.
- Evidence contract: a drawing task is "done" only with brief, action journal, before/after entity inventories, a nonblank screenshot, validation, and the final DWG.

### gstarcad-mcp-server — the adapter (this repo)

Layout under `src/gstarcad_mcp/`:

| Package | Responsibility |
| --- | --- |
| `runtime/` | COM actor (single thread), command envelope, dispatcher, document registry, health, lifecycle |
| `policy/` | permission profiles, workspace sandbox, idempotency, revisions, leases (interface), limits |
| `schemas/` | strict Pydantic request/result models (UUIDs at the boundary, no absolute paths) |
| `tools/` | thin MCP handlers: status, documents, inspection, editing, evidence |
| `resources/` | `gcad://` status/document/run resources |
| `prompts/` | gcadclaw workflow prompts |
| `runs/` | run store, atomic manifest, append-only action journal, validation |
| `cli.py` | `serve`, `status`, `validate-env`, `print-config`, `list-tools`, `version` |

## Data flow (mutating tool call)

```text
MCP argument validation → permission check → workspace/path validation
→ idempotency lookup → document/revision check → enqueue CadCommand
→ actor resolves document, builds explicit Context
→ pygcadwin operation executes → result serialized before crossing the thread
→ revision incremented → journal/audit persisted → typed MCP result returned
```

No handler bypasses this flow to call `Gcad`/`Context` directly.

## Constraints and invariants

- **One COM actor thread.** All COM initialization/references/calls stay on it; raw COM objects never cross the boundary; owner-thread guards enforce this.
- **Explicit document identity.** Mutating tools require `document_id` and honor `expected_revision`; `runtime_id` marks restart invalidation.
- **Idempotent retries.** Client-generated `operation_id` + request hash; conflicts are explicit.
- **Honest transactions.** Batches report the real transaction mode (`best_effort` until undo grouping is verified) and exact committed handles on partial commit.
- **Workspace sandbox.** All client paths are workspace-relative; hostile paths rejected; results return relative paths and `gcad://` URIs.
- **Evidence is contractual.** Missing evidence yields `partial`, never full success.
- **Save is the last mutation.** `gcad_finalize_run` captures the final screenshot *before* the SaveAs: on some GstarCAD versions (e.g. 2026) the view change performed during screenshot capture re-marks the document dirty, so saving last is what keeps `saved_after_mutation` true and `reject_dirty` closes working.
- **Multi-version GstarCAD via ProgID discovery.** `cad.prog_id = "auto"` (the default) delegates to pygcadwin's cascade: all registered `GStarCAD/Gcad.Application[.N]` ProgIDs, newest first, attach-then-launch. An explicit ProgID (config or `GSTARCAD_MCP_PROG_ID`) pins one version; `gcad_get_status.connected_prog_id` reports the winner. Verified against 2026 (`.26`) and 2027 (`.27`).
- **Stdout is protocol.** All logging goes to stderr or rotating files.
- **Windows-only live runtime.** Off-Windows, schema/contract tests import and run; live operations report `PLATFORM_UNSUPPORTED`.

## Status

MVP implementation per the guideline's PR plan; see `CHANGELOG.md`.

Verification state: fake-COM unit/contract suite green (`uv run pytest tests -q`, 170 passed); live stdio smokes green on both GstarCAD 2026 and 2027 — `scripts/smoke_full.py` (55 checks covering every tool, action op, prompt, resource, and error path) and `scripts/smoke_mcp.py` (prompt-driven drawing workflow ending in a `succeeded` finalize). Rendered prompt snapshots used by the smokes live in `docs/prompts/`.
