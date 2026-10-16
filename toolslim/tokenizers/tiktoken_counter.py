from __future__ import annotations

from functools import lru_cache

import tiktoken

from toolslim.models import ToolDef
from toolslim.tokenizers.base import tool_text


@lru_cache(maxsize=8)
def _encoding(name: str) -> tiktoken.Encoding:
    return tiktoken.get_encoding(name)


class TiktokenCounter:
    """Offline approximation. Exact for OpenAI models that use the encoding, an estimate
    for everyone else (including Claude)."""

    def __init__(self, encoding: str = "o200k_base") -> None:
        self.encoding = encoding
        self.name = f"tiktoken:{encoding}"

    def count_text(self, text: str) -> int:
        return len(_encoding(self.encoding).encode(text, disallowed_special=()))

    def count_tool(self, tool: ToolDef) -> int:
        return self.count_text(tool_text(tool))

    def count_tools(self, tools: list[ToolDef]) -> int:
        return sum(self.count_tool(t) for t in tools)
