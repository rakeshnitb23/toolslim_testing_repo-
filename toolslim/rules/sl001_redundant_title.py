"""SL001 redundant-title

Pydantic puts a ``title`` on every field that just repeats the field name
(``"repo_path": {"title": "Repo Path", ...}``), on every ``$defs`` model
(``"Address": {"title": "Address"}``) and on the arguments model
(``"title": "search_issuesArguments"``). ``title`` is an annotation, so dropping it never
changes what validates; we only drop it when it carries no information.
"""

from __future__ import annotations

from toolslim.models import ToolDef
from toolslim.rules.base import BaseRule, Schema, register_rule
from toolslim.schema import map_schemas, normalize_name

_ARG_SUFFIXES = ("", "arguments", "args", "input", "inputs", "params", "parameters", "request")


def _drop_title(sub: object, name: str) -> object:
    if (
        isinstance(sub, dict)
        and isinstance(sub.get("title"), str)
        and normalize_name(sub["title"]) == normalize_name(name)
    ):
        return {k: v for k, v in sub.items() if k != "title"}
    return sub


@register_rule
class RedundantTitle(BaseRule):
    id = "SL001"
    name = "redundant-title"
    lossless = True
    order = 30
    summary = "Drop `title` when it only repeats the property, $defs or tool name."

    def apply_tool(self, tool: ToolDef) -> ToolDef:
        def fix(node: Schema) -> Schema:
            for key in ("properties", "$defs", "definitions"):
                if isinstance(node.get(key), dict):
                    node[key] = {k: _drop_title(v, k) for k, v in node[key].items()}
            return node

        schema = map_schemas(tool.input_schema, fix)
        title = schema.get("title") if isinstance(schema, dict) else None
        if isinstance(title, str):
            tool_key = normalize_name(tool.name)
            if normalize_name(title) in {tool_key + s for s in _ARG_SUFFIXES}:
                schema = {k: v for k, v in schema.items() if k != "title"}
        if schema == tool.input_schema:
            return tool
        return tool.with_changes(input_schema=schema)
