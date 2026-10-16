"""toolslim: measure and losslessly slim LLM tool / MCP schemas."""

from __future__ import annotations

from typing import Any

from toolslim.loaders import dump_tools, load_json_file, parse_tools
from toolslim.models import ToolDef
from toolslim.pipeline import RuleResult, SlimResult, run_pipeline
from toolslim.rules import all_rules, register_rule, select_rules
from toolslim.tokenizers import TiktokenCounter, TokenCounter, get_counter

__version__ = "0.1.0"


def slim_tools(
    tools: list[dict[str, Any]],
    *,
    rules: list[str] | None = None,
    exclude: list[str] | None = None,
    lossy: bool = False,
) -> list[dict[str, Any]]:
    """Slim tool definitions and return them in the same wire shape they came in.

    Accepts MCP, Anthropic and OpenAI (chat or responses) tool dicts. The input list is
    never modified.

    >>> slim = slim_tools([{"name": "get_user", "inputSchema": {"type": "object",
    ...     "title": "get_userArguments", "properties": {"user_id": {"type": "string",
    ...     "title": "User Id"}}}}])
    >>> slim[0]["inputSchema"]
    {'type': 'object', 'properties': {'user_id': {'type': 'string'}}}
    """
    parsed = parse_tools(tools)
    result = run_pipeline(parsed, select_rules(rules, exclude, lossy=lossy))
    return [t.to_wire() for t in result.tools]


def measure_tools(tools: list[dict[str, Any]], counter: str = "o200k_base") -> dict[str, int]:
    """Tokens per tool name, for any supported wire shape."""
    c = get_counter(counter)
    return {t.name: c.count_tool(t) for t in parse_tools(tools)}


__all__ = [
    "RuleResult",
    "SlimResult",
    "TiktokenCounter",
    "TokenCounter",
    "ToolDef",
    "__version__",
    "all_rules",
    "dump_tools",
    "get_counter",
    "load_json_file",
    "measure_tools",
    "parse_tools",
    "register_rule",
    "run_pipeline",
    "select_rules",
    "slim_tools",
]
