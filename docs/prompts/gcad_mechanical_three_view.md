<!-- MCP prompt: gcad_mechanical_three_view -->
<!-- description: Three-view orthographic mechanical drawing workflow. -->
<!-- test arguments: {"requirement": "A stepped shaft, 80 mm long, three views."} -->

## role: user

---
name: mechanical_three_view
version: "0.2.0"
license: MIT
description: Drafting guidance for top/front/right-side orthographic projections, hidden lines, centerlines, and dimensioning conventions.
placeholders: [requirement, units, output_path]
---

# Mechanical three-view drawing guidance

Use this when producing top, front, and right-side orthographic views of a mechanical part in GstarCAD through the `gcad_*` MCP tools. Combine it with the `create_2d_drawing` procedure; this prompt supplies the projection and annotation conventions.

## Requirement

{{requirement}}

Units: {{units}}. Output DWG: {{output_path}}.

## Projection layout

- Use first-angle or third-angle projection consistently; default to third-angle unless the requirement states otherwise.
- **Top/plan view** shows the footprint in X and Y, centered on the origin unless a better datum is given.
- **Front/elevation view** shows height (Z) and width (X). Place it below or above the top view per the chosen projection standard.
- **Right-side view** shows height (Z) and depth (Y). Place it beside the front view per the projection standard.
- Keep consistent scale across all three views and align corresponding features so dimensions project cleanly between views.
- Replace one side view with a section or detail view when it communicates internal geometry better; label sections and details explicitly.

## Hidden lines

- Show features occluded from the current view as hidden lines (dashed linetype) on a dedicated hidden layer.
- Include hidden lines for bores, holes, slots, and internal steps that are not visible in the view.
- Omit hidden lines only where they would clutter the view without adding information; note the omission as an assumption.

## Centerlines

- Draw centerlines on a dedicated centerline layer for every axis of symmetry, every hole, and every bolt circle.
- Extend centerlines slightly beyond the feature they reference.
- For circular features in the top view, use crossing centerlines through the center; for cylindrical features in elevation, use parallel centerlines along the axis.

## Dimensioning conventions

- Dimension each feature in the view where its true shape appears.
- Annotate hole diameters with the Ø symbol, hole counts, and spacing or bolt-circle diameter.
- Give overall length, width, and height once per drawing; avoid redundant chained dimensions that can conflict.
- Annotate thickness, fillet and chamfer sizes (R for radius, C or linear for chamfer), and any critical tolerances the requirement states.
- Place dimension text on a dimensions layer and notes on a text/notes layer; keep dimensions outside the part outline where practical.

## Completion

Follow the `create_2d_drawing` evidence procedure: before/after entity evidence via `gcad_capture_before_state` and `gcad_query_entities`, a reviewed nonblank screenshot via `gcad_capture_view`, and `gcad_collect_evidence` → `gcad_validate_run` → `gcad_finalize_run`. Record the projection standard and any omitted hidden lines as assumptions in the brief.


## Task parameters

- requirement: A stepped shaft, 80 mm long, three views.
- scale hint: 1:1
