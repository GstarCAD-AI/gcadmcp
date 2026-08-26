# Architecture

`gstarcad-mcp-server` is a protocol adapter and workflow runtime around
`pygcadwin`. It is not a second CAD library.

```text
MCP Hosts (Codex / Claude / VS Code / other)
        │ stdio
        ▼
gstarcad-mcp-server
  MCP layer            tools, resources, prompts, typed errors, structured outputs
  policy/session layer permissions, workspace sandbox, idempotency, revisions, audit
  dedicated COM actor  one Windows thread, command queue, document registry
        │ pygcadwin operations registry + services (explicit Context)
        ▼ pywin32 / COM
GstarCAD (interactive desktop session)
```

Side stores: workspace run artifacts, idempotency journal, structured audit
log.

## Layers

- **MCP layer** — thin handlers. Validate input models, check permissions and
  limits, look up idempotency, build a serializable `CadCommand`, await the
  actor, map expected errors to `ToolError`.
- **Policy layer** — workspace path resolution, permission profiles
  (`readonly`, `assistive`, `authoring`, `automation`), idempotency store,
  revision checks, append-only audit.
- **COM actor** — the only thread that touches COM. Owns the `Gcad` session
  and the document registry (`document_id` → actor-only document entry).
  Results are serialized before crossing the thread boundary; raw COM
  objects never leave it.
- **pygcadwin** — typed operation registry and services; transport
  independent; no MCP dependency.
- **gcadclaw-assets** — canonical prompts, workflows, contracts, and evals
  loaded via `importlib.resources`.

## Request flow (mutating tool)

```text
MCP argument validation → permission check → workspace/path validation
→ idempotency lookup → document/revision check → enqueue CadCommand
→ actor resolves document, builds explicit Context
→ pygcadwin operation executes → result serialized → revision incremented
→ journal persisted → typed MCP result returned
```

## Reliability model

- Operation IDs make retries idempotent; same ID + same request hash returns
  the stored result, same ID + different hash raises `IDEMPOTENCY_CONFLICT`.
- Per-document server revisions detect stale writes (`DOCUMENT_CONFLICT`).
- Batches report the honest transaction mode (`best_effort` until undo
  grouping is verified for the installed GstarCAD) and exact committed
  handles on partial commit.
- CAD disconnect marks the runtime `DEGRADED`; mutations are rejected until
  an operator recovers or a controlled reconnect succeeds.

## Evidence model

Runs live under `workspace/runs/<date>/<run_id>/` with manifest, brief,
append-only `actions.jsonl`, before/after entity inventories, screenshots,
validation, and feedback. Missing evidence yields `partial`, never full
success. See ADR-0008.
