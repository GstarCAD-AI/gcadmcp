<!-- MCP prompt: gcad_validate_before_delivery -->
<!-- description: Validation checklist to run before declaring delivery. -->
<!-- test arguments: {} -->

## role: user

---
name: validate_before_delivery
version: "0.2.0"
license: MIT
description: Run the 8-level validation hierarchy over a finished GstarCAD run before delivering or claiming success.
placeholders: [run_id]
---

# Validate a GstarCAD run before delivery

You are operating GstarCAD through the dedicated GstarCAD MCP server (`gcad_*` tools). Before delivering a drawing or claiming success, run this validation hierarchy in order. Each level produces a `ValidationCheck` record (check id, category, status, message, evidence URIs) that belongs in the run manifest and the `validation_result`.

Target run: {{run_id}}

## The 8-level validation hierarchy

Run the levels in order; a failed level does not exempt the remaining levels — record every level you can evaluate.

1. **Execution** — Confirm the action sequence ran without uncaught exceptions. Check the final status of every row in `actions.jsonl`.
2. **Save** — Confirm the DWG was saved to the expected path and the file exists.
3. **Entity classes and layers** — Confirm `after_entities.json` contains the expected object classes and layers from the brief.
4. **Entity counts and handles** — Confirm entity counts and handles match the task intent; flag unexpected duplicates or missing entities.
5. **Annotations** — Confirm the dimensions, labels, hatches, and tables required by the brief exist in the entity evidence.
6. **Screenshot capture** — Confirm screenshot capture succeeded after an appropriate zoom or viewport operation (`gcad_capture_view`).
7. **Screenshot nonblank** — Confirm the screenshot is nonblank and not a uniformly black or white repaint failure.
8. **Visual review** — Read the screenshot and inspect it for missing, stale, incorrectly scaled, or off-screen geometry.

## Recording results

- Call `gcad_validate_run` to execute the hierarchy and produce a `validation_result` conforming to `validation_result.schema.json`.
- Map each level to a check with a stable check id and an informative category (e.g. `execution`, `save`, `entities`, `annotations`, `screenshot`, `visual`).
- For each check set `status` to `passed`, `failed`, `warning`, or `not_run`, and attach the evidence URIs (entity JSONs, screenshot, DWG) that justify the verdict.
- Roll the checks up into the overall result and the run status.

## Delivery rules

- Do not deliver or claim success while any of levels 1–7 fails.
- A level-8 concern that does not contradict the entity evidence may be recorded as a `warning` with a caveat in the feedback report.
- If screenshot evidence is unavailable, the run is at best `partial`; entity evidence alone never upgrades it to full success.


## Task parameters


