"""SL005 description-whitespace

Docstring-derived descriptions carry indentation, trailing spaces and blank-line runs.
We dedent (``inspect.cleandoc``), strip trailing spaces, collapse runs of blank lines to
one, collapse runs of spaces inside a line (leading indentation is kept, so nested lists
survive) and unwrap ``**bold**``. Line breaks are kept: they carry structure.
"""

from __future__ import annotations

import inspect
import re

from toolslim.models import ToolDef
from toolslim.rules.base import BaseRule, Schema, register_rule
from toolslim.schema import map_schemas

_BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
_INNER_SPACES = re.compile(r"(?<=\S)[ \t]{2,}")
_BLANK_RUNS = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    text = inspect.cleandoc(text.replace("\r\n", "\n").replace("\t", "    "))
    text = _BOLD.sub(r"\1", text)
    lines = [_INNER_SPACES.sub(" ", line.rstrip()) for line in text.split("\n")]
    return _BLANK_RUNS.sub("\n\n", "\n".join(lines)).strip()


@register_rule
class DescriptionWhitespace(BaseRule):
    id = "SL005"
    name = "description-whitespace"
    lossless = True
    order = 10
    summary = "Dedent and collapse whitespace in descriptions; unwrap **bold**."

    def apply_tool(self, tool: ToolDef) -> ToolDef:
        def fix(node: Schema) -> Schema:
            if isinstance(node.get("description"), str):
                node["description"] = clean_text(node["description"])
            return node

        schema = map_schemas(tool.input_schema, fix)
        desc = clean_text(tool.description) if isinstance(tool.description, str) else None
        if schema == tool.input_schema and desc == tool.description:
            return tool
        return tool.with_changes(input_schema=schema, description=desc)
