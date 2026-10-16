"""Rule protocol, base class and the ``@register_rule`` registry."""

from __future__ import annotations

import json
from typing import Any, ClassVar, Protocol, TypeVar, runtime_checkable

from toolslim.models import ToolDef

Schema = dict[str, Any]


def same_json(a: Any, b: Any) -> bool:
    """Order-sensitive equality (unlike ``==`` on dicts)."""
    return json.dumps(a, ensure_ascii=False) == json.dumps(b, ensure_ascii=False)


@runtime_checkable
class Rule(Protocol):
    id: str  # "SL001"
    name: str  # "redundant-title"
    lossless: bool  # True = validation-equivalent; on by default
    order: int  # execution order inside the pipeline (lower runs first)
    summary: str

    def apply(self, tools: list[ToolDef]) -> list[ToolDef]:
        """Return new tools. Must NOT mutate ``tools`` or anything inside them."""
        ...


class BaseRule:
    """Convenience base: override ``apply_schema`` (or ``apply_tool`` for rules that
    need the tool name / description). ``apply`` maps over the list."""

    id: ClassVar[str]
    name: ClassVar[str]
    lossless: ClassVar[bool] = True
    order: ClassVar[int] = 100
    summary: ClassVar[str] = ""

    def apply_schema(self, schema: Schema) -> Schema:
        return schema

    def apply_tool(self, tool: ToolDef) -> ToolDef:
        new_schema = self.apply_schema(tool.input_schema)
        # Compare serialised: dict == ignores key order, but order changes tokens.
        if same_json(new_schema, tool.input_schema):
            return tool
        return tool.with_changes(input_schema=new_schema)

    def apply(self, tools: list[ToolDef]) -> list[ToolDef]:
        return [self.apply_tool(t) for t in tools]

    def __repr__(self) -> str:
        return f"<{self.id} {self.name}>"


REGISTRY: dict[str, type[BaseRule]] = {}

R = TypeVar("R", bound=type[BaseRule])


def register_rule(cls: R) -> R:
    """Class decorator: add a rule to the registry under its ``id``.

    Contributors add a rule by dropping one file in ``toolslim/rules/``; the package
    ``__init__`` imports every module there, which runs this decorator.
    """
    for attr in ("id", "name"):
        if not getattr(cls, attr, None):
            raise TypeError(f"{cls.__name__} must define a non-empty '{attr}'")
    if cls.id in REGISTRY and REGISTRY[cls.id] is not cls:
        raise ValueError(f"duplicate rule id {cls.id}: {REGISTRY[cls.id].__name__}, {cls.__name__}")
    REGISTRY[cls.id] = cls
    return cls
