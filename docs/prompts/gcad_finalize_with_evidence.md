<!-- MCP prompt: gcad_finalize_with_evidence -->
<!-- description: Finalize a run and report the canonical artifact set. -->
<!-- test arguments: {} -->

## role: user

---
name: finalize_with_evidence
version: "0.2.0"
license: MIT
description: Assemble the canonical artifact set and finalize a GstarCAD run, forbidding full success without complete evidence.
placeholders: [run_id, output_path]
---

# Finalize a GstarCAD run with evidence

You are operating GstarCAD through the dedicated GstarCAD MCP server (`gcad_*` tools). Close out a run only when the canonical evidence set is complete. The artifact list below is a completion contract: no full-success claim is permitted without it.

Target run: {{run_id}}
Saved DWG path: {{output_path}}

## Canonical artifact list

A completed drawing run must persist all of the following:

- **Run manifest** — a `run_manifest` conforming to the `run_manifest.schema.json` contract: run id, status, title, intent, units, assumptions, document identity and revisions, artifact map, validations, and repairs.
- **Brief** (`brief.md`) — intent, dimensions, units, assumptions, layers, expected entities, annotations, output paths, and validation targets.
- **Actions** (`actions.jsonl`) — one row per executed operation with step, operation, arguments, status, handles or output paths, and error text for failures.
- **Before entities** (`before_entities.json`) — the entity inventory captured before mutation.
- **After entities** (`after_entities.json`) — the entity inventory captured after mutation, conforming to the `evidence.schema.json` entity shape.
- **Nonblank screenshot** — at least one reviewed PNG that is not uniformly black or white and shows the intended geometry.
- **Feedback/validation** — `feedback.md` or `feedback.json`, plus the `validation_result` from `gcad_validate_run`.
- **Final DWG** — the saved `.dwg` at {{output_path}} when saving succeeds.

## Procedure

1. Confirm the DWG is saved to {{output_path}}. If the save failed, record it and finalize as `partial` or `failed`.
2. Call `gcad_collect_evidence` to assemble the before/after entity inventories, screenshot, and action log into the run record.
3. Call `gcad_validate_run` to run the validation hierarchy and obtain a `validation_result`.
4. Reconcile the manifest: set `status`, the `artifacts` map, the `validations` list, and any `repairs`.
5. Call `gcad_finalize_run` to persist the manifest and close the run.

## Completion rules

Do not:

- claim success from generated code or issued actions alone;
- finalize as `succeeded` while any required artifact is missing;
- accept a uniformly black or white screenshot as evidence;
- finalize a drawing-modifying run without a nonblank screenshot;
- claim a validation step that was not actually run.

If any artifact is missing after best-effort repair, finalize with the honest status (`partial` or `failed`) and record what is missing in the manifest warnings. Prefer an accurate partial result over a false full success.


## Task parameters


