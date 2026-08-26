# Security Policy

## Scope

`gstarcad-mcp-server` is a local MCP server that automates GstarCAD through
COM on a Windows interactive desktop session. Security is designed around a
single local operator and one controlled CAD instance.

## Prohibited capabilities (by design)

The server never exposes:

- arbitrary Python execution, `eval`, or shell commands;
- raw COM dispatch or arbitrary COM method invocation;
- raw `SendCommand` / arbitrary CAD command strings;
- unrestricted filesystem access (all paths are workspace-relative);
- network listeners in the default `stdio` deployment.

## Path policy

All client-provided paths are workspace-relative and resolved through a single
canonicalizer that rejects absolute paths, `..` traversal, UNC paths, Windows
device names (`CON`, `NUL`, ...), alternate data streams, symlink/junction
escape, and disallowed extensions.

Allowed extensions (defaults):

- Inputs: `.dwg`, `.dxf`
- Outputs: `.dwg`, `.dxf`, `.png`, `.json`, `.jsonl`, `.md`

## Permission profiles

Server-side enforcement (tool annotations are hints, not authorization):

| Profile | Intent |
|---|---|
| `readonly` | inspection and screenshots only |
| `assistive` | guided editing with explicit saves |
| `authoring` | full document authoring (default) |
| `automation` | unattended server-owned documents only |

Destructive operations (delete, discard, overwrite, quit) require explicit
arguments plus profile permission and are denied by default for external
(user-owned) documents.

## Prompt injection boundary

Drawing content (text entities, layer names, table cells, filenames) is
untrusted data. It is returned as data, never executed, never used to modify
tool definitions or policy.

## Audit

Mutating operations, permission/path denials, saves, destructive actions, and
partial commits are recorded in an append-only audit log with safe relative
paths and hashes. Audit logs may contain more detail than client-visible
errors but never secrets.

## Reporting an issue

Report vulnerabilities through the GstarCAD-AI organization security contact.
Please include reproduction steps against `gstarcad-mcp validate-env` output.
