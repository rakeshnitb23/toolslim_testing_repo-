"""Render results as rich tables, JSON or GitHub-flavoured markdown."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.table import Table

from toolslim.pipeline import SlimResult


def pct(saved: int, before: int) -> str:
    return f"{100.0 * saved / before:.1f}%" if before else "0.0%"


def measure_table(per_tool: dict[str, int], counter: str) -> Table:
    total = sum(per_tool.values())
    table = Table(title=f"Tool-definition tokens ({counter})", show_footer=True)
    table.add_column("tool", footer=f"{len(per_tool)} tools")
    table.add_column("tokens", justify="right", footer=str(total))
    table.add_column("share", justify="right", footer="100%")
    for name, n in sorted(per_tool.items(), key=lambda kv: -kv[1]):
        table.add_row(name, str(n), pct(n, total))
    return table


def slim_tables(result: SlimResult) -> list[Table]:
    rules = Table(title=f"Savings per rule ({result.counter_name})", show_footer=True)
    rules.add_column("rule", footer="total")
    rules.add_column("tools changed", justify="right")
    rules.add_column("tokens saved", justify="right", footer=str(result.saved))
    rules.add_column(
        "% of original", justify="right", footer=pct(result.saved, result.tokens_before)
    )
    for r in result.per_rule:
        rules.add_row(
            f"{r.rule_id} {r.rule_name}",
            str(r.tools_changed),
            str(r.saved),
            pct(r.saved, result.tokens_before),
        )
    summary = Table(title="Before / after")
    for col in ("tools", "before", "after", "saved"):
        summary.add_column(col, justify="right")
    summary.add_row(
        str(len(result.tools)),
        str(result.tokens_before),
        str(result.tokens_after),
        f"{result.saved} ({pct(result.saved, result.tokens_before)})",
    )
    return [summary, rules]


def print_tables(tables: list[Table]) -> None:
    console = Console()
    for t in tables:
        console.print(t)


def slim_json(result: SlimResult) -> dict[str, Any]:
    return {
        "counter": result.counter_name,
        "tools": len(result.tools),
        "tokens_before": result.tokens_before,
        "tokens_after": result.tokens_after,
        "saved": result.saved,
        "percent_saved": round(result.percent_saved, 2),
        "rules": [
            {
                "id": r.rule_id,
                "name": r.rule_name,
                "saved": r.saved,
                "tools_changed": r.tools_changed,
            }
            for r in result.per_rule
        ],
        "per_tool": {
            n: {"before": result.per_tool_before.get(n), "after": a}
            for n, a in result.per_tool_after.items()
        },
    }


def check_markdown(
    *,
    counter: str,
    baseline: dict[str, int],
    current: dict[str, int],
    limit_desc: str,
    passed: bool,
    potential: SlimResult | None = None,
) -> str:
    base_total, cur_total = sum(baseline.values()), sum(current.values())
    delta = cur_total - base_total
    icon = "✅" if passed else "❌"
    lines = [
        f"### {icon} toolslim: tool-definition tokens",
        "",
        f"**{base_total} → {cur_total}** ({delta:+d}, "
        f"{(100.0 * delta / base_total if base_total else 0):+.1f}%) · budget: {limit_desc} · "
        f"tokenizer `{counter}`",
        "",
    ]
    changes = []
    for name in sorted(set(baseline) | set(current)):
        b, c = baseline.get(name), current.get(name)
        if b != c:
            changes.append((name, b, c))
    if changes:
        lines += ["| tool | baseline | now | Δ |", "|---|---:|---:|---:|"]
        for name, b, c in sorted(changes, key=lambda x: -abs((x[2] or 0) - (x[1] or 0))):
            d = (c or 0) - (b or 0)
            lines.append(
                f"| `{name}` | {b if b is not None else 'new'} | "
                f"{c if c is not None else 'removed'} | {d:+d} |"
            )
    else:
        lines.append("No per-tool changes.")
    if potential is not None and potential.saved > 0:
        lines += [
            "",
            f"💡 `toolslim slim` would cut these definitions by **{potential.saved} tokens "
            f"({potential.percent_saved:.1f}%)** with lossless rules.",
        ]
    return "\n".join(lines) + "\n"
