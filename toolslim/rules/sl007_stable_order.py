"""SL007 stable-order

Sorts tools by name and puts keywords inside every schema object in one canonical order.
It saves ~0 tokens. What it buys is a byte-identical tool block across runs and machines,
so the provider's prompt-cache prefix keeps matching even when the server (or a dict
merge somewhere upstream) emits tools in a different order.

The order of ``properties`` is NOT changed: parameter order is a signal to the model.
"""

from __future__ import annotations

from toolslim.models import ToolDef
from toolslim.rules.base import BaseRule, Schema, register_rule
from toolslim.schema import map_schemas

_FIRST = (
    "$schema", "$id", "$ref", "title", "description", "type", "enum", "const", "format",
    "properties", "required", "additionalProperties", "items",
)  # fmt: skip
_RANK = {k: i for i, k in enumerate(_FIRST)}


def _key(k: str) -> tuple[int, str]:
    return (_RANK.get(k, len(_FIRST)), k)


@register_rule
class StableOrder(BaseRule):
    id = "SL007"
    name = "stable-order"
    lossless = True
    order = 90  # last, so it orders whatever the other rules produced
    summary = "Sort tools by name and schema keywords canonically (keeps prompt cache warm)."

    def apply_schema(self, schema: Schema) -> Schema:
        return map_schemas(schema, lambda node: {k: node[k] for k in sorted(node, key=_key)})

    def apply(self, tools: list[ToolDef]) -> list[ToolDef]:
        return sorted((self.apply_tool(t) for t in tools), key=lambda t: t.name)
