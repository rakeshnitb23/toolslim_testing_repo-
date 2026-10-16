"""Run rules in order and record what each one saved."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field

from toolslim.models import ToolDef
from toolslim.rules import BaseRule, select_rules
from toolslim.tokenizers import TiktokenCounter, TokenCounter


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    rule_name: str
    tokens_before: int
    tokens_after: int
    tools_changed: int

    @property
    def saved(self) -> int:
        return self.tokens_before - self.tokens_after


@dataclass(frozen=True)
class SlimResult:
    tools: list[ToolDef]
    original: list[ToolDef]
    counter_name: str
    tokens_before: int
    tokens_after: int
    per_rule: list[RuleResult] = field(default_factory=list)
    per_tool_before: dict[str, int] = field(default_factory=dict)
    per_tool_after: dict[str, int] = field(default_factory=dict)

    @property
    def saved(self) -> int:
        return self.tokens_before - self.tokens_after

    @property
    def percent_saved(self) -> float:
        return 100.0 * self.saved / self.tokens_before if self.tokens_before else 0.0


class RuleMutatedInputError(RuntimeError):
    """A rule changed the tools it was given instead of returning new ones."""


def run_pipeline(
    tools: Sequence[ToolDef],
    rules: Sequence[BaseRule] | None = None,
    counter: TokenCounter | None = None,
    *,
    check_mutation: bool = True,
) -> SlimResult:
    counter = counter or TiktokenCounter()
    rules = list(rules) if rules is not None else select_rules()
    # Deep copy at the boundary: the caller's objects are never touched, so the
    # "before" numbers can't be corrupted by a rule that edits in place.
    original = [t.model_copy(deep=True) for t in tools]
    current = [t.model_copy(deep=True) for t in tools]

    # Totals come from the list, not the per-name dict: duplicate names must not collapse.
    per_tool_before = {t.name: counter.count_tool(t) for t in original}
    before = counter.count_tools(original)
    tokens = before
    per_rule: list[RuleResult] = []
    for rule in rules:
        snapshot = _fingerprint(current) if check_mutation else None
        new = list(rule.apply(current))
        if check_mutation and _fingerprint(current) != snapshot:
            raise RuleMutatedInputError(f"{rule.id} {rule.name} mutated its input")
        changed = _count_changed(current, new)
        after = counter.count_tools(new) if changed else tokens
        per_rule.append(RuleResult(rule.id, rule.name, tokens, after, changed))
        current, tokens = new, after

    per_tool_after = {t.name: counter.count_tool(t) for t in current}
    return SlimResult(
        tools=current,
        original=original,
        counter_name=counter.name,
        tokens_before=before,
        tokens_after=counter.count_tools(current),
        per_rule=per_rule,
        per_tool_before=per_tool_before,
        per_tool_after=per_tool_after,
    )


def _fingerprint(tools: list[ToolDef]) -> str:
    return json.dumps([t.model_dump() for t in tools], ensure_ascii=False)


def _count_changed(old: list[ToolDef], new: list[ToolDef]) -> int:
    def key(t: ToolDef) -> str:  # order-sensitive, unlike ToolDef ==
        return json.dumps(t.model_dump(), ensure_ascii=False)

    by_name = {t.name: key(t) for t in old}
    changed = sum(1 for t in new if by_name.get(t.name) != key(t))
    if [t.name for t in old] != [t.name for t in new]:
        changed = max(changed, 1)  # a reorder counts as a change
    return changed
