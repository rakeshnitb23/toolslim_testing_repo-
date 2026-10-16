# Contributing to toolslim

Thanks for helping. PRs get a first response within 24 hours.

## Setup

```bash
git clone https://github.com/rakeshnitb23/toolslim && cd toolslim
uv venv && uv pip install -e ".[dev]" pytest-xdist
pre-commit install
pytest -n auto
```

## Add a rule in three files

1. **`toolslim/rules/slNNN_your_name.py`**

   ```python
   from toolslim.rules.base import BaseRule, Schema, register_rule
   from toolslim.schema import map_schemas


   @register_rule
   class YourRule(BaseRule):
       id = "SL009"
       name = "your-name"
       lossless = True  # False = opt-in via --lossy (use ids SL101+ for lossy rules)
       order = 45  # where it runs in the pipeline (see existing rules)
       summary = "One line for `toolslim rules`."

       def apply_schema(self, schema: Schema) -> Schema:
           def fix(node: Schema) -> Schema:
               ...  # node is a fresh dict: return a new/edited one
               return node

           return map_schemas(schema, fix)
   ```

   Rules must **not mutate** their input. Always go through `map_schemas`, which hands you fresh dicts, and which knows that a property *named* `title` isn't the `title` keyword. The pipeline raises `RuleMutatedInputError` if a rule edits in place. Override `apply_tool` if you need the tool name or description, or `apply` for list-level rules.

2. **`tests/fixtures/slNNN_before.json`**: tools (MCP shape) covering the cases you change *and* the look-alike cases you must leave alone.

3. **`tests/fixtures/slNNN_after.json`**: exactly what the rule should produce, key order included.

That's it. The registry picks the rule up automatically, and the existing tests then check that it:

- turns `before` into `after`
- doesn't mutate input, is idempotent, and never makes tools bigger
- for lossless rules, keeps validation equivalent on your fixtures **and on all 169 real tools** in `bench/snapshots/`

If the equivalence test fails, the report shows the exact instance one schema accepts and the other rejects. That's usually a real bug, not a flaky test.

## Other contributions

- **Tokenizer**: implement the `TokenCounter` protocol in `toolslim/tokenizers/`.
- **Loader**: return `list[ToolDef]` from `toolslim/loaders/`.
- **Benchmark server**: add it to `bench/servers.yaml`, run `python bench/snapshot.py <name>` and `python bench/run_bench.py`, and commit the snapshot and `RESULTS.md`. Never edit `RESULTS.md` by hand.

Labels: `good first issue`, `rule`, `tokenizer`, `loader`, `benchmark`.
