# Changelog

All notable changes to `gstarcad-mcp-server` are documented here.

## [0.1.0] - Unreleased

### Added

- MCP server built on the official Python SDK v2 (`mcp>=2,<3`), `stdio` first.
- Single dedicated COM actor thread serializing all GstarCAD COM access.
- Document registry with server-generated UUIDs and per-document revisions.
- Tools: `gcad_get_status`, `gcad_list_documents`, `gcad_new_document`,
  `gcad_open_document`, `gcad_activate_document`, `gcad_save_document`,
  `gcad_close_document`, `gcad_list_layers`, `gcad_list_layouts`,
  `gcad_query_entities`, `gcad_get_entities`, `gcad_ensure_layers`,
  `gcad_create_entities`, `gcad_apply_actions`, `gcad_capture_view`,
  `gcad_begin_run`, `gcad_capture_before_state`, `gcad_collect_evidence`,
  `gcad_validate_run`, `gcad_finalize_run`, `gcad_get_run_status`.
- Operation-ID idempotency, optimistic revision checks, and an append-only
  action journal.
- Workspace sandbox with relative-path policy and extension allow-lists.
- Permission profiles: `readonly`, `assistive`, `authoring`, `automation`.
- Run/evidence store with manifest, inventories, screenshots, validation.
- Resources for status, documents, and run artifacts; prompts loaded from
  `gcadclaw-assets`.
- CLI: `serve`, `status`, `validate-env`, `print-config`, `list-tools`,
  `version`.
