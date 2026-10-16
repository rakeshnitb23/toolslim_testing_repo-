# Good first issues to open on launch day

Paste each as an issue with the `good first issue` label (plus the second label shown).

1. **SL101 `max-description-length`** (`rule`): lossy, opt-in. Truncate descriptions over N chars at a sentence boundary. Needs `--max-description` CLI option.
2. **SL102 `drop-examples`** (`rule`): lossy, opt-in. Remove `examples` keyword everywhere.
3. **Gemini `count_tokens` adapter** (`tokenizer`): implement `TokenCounter` in `toolslim/tokenizers/gemini_counter.py` behind a `[gemini]` extra.
4. **LangChain `BaseTool` loader** (`loader`): `toolslim.loaders.langchain.load_tools(list[BaseTool]) -> list[ToolDef]` via `convert_to_openai_tool`.
5. **OpenAI Agents SDK loader** (`loader`): turn `FunctionTool` objects into `ToolDef`.
6. **Add a public MCP server to the benchmark** (`benchmark`): add to `bench/servers.yaml`, snapshot, rerun `run_bench.py`.
7. **`--format sarif`** (`good first issue`): emit `toolslim check` findings as SARIF for GitHub code scanning.
8. **`pre-commit` hook** (`good first issue`): add `.pre-commit-hooks.yaml` exposing `toolslim check`.
