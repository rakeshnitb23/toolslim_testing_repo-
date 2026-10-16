"""A small FastMCP-style server with Pydantic arguments, modelled on a read-only
document-lookup tool (GroundedDocs). It exists so the benchmark includes the schema
shape Python teams actually ship: titles everywhere, Optional[...] = None, nested models.

Run: python bench/servers/docs_lookup_server.py   (stdio)
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP

mcp = FastMCP("docs-lookup")


class DateRange(BaseModel):
    start: date | None = Field(None, description="Inclusive start date")
    end: date | None = Field(None, description="Inclusive end date")


class SearchFilters(BaseModel):
    """Restrict which documents are searched."""

    workspace_id: str | None = Field(None, description="The workspace ID")
    file_types: list[Literal["pdf", "docx", "md", "txt"]] | None = None
    uploaded: DateRange | None = None
    tags: list[str] = Field(default_factory=list, description="Only documents with all tags")


@mcp.tool()
def search_documents(
    query: str = Field(description="Natural-language question or keywords"),
    filters: SearchFilters | None = None,
    top_k: int = Field(5, ge=1, le=50, description="Maximum number of chunks to return"),
    mode: Literal["hybrid", "vector", "keyword"] | None = None,
    rerank: bool = True,
) -> str:
    """
    Search the user's documents and return the best-matching chunks.

    Each chunk includes its **document id**, page and a stable chunk id so answers
    can cite it.
    """
    return "[]"


@mcp.tool()
def get_chunk(
    document_id: str = Field(description="The document ID"),
    chunk_id: str = Field(description="The chunk ID"),
    include_neighbors: int | None = Field(None, ge=0, le=3, description="Neighbor chunks"),
) -> str:
    """Fetch one chunk by id, optionally with neighbouring chunks for context."""
    return ""


@mcp.tool()
def list_documents(
    workspace_id: str | None = None,
    page: int = Field(1, ge=1, description="Page number"),
    page_size: int = Field(20, ge=1, le=100, description="Page size"),
    sort: Literal["name", "uploaded_at", "size"] | None = None,
) -> str:
    """List documents the caller can read, newest first."""
    return "[]"


@mcp.tool()
def get_document_metadata(document_id: str = Field(description="Document ID")) -> str:
    """Return title, page count, upload date and content hash for one document."""
    return "{}"


if __name__ == "__main__":
    mcp.run()
