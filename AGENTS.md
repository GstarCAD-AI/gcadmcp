# AGENTS.md

This file provides guidance to the AI agent when working with code in this repository.

## What this repo is
- gcadmcp: an MCP server for GstarCAD (GCAD), built on two sibling projects:
  - `../pygcadwin` — Python COM automation for GstarCAD; the sole CAD engine (v0.2.x: schemas/operations/services plus the stable core `Gcad`/`Context`/`Document`/`layouts` APIs the server's dispatcher drives).
  - `../gcadclaw` — packaged as `gcadclaw-assets`: the drawing workflow prompts, contracts, and evals the server's prompts load at runtime.
- Implemented: `src/gstarcad_mcp/` is the server package (21 `gcad_*` tools, `gcad://` resources, 6 prompts, CLI `gstarcad-mcp`); tests live in `tests/` (fake-COM unit/contract/actor suites plus env-gated live tests in `tests/integration_windows/`).
- Commands: `uv sync --all-extras`, `uv run pytest tests -q` (add `GSTARCAD_MCP_INTEGRATION=1` for live GstarCAD tests), `uv run gstarcad-mcp serve|status|validate-env|print-config|list-tools|version`.
- Lint/format: pre-commit runs on commit after `uv run pre-commit install`; manually `uv run pre-commit run --all-files`. Black owns formatting (line-length 100); ruff lints E+F only — keep that scope, the codebase deliberately uses patterns other rule classes flag (blind COM catches, loop lambdas, Pydantic `Field()` defaults). Do not re-introduce `ruff format`.
- Testing quirks: the suite is anyio-based with `anyio_mode = "auto"`; pytest-asyncio is disabled via `addopts = ["-p", "no:asyncio"]` (its fixture finalizers break MCP client teardown). Don't add `pytest.mark.asyncio` or re-enable the plugin. Live tests need `GSTARCAD_MCP_INTEGRATION=1` and run serially on Windows only.
- Read `ARCHITECTURE.md` before designing or modifying code; keep it updated when the design changes.

## Ground rules
- The MCP layer stays a thin adapter: no CAD or drafting logic here. New operations are added to `../pygcadwin/pygcadwin/tools.py` first, then surfaced as MCP tools.
- Never invent `pygcadwin` API names — inspect `../pygcadwin/pygcadwin/` first.
- Live CAD runs need Windows with GstarCAD installed and registered as a COM server; on other hosts only static checks are possible.
- Sibling directories under `D:\works\` are separate projects; stay in this directory unless directed elsewhere (pygcadwin and gcadclaw are the two intentional exceptions above).

## opencode.json
- Configures opencode itself: a custom `alibaba` provider via `@ai-sdk/openai-compatible` pointing at DashScope OpenAI-compatible mode (`https://dashscope.aliyuncs.com/compatible-mode/v1`). Edits here are opencode configuration, not application code.
- The API key is injected from the `ALIBABA_API_KEY` environment variable via `{env:...}` interpolation — never hardcode it. If provider auth fails, check that env var first.
- `model` / `small_model` and keys under `provider.alibaba.models` must remain valid DashScope model IDs (currently `alibaba/qwen3.8-max` and `alibaba/qwen3.6-flash`).
