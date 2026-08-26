# MCP Prompt Snapshots

Rendered snapshots of the six `gstarcad-mcp` prompts, captured from the live
server (`get_prompt`) with the same arguments used by the smoke tests
(`scripts/smoke_full.py`).

| File | Test argument |
| --- | --- |
| `gcad_create_2d_drawing.md` | `requirement`: "A 100x60 plate with holes." |
| `gcad_modify_existing_drawing.md` | `requirement`: "Enlarge the center hole to R12." |
| `gcad_mechanical_three_view.md` | `requirement`: "A stepped shaft, 80 mm long, three views." |
| `gcad_review_and_repair.md` | `requirement`: "Screenshot came out blank; review and repair." |
| `gcad_finalize_with_evidence.md` | (none) |
| `gcad_validate_before_delivery.md` | (none) |

Each file's leading HTML comments record the prompt name, its MCP description,
and the exact arguments it was rendered with. The authoritative prompt sources
are the `gcadclaw-assets` package files loaded by `gstarcad_mcp.prompts`; these
snapshots are test references, not a source of truth — regenerate them after
changing prompts.
