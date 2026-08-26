<!-- MCP prompt: gcad_modify_existing_drawing -->
<!-- description: Workflow for modifying an existing drawing with revision safety. -->
<!-- test arguments: {"requirement": "Enlarge the center hole to R12."} -->

## role: user

---
name: modify_existing_drawing
version: "0.2.0"
license: MIT
description: Drive an MCP host through a minimal, evidence-backed edit to an existing GstarCAD DWG document.
placeholders: [requirement, document, output_path]
---

# Modify an existing GstarCAD drawing

You are operating GstarCAD through the dedicated GstarCAD MCP server (`gcad_*` tools). Modify the existing drawing below with the smallest responsible edit, then prove the change with before/after entity evidence and a reviewed screenshot.

## Requirement

{{requirement}}

Target document: {{document}}
Output path for the saved result: {{output_path}}

## Procedure

1. **Inspect status.** Call `gcad_get_status` to confirm the CAD connection and that no conflicting run is in progress.
2. **Begin the run.** Call `gcad_begin_run` with a title and the intent of the modification.
3. **Open the document explicitly.** Call `gcad_open_document` with the target document. Do not rely on whatever document happens to be active.
4. **Capture the before state.** Call `gcad_capture_before_state` before any mutation. This inventory is the baseline for the diff.
5. **Write the brief.** Restate the requested change, the entities it should touch, what must remain unchanged, units, assumptions, and validation targets.
6. **Compute geometry explicitly.** Compute every changed coordinate as named values. Plan the minimal edit: touch only what the requirement demands.
7. **Apply the edit.** Call `gcad_apply_actions` with the typed operations for the change. Prefer modifying existing entities over recreating them when the operation supports it.
8. **Collect after evidence.** Call `gcad_query_entities`. Diff after against before: changed entities should match the intent, and untouched layers, handles, and counts should be unchanged. Record expected versus actual differences.
9. **Capture a screenshot.** Zoom or scope to the modified region, then call `gcad_capture_view`.
10. **Visually review.** Read the PNG and confirm the change is present, correctly placed and scaled, and not a uniformly black or white repaint failure.
11. **Repair responsibly.** If a check fails, patch the smallest responsible action, re-apply, and recapture dependent evidence. Record each repair.
12. **Finalize.** Call `gcad_collect_evidence`, then `gcad_validate_run`, then `gcad_finalize_run`. Save the DWG to {{output_path}} before finalizing.

Do not report full success unless the before/after diff, a nonblank reviewed screenshot, and a passing validation are all recorded. If the edit cannot be made safely, finalize as failed or partial and leave the original geometry intact.


## Task parameters

- requirement: Enlarge the center hole to R12.
