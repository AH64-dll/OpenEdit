# Plan D: Tool System Redesign — 4 Pillars (query, edit, script, render)

## Objective
Consolidate 14 fragmented tools into 4 pillar tools, eliminate the propose-then-commit pattern (dedicated tools return ops, then `run_python` commits them), auto-inject sandbox headers, and add comprehensive tool tests.

## Current state (14 tools → 4 pillars)

| Current tool | Pillar | Notes |
|---|---|---|
| `list_assets` | **query** → `query_project` | Merged into unified query tool |
| `get_pending_notes` | **query** → `query_project` | Merged into unified query tool |
| `get_style_profile` | **query** → `query_project` | Merged into unified query tool |
| `analyze_narrative` | **query** → `query_project` | Merged into unified query tool |
| `search_assets` | **query** → `query_project` | Merged into unified query tool |
| `add_marker` | **edit** → `edit_project` | Merged into unified edit tool |
| `set_pinned_value` | **edit** → `edit_project` | Merged into unified edit tool |
| `run_python` | **script** → `run_script` | Kept as-is (it's the escape hatch) |
| `trigger_render` | **render** → `trigger_render` | Kept as-is (it's already simplified) |
| `generate_visual_for_segment` | **edit** → `edit_project` | As an "operation" type |
| `place_sfx` | **edit** → `edit_project` | As an "operation" type |
| `propose_silence_cuts` | **edit** → `edit_project` | As an "operation" type |
| `select_music` | **edit** → `edit_project` | As an "operation" type |
| `import_asset` | **edit** → `edit_project` | As an "operation" type |

## Files affected
- `open_edit/serve/tool_schemas.py` — complete rewrite (lines 1–457)
- `open_edit/serve/agent.py` — tool dispatch, system prompt (lines 247–280, 311–323, 627–659)
- `open_edit/serve/tool_executor.py` — dispatch logic (lines 1–179)
- `open_edit/serve/pi_bridge.py` — tool routing (lines 75–105)
- `open_edit/agent/tools/` — 13 files to refactor (or keep wrappers)
- `open_edit/serve/llm.py` — system prompt generation
- `open_edit/agent/sandbox_bridge.py` — header auto-injection
- `open_edit/agent/libs.py` — header parsing changes

## The 4 pillar tools

### 1. `query_project` — Read-only project queries
```python
{
    "name": "query_project",
    "description": "Query the project for information. Supports: 'list_assets', 'get_pending_notes', 'get_style_profile', 'analyze_narrative', 'search_assets', and any Python expression evaluated read-only in the sandbox.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "enum": [
                    "list_assets", "get_pending_notes", "get_style_profile",
                    "analyze_narrative", "search_assets"
                ],
                "description": "Which query to run."
            },
            "params": {
                "type": "object",
                "description": "Query-specific parameters. For 'search_assets': {query, kind, limit}. For 'analyze_narrative': {asset_hash}. For 'get_style_profile': {op_type}. For 'get_pending_notes': {summary_only}.",
                "default": {}
            }
        },
        "required": ["query"],
        "additionalProperties": false
    }
}
```
- **Why merge**: 5 read-only tools → 1. Less LLM cognitive load. The tool description can explain all sub-queries.
- **Implementation**: `dispatch_query(query, params)` routes to existing functions in `open_edit.agent.tools`.
- **Result shape**: Always `{"status": "ok", "data": <query-specific>}` or `{"status": "error", "error": "..."}`.

### 2. `edit_project` — All mutations (commit immediately, no propose-then-commit)
```python
{
    "name": "edit_project",
    "description": "Apply an edit operation to the project. Operations are committed immediately — no separate commit step needed. Supported operations: 'add_marker', 'set_pinned_value', 'add_clip', 'remove_clip', 'move_clip', 'trim_clip', 'split_clip', 'add_effect', 'remove_effect', 'set_effect_param', 'add_transition', 'remove_transition', 'set_audio_gain', 'normalize_audio', 'import_asset', 'group_edits'. To generate creative suggestions (SFX, music, visuals, silence cuts), use the 'generate' param instead — those return ops for review without committing.",
    "input_schema": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "description": "The operation to apply. Committed immediately."
            },
            "params": {
                "type": "object",
                "description": "Operation-specific parameters.",
                "default": {}
            },
            "generate": {
                "type": "string",
                "enum": ["sfx", "music", "visual", "silence_cuts"],
                "description": "Instead of an operation, generate creative suggestions for review. The suggestions are returned as a list of ops — review them and then commit via edit_project with operation='apply_generated_ops' and params={ops: [...]}."
            },
            "generate_params": {
                "type": "object",
                "description": "Parameters for the generate mode: {asset_hash, segment_id, template, text, mood, library_path, ...}",
                "default": {}
            }
        },
        "additionalProperties": false
    }
}
```
- **Why merge**: 8 mutation tools + 4 proposal tools → 1. The `generate` param preserves creative suggestion capability. No more propose-then-commit cycle for simple edits.
- **Why keep `generate`**: SFX/music/visual/silence_cuts are genuinely "suggestive" — the LLM should see suggestions before deciding. But now it's one tool with sub-modes, not 4 separate tools.
- **Implementation**: `dispatch_edit(operation, params)` routes to existing functions. `dispatch_generate(kind, params)` routes to the proposal functions.

### 3. `run_script` — Free-form Python escape hatch (unchanged, minimal fix)
```python
{
    "name": "run_script",
    "description": "Run Python in the bwrap+seccomp sandbox for complex multi-step edits. Same as the current run_python but with automatic sandbox header injection. The header is added automatically — you do NOT need to write # ir_api_version: ... by hand.",
    "input_schema": {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python source to execute. The sandbox header is injected automatically."
            },
            "timeout_sec": {
                "type": "integer",
                "description": "Timeout in seconds. Default 30.",
                "default": 30
            },
            "parent_op_id": {
                "type": "string",
                "description": "Optional parent op ID for grouping."
            }
        },
        "required": ["code"],
        "additionalProperties": false
    }
}
```
- **Changes from `run_python`**: Renamed to `run_script` (cleaner name). Header is auto-injected. No `mem_mb`, `project_id`, `originating_note_id` in schema (those are injected server-side).
- **Auto-injection**: `sandbox_bridge.py` prepends the header before calling the sandbox binary. This eliminates the #1 cause of sandbox rejection errors.

### 4. `trigger_render` — Render trigger (unchanged)
Kept as-is from current tool_schemas.py lines 318-342. Already well-designed.

---

## Sub-agent breakdown

### Agent D1: Implement `query_project` + `edit_project` Tools
**Scope:** Write the new unified tools. Keep backward-compatible wrappers so existing code doesn't break. Deprecate old individual schemas.

**Specific tasks:**
1. Create `open_edit/serve/pillar_tools.py` with:
   - `dispatch_query(query: str, params: dict, project_path: Path) -> dict`
   - `dispatch_edit(operation: str, params: dict, project_path: Path) -> dict`
   - `dispatch_generate(kind: str, params: dict, project_path: Path) -> dict`
   - Each function imports and calls the existing individual tool functions
   - `dispatch_query`: routes to `list_assets`, `get_pending_notes`, `get_style_profile`, `analyze_narrative`, `search_assets`
   - `dispatch_edit`: routes to `add_marker`, `set_pinned_value`, `import_asset`, plus IR ops (add_clip, remove_clip, etc.) via `make_ir()`
   - `dispatch_generate`: routes to `place_sfx`, `select_music`, `generate_visual_for_segment`, `propose_silence_cuts`
2. Add `apply_generated_ops` operation to `dispatch_edit` that takes a list of op dicts and commits them
3. Add error handling: unknown query/operation/generate kind returns `{"status": "error", "error": "unknown <kind>: <value>"}`
4. Update `tool_schemas.py` to REPLACE the 14 old schemas with the 4 new pillar schemas
5. Keep old individual tool functions working (they're called by the dispatcher) but remove them from `TOOL_SCHEMAS`
6. Update `TOOL_USAGE_GUIDE` to reference only the 4 pillar tools
7. Add backward-compatible aliases:
   - `TOOL_BY_NAME` can still resolve old names -> map to new pillar dispatcher
   - Or just remove old names and let the LLM discover the new ones via the schema
8. Update `TOOL_BY_NAME` lookup to handle both old and new names for a transition period

**Verification:**
- `python -c "from open_edit.serve.tool_schemas import TOOL_SCHEMAS; assert len(TOOL_SCHEMAS) == 4"`
- `python -c "from open_edit.serve.pillar_tools import dispatch_query, dispatch_edit; print('ok')"`
- All existing tool functions still importable from `open_edit.agent.tools`
- `dispatch_query('list_assets', {}, '/path/to/project')` returns assets
- `dispatch_edit('add_marker', {'t_start': 0, 'text': 'test'}, '/path/to/project')` creates a marker

---

### Agent D2: Auto-Inject Sandbox Headers + Simplify `run_script`
**Scope:** Remove the manual header requirement from `run_script` (renamed from `run_python`). Auto-inject from server-side. Eliminate the #1 source of sandbox errors.

**Specific tasks:**
1. Modify `run_free_form` in `sandbox_bridge.py` to auto-inject the header:
   - Check if the first line matches `# ir_api_version:` pattern
   - If yes: keep as-is (backward compat)
   - If no: prepend `# ir_api_version: 0.1; libs: {}\n` before the code
   - This makes the header invisible to the LLM — they just write Python
2. Update `pyagent_run_python.py` to NOT require `project_id` in args (already injected by bridge)
3. Rename `run_python` function to `run_script` in tools with a `run_python` alias for backward compat:
   - `open_edit/agent/tools/pyagent_run_python.py` → add `run_script = run_python` alias
4. Update `_helpers.py` `make_ir` to accept optional `parent_op_id` instead of requiring it via `args`
5. Update `tool_executor.py` to map `run_python` → `run_script` if the old name is called
6. Update `agent.py` system prompt TOOL_USAGE_GUIDE to reference `run_script` instead of `run_python`
7. Update sandbox header parsing in `open_edit/agent/libs.py`:
   - Keep the `re.MULTILINE` + `.search()` approach (it's correct)  
   - But also add a pre-parse step that auto-injects the header if missing
   - This means the sandbox binary NEVER receives code without a header
8. Add tests: `tests/test_pillar_tools.py` with:
   - `run_script` called with and without header
   - Both work (header injected server-side if missing)
   - `run_python` name still works (backward compat)

**Verification:**
- `python -c "from open_edit.agent.tools import run_script; assert callable(run_script)"`
- `python -c "from open_edit.agent.tools import run_python; assert callable(run_python)"`
- Running `run_script` with `code="ir.add_clip(...)"` works without manual header
- Running `run_script` with `code="# ir_api_version: 0.1; libs: {}\nir.add_clip(...)"` also works (backward compat)
- Sandbox header auto-injection test: verify header is prepended correctly

---

### Agent D3: Update Agent Loop + System Prompt + Pi Bridge + Tests
**Scope:** Update all dispatch paths (agent loop, pi bridge) to handle the 4 new pillar tools. Update the system prompt to reference only 4 tools. Add comprehensive tests.

**Specific tasks:**
1. Update `tool_executor.py`:
   - Add `query_project`, `edit_project`, `run_script` to the dispatch
   - Route `query_project` → `pillar_tools.dispatch_query`
   - Route `edit_project` → `pillar_tools.dispatch_edit`
   - Route `run_script` → `open_edit.agent.tools.run_script`
   - Keep `trigger_render` as-is
   - Add backward compat mapping: old names → new dispatchers
2. Update `pi_bridge.py`:
   - Add routing for new tool names in `_run_tool`
   - Remove `project_id` injection hack (line 90-100) — the pillar tools handle it
   - Actually, keep `project_id` injection for backward compat but simplify
3. Update `_build_system_prompt` in `agent.py`:
   - Replace `TOOL_USAGE_GUIDE` with new guide referencing only 4 tools
   - Tool summary lists 4 lines instead of 14
   - Remove `IR_MODEL_SUMMARY` from system prompt (moved into `run_script` description)
   - Or keep it but make it shorter
4. Update `_execute_tool` in `agent.py` to handle the 4 new tool names
5. Create `tests/test_pillar_integration.py`:
   - `query_project` with all 5 query modes via the agent loop
   - `edit_project` with 5+ operation types
   - `run_script` executes Python in sandbox
   - `trigger_render` renders (mock the binary)
   - Full turn with all 4 tools
   - Backward compatibility: old tool names still work via mapping
6. Create `tests/test_pillar_schemas.py`:
   - All 4 schemas have `additionalProperties: false`
   - Each `query` enum value is valid
   - Each `operation` enum value is valid (for `edit_project`)
   - Each `generate` enum value is valid
   - `run_script` has correct fields

**Verification:**
- `pytest tests/ -v` passes (all old + new tests)
- `run_agent_turn` with a query → dispatches to `query_project`
- `run_agent_turn` with an edit → dispatches to `edit_project`
- `pi_bridge` handles both old and new tool names
- System prompt lists exactly 4 tools
- All 14 old tool names still resolve (backward compat map)

---

## Integration verification (all 3 agents done)
1. Full test suite: `pytest tests/ -v`
2. Manual test: start server, send "list all assets" → LLM calls `query_project` with `query: "list_assets"` → returns assets
3. Manual test: send "add a marker at 5s" → LLM calls `edit_project` with `operation: "add_marker"` → marker created
4. Manual test: send "render it" → LLM calls `trigger_render` → render starts
5. Manual test: send "add a fade out to first clip" → LLM calls `run_script` → Python executes in sandbox
6. System prompt under 500 lines (currently ~600+ lines with all tool schemas + usage guide)
7. No regression in existing functionality
