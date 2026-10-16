"""Importing this package registers every rule module in it (one file per rule)."""

from __future__ import annotations

import importlib
import pkgutil

from toolslim.rules.base import REGISTRY, BaseRule, Rule, register_rule

for _mod in pkgutil.iter_modules(__path__):
    if _mod.name.startswith("sl"):
        importlib.import_module(f"{__name__}.{_mod.name}")


def all_rules() -> list[BaseRule]:
    return sorted((cls() for cls in REGISTRY.values()), key=lambda r: (r.order, r.id))


def select_rules(
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    *,
    lossy: bool = False,
) -> list[BaseRule]:
    """Pick rules by id or name. Lossless rules are on by default; lossy ones only when
    ``lossy=True`` or named in ``include``."""

    def matches(rule: BaseRule, keys: list[str]) -> bool:
        keys_l = {k.lower() for k in keys}
        return rule.id.lower() in keys_l or rule.name.lower() in keys_l

    chosen = []
    for rule in all_rules():
        if include:
            if not matches(rule, include):
                continue
        elif not (rule.lossless or lossy):
            continue
        if exclude and matches(rule, exclude):
            continue
        chosen.append(rule)
    if include:
        unknown = [k for k in include if not any(matches(r, [k]) for r in all_rules())]
        if unknown:
            raise KeyError(f"unknown rule(s): {', '.join(unknown)}")
    return chosen


__all__ = ["REGISTRY", "BaseRule", "Rule", "all_rules", "register_rule", "select_rules"]
