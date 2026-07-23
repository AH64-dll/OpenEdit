# Plan A: Tool Schema Audit + Fix

## Objective
Fix all 7 schema/implementation mismatches in `tool_schemas.py`, add rigorous validation, standardize error shapes, and add dedicated tool tests.

## Files affected
- `open_edit/serve/tool_schemas.py` — 14 schemas, lines 1–457
- `open_edit/serve/pi_bridge.py` — `project_id` injection hack, lines 75–105
- `open_edit/serve/tool_executor.py` — dispatch layer, lines 1–179
- `open_edit/agent/tools/pyagent_*.py` — 13 tool implementations
- `open_edit/agent/tools/_helpers.py` — shared helpers

## Schema mismatches (7 tools)
| Tool | Schema says | Implementation expects |
|------|------------|----------------------|
| `add_marker` | `t_start`, `t_end`(opt), `text` | + `project_id` (required) |
| `analyze_narrative` | `asset_hash`, `granularity` | `asset_hash`, `use_llm` (bool, opt) — no `granularity` |
| `generate_visual_for_segment` | `segment_id`, `template`, `text`, `duration_s` | `asset_hash`, `beat_type`, `template`, `params`(dict), `project_id` |
| `get_pending_notes` | `offset` | `project_id`, `summary_only`(bool, opt) — no `offset` |
| `place_sfx` | `asset_hash`, `mood` | `asset_hash`, `library_path`(opt), `music_downbeats`(opt) — no `mood` |
| `propose_silence_cuts` | `min_duration_s`, `threshold_db` | `threshold_ms`(int, opt) — float seconds → ms mismatch |
| `select_music` | `asset_hash`, `mood`, `bpm_target` | `asset_hash`, `library_path`(opt) — no `mood`/`bpm` |
| `run_python` | `code`, `timeout_s` | `code`, `timeout_sec`(int), `mem_mb`, `project_id`, `parent_op_id`, `originating_note_id` |

---

## Sub-agent breakdown

### Agent A1: Schema Canonicalization
**Scope:** Rewrite all 14 schemas in `tool_schemas.py` to match actual tool signatures. Add `additionalProperties: false` to every schema. Add `project_id` as an injected field (documented as `x-injected: true` but still required in schema for the pi bridge — except for `search_assets` which is project-agnostic).

**Specific tasks:**
1. Update `add_marker` schema: add `project_id: string`, `additionalProperties: false`
2. Update `analyze_narrative` schema: replace `granularity` enum with `use_llm: boolean` (default false), add `additionalProperties: false`
3. Update `generate_visual_for_segment` schema: replace all fields with `asset_hash`, `beat_type`, `template`, `params`(object), `project_id`; add `additionalProperties: false`
4. Update `get_pending_notes` schema: replace `offset` with `summary_only: boolean` (default false), add `additionalProperties: false`
5. Update `place_sfx` schema: replace `mood` with `library_path: string`(opt), `music_downbeats: array(number)`(opt), add `additionalProperties: false`
6. Update `propose_silence_cuts` schema: replace `min_duration_s`/`threshold_db` with `threshold_ms: integer`(opt, default 400), add `additionalProperties: false`
7. Update `select_music` schema: replace `mood`/`bpm_target` with `library_path: string`(opt), add `additionalProperties: false`
8. Update `run_python` schema: add `timeout_sec: integer` (default 30, rename from `timeout_s`), `mem_mb: integer`(opt), `project_id: string`, `parent_op_id: string`(opt), `originating_note_id: string`(opt); add `additionalProperties: false`
9. Update `import_asset` schema: add `project_id: string`, `additionalProperties: false`
10. Ensure `trigger_render`, `search_assets`, `list_assets`, `set_pinned_value`, `get_style_profile` all have `additionalProperties: false` and no missing fields

