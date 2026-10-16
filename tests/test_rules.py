from __future__ import annotations

import json

import pytest
from conftest import FIXTURES, all_snapshot_tools, as_json, fixture_tools

from toolslim.models import ToolDef
from toolslim.pipeline import RuleMutatedInputError, run_pipeline
from toolslim.rules import REGISTRY, BaseRule, all_rules, register_rule, select_rules
from toolslim.rules.sl005_description_whitespace import clean_text
from toolslim.rules.sl006_echo_description import is_echo

RULE_IDS = sorted(REGISTRY)


@pytest.mark.parametrize("rule_id", RULE_IDS)
def test_fixture_before_after(rule_id, load):
    """Each rule turns slNNN_before.json into exactly slNNN_after.json (key order too)."""
    stem = rule_id.lower()
    before, after = load(f"{stem}_before.json"), load(f"{stem}_after.json")
    got = REGISTRY[rule_id]().apply(before)
    assert as_json([t.to_wire() for t in got]) == as_json([t.to_wire() for t in after])


@pytest.mark.parametrize("rule_id", RULE_IDS)
def test_every_rule_has_fixtures(rule_id):
    stem = rule_id.lower()
    assert (FIXTURES / f"{stem}_before.json").exists()
    assert (FIXTURES / f"{stem}_after.json").exists()


@pytest.mark.parametrize("rule_id", RULE_IDS)
def test_rule_does_not_mutate_input(rule_id):
    tools = [t for _, t in fixture_tools() + all_snapshot_tools()]
    snapshot = json.dumps([t.model_dump() for t in tools])
    REGISTRY[rule_id]().apply(tools)
    assert json.dumps([t.model_dump() for t in tools]) == snapshot


@pytest.mark.parametrize("rule_id", RULE_IDS)
def test_rule_is_idempotent(rule_id):
    rule = REGISTRY[rule_id]()
    tools = [t for _, t in fixture_tools() + all_snapshot_tools()]
    once = rule.apply(tools)
    twice = rule.apply(once)
    assert as_json([t.model_dump() for t in once]) == as_json([t.model_dump() for t in twice])


def test_pipeline_never_increases_tokens():
    tools = [t for _, t in fixture_tools() + all_snapshot_tools()]
    result = run_pipeline(tools)
    assert result.tokens_after <= result.tokens_before
    for r in result.per_rule:
        if r.rule_id == "SL007":
            # Canonical keyword order is for cache stability, not size: it may cost a
            # token here and there, but never more than 0.1%.
            assert -r.saved <= max(5, r.tokens_before // 1000)
        else:
            assert r.saved >= 0, f"{r.rule_id} made things bigger"


def test_pipeline_catches_a_mutating_rule():
    class Evil(BaseRule):
        id, name = "SL999", "evil"

        def apply(self, tools):
            tools[0].input_schema["sneaky"] = True  # in-place edit: the bug we guard against
            return tools

    tool = ToolDef(name="x", input_schema={"type": "object"})
    with pytest.raises(RuleMutatedInputError):
        run_pipeline([tool], [Evil()])
    assert "sneaky" not in tool.input_schema  # caller's object is untouched either way


def test_registry_and_selection():
    assert [r.id for r in all_rules()] == ["SL005", "SL006", "SL001", "SL008", "SL003",
                                           "SL004", "SL002", "SL007"]  # fmt: skip
    assert [r.id for r in select_rules(["redundant-title", "SL002"])] == ["SL001", "SL002"]
    assert "SL007" not in [r.id for r in select_rules(exclude=["stable-order"])]
    with pytest.raises(KeyError):
        select_rules(["nope"])


def test_register_rule_rejects_duplicates_and_missing_ids():
    with pytest.raises(ValueError):

        @register_rule
        class Dup(BaseRule):
            id, name = "SL001", "dup"

    with pytest.raises(TypeError):

        @register_rule
        class NoId(BaseRule):
            name = "no-id"


@pytest.mark.parametrize(
    ("name", "desc", "echo"),
    [
        ("user_id", "The user ID", True),
        ("user_id", "The ID of the user.", True),
        ("repoName", "Repo name", True),
        ("limit", "Maximum number of results", False),
        ("path", "Absolute path to the file", False),
        ("q", "The query", False),
    ],
)
def test_is_echo(name, desc, echo):
    assert is_echo(name, desc) is echo


def test_clean_text_keeps_identifiers():
    assert clean_text("call  __init__  with *args") == "call __init__ with *args"
    assert clean_text("a **b** c") == "a b c"


def test_tuple_items_refs_are_seen():
    """Regression: draft-07 tuple-form items once went unwalked, so SL004 could delete a
    def that was only referenced from inside it."""
    schema = {"type": "array", "items": [{"$ref": "#/definitions/A"}, {"$ref": "#/definitions/B"}],
              "definitions": {"A": {"type": "string"}, "B": {"type": "integer"},
                              "C": {"type": "null"}}}  # fmt: skip
    out = REGISTRY["SL004"]().apply_schema(schema)
    assert out == {"type": "array", "items": [{"type": "string"}, {"type": "integer"}]}
