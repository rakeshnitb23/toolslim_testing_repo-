from __future__ import annotations

import json
from pathlib import Path

import pytest

from toolslim.loaders import load_json_file
from toolslim.models import ToolDef

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
SNAPSHOTS = ROOT / "bench" / "snapshots"


def snapshot_files() -> list[Path]:
    return sorted(SNAPSHOTS.glob("*.json")) if SNAPSHOTS.exists() else []


def all_snapshot_tools() -> list[tuple[str, ToolDef]]:
    out = []
    for path in snapshot_files():
        for tool in load_json_file(path):
            out.append((f"{path.stem}:{tool.name}", tool))
    return out


def fixture_tools() -> list[tuple[str, ToolDef]]:
    out = []
    for path in sorted(FIXTURES.glob("*_before.json")):
        for tool in load_json_file(path):
            out.append((f"{path.stem}:{tool.name}", tool))
    return out


@pytest.fixture
def load():
    def _load(name: str) -> list[ToolDef]:
        return load_json_file(FIXTURES / name)

    return _load


def as_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)