**Verification:**
- Run `python -c "from open_edit.serve.tool_schemas import TOOL_SCHEMAS; assert all('additionalProperties' in t['input_schema'] for t in TOOL_SCHEMAS)"`
- Every schema has `additionalProperties: false`
- No schema references fields that don't exist in the implementation

**Output for next agent:** Updated `tool_schemas.py`

---

### Agent A2: Schema Validation Layer
**Scope:** Add a validation layer that validates tool arguments against schemas before dispatch. Catch mismatches early with clear error messages instead of cryptic `KeyError`s from inside tool implementations.

**Specific tasks:**
1. Create `open_edit/serve/schema_validator.py` with:
   - `validate_tool_args(name: str, args: dict) -> None` that raises `SchemaValidationError` on mismatch
   - Uses `jsonschema` (check if it's a dependency; if not, hand-roll a fast check since schemas are simple)
   - Validates: required fields present, no extra fields (via `additionalProperties: false`), types match (number/int/string/bool)
   - Error shape: `{"status": "error", "error": "schema_validation_failed", "detail": {"tool": name, "field": "...", "expected": "...", "got": "..."}}`
2. Add `SchemaValidationError` exception class
3. Wire `validate_tool_args` into `tool_executor.py` `execute_tool()` function (line ~45) before calling the tool function
4. Wire into `pi_bridge.py` `_run_tool()` function (line ~102) before calling the tool
5. Add tests: `tests/test_schema_validator.py` with:
   - Valid args pass through
   - Missing required field raises
   - Extra field (with `additionalProperties: false`) raises
   - Type mismatch raises
   - All 14 tools validated

**Verification:**
- `pytest tests/test_schema_validator.py -v` passes
- `python -c "from open_edit.serve.schema_validator import validate_tool_args; validate_tool_args('list_assets', {}); print('ok')"`
- `python -c "from open_edit.serve.schema_validator import validate_tool_args; validate_tool_args('add_marker', {'t_start': 0, 'text': ''}); print('ok')"` fails with clear error about missing `project_id`

**Output for next agent:** `schema_validator.py`, updated `tool_executor.py`, updated `pi_bridge.py`, `test_schema_validator.py`

---

### Agent A3: Tool Implementation Audit + Tests
**Scope:** Audit all 14 tool implementations for consistency, add dedicated tests for each tool. Fix any bugs found during audit.

**Specific tasks:**
1. Read every `pyagent_*.py` implementation and verify:
   - Return shape is consistent (all return `dict` with `status` key or similar)
   - Error paths return `{"status": "error", "error": "..."}` (never raise uncaught exceptions to the caller)
   - All required args are accessed with `[]` (not `.get()`) so validation catches misses
   - Optional args use `.get()` with sensible defaults
2. For tools that expect `project_id` but don't use it (marked as `x-injected: true`), add docstring noting it's injected by the bridge
3. Fix any bugs found (document each fix)
4. Create `tests/test_tools.py` with at least one test per tool:
   - Test with valid args (mock DB/stores)
   - Test with missing required args (expect `KeyError` or validated error)
   - Test error paths (missing asset, empty DB, etc.)
   - `import_asset`: test with `result_id` path and `source_url` path
   - `run_python`: test with valid code and timeout
   - `trigger_render`: test all 3 modes, test failure paths
5. Verify `tool_executor.py` handles all tool names correctly (including `trigger_render` routing)

**Verification:**
- `pytest tests/test_tools.py -v` passes
- Every tool has at least 2 test cases (happy path + error path)
- All `except` clauses in tools return structured error dicts, don't re-raise

**Output for next agent:** Fixed tool implementations (if any), `test_tools.py`

---

## Integration verification (all 3 agents done)
1. Full test suite: `pytest tests/ -v`
2. Manual schema check: `python -c "from open_edit.serve.tool_schemas import TOOL_SCHEMAS; print(len(TOOL_SCHEMAS), 'schemas OK')"`
3. Pi bridge smoke test: start server, send tool call via WebSocket, verify result
4. Agent turn smoke test: send user message, verify tool call executes and result comes back
