"""Property-based checks that a slimmed schema accepts exactly what the original did.

Three probes, all must agree:
  1. generate valid instances from the ORIGINAL, validate against the SLIM schema
  2. generate valid instances from the SLIM schema, validate against the ORIGINAL
  3. mutate those instances (null / wrong type / dropped key / extra key, at every
     depth) and check both schemas give the same verdict, which catches a slim schema
     that *rejects* or *accepts* something the original didn't.

Needs the test extra: ``pip install toolslim[test]``.
"""

from __future__ import annotations

import copy
import os
import random
import warnings
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from hypothesis import HealthCheck, Phase, given, settings
from hypothesis import strategies as st
from jsonschema import Draft202012Validator
from jsonschema.validators import validator_for

# Boundary-ish values: empty/short/long strings, small/huge/negative/fractional numbers,
# empty/long arrays, objects. Long ones catch dropped max* constraints.
_MUTANT_VALUES: list[Any] = [
    None,
    True,
    0,
    -1,
    1.5,
    10**9,
    -(10**9),
    "",
    "x",
    "xyz",
    "x" * 300,
    "2026-10-16",
    "not-a-date",
    [],
    [None],
    list(range(60)),
    {},
    {"x": 1},
]


@dataclass
class EquivalenceReport:
    examples: int = 0
    generated_from: list[str] = field(default_factory=list)  # which directions generated
    mismatches: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.mismatches


def _validator(schema: dict[str, Any]):
    cls = validator_for(schema, default=Draft202012Validator)
    return cls(schema)


def _verdict(validator: Any, value: Any) -> bool | str:
    """True/False, or "error" when the schema can't even be applied (counts as a mismatch
    against a schema that can)."""
    try:
        return validator.is_valid(value)
    except Exception as exc:
        return f"error: {type(exc).__name__}"


def mutants(instance: Any, depth: int = 3) -> Iterator[Any]:
    """Small edits of ``instance`` at every position down to ``depth`` levels."""
    for v in _MUTANT_VALUES:
        yield v
    if depth <= 0:
        return
    if isinstance(instance, dict):
        yield {**instance, "__toolslim_extra__": 1}
        for k, v in instance.items():
            dropped = {kk: vv for kk, vv in instance.items() if kk != k}
            yield dropped
            for m in mutants(v, depth - 1):
                yield {**instance, k: m}
    elif isinstance(instance, list) and instance:
        yield instance[:-1]
        yield [*instance, instance[0]]  # duplicate (uniqueItems), longer (maxItems)
        for i, v in enumerate(instance[:3]):
            for m in mutants(v, depth - 1):
                yield [*instance[:i], m, *instance[i + 1 :]]


def unroll_refs(schema: dict[str, Any], depth: int = 3) -> dict[str, Any]:
    """Inline local ``#/$defs/X`` refs, cutting recursion at ``depth`` with ``{}``.

    Only used to build a *sampler*: hypothesis-jsonschema can't generate from recursive
    schemas. Every verdict still comes from validating against the real schemas.
    """
    from toolslim.rules.sl004_inline_single_use_defs import _parse_ref

    defs = {}
    for container in ("$defs", "definitions"):
        if isinstance(schema.get(container), dict):
            for k, v in schema[container].items():
                defs[(container, k)] = v

    def walk(node: Any, stack: tuple) -> Any:
        if isinstance(node, list):
            return [walk(x, stack) for x in node]
        if not isinstance(node, dict):
            return node
        parsed = _parse_ref(node.get("$ref")) if "$ref" in node else None
        if parsed is not None and parsed in defs:
            if stack.count(parsed) >= depth:
                return {}
            body = walk(defs[parsed], (*stack, parsed))
            rest = {k: walk(v, stack) for k, v in node.items() if k != "$ref"}
            if isinstance(body, dict) and not (set(rest) & set(body)):
                return {**body, **rest}
            return {"allOf": [body, rest]} if rest else body
        return {k: walk(v, stack) for k, v in node.items() if k not in ("$defs", "definitions")}

    return walk(schema, ())


