"""MCP prompt contract tests (guideline §19, §31.7)."""

from __future__ import annotations

import re

import pytest
from support.flows import EXPECTED_PROMPT_NAMES

pytestmark = pytest.mark.anyio

_DRIVE_PATH = re.compile(r"[A-Za-z]:[\\/]")
_UNC_PATH = re.compile(r"\\\\[A-Za-z0-9]")

SAMPLE_ARGS = (
    {"requirement": "Draw an 80x50 plate with two 3mm holes."},
    {"requirement": "Draw a plate.", "units": "millimeters"},
    {},
)


class TestPromptCatalog:
    async def test_exact_prompt_names(self, client):
        result = await client.list_prompts()
        names = {prompt.name for prompt in result.prompts}
        missing = EXPECTED_PROMPT_NAMES - names
        extra = names - EXPECTED_PROMPT_NAMES
        assert not missing, f"missing prompts: {sorted(missing)}"
        assert not extra, f"unexpected prompts: {sorted(extra)}"

    async def test_every_prompt_renders(self, client):
        result = await client.list_prompts()
        for prompt in result.prompts:
            rendered = None
            last_error: Exception | None = None
            for args in SAMPLE_ARGS:
                try:
                    rendered = await client.get_prompt(prompt.name, args)
                    break
                except Exception as exc:  # noqa: BLE001 - try next argument shape
                    last_error = exc
            assert (
                rendered is not None
            ), f"prompt {prompt.name!r} could not be rendered: {last_error!r}"
            messages = rendered.messages
            assert messages, f"prompt {prompt.name!r} returned no messages"
            total_text = "".join(str(getattr(message.content, "text", "")) for message in messages)
            assert (
                len(total_text) > 100
            ), f"prompt {prompt.name!r} is suspiciously short ({len(total_text)} chars)"

    async def test_prompts_do_not_leak_absolute_paths(self, client):
        result = await client.list_prompts()
        for prompt in result.prompts:
            for args in SAMPLE_ARGS:
                try:
                    rendered = await client.get_prompt(prompt.name, args)
                except Exception:  # noqa: BLE001
                    continue
                for message in rendered.messages:
                    text = str(getattr(message.content, "text", ""))
                    assert not _DRIVE_PATH.search(text), f"absolute path in {prompt.name}"
                    assert not _UNC_PATH.search(text), f"UNC path in {prompt.name}"
                break
