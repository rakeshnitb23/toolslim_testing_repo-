"""SL003 drop-null-default

Every ``Optional[...] = None`` field in Pydantic gets ``"default": null``. ``default`` is an
annotation (validators ignore it), and "not in ``required``" already tells the model the
field is optional, so the annotation adds tokens and no information.
"""

from __future__ import annotations

from toolslim.rules.base import BaseRule, Schema, register_rule
from toolslim.schema import map_schemas


@register_rule
class DropNullDefault(BaseRule):
    id = "SL003"
    name = "drop-null-default"
    lossless = True
    order = 40
    summary = 'Remove `"default": null` on properties that are not required.'

    def apply_schema(self, schema: Schema) -> Schema:
        def fix(node: Schema) -> Schema:
            props = node.get("properties")
            if not isinstance(props, dict):
                return node
            required = node.get("required")
            required = set(required) if isinstance(required, list) else set()
            node["properties"] = {
                k: (
                    {kk: vv for kk, vv in v.items() if kk != "default"}
                    if isinstance(v, dict)
                    and k not in required
                    and "default" in v
                    and v["default"] is None
                    else v
                )
                for k, v in props.items()
            }
            return node

        return map_schemas(schema, fix)
