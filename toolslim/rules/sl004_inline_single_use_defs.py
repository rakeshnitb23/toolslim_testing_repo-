"""SL004 inline-single-use-defs

Pydantic hoists every nested model into ``$defs`` and points at it with ``$ref`` even when
it is used once. Inlining a once-used def saves its key plus the ``$ref`` string; deleting
unreferenced defs saves the whole body.

Conservative on purpose. We leave the schema alone when it has anything we can't reason
about locally: refs that aren't ``#/$defs/<name>`` (or ``#/definitions/<name>``),
``$id`` / ``$anchor`` / ``$dynamicRef`` anywhere. We never inline a recursive def, and we
only inline a ``$ref`` whose siblings are pure annotations (``description`` etc.), so the
merge can't change what validates.
"""

from __future__ import annotations

import copy
from typing import Any

from toolslim.rules.base import BaseRule, Schema, register_rule
from toolslim.schema import ANNOTATIONS, iter_schemas, iter_schemas_skipping_defs, map_schemas

_UNSAFE_KEYS = frozenset({"$id", "$anchor", "$dynamicAnchor", "$dynamicRef", "$recursiveRef",
                          "$recursiveAnchor"})  # fmt: skip


def _parse_ref(ref: Any) -> tuple[str, str] | None:
    """``#/$defs/Foo`` -> (``$defs``, ``Foo``). None for anything else."""
    if not isinstance(ref, str):
        return None
    for container in ("$defs", "definitions"):
        prefix = f"#/{container}/"
        if ref.startswith(prefix):
            name = ref[len(prefix) :]
            if "/" in name or "%" in name:
                return None
            return container, name.replace("~1", "/").replace("~0", "~")
    return None


def _refs_in(node: Any) -> list[tuple[str, str]] | None:
    """All def refs inside ``node`` (not descending into defs). None = unsafe schema."""
    out = []
    for sub in iter_schemas_skipping_defs(node):
        if _UNSAFE_KEYS & sub.keys():
            return None
        if "$ref" in sub:
            parsed = _parse_ref(sub["$ref"])
            if parsed is None:
                return None
            out.append(parsed)
    return out


@register_rule
class InlineSingleUseDefs(BaseRule):
    id = "SL004"
    name = "inline-single-use-defs"
    lossless = True
    order = 50
    summary = "Inline $defs referenced exactly once; delete unreferenced $defs."

    def apply_schema(self, schema: Schema) -> Schema:
        if not isinstance(schema, dict):
            return schema
        defs: dict[tuple[str, str], Any] = {}
        for container in ("$defs", "definitions"):
            if isinstance(schema.get(container), dict):
                for k, v in schema[container].items():
                    defs[(container, k)] = v
        if not defs:
            return schema
        # Any unsafe keyword anywhere (including inside defs) -> leave the schema alone.
        if any(_UNSAFE_KEYS & s.keys() for s in iter_schemas(schema)):
            return schema

        root_refs = _refs_in(schema)
        if root_refs is None:
            return schema
        def_refs: dict[tuple[str, str], list[tuple[str, str]]] = {}
        for key, body in defs.items():
            refs = _refs_in(body)
            if refs is None:
                return schema
            def_refs[key] = refs
        if any(r not in defs for r in root_refs) or any(
            r not in defs for refs in def_refs.values() for r in refs
        ):
            return schema  # dangling ref: not ours to fix

        # Reachability from the root (unreachable defs get deleted).
        reachable: set[tuple[str, str]] = set()
        stack = list(root_refs)
        while stack:
            key = stack.pop()
            if key not in reachable:
                reachable.add(key)
                stack.extend(def_refs[key])

        # Use counts over the root and reachable defs only.
        counts: dict[tuple[str, str], int] = dict.fromkeys(reachable, 0)
        for r in root_refs:
            counts[r] += 1
        for key in reachable:
            for r in def_refs[key]:
                counts[r] += 1

        def recursive(start: tuple[str, str]) -> bool:
            seen, todo = set(), list(def_refs[start])
            while todo:
                k = todo.pop()
                if k == start:
                    return True
                if k not in seen:
                    seen.add(k)
                    todo.extend(def_refs[k])
            return False

        inlinable = {k for k in reachable if counts[k] == 1 and not recursive(k)}

        def substitute(node: Any) -> Any:
            def fix(sub: Schema) -> Schema:
                parsed = _parse_ref(sub.get("$ref"))
                if parsed not in inlinable:
                    return sub
                siblings = {k: v for k, v in sub.items() if k != "$ref"}
                if not set(siblings) <= ANNOTATIONS:
                    return sub  # validation siblings: merging could change semantics
                body = defs[parsed]
                if not isinstance(body, dict):
                    return sub  # boolean def schema: keep the ref
                return {**substitute(copy.deepcopy(body)), **siblings}

            return map_schemas(node, fix)

        # A def stays if it can't be inlined, or if its single ref had validation
        # siblings (so `substitute` kept the ref). Find which refs survive.
        out = {k: v for k, v in schema.items() if k not in ("$defs", "definitions")}
        out = substitute(out)
        kept_bodies = {k: substitute(copy.deepcopy(defs[k])) for k in reachable - inlinable}
        # Re-scan: defs whose ref survived substitution must be kept too.
        while True:
            live = set()
            for node in [out, *kept_bodies.values()]:
                for sub in iter_schemas_skipping_defs(node):
                    parsed = _parse_ref(sub.get("$ref"))
                    if parsed:
                        live.add(parsed)
            missing = live - kept_bodies.keys()
            if not missing:
                break
            for k in missing:
                kept_bodies[k] = substitute(copy.deepcopy(defs[k]))

        # Rebuild the containers in their original key order and original position.
        result: Schema = {}
        for k, v in schema.items():
            if k in ("$defs", "definitions"):
                kept = {name: kept_bodies[(k, name)] for name in v if (k, name) in kept_bodies}
                if kept:
                    result[k] = kept
            else:
                result[k] = out[k]
        return result
