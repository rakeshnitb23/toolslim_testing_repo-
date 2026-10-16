from __future__ import annotations

import json
from typing import Protocol, runtime_checkable

from toolslim.models import ToolDef


@runtime_checkable
class TokenCounter(Protocol):
    name: str

    def count_tool(self, tool: ToolDef) -> int: ...

    def count_tools(self, tools: list[ToolDef]) -> int: ...


def tool_text(tool: ToolDef) -> str:
    """The text we tokenize for one tool: its wire shape as compact JSON.

    Providers re-render tools internally, so no local serialisation matches billing
    exactly; compact JSON is the stable, whitespace-free approximation. Use the
    Anthropic counter for ground truth on Claude.
    """
    return json.dumps(tool.to_wire(), separators=(",", ":"), ensure_ascii=False)
