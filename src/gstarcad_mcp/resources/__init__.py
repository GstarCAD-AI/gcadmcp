"""Read-only MCP resources (§18)."""

from gstarcad_mcp.resources.documents import register_document_resources
from gstarcad_mcp.resources.runs import register_run_resources

__all__ = ["register_document_resources", "register_run_resources"]
