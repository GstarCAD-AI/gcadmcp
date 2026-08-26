# Security

## Threat model

The server runs locally and controls a desktop CAD application. Threats
considered: hostile tool arguments (path traversal, oversize batches),
prompt injection through drawing content, accidental damage to user-owned
documents, and unsafe concurrency on COM objects.

## Prohibited capabilities

No arbitrary Python/shell execution, no raw COM dispatch, no raw
`SendCommand`, no unrestricted filesystem access, no network listener in
`stdio` mode. See `SECURITY.md`.

## Workspace sandbox

One canonical resolver handles every client-supplied path:

- workspace-relative only; absolute paths rejected;
- `..` traversal, UNC paths, Windows device names, alternate data streams,
  reserved names, and symlink/junction escape rejected;
- extension allow-lists: inputs `.dwg`/`.dxf`, outputs
  `.dwg`/`.dxf`/`.png`/`.json`/`.jsonl`/`.md`;
- overwrite requires explicit argument plus policy permission.

Results carry workspace-relative paths and `gcad://` resource URIs. Absolute
paths appear only in local audit logs, never in client-visible output.

## Permissions

Enforced server-side per operation (see `PermissionProfile`). Tool
annotations are hints only. Destructive operations (delete, discard,
overwrite, close external, quit) are explicit and profile-restricted;
external (user-owned) documents are protected by default.

## Prompt injection

Drawing text, layer names, table cells, and filenames are returned as data
and labeled as extracted drawing content in prompts/resources. Tool
definitions and policy never change based on drawing content.

## Audit

Append-only `workspace/logs/audit.jsonl` records startup/shutdown, document
open/create/close, every mutation, save/overwrite, denials, partial commits,
and reconnects with hashes and relative paths.

## COM safety

All COM access is serialized on one actor thread (ADR-0003). Owner-thread
guards in `pygcadwin` raise `CadThreadAffinityError` on violations.
