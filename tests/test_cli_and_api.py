from __future__ import annotations

import json

import pytest
from conftest import FIXTURES, ROOT
from typer.testing import CliRunner

from toolslim import measure_tools, slim_tools
from toolslim.cli import app
from toolslim.loaders import ToolLoadError, parse_tools
from toolslim.tokenizers.anthropic_counter import AnthropicCounter

runner = CliRunner()
PYDANTIC = ROOT / "examples" / "pydantic_tools.json"

OPENAI_CHAT = {"type": "function", "function": {"name": "f", "description": "d", "strict": True,
               "parameters": {"type": "object", "title": "F", "properties": {}}}}  # fmt: skip
OPENAI_RESP = {"type": "function", "name": "f", "parameters": {"type": "object", "title": "F"}}
ANTHROPIC = {"name": "f", "input_schema": {"type": "object", "title": "F"},
             "cache_control": {"type": "ephemeral"}}  # fmt: skip
MCP = {"name": "f", "inputSchema": {"type": "object", "title": "F"},
       "annotations": {"readOnlyHint": True}}  # fmt: skip


@pytest.mark.parametrize("raw", [OPENAI_CHAT, OPENAI_RESP, ANTHROPIC, MCP])
def test_slim_tools_keeps_wire_shape_and_extra_fields(raw):
    out = slim_tools([raw])[0]
    assert set(out) == set(raw)  # same top-level keys, extras carried through
    if "function" in raw:
        assert out["function"]["strict"] is True
        assert "title" not in out["function"]["parameters"]
    else:
        key = {"input_schema", "inputSchema", "parameters"} & set(raw)
        assert "title" not in out[key.pop()]


def test_slim_tools_does_not_touch_input():
    raw = [json.loads(json.dumps(MCP))]
    before = json.dumps(raw)
    slim_tools(raw)
    assert json.dumps(raw) == before


@pytest.mark.parametrize(
    "data",
    [[MCP], {"tools": [MCP]}, {"jsonrpc": "2.0", "id": 1, "result": {"tools": [MCP]}}, MCP],
)
def test_loader_accepts_list_shapes(data):
    assert [t.name for t in parse_tools(data)] == ["f"]


def test_loader_rejects_junk():
    with pytest.raises(ToolLoadError):
        parse_tools([{"description": "no name"}])
    with pytest.raises(ToolLoadError):
        parse_tools("nope")


def test_measure_tools_api():
    counts = measure_tools([MCP])
    assert counts["f"] > 0


def test_cli_measure_json():
    res = runner.invoke(app, ["measure", str(PYDANTIC), "--json"])
    assert res.exit_code == 0, res.output
    data = json.loads(res.output)
    assert data["total"] == sum(data["tools"].values()) > 0


def test_cli_slim_writes_file(tmp_path):
    out = tmp_path / "slim.json"
    res = runner.invoke(app, ["slim", str(PYDANTIC), "-o", str(out), "--json"])
    assert res.exit_code == 0, res.output
    report = json.loads(res.output)
    assert report["tokens_after"] < report["tokens_before"]
    assert json.loads(out.read_text())[0]["name"] == "search_users"


def test_cli_slim_rule_selection():
    res = runner.invoke(app, ["slim", str(PYDANTIC), "--json", "-r", "SL001,SL003"])
    assert [r["id"] for r in json.loads(res.output)["rules"]] == ["SL001", "SL003"]
    res = runner.invoke(app, ["slim", str(PYDANTIC), "-r", "bogus"])
    assert res.exit_code == 2


def test_cli_check_passes_then_fails_on_bloat(tmp_path):
    tools_path = tmp_path / "tools.json"
    tools = json.loads(PYDANTIC.read_text())
    tools_path.write_text(json.dumps(tools))
    baseline = tmp_path / "base.json"

    res = runner.invoke(app, ["check", str(tools_path), "-b", str(baseline), "--write-baseline"])
    assert res.exit_code == 0 and baseline.exists()

    md = tmp_path / "report.md"
    res = runner.invoke(app, ["check", str(tools_path), "-b", str(baseline), "--markdown", str(md)])
    assert res.exit_code == 0, res.output
    assert "✅" in md.read_text()

    tools[0]["description"] += " " + "This tool is very helpful and thorough. " * 30
    tools_path.write_text(json.dumps(tools))
    res = runner.invoke(app, ["check", str(tools_path), "-b", str(baseline),
                              "--max-increase", "10%", "--markdown", str(md)])  # fmt: skip
    assert res.exit_code == 1
    text = md.read_text()
    assert "❌" in text and "`search_users`" in text and "would cut" in text

    res = runner.invoke(app, ["check", str(tools_path), "-b", str(baseline),
                              "--max-increase", "100000"])  # fmt: skip
    assert res.exit_code == 0


def test_cli_needs_exactly_one_source():
    assert runner.invoke(app, ["measure"]).exit_code == 2


def test_cli_rules_lists_everything():
    res = runner.invoke(app, ["rules"])
    for rid in ("SL001", "SL004", "SL008"):
        assert rid in res.output


class _FakeMessages:
    """Pretends to be count_tokens: 10 base + 40 tool-use prompt + len(json)//4 per tool."""

    def count_tokens(self, *, model, messages, tools=None):
        n = 10
        if tools:
            n += 40 + sum(len(json.dumps(t)) // 4 for t in tools)

        class R:
            input_tokens = n

        return R()


class _FakeClient:
    messages = _FakeMessages()


def test_anthropic_counter_subtracts_baseline_and_overhead():
    from toolslim.loaders import load_json_file

    tools = load_json_file(FIXTURES / "sl001_before.json")
    c = AnthropicCounter("claude-test", client=_FakeClient())
    expected_defs = sum(len(json.dumps(c._wire(t))) // 4 for t in tools)
    assert c.count_tools(tools) == 40 + expected_defs
    assert c.tool_use_overhead() == 40
    assert c.count_tool(tools[0]) == len(json.dumps(c._wire(tools[0]))) // 4
    assert c.count_tools([]) == 0
