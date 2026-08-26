"""Input limits enforced before commands reach the actor (guideline 25.2)."""

from __future__ import annotations

from typing import Any

from gstarcad_mcp.config import LimitsSection
from gstarcad_mcp.errors import INVALID_ACTION, ExpectedCadError


class LimitsPolicy:
    def __init__(self, limits: LimitsSection) -> None:
        self.limits = limits

    def check_batch(self, actions: list[Any]) -> None:
        lim = self.limits
        # The mutation budget covers geometry/entity-changing actions; layer and view
        # operations (ensure_layer, regen, zoom_extents) do not consume it.
        entity_actions = [
            action
            for action in actions
            if (action.get("op") if isinstance(action, dict) else getattr(action, "op", None))
            not in {"ensure_layer", "regen", "zoom_extents"}
        ]
        if len(entity_actions) > lim.max_actions_per_batch:
            raise ExpectedCadError(
                INVALID_ACTION,
                f"Batch has {len(entity_actions)} actions; maximum is {lim.max_actions_per_batch}.",
            )
        total_vertices = 0
        for action in actions:
            data = action if isinstance(action, dict) else action.model_dump()
            op = data.get("op")
            vertices = data.get("vertices")
            if op == "create_polyline" and vertices is not None:
                count = len(vertices)
                if count > lim.max_vertices_per_polyline:
                    raise ExpectedCadError(
                        INVALID_ACTION,
                        f"Polyline has {count} vertices; maximum is "
                        f"{lim.max_vertices_per_polyline}.",
                    )
                total_vertices += count
            if op == "create_rect":
                total_vertices += 4
            text = data.get("text")
            if isinstance(text, str) and len(text) > lim.max_text_length:
                raise ExpectedCadError(
                    INVALID_ACTION,
                    f"Text length {len(text)} exceeds maximum {lim.max_text_length}.",
                )
            if op == "create_table":
                rows = data.get("rows") or 0
                cols = data.get("columns") or 0
                if rows * cols > lim.max_table_cells:
                    raise ExpectedCadError(
                        INVALID_ACTION,
                        f"Table has {rows * cols} cells; maximum is {lim.max_table_cells}.",
                    )
        if total_vertices > lim.max_total_vertices_per_batch:
            raise ExpectedCadError(
                INVALID_ACTION,
                f"Batch has {total_vertices} vertices; maximum is "
                f"{lim.max_total_vertices_per_batch}.",
            )

    def check_handles(self, handles: list[str]) -> None:
        if len(handles) > self.limits.max_entity_handles_per_request:
            raise ExpectedCadError(
                INVALID_ACTION,
                f"Too many handles ({len(handles)}); maximum is "
                f"{self.limits.max_entity_handles_per_request}.",
            )

    def check_page_size(self, limit: int) -> None:
        if limit > self.limits.max_query_page_size:
            raise ExpectedCadError(
                INVALID_ACTION,
                f"Page size {limit} exceeds maximum {self.limits.max_query_page_size}.",
            )

    def check_screenshot_size(self, width: int | None, height: int | None) -> None:
        if width is not None and width > self.limits.max_screenshot_width:
            raise ExpectedCadError(INVALID_ACTION, "Screenshot width exceeds configured maximum.")
        if height is not None and height > self.limits.max_screenshot_height:
            raise ExpectedCadError(INVALID_ACTION, "Screenshot height exceeds configured maximum.")
