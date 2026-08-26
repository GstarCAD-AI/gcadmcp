<!-- MCP prompt: gcad_create_2d_drawing -->
<!-- description: Brief-first workflow for creating a new 2D drawing with evidence. -->
<!-- test arguments: {"requirement": "A 100x60 plate with holes."} -->

## role: user

---
name: create_2d_drawing
version: "0.2.0"
license: MIT
description: Drive an MCP host through creating a 2D GstarCAD DWG drawing from a natural-language requirement with full evidence.
placeholders: [requirement, units, output_path]
---

# Create a 2D GstarCAD drawing

You are operating GstarCAD through the dedicated GstarCAD MCP server (`gcad_*` tools). Create the drawing described below, then prove the result with entity evidence, a reviewed screenshot, and a validated run record. Never claim success from issued actions alone.

## Requirement

{{requirement}}

## Drafting defaults

Apply these defaults unless the requirement overrides them; do not ask for clarification only because units, "2D", output format, base plane, origin, or common conventions were omitted:

- Units: {{units}} (default millimeters). 2D drafting only.
- Draw in model space on the XY plane. Positive Z is the elevation axis for front/side/section references.
- Place the origin at the center of the main part unless a mating interface, pivot, or datum feature is a better datum.
- For ordinary parts produce top/plan, front/elevation, and right-side orthographic views; substitute a section or detail view when it communicates better.
- Use closed outlines for visible profiles, centerlines for axes and symmetry, hidden lines only when useful, hatches for cut material.
- Create named layers for outline/body, cut/hole, centerline, hidden, dimensions, text/notes, and construction; use part-specific layers where helpful.
- Annotate critical sizes, hole diameters, spacing and bolt circles, thickness/height notes, fillet/chamfer notes, view labels, and assumptions.
- Heuristics when unspecified: 2.0–3.0 mm walls for small plastic enclosures; 1.0–3.0 mm cosmetic fillets where safe; M3/M4/M5 normal clearance holes of 3.4/4.5/5.5 mm.
- Save the final DWG to: {{output_path}}

Ask one focused question only when the drawing is impossible, fit- or safety-critical, compliance-bound, or lacks any usable dimension. Otherwise proceed with explicit assumptions and record them in the brief.

## Procedure

Follow these steps in order, using the MCP tools:

1. **Inspect status.** Call `gcad_get_status` to confirm the CAD connection, the active document, and that no conflicting run is in progress. If a prior run is stale or conflicted, resolve it before starting.
2. **Begin the run.** Call `gcad_begin_run` with a short title and the intent derived from the requirement. Record the returned `run_id`.
3. **Create the document.** Call `gcad_new_document` (or `gcad_open_document` when editing an existing file) so the run owns a known document.
4. **Write the brief.** Restate intent, dimensions, units, assumptions, layers, expected entities, annotations, output path, and validation targets. The brief is the contract the evidence will be checked against.
5. **Capture the before state.** Call `gcad_capture_before_state` to snapshot the empty or pre-existing entity inventory.
6. **Compute geometry explicitly.** Before applying anything, compute every coordinate as named values (lengths, radii, centers, angles, spacing). Never let the CAD tool infer geometry implicitly.
7. **Apply the drawing.** Call `gcad_apply_actions` with typed operations (layers, segments, circles, arcs, polylines, rectangles, text, dimensions, hatches), one coherent batch at a time. Prefer typed operations over raw commands.
8. **Collect after evidence.** Call `gcad_query_entities` and compare counts, object names, layers, handles, colors, linetypes, and lineweights against the brief.
9. **Capture a screenshot.** Zoom or scope to the intended view, then call `gcad_capture_view` to produce a PNG resource.
10. **Visually review.** Read the PNG resource and inspect it yourself: confirm the intended geometry is present, correctly scaled, on screen, and not a uniformly black or white repaint failure.
11. **Repair responsibly.** If any check fails, patch the smallest responsible action, re-apply it, and recapture the evidence that depends on it (entities, then screenshot). Record each repair attempt.
12. **Finalize.** Call `gcad_collect_evidence` to assemble the artifact set, `gcad_validate_run` to run the validation hierarchy, and `gcad_finalize_run` to close the run with the status the evidence supports. Save the DWG to {{output_path}} before finalizing.

Do not report full success unless the entity evidence, a nonblank reviewed screenshot, and a passing validation are all recorded in the run.


## Task parameters

- requirement: A 100x60 plate with holes.
- units: millimeters
- output relative path: outputs/drawing.dwg
- evidence level: standard
- drafting profile: authoring
