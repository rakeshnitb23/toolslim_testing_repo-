"""Load tool definitions from JSON in any of the common shapes.

Accepted top-level shapes:
  * a list of tools
  * ``{"tools": [...]}``                      (an MCP ``tools/list`` result)
  * ``{"result": {"tools": [...]}}``          (a raw JSON-RPC ``tools/list`` response)

Accepted per-tool shapes:
  * MCP:              ``{"name", "description", "inputSchema"}``
  * Anthropic:        ``{"name", "description", "input_schema"}``
  * OpenAI chat:      ``{"type": "function", "function": {"name", "description", "parameters"}}``
  * OpenAI responses: ``{"type": "function", "name", "description", "parameters"}``
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from toolslim.models import ToolDef


class ToolLoadError(ValueError):
    pass


def parse_tool(raw: dict[str, Any]) -> ToolDef:
    if not isinstance(raw, dict):
        raise ToolLoadError(f"tool must be an object, got {type(raw).__name__}")
    if raw.get("type") == "function" and isinstance(raw.get("function"), dict):
        fn = dict(raw["function"])
        return ToolDef(
            name=fn.pop("name"),
            description=fn.pop("description", None),
            input_schema=fn.pop("parameters", None) or {"type": "object"},
            source_format="openai_chat",
            extra=fn,
        )
    body = dict(raw)
    if "name" not in body:
        raise ToolLoadError(f"tool has no 'name': keys={sorted(body)}")
    shapes = {"inputSchema": "mcp", "input_schema": "anthropic", "parameters": "openai_responses"}
    key = next((k for k in shapes if k in body), None)
    if key is None:
        schema, fmt = {"type": "object"}, "mcp"
    else:
        schema, fmt = body.pop(key), shapes[key]
    if fmt == "openai_responses":
        body.pop("type", None)
    return ToolDef(
        name=body.pop("name"),
        description=body.pop("description", None),
        input_schema=schema or {"type": "object"},
        source_format=fmt,  # type: ignore[arg-type]
        extra=body,
    )


def parse_tools(data: Any) -> list[ToolDef]:
    if isinstance(data, dict):
        if isinstance(data.get("result"), dict):
            data = data["result"]
        if "tools" in data:
            data = data["tools"]
        elif "name" in data or "function" in data:
            data = [data]
    if not isinstance(data, list):
        raise ToolLoadError("expected a list of tools or an object with a 'tools' key")
    return [parse_tool(t) for t in data]


def load_json_file(path: str | Path) -> list[ToolDef]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ToolLoadError(f"{path}: invalid JSON ({exc})") from exc
    return parse_tools(data)


def dump_tools(tools: list[ToolDef], *, indent: int | None = 2) -> str:
    """Serialise tools back into their source wire shape."""
    return json.dumps([t.to_wire() for t in tools], indent=indent, ensure_ascii=False)
