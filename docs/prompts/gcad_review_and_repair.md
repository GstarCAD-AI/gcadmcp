<!-- MCP prompt: gcad_review_and_repair -->
<!-- description: Failure-class-driven review and smallest-responsible repair. -->
<!-- test arguments: {"requirement": "Screenshot came out blank; review and repair."} -->

## role: user

---
name: review_and_repair
version: "0.2.0"
license: MIT
description: Classify a failed or incomplete GstarCAD run and apply the smallest responsible repair, recapturing dependent evidence.
placeholders: [run_id]
---

# Review and repair a GstarCAD run

You are operating GstarCAD through the dedicated GstarCAD MCP server (`gcad_*` tools). A run has failed, produced weak evidence, or stalled. Diagnose it, classify the failure, apply the smallest responsible repair, and recapture every piece of evidence that depends on the repaired step.

Target run: {{run_id}}

## Diagnose

1. Call `gcad_get_status` to see the CAD connection, active document, and current run state.
2. Read the run's `actions.jsonl`, `before_entities.json`, `after_entities.json`, feedback report, and any screenshot already captured.
3. Compare actual state against the brief's expected entities, layers, counts, and output paths.

## Classify the failure

Assign each failure to exactly one class before repairing:

- **COM connection** — GstarCAD not registered, no active document, startup or handle failure.
- **Source/action** — syntax error, unknown operation, or missing required argument in the action batch.
- **Geometry** — missing object, wrong scale, open outline, wrong coordinate assumption, or duplicate entity.
- **Layer/style** — wrong layer, missing color, linetype, or lineweight, or dimension/title layer misuse.
- **Dimension/annotation** — missing or wrong dimension, label, hatch, table, or note required by the brief.
- **Screenshot** — no window handle, empty client area, capture backend failure, blank or uniform image, stale content, or missing PNG.
- **Save** — missing output directory, invalid path, or GstarCAD save error.
- **Policy/conflict** — requirement conflicts with drawing state, safety/compliance constraint, or an in-progress run blocks the operation.

## Repair procedure

1. Patch the smallest responsible source or action. Do not rewrite the whole drawing for a localized fault.
2. Re-run only the failed step via `gcad_apply_actions` (or the specific repair tool), not unrelated work.
3. Recapture every piece of evidence that depends on the repaired step:
   - If geometry or entities changed, rerun `gcad_query_entities`.
   - If the view or screenshot failed, redo the zoom/scope then `gcad_capture_view`.
4. Record the failed attempt and the repair in the feedback report and the run manifest's `repairs` list.

## One-shot screenshot repair

If screenshot capture fails or returns a blank/uniform image, make exactly one focused repair: ensure GstarCAD is visible, restore or maximize its window, call the zoom-extents or scoping operation, wait briefly for repaint, then retry `gcad_capture_view`. If the retry still fails, stop.

## Partial completion

If the screenshot cannot be produced after the one-shot repair, mark the run **partial**. Preserve the entity evidence, action log, and DWG output. Entity evidence alone is not a full success; never report full success without a reviewed, nonblank screenshot.

## Finalize

After repairing, call `gcad_collect_evidence`, `gcad_validate_run`, and `gcad_finalize_run` so the run reflects the repaired state. Set the status to what the evidence supports: `succeeded`, `partial`, or `failed`.


## Task parameters

- requirement: Screenshot came out blank; review and repair.
