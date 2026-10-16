"""``toolslim measure | slim | check | rules``."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from toolslim import __version__
from toolslim.loaders import ToolLoadError, dump_tools, load_json_file
from toolslim.models import ToolDef
from toolslim.pipeline import run_pipeline
from toolslim.report import (
    check_markdown,
    measure_table,
    print_tables,
    slim_json,
    slim_tables,
)
from toolslim.rules import all_rules, select_rules
from toolslim.tokenizers import get_counter

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Measure and losslessly slim the tool / MCP schemas an agent sends every turn.",
)
err = Console(stderr=True)

SourceArg = Annotated[
    Optional[Path],  # noqa: UP045 - typer needs Optional on 3.9-style introspection
    typer.Argument(help="JSON file of tools (MCP, Anthropic, OpenAI or a tools/list result)."),
]
McpOpt = Annotated[
    Optional[str],  # noqa: UP045
    typer.Option("--mcp", help='Launch an MCP server over stdio, e.g. "uvx mcp-server-git".'),
]
TokenizerOpt = Annotated[
    str,
    typer.Option("--tokenizer", "-t",
                 help="o200k_base | cl100k_base | anthropic[:model] (needs API key)."),
]  # fmt: skip


def _load(source: Path | None, mcp: str | None) -> list[ToolDef]:
    if (source is None) == (mcp is None):
        err.print("[red]give exactly one of SOURCE or --mcp[/red]")
        raise typer.Exit(2)
    try:
        if mcp:
            from toolslim.loaders.mcp_stdio import load_mcp_stdio

            return load_mcp_stdio(mcp)
        assert source is not None
        return load_json_file(source)
    except (ToolLoadError, FileNotFoundError, RuntimeError) as exc:
        err.print(f"[red]error:[/red] {escape(str(exc))}")
        raise typer.Exit(2) from exc


def _split(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    return [v.strip() for item in values for v in item.split(",") if v.strip()]


def _version(value: bool) -> None:
    if value:
        print(f"toolslim {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[bool, typer.Option("--version", callback=_version, is_eager=True)] = False,
) -> None:
    pass


@app.command()
def measure(
    source: SourceArg = None,
    mcp: McpOpt = None,
    tokenizer: TokenizerOpt = "o200k_base",
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON instead of a table.")] = False,
    save: Annotated[
        Optional[Path],  # noqa: UP045
        typer.Option("--save", help="Also write the loaded tools (wire shape) to this file."),
    ] = None,
) -> None:
    """Count tokens per tool."""
    tools = _load(source, mcp)
    counter = get_counter(tokenizer)
    per_tool = {t.name: counter.count_tool(t) for t in tools}
    if save:
        save.write_text(dump_tools(tools) + "\n", encoding="utf-8")
    if as_json:
        print(json.dumps({"counter": counter.name, "total": sum(per_tool.values()),
                          "tools": per_tool}, indent=2))  # fmt: skip
    else:
        print_tables([measure_table(per_tool, counter.name)])


@app.command()
def slim(
    source: SourceArg = None,
    mcp: McpOpt = None,
    output: Annotated[
        Optional[Path],  # noqa: UP045
        typer.Option("--output", "-o", help="Write slimmed tools here ('-' for stdout)."),
    ] = None,
    rules: Annotated[
        Optional[list[str]],  # noqa: UP045
        typer.Option("--rules", "-r", help="Only these rule ids/names (comma separated)."),
    ] = None,
    exclude: Annotated[
        Optional[list[str]],  # noqa: UP045
        typer.Option("--exclude", "-x", help="Skip these rule ids/names."),
    ] = None,
    lossy: Annotated[bool, typer.Option("--lossy", help="Also run opt-in lossy rules.")] = False,
    tokenizer: TokenizerOpt = "o200k_base",
    as_json: Annotated[bool, typer.Option("--json", help="Print the report as JSON.")] = False,
) -> None:
    """Apply lossless rules and show the savings per rule."""
    tools = _load(source, mcp)
    try:
        chosen = select_rules(_split(rules), _split(exclude), lossy=lossy)
    except KeyError as exc:
        err.print(f"[red]{exc.args[0]}[/red]")
        raise typer.Exit(2) from exc
    result = run_pipeline(tools, chosen, get_counter(tokenizer))
    if output is not None:
        text = dump_tools(result.tools) + "\n"
        if str(output) == "-":
            sys.stdout.write(text)
            return
        output.write_text(text, encoding="utf-8")
    if as_json:
        print(json.dumps(slim_json(result), indent=2))
    else:
        print_tables(slim_tables(result))
        if output is not None:
            err.print(f"wrote {output}")


def _parse_limit(limit: str) -> tuple[float | None, int | None]:
    limit = limit.strip()
    if limit.endswith("%"):
        return float(limit[:-1]), None
    return None, int(limit)


@app.command()
def check(
    source: SourceArg = None,
    mcp: McpOpt = None,
    baseline: Annotated[
        Path, typer.Option("--baseline", "-b", help="Baseline JSON from --write-baseline.")
    ] = Path("token-baseline.json"),
    max_increase: Annotated[
        str, typer.Option("--max-increase", help="Allowed growth: '10%' or a token count.")
    ] = "10%",
    write_baseline: Annotated[
        bool, typer.Option("--write-baseline", help="Record the current numbers and exit 0.")
    ] = False,
    markdown: Annotated[
        Optional[Path],  # noqa: UP045
        typer.Option("--markdown", help="Write a PR-comment markdown report here."),
    ] = None,
    tokenizer: TokenizerOpt = "o200k_base",
) -> None:
    """CI gate: exit 1 if tool-definition tokens grew past the budget."""
    tools = _load(source, mcp)
    counter = get_counter(tokenizer)
    current = {t.name: counter.count_tool(t) for t in tools}
    if write_baseline:
        baseline.write_text(json.dumps({"counter": counter.name, "total": sum(current.values()),
                                        "tools": current}, indent=2) + "\n")  # fmt: skip
        err.print(f"wrote baseline {baseline} ({sum(current.values())} tokens)")
        return
    if not baseline.exists():
        err.print(f"[red]baseline {baseline} not found; create it with --write-baseline[/red]")
        raise typer.Exit(2)
    data = json.loads(baseline.read_text())
    if data.get("counter") and data["counter"] != counter.name:
        err.print(f"[yellow]warning: baseline used {data['counter']}, now {counter.name}[/yellow]")
    base = {k: int(v) for k, v in data.get("tools", {}).items()}
    base_total, cur_total = sum(base.values()), sum(current.values())
    try:
        pct_limit, abs_limit = _parse_limit(max_increase)
    except ValueError as exc:
        err.print(f"[red]bad --max-increase {max_increase!r}[/red]")
        raise typer.Exit(2) from exc
    allowed = abs_limit if abs_limit is not None else int(base_total * (pct_limit or 0) / 100)
    passed = cur_total - base_total <= allowed

    potential = run_pipeline(tools, select_rules(), counter)
    report = check_markdown(counter=counter.name, baseline=base, current=current,
                            limit_desc=f"+{max_increase}", passed=passed,
                            potential=potential)  # fmt: skip
    if markdown:
        markdown.write_text(report, encoding="utf-8")
    print(report)
    raise typer.Exit(0 if passed else 1)


@app.command("rules")
def list_rules() -> None:
    """List the available rules."""
    table = Table(title="toolslim rules")
    for col in ("id", "name", "lossless", "what it does"):
        table.add_column(col)
    for r in all_rules():
        table.add_row(r.id, r.name, "yes" if r.lossless else "no (opt-in)", r.summary)
    Console().print(table)


if __name__ == "__main__":  # pragma: no cover
    app()