def _sample(schema: dict[str, Any], n: int) -> list[Any]:
    from hypothesis_jsonschema import from_schema

    schema = unroll_refs(schema)
    out: list[Any] = []

    @settings(
        max_examples=n,
        deadline=None,
        database=None,
        derandomize=True,
        phases=[Phase.generate],
        suppress_health_check=list(HealthCheck),
    )
    @given(from_schema(schema, allow_x00=False))
    def collect(value: Any) -> None:
        out.append(value)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        collect()
    return out


def _seed_instances(schema: dict[str, Any]) -> list[Any]:
    """Hand-made instances so probes run even when generation isn't possible."""
    props = schema.get("properties") if isinstance(schema, dict) else None
    seeds: list[Any] = [{}]
    if isinstance(props, dict):
        seeds.append(dict.fromkeys(props, None))
        seeds.append(dict.fromkeys(props, "x"))
        seeds.append(dict.fromkeys(props, 1))
    return seeds


_THOROUGH = os.environ.get("TOOLSLIM_EQUIV_THOROUGH") == "1"


def check_equivalent(
    original: dict[str, Any],
    slim: dict[str, Any],
    *,
    max_examples: int | None = None,
    mutants_per_instance: int | None = None,
) -> EquivalenceReport:
    """Compare two schemas by validation verdicts. ``TOOLSLIM_EQUIV_THOROUGH=1`` runs
    200 generated examples per direction and every mutant (slow, for nightly CI)."""
    if max_examples is None:
        max_examples = 200 if _THOROUGH else 40
    if mutants_per_instance is None:
        mutants_per_instance = 0 if _THOROUGH else 60
    report = EquivalenceReport()
    v_orig, v_slim = _validator(original), _validator(slim)

    instances: list[tuple[str, Any]] = []
    for label, schema in (("original", original), ("slim", slim)):
        try:
            sampled = _sample(schema, max_examples)
            instances += [(label, x) for x in sampled]
            report.generated_from.append(label)
        except Exception as exc:  # generation is best-effort; probes 3 still run
            report.skipped.append(f"generate from {label}: {type(exc).__name__}: {exc}"[:300])
    instances += [("seed", x) for x in _seed_instances(original)]

    seen: set[str] = set()

    def probe(source: str, value: Any, *, must_be_valid: str | None) -> None:
        key = repr(value)
        if key in seen:
            return
        seen.add(key)
        report.examples += 1
        a, b = _verdict(v_orig, value), _verdict(v_slim, value)
        if a != b:
            report.mismatches.append(
                {
                    "instance": copy.deepcopy(value),
                    "from": source,
                    "valid_in_original": a,
                    "valid_in_slim": b,
                }
            )
        elif must_be_valid == "original" and not a:
            report.skipped.append("hypothesis produced an instance the original rejects")

    rng = random.Random(0)  # deterministic: the same schema always gets the same probes
    for source, value in instances:
        probe(source, value, must_be_valid=source if source != "seed" else None)
        all_mutants = list(mutants(value))
        if mutants_per_instance and len(all_mutants) > mutants_per_instance:
            # Keep every top-level mutant, sample the deep ones.
            head = all_mutants[: len(_MUTANT_VALUES)]
            all_mutants = head + rng.sample(
                all_mutants[len(head) :], mutants_per_instance - len(head)
            )
        for m in all_mutants:
            probe(f"mutant of {source}", m, must_be_valid=None)
            if len(report.mismatches) >= 5:
                return report
    return report


def instance_strategy() -> st.SearchStrategy[Any]:
    """Arbitrary JSON values (handy for ad-hoc fuzzing)."""
    scalars = st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False) | st.text()
    return st.recursive(
        scalars,
        lambda kids: (
            st.lists(kids, max_size=3) | st.dictionaries(st.text(max_size=5), kids, max_size=3)
        ),
        max_leaves=8,
    )
