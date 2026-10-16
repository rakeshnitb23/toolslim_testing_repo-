"""SL002 anyof-to-type-array

``{"anyOf": [{"type": "string"}, {"type": "null"}]}`` -> ``{"type": ["string", "null"]}``.

The obvious rewrite, ``anyOf[X, null]`` -> ``X``, is WRONG: it rejects callers who send an
explicit ``null``. A type array keeps ``null`` legal.

We also merge branches that carry keywords which only apply to that branch's type, e.g.
``anyOf[{"type": "object", "properties": {...}}, {"type": "null"}]`` becomes
``{"type": ["object", "null"], "properties": {...}}``. That is equivalent because
``properties`` ignores non-objects, so ``null`` still passes and objects are checked
exactly as before. ``oneOf`` gets the same treatment when the branch types are disjoint
(then "exactly one matches" == "at least one matches").

``Optional[Literal["a", "b"]]`` (``anyOf[{type: string, enum: [a, b]}, {type: null}]``)
becomes ``{"enum": ["a", "b", null]}``: same accepted set, far fewer tokens.
"""

from __future__ import annotations

import json
from typing import Any

from toolslim.rules.base import BaseRule, Schema, register_rule
from toolslim.schema import map_schemas

_NUM = frozenset({"number", "integer"})
# keyword -> the JSON types it constrains (it ignores every other type)
KW_TYPES: dict[str, frozenset[str]] = {
    **dict.fromkeys(("minLength", "maxLength", "pattern"), frozenset({"string"})),
    **dict.fromkeys(
        ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf"), _NUM
    ),
    **dict.fromkeys(
        ("items", "prefixItems", "minItems", "maxItems", "uniqueItems", "contains",
         "minContains", "maxContains"),
        frozenset({"array"}),
    ),
    **dict.fromkeys(
        ("properties", "required", "additionalProperties", "patternProperties",
         "minProperties", "maxProperties", "propertyNames", "dependentRequired",
         "dependentSchemas"),
        frozenset({"object"}),
    ),
}  # fmt: skip
_HOISTABLE_ANNOTATIONS = frozenset({"title", "description"})
_BLOCKERS = frozenset({"type", "unevaluatedProperties", "unevaluatedItems"})


def _types_of(branch: Any) -> list[str] | None:
    if not isinstance(branch, dict):
        return None
    t = branch.get("type")
    if isinstance(t, str):
        return [t]
    if isinstance(t, list) and t and all(isinstance(x, str) for x in t):
        return list(t)
    return None


def _expand(types: list[str]) -> set[str]:
    """``number`` overlaps ``integer`` (every integer is a number)."""
    out = set(types)
    if "number" in out:
        out.add("integer")
    return out


def _try_merge(node: Schema, key: str) -> Schema | None:
    branches = node.get(key)
    if not isinstance(branches, list) or not branches:
        return None
    if _BLOCKERS & node.keys():
        return None
    typesets = [_types_of(b) for b in branches]
    if any(ts is None for ts in typesets):
        return None

    merged_types: list[str] = []
    seen: set[str] = set()
    hoisted: dict[str, Any] = {}
    for i, (branch, types) in enumerate(zip(branches, typesets, strict=True)):
        assert types is not None
        mine = _expand(types)
        if mine & seen:
            return None  # overlapping types: anyOf/oneOf semantics would differ
        seen |= mine
        merged_types.extend(t for t in types if t not in merged_types)
        others = set().union(*(_expand(ts) for j, ts in enumerate(typesets) if j != i and ts))
        for kw, value in branch.items():
            if kw == "type":
                continue
            if kw in _HOISTABLE_ANNOTATIONS:
                pass
            elif kw in KW_TYPES:
                if len(types) != 1 or KW_TYPES[kw] & others:
                    return None  # keyword would start constraining another branch's values
            else:
                return None  # enum/const/format/$ref/... apply to every type: unsafe
            if kw in hoisted or kw in node:
                return None  # collision: can't hoist two values into one slot
            hoisted[kw] = value

    out: Schema = {}
    for k, v in node.items():
        if k == key:
            out["type"] = merged_types[0] if len(merged_types) == 1 else merged_types
            out.update(hoisted)
        else:
            out[k] = v
    return out


def _json_type_ok(value: Any, t: str) -> bool:
    if t == "null":
        return value is None
    if t == "boolean":
        return isinstance(value, bool)
    if t == "string":
        return isinstance(value, str)
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "array":
        return isinstance(value, list)
    if t == "object":
        return isinstance(value, dict)
    return False


def _enum_key(value: Any) -> str:
    """JSON-Schema equality: 1 == 1.0, but True != 1."""
    if isinstance(value, bool) or value is None:
        return repr(value)
    if isinstance(value, (int, float)):
        return f"n:{float(value)!r}"
    return "j:" + json.dumps(value, sort_keys=True)


def _branch_values(branch: Any) -> list[Any] | None:
    """Values a branch accepts if it is a pure value list, else None."""
    if not isinstance(branch, dict):
        return None
    keys = set(branch)
    if keys == {"type"} and branch["type"] == "null":
        return [None]
    if "enum" in keys and isinstance(branch["enum"], list):
        values = list(branch["enum"])
        rest = keys - {"enum"}
    elif "const" in keys:
        values = [branch["const"]]
        rest = keys - {"const"}
    else:
        return None
    if rest - {"type"}:
        return None
    if "type" in rest:
        types = branch["type"] if isinstance(branch["type"], list) else [branch["type"]]
        # The type keyword is redundant only if every listed value already satisfies it.
        if not all(any(_json_type_ok(v, t) for t in types) for v in values):
            return None
    return values


def _try_enum_merge(node: Schema, key: str) -> Schema | None:
    """``anyOf[{type: string, enum: [a, b]}, {type: null}]`` -> ``{enum: [a, b, null]}``.

    Pydantic emits this for every ``Optional[Literal[...]]``.
    """
    branches = node.get(key)
    if not isinstance(branches, list) or len(branches) < 2:
        return None
    if ({"enum", "const"} | _BLOCKERS) & node.keys():
        return None
    per_branch = [_branch_values(b) for b in branches]
    if any(v is None for v in per_branch):
        return None
    if not any(isinstance(b, dict) and ("enum" in b or "const" in b) for b in branches):
        return None
    merged: list[Any] = []
    seen: set[str] = set()
    for values in per_branch:
        assert values is not None
        branch_keys = {_enum_key(v) for v in values}
        if key == "oneOf" and branch_keys & seen:
            return None  # a value in two oneOf branches is rejected; merging would accept it
        for v in values:
            k = _enum_key(v)
            if k not in seen:
                merged.append(v)
                seen.add(k)
        seen |= branch_keys
    out: Schema = {}
    for k, v in node.items():
        if k == key:
            out["enum"] = merged
        else:
            out[k] = v
    return out


@register_rule
class AnyOfToTypeArray(BaseRule):
    id = "SL002"
    name = "anyof-to-type-array"
    lossless = True
    order = 60  # after SL004 so inlined Optional[Model] branches can merge too
    summary = "Collapse anyOf/oneOf of disjoint simple types into a `type` array."

    def apply_schema(self, schema: Schema) -> Schema:
        def fix(node: Schema) -> Schema:
            for key in ("anyOf", "oneOf"):
                merged = _try_merge(node, key)
                if merged is None:
                    merged = _try_enum_merge(node, key)
                if merged is not None:
                    node = merged
            return node

        return map_schemas(schema, fix)
