"""SL008 drop-schema-dialect

zod-to-json-schema (most TypeScript MCP servers) stamps
``"$schema": "http://json-schema.org/draft-07/schema#"`` on every tool: ~14 tokens a tool,
repeated every turn. Without ``$schema`` a validator uses its default dialect (2020-12 per
the MCP spec), so we only drop it when the schema means the same thing in both:

* draft-2020-12 / 2019-09 / draft-07 / draft-06 URIs only (not draft-04: boolean
  ``exclusiveMinimum`` changed meaning)
* none of the keywords whose semantics changed between those drafts appear anywhere:
  array-form ``items`` / ``additionalItems`` / ``prefixItems``, ``dependencies`` and its
  split forms, ``$id`` / ``$anchor`` / ``$recursive*`` / ``$dynamic*``,
  ``unevaluated*``, and ``$ref`` with non-annotation siblings (draft-07 ignores them).
"""

from __future__ import annotations

from toolslim.rules.base import BaseRule, Schema, register_rule
from toolslim.schema import ANNOTATIONS, iter_schemas

_SAFE_DIALECTS = {
    "https://json-schema.org/draft/2020-12/schema",
    "https://json-schema.org/draft/2019-09/schema",
    "http://json-schema.org/draft-07/schema",
    "http://json-schema.org/draft-06/schema",
}
_DRAFT_SENSITIVE = frozenset(
    {"additionalItems", "prefixItems", "dependencies", "dependentRequired",
     "dependentSchemas", "$id", "id", "$anchor", "$recursiveRef", "$recursiveAnchor",
     "$dynamicRef", "$dynamicAnchor", "unevaluatedItems", "unevaluatedProperties",
     "$vocabulary"}
)  # fmt: skip


def _norm(uri: str) -> str:
    return uri.rstrip("#").replace(
        "https://json-schema.org/draft-0", "http://json-schema.org/draft-0"
    )


def dialect_neutral(schema: Schema) -> bool:
    for sub in iter_schemas(schema):
        if _DRAFT_SENSITIVE & sub.keys():
            return False
        if isinstance(sub.get("items"), list):
            return False
        if "$ref" in sub and not (set(sub) - {"$ref"}) <= ANNOTATIONS:
            return False
        if sub is not schema and "$schema" in sub:
            return False  # embedded dialect switch
    return True


@register_rule
class DropSchemaDialect(BaseRule):
    id = "SL008"
    name = "drop-schema-dialect"
    lossless = True
    order = 35
    summary = "Drop `$schema` when the schema reads the same in draft-07 and 2020-12."

    def apply_schema(self, schema: Schema) -> Schema:
        uri = schema.get("$schema") if isinstance(schema, dict) else None
        if not isinstance(uri, str) or _norm(uri) not in {_norm(u) for u in _SAFE_DIALECTS}:
            return schema
        if not dialect_neutral(schema):
            return schema
        return {k: v for k, v in schema.items() if k != "$schema"}
