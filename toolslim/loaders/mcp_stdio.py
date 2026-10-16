"""Launch an MCP server over stdio and read its ``tools/list``.

Needs the optional extra: ``pip install toolslim[mcp]``.
"""

from __future__ import annotations

import os
import shlex
from typing import Any

from toolslim.loaders.json_file import parse_tools
from toolslim.models import ToolDef


async def _list_tools_async(
    command: str, args: list[str], env: dict[str, str] | None
) -> list[dict[str, Any]]:
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError as exc:  # pragma: no cover - depends on install
        raise RuntimeError("MCP support needs: pip install 'toolslim[mcp]'") from exc

    params = StdioServerParameters(command=command, args=args, env=env)
    tools: list[dict[str, Any]] = []
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        cursor = None
        while True:  # tools/list is paginated
            if cursor is None:
                result = await session.list_tools()
            else:
                from mcp.types import PaginatedRequestParams

                result = await session.list_tools(params=PaginatedRequestParams(cursor=cursor))
            for tool in result.tools:
                tools.append(tool.model_dump(by_alias=True, exclude_none=True, mode="json"))
            cursor = getattr(result, "next_cursor", None) or getattr(result, "nextCursor", None)
            if not cursor:
                break
    return tools


def list_tools_raw(command_line: str, env: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Return the server's tools exactly as ``tools/list`` sent them (MCP wire shape)."""
    parts = shlex.split(command_line)
    if not parts:
        raise ValueError("empty --mcp command")
    full_env = {**os.environ, **(env or {})}
    try:
        import anyio  # ships with the `mcp` extra
    except ImportError as exc:
        raise RuntimeError("MCP support needs: pip install 'toolslim[mcp]'") from exc
    return anyio.run(_list_tools_async, parts[0], parts[1:], full_env)


def load_mcp_stdio(command_line: str, env: dict[str, str] | None = None) -> list[ToolDef]:
    return parse_tools(list_tools_raw(command_line, env))
