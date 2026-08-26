"""MCP tool handlers (thin: validate -> permission -> limits -> idempotency -> actor)."""

from gstarcad_mcp.tools.documents import register_document_tools
from gstarcad_mcp.tools.editing import register_editing_tools
from gstarcad_mcp.tools.evidence import register_evidence_tools
from gstarcad_mcp.tools.inspection import register_inspection_tools
from gstarcad_mcp.tools.status import register_status_tools

TOOL_CATALOG: list[dict[str, object]] = [
    {"name": "gcad_get_status", "read_only": True, "permission": "cad.status.read"},
    {"name": "gcad_list_documents", "read_only": True, "permission": "cad.document.read"},
    {"name": "gcad_new_document", "read_only": False, "permission": "cad.document.create"},
    {"name": "gcad_open_document", "read_only": False, "permission": "cad.document.open"},
    {"name": "gcad_activate_document", "read_only": False, "permission": "cad.document.read"},
    {"name": "gcad_save_document", "read_only": False, "permission": "cad.document.save"},
    {"name": "gcad_close_document", "read_only": False, "permission": "cad.document.close"},
    {"name": "gcad_list_layers", "read_only": True, "permission": "cad.entity.read"},
    {"name": "gcad_list_layouts", "read_only": True, "permission": "cad.entity.read"},
    {"name": "gcad_query_entities", "read_only": True, "permission": "cad.entity.read"},
    {"name": "gcad_get_entities", "read_only": True, "permission": "cad.entity.read"},
    {"name": "gcad_ensure_layers", "read_only": False, "permission": "cad.layer.create"},
    {"name": "gcad_create_entities", "read_only": False, "permission": "cad.entity.create"},
    {"name": "gcad_apply_actions", "read_only": False, "permission": "cad.entity.create"},
    {"name": "gcad_capture_view", "read_only": False, "permission": "cad.view.capture"},
    {"name": "gcad_begin_run", "read_only": False, "permission": "cad.run.manage"},
    {"name": "gcad_capture_before_state", "read_only": False, "permission": "cad.run.manage"},
    {"name": "gcad_collect_evidence", "read_only": False, "permission": "cad.run.manage"},
    {"name": "gcad_validate_run", "read_only": True, "permission": "cad.run.manage"},
    {"name": "gcad_finalize_run", "read_only": False, "permission": "cad.run.manage"},
    {"name": "gcad_get_run_status", "read_only": True, "permission": "cad.run.manage"},
]

__all__ = [
    "TOOL_CATALOG",
    "register_document_tools",
    "register_editing_tools",
    "register_evidence_tools",
    "register_inspection_tools",
    "register_status_tools",
]
