"""Snapshot tools/list from the servers in bench/servers.yaml into bench/snapshots/."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import yaml

from toolslim.loaders.mcp_stdio import list_tools_raw

BENCH = Path(__file__).parent


def main(only: list[str]) -> int:
    cfg = yaml.safe_load((BENCH / "servers.yaml").read_text())
    out_dir = BENCH / "snapshots"
    out_dir.mkdir(exist_ok=True)
    failed = 0
    with tempfile.TemporaryDirectory() as tmp:
        for server in cfg["servers"]:
            if only and server["name"] not in only:
                continue
            cmd = server["command"].replace("{tmpdir}", tmp)
            try:
                tools = list_tools_raw(cmd, server.get("env"))
            except Exception as exc:
                print(f"FAIL {server['name']}: {exc}", file=sys.stderr)
                failed += 1
                continue
            path = out_dir / f"{server['name']}.json"
            path.write_text(json.dumps(tools, indent=2, ensure_ascii=False) + "\n")
            print(f"ok   {server['name']}: {len(tools)} tools -> {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
