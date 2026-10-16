"""JSON Schema traversal that knows which keywords hold subschemas.

The point of this module: a property *called* ``title`` or ``description`` lives inside
``properties`` and must never be mistaken for the ``title`` / ``description`` keyword.
Every rule walks schemas through ``map_schemas`` so they all get that right for free.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

Schema = dict[str, Any]

# keyword -> its value is a single subschema
SINGLE = (
    "additionalProperties", "items", "contains", "propertyNames", "not", "if", "then",
    "else", "unevaluatedItems", "unevaluatedProperties", "additionalItems",
)  # fmt: skip
# keyword -> its value is a list of subschemas
LISTS = ("allOf", "anyOf", "oneOf", "prefixItems")
# keywords that may also hold a list of subschemas (draft-07 tuple validation)
TUPLE_ITEMS = ("items",)
# keyword -> its value is a {name: subschema} map
MAPS = ("properties", "patternProperties", "dependentSchemas", "$defs", "definitions")

ANNOTATIONS = frozenset(
    {"title", "description", "default", "examples", "deprecated", "readOnly", "writeOnly",
     "$comment"}
)  # fmt: skip


def map_schemas(schema: Any, fn: Callable[[Schema], Schema]) -> Any:
    """Rebuild ``schema`` bottom-up, applying ``fn`` to every (sub)schema object.

    ``fn`` receives a *new* dict whose children have already been transformed and must
    return a dict. The input is never mutated.
    """
    if not isinstance(schema, dict):
        return schema  # boolean schemas (true/false) and junk pass through
    out: Schema = {}
    for key, value in schema.items():
        # Lists first: draft-07 tuple-form `items` is a list even though `items` is in SINGLE.
        if (key in LISTS or key in TUPLE_ITEMS) and isinstance(value, list):
            out[key] = [map_schemas(v, fn) for v in value]
        elif key in SINGLE:
            out[key] = map_schemas(value, fn)
        elif key in MAPS and isinstance(value, dict):
            out[key] = {k: map_schemas(v, fn) for k, v in value.items()}
        else:
            out[key] = value
    return fn(out)


def iter_schemas(schema: Any) -> Iterator[Schema]:
    """Yield every (sub)schema object, parents before children."""
    if not isinstance(schema, dict):
        return
    yield schema
    for key, value in schema.items():
        if (key in LISTS or key in TUPLE_ITEMS) and isinstance(value, list):
            for v in value:
                yield from iter_schemas(v)
        elif key in SINGLE:
            yield from iter_schemas(value)
        elif key in MAPS and isinstance(value, dict):
            for v in value.values():
                yield from iter_schemas(v)


def iter_schemas_skipping_defs(schema: Any) -> Iterator[Schema]:
    """Like ``iter_schemas`` but does not descend into ``$defs`` / ``definitions``."""
    if not isinstance(schema, dict):
        return
    yield schema
    for key, value in schema.items():
        if key in ("$defs", "definitions"):
            continue
        if (key in LISTS or key in TUPLE_ITEMS) and isinstance(value, list):
            for v in value:
                yield from iter_schemas_skipping_defs(v)
        elif key in SINGLE:
            yield from iter_schemas_skipping_defs(value)
        elif key in MAPS and isinstance(value, dict):
            for v in value.values():
                yield from iter_schemas_skipping_defs(v)


def normalize_name(text: str) -> str:
    """``User_ID``, ``user-id``, ``User Id`` and ``userId`` all become ``userid``."""
    return "".join(ch for ch in text.lower() if ch.isalnum())
