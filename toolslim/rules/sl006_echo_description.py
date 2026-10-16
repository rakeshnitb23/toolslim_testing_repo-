"""SL006 echo-description

``"user_id": {"description": "The user ID"}`` tells the model nothing the key didn't. We
drop a property description when, after removing filler words, every word in it is
already in the property name. "Maximum number of results" on ``limit`` is kept.
"""

from __future__ import annotations

import re

from toolslim.rules.base import BaseRule, Schema, register_rule
from toolslim.schema import map_schemas

_FILLER = frozenset(
    [
        "the",
        "a",
        "an",
        "of",
        "for",
        "to",
        "this",
        "that",
        "is",
        "param",
        "parameter",
        "value",
        "field",
        "argument",
        "arg",
        "input",
        "given",
        "specified",
        "provided",
    ]
)
_WORD = re.compile(r"[a-z0-9]+")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _words(text: str) -> set[str]:
    text = _CAMEL.sub(" ", text).lower()
    return {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in _WORD.findall(text)}


def is_echo(prop_name: str, description: str) -> bool:
    desc = _words(description) - _FILLER
    name = _words(prop_name)
    return bool(name) and desc <= name


@register_rule
class EchoDescription(BaseRule):
    id = "SL006"
    name = "echo-description"
    lossless = True
    order = 20
    summary = "Drop a property description that only restates the property name."

    def apply_schema(self, schema: Schema) -> Schema:
        def fix(node: Schema) -> Schema:
            props = node.get("properties")
            if not isinstance(props, dict):
                return node
            node["properties"] = {
                k: (
                    {kk: vv for kk, vv in v.items() if kk != "description"}
                    if isinstance(v, dict)
                    and isinstance(v.get("description"), str)
                    and is_echo(k, v["description"])
                    else v
                )
                for k, v in props.items()
            }
            return node

        return map_schemas(schema, fix)
