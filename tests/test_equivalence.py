"""Every lossless rule must keep the set of valid arguments identical.

Runs on the hand-written fixtures AND on every real server snapshot in bench/snapshots.
"""

from __future__ import annotations

import pytest
from conftest import all_snapshot_tools, fixture_tools

from toolslim.equivalence import check_equivalent, mutants
from toolslim.pipeline import run_pipeline
from toolslim.rules import REGISTRY, select_rules

CASES = fixture_tools() + all_snapshot_tools()


def _assert_equivalent(original, slim, label):
    report = check_equivalent(original, slim)
    assert report.ok, f"{label}: {report.mismatches[:2]}"
    assert report.examples > 0


@pytest.mark.parametrize(("label", "tool"), CASES, ids=[c[0] for c in CASES])
def test_full_pipeline_is_equivalent(label, tool):
    slim = run_pipeline([tool], select_rules()).tools[0]
    _assert_equivalent(tool.input_schema, slim.input_schema, label)


FIXTURE_CASES = fixture_tools()


@pytest.mark.parametrize("rule_id", sorted(REGISTRY))
def test_each_rule_alone_is_equivalent_on_fixtures(rule_id):
    rule = REGISTRY[rule_id]()
    for label, tool in FIXTURE_CASES:
        slim = rule.apply([tool])[0]
        _assert_equivalent(tool.input_schema, slim.input_schema, f"{rule_id} {label}")


def test_checker_catches_the_naive_optional_rewrite():
    """The tempting rewrite anyOf[X, null] -> X rejects explicit nulls. Prove we'd notice."""
    original = {
        "type": "object",
        "properties": {"limit": {"anyOf": [{"type": "integer"}, {"type": "null"}]}},
    }
    naive = {"type": "object", "properties": {"limit": {"type": "integer"}}}
    report = check_equivalent(original, naive)
    assert not report.ok
    assert any(m["instance"].get("limit", 0) is None for m in report.mismatches
               if isinstance(m["instance"], dict))  # fmt: skip


def test_checker_catches_a_dropped_constraint():
    original = {"type": "object", "properties": {"n": {"type": "integer", "maximum": 5}}}
    loosened = {"type": "object", "properties": {"n": {"type": "integer"}}}
    assert not check_equivalent(original, loosened).ok


def test_checker_catches_merging_enum_with_overlapping_oneof():
    original = {"oneOf": [{"enum": ["a", "b"]}, {"enum": ["b", "c"]}]}
    wrong = {"enum": ["a", "b", "c"]}  # "b" is rejected by oneOf (matches twice)
    assert not check_equivalent(original, wrong).ok


def test_mutants_cover_nested_nulls():
    found = list(mutants({"a": {"b": 1}}))
    assert {"a": {"b": None}} in found
    assert {"a": None} in found
    assert {} in found


def test_dropping_schema_would_break_tuple_items():
    """Why SL008 refuses array-form items: 2020-12 can't even apply that schema."""
    original = {"$schema": "http://json-schema.org/draft-07/schema#", "type": "array",
                "items": [{"type": "string"}, {"type": "integer"}]}  # fmt: skip
    dropped = {k: v for k, v in original.items() if k != "$schema"}
    assert not check_equivalent(original, dropped).ok


def test_dropping_schema_would_activate_ref_siblings():
    """Why SL008 refuses $ref with validation siblings: draft-07 ignores them."""
    original = {"$schema": "http://json-schema.org/draft-07/schema#", "type": "object",
                "properties": {"x": {"$ref": "#/definitions/S", "maxLength": 2}},
                "definitions": {"S": {"type": "string"}}}  # fmt: skip
    dropped = {k: v for k, v in original.items() if k != "$schema"}
    assert not check_equivalent(original, dropped).ok
