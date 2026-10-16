"""Ground-truth token counts from Anthropic's ``count_tokens`` endpoint.

Needs ``pip install toolslim[anthropic]`` and ``ANTHROPIC_API_KEY``. The endpoint is free
but rate limited. A request with tools also carries a fixed tool-use system prompt, so we
subtract a no-tools baseline to report only what the definitions cost.
"""

from __future__ import annotations

from typing import Any

from toolslim.models import ToolDef

_PROBE = [{"role": "user", "content": "hi"}]


class AnthropicCounter:
    def __init__(self, model: str = "claude-sonnet-5-5", client: Any | None = None) -> None:
        if client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError("needs: pip install 'toolslim[anthropic]'") from exc
            client = anthropic.Anthropic()
        self.client = client
        self.model = model
        self.name = f"anthropic:{model}"
        self._baseline: int | None = None
        self._overhead: int | None = None

    def _count(self, tools: list[dict[str, Any]] | None) -> int:
        kwargs: dict[str, Any] = {"model": self.model, "messages": _PROBE}
        if tools:
            kwargs["tools"] = tools
        return self.client.messages.count_tokens(**kwargs).input_tokens

    @staticmethod
    def _wire(tool: ToolDef) -> dict[str, Any]:
        wire = tool.to_wire("anthropic")
        # Keep only what the Messages API accepts on a custom tool.
        allowed = {"name", "description", "input_schema", "cache_control", "strict"}
        return {k: v for k, v in wire.items() if k in allowed}

    def _base(self) -> int:
        if self._baseline is None:
            self._baseline = self._count(None)
        return self._baseline

    def count_tools(self, tools: list[ToolDef]) -> int:
        if not tools:
            return 0
        return self._count([self._wire(t) for t in tools]) - self._base()

    def count_tool(self, tool: ToolDef) -> int:
        """Marginal cost of one tool: excludes the one-off tool-use system prompt, which is
        estimated once as count([t]) - count_without_tool_body. Summing per-tool numbers
        therefore approximates ``count_tools`` minus that fixed overhead."""
        return self.count_tools([tool]) - self.tool_use_overhead()

    def tool_use_overhead(self) -> int:
        """Tokens added by having *any* tool, beyond the definition itself."""
        if self._overhead is None:
            stub = ToolDef(name="x", input_schema={"type": "object"})
            stub_cost = self.count_tools([stub])
            two = self.count_tools([stub, stub.with_changes(name="y")])
            per_stub = two - stub_cost
            self._overhead = stub_cost - per_stub
        return self._overhead
