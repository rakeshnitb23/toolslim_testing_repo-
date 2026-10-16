"""The one data type every part of toolslim passes around."""

from __future__ import annotations

import copy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SourceFormat = Literal["mcp", "anthropic", "openai_chat", "openai_responses"]


class ToolDef(BaseModel):
    """A tool definition, normalised away from any one provider's wire shape.

    The model is frozen so a ToolDef can't be reassigned in place. ``input_schema`` is
    still a plain dict (JSON Schema is open-ended), so rules must treat it as read-only
    and return new dicts. The pipeline deep-copies at its boundary to enforce that.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    description: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object"})
    source_format: SourceFormat = "mcp"
    # Fields we don't touch (annotations, outputSchema, strict, cache_control, ...) are
    # carried through untouched so a round trip doesn't lose them.
    extra: dict[str, Any] = Field(default_factory=dict)

    def with_changes(self, **changes: Any) -> ToolDef:
        """Return a new ToolDef with ``changes`` applied (the original is untouched)."""
        return self.model_copy(update=changes, deep=True)

    def to_wire(self, fmt: SourceFormat | None = None) -> dict[str, Any]:
        """Render back into a provider's wire shape (defaults to the source shape)."""
        fmt = fmt or self.source_format
        schema = copy.deepcopy(self.input_schema)
        extra = copy.deepcopy(self.extra)
        if fmt == "openai_chat":
            fn: dict[str, Any] = {"name": self.name}
            if self.description is not None:
                fn["description"] = self.description
            fn["parameters"] = schema
            fn.update(extra)
            return {"type": "function", "function": fn}
        out: dict[str, Any] = {}
        if fmt == "openai_responses":
            out["type"] = "function"
        out["name"] = self.name
        if self.description is not None:
            out["description"] = self.description
        key = {"mcp": "inputSchema", "anthropic": "input_schema"}.get(fmt, "parameters")
        out[key] = schema
        out.update(extra)
        return out
