# OpenEdit Code Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure OpenEdit from a tangled monolith (4,190 graph nodes, god files up to 1,521 lines, broken layering, red test suite) into a clean layered architecture with one responsibility per module, one validator, one dispatcher, and a green test suite — making it debuggable by humans and reliable for agents.

**Architecture:** Enforce one-directional layering: `cli` (thin root) → `serve` (web shell) + `mcp` (transport) → `kernel` (shared core) → `agent` (sandbox + tools) → `ir` (pure domain) + `storage` (SQLite) + `render`/`qc`/`style` (engines). Two hard rules: **kernel never imports serve**; **ir never imports agent/storage/serve**. Work proceeds in 8 phases: P0 fix runtime bugs → P1 delete dead code → P2 fix layering → P3 unify dispatcher/validators → P4 standardize tool contract → P5 split god files → P6 dedupe shared infrastructure → P7 wire orphaned features.

**Tech Stack:** Python 3.14, Pydantic v2, FastAPI, SQLite, pytest (existing). No new dependencies.

## Global Constraints

- Layering rules (enforced by `tests/test_layering.py` from Task 2.5 onward):
  - `grep -rn "open_edit.serve" open_edit/kernel/ open_edit/mcp/ open_edit/ir/` → must be empty.
  - `grep -rn "open_edit.agent\|open_edit.storage\|open_edit.serve" open_edit/ir/` → must be empty.
  - `grep -rn "ir.apply\|ir.api\|ir.factory" open_edit/storage/` → must be empty (storage may import `ir.types`/`ir.validate`/`ir.ids`/`ir.hash` only — user-approved amendment 2026-07-31: `ir.hash` is pure and needed by `storage/timeline_cache.py`).
- Test command everywhere: `python3 -m pytest tests/ -x -q`. After each task the suite must be green (`pytest tests/` full run, no skips of pre-existing tests).
- No new third-party dependencies. `pyproject.toml` is not modified except `cli.py --version` reading metadata (Task 1.11).
- Keep all agent-facing tool *names* and *argument keys* stable until Task 4.x completes; external contracts are free to change after this plan (user-approved), but each change must be accompanied by its schema/skill update in the same commit.
- Commit message style: `refactor(area): short description` (repo uses conventional-ish commits, see `git log`).
- Do not run formatters/linters on files you are not touching in the task.
- After every commit: `git status` must show a clean tree.

---

## Phase 0 — Stop the Bleeding (P0 runtime bugs)

### Task 0.1: Fix broken pi_bridge imports

**Files:**
- Modify: `open_edit/serve/pi_bridge.py:114,121,126`
- Test: `tests/test_serve_pi_bridge.py`

**Interfaces:**
- Consumes: `open_edit.kernel.schema_validator.validate_or_error` (already imported at `pi_bridge.py:36`), `open_edit.kernel.pillar_tools.dispatch_query/dispatch_edit/dispatch_generate`
- Produces: working `_run_agent_tool` for the TS pi-extension subprocess path

- [ ] **Step 1: Confirm the failure**

Run: `python3 -m pytest tests/test_serve_pi_bridge.py -x -q`
Expected: `FAILED tests/test_serve_pi_bridge.py::test_bridge_add_marker_round_trip` with `ModuleNotFoundError: No module named 'open_edit.serve.schema_validator'`

- [ ] **Step 2: Delete the broken redundant import**

In `open_edit/serve/pi_bridge.py`, delete line 114 exactly:

```python
    from .schema_validator import validate_or_error as _validate_or_error
```

(line 36 already provides `validate_or_error` from `open_edit.kernel.schema_validator`; do not add a second import).

- [ ] **Step 3: Repoint pillar imports to kernel**

Replace lines 121 and 126:

```python
        from .pillar_tools import dispatch_query
```
```python
        from .pillar_tools import dispatch_edit, dispatch_generate
```

with:

```python
        from open_edit.kernel.pillar_tools import dispatch_query
```
```python
        from open_edit.kernel.pillar_tools import dispatch_edit, dispatch_generate
```

- [ ] **Step 4: Run the pi-bridge tests**

Run: `python3 -m pytest tests/test_serve_pi_bridge.py -q`
Expected: all PASS.

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest tests/ -q`
Expected: only pre-existing failures unrelated to pi_bridge (record them; they are fixed in Task 0.4 or later tasks).

- [ ] **Step 6: Commit**

```bash
git add open_edit/serve/pi_bridge.py tests/test_serve_pi_bridge.py
git commit -m "fix(serve): repoint pi_bridge imports to kernel after monorepo flatten"
```

### Task 0.2: Fix broken edit_graph_service import in app.py

**Files:**
- Modify: `open_edit/serve/app.py:910`
- Test: `tests/test_serve_edit_graph_api.py`

**Interfaces:**
- Consumes: `open_edit.kernel.edit_graph_service.apply_command`, `EditGraphCommandError`, `open_edit.storage.edit_graph.GraphRevisionConflict`
- Produces: working `POST /api/projects/{project_id}/ops`

- [ ] **Step 1: Confirm the failure**

Run: `python3 -c "from open_edit.serve.app import app"` — if import is too heavy, run:
`python3 -c "import open_edit.serve.edit_graph_service"` 
Expected: `ModuleNotFoundError: No module named 'open_edit.serve.edit_graph_service'`

- [ ] **Step 2: Repoint the import**

In `open_edit/serve/app.py:910`, replace:

```python
    from .edit_graph_service import EditGraphCommandError, apply_command
```

with:

```python
    from open_edit.kernel.edit_graph_service import EditGraphCommandError, apply_command
```

- [ ] **Step 3: Write a regression test for POST /ops**

Append to `tests/test_serve_edit_graph_api.py` (follow existing fixtures in that file — they already build a project via `TestClient`):

```python
def test_post_ops_endpoint_applies_timeline_command(client, tmp_project):
    project_id = tmp_project["id"]
    resp = client.post(
        f"/api/projects/{project_id}/ops",
        json={"command": "add_clip", "params": {"asset_hash": "h", "track_index": 0, "start_sec": 0.0, "duration_sec": 5.0}},
    )
    assert resp.status_code in (200, 201, 400), resp.text
```

Match the exact request model (`TimelineCommandRequest`) fields by reading `serve/app.py` around the endpoint; if the model requires different params, adjust the payload to the schema — the assertion that matters is **not 500**.

- [ ] **Step 4: Run the regression test**

Run: `python3 -m pytest tests/test_serve_edit_graph_api.py -q`
Expected: PASS (previously the route 500'd).

- [ ] **Step 5: Commit**

```bash
git add open_edit/serve/app.py tests/test_serve_edit_graph_api.py
git commit -m "fix(serve): repoint ops route to kernel edit_graph_service"
```

### Task 0.3: Fix RenderSnapshots dead fallback in projects.py

**Files:**
- Modify: `open_edit/serve/projects.py:513-522`
- Test: `tests/test_serve_projects.py`

**Interfaces:**
- Consumes: `open_edit.storage.render_snapshots.RenderSnapshotStore`
- Produces: working render-snapshot listing in the projects endpoint

- [ ] **Step 1: Fix the import and probe**

In `open_edit/serve/projects.py:513-522`, replace the broken block. Current code (verify before editing):

```python
    try:
        from open_edit.storage.render_snapshots import RenderSnapshots

        snapp = RenderSnapshots(...)
        ...
    except Exception:
        pass
```

Replace with:

```python
    from open_edit.storage.render_snapshots import RenderSnapshotStore

    try:
        snapshots = RenderSnapshotStore(db_path).list_for_project(project_id)
    except (ImportError, sqlite3.Error, OSError):
        snapshots = []
```

Read `storage/render_snapshots.py` first and use its actual constructor signature and list method name (it may be `list_all` or similar — check the source, do not guess). Remove the `hasattr` probing loop entirely.

- [ ] **Step 2: Delete `_render_row_to_dict`**

If `_render_row_to_dict` in `serve/projects.py` exists solely for the snapshot fallback (check callers with grep; delete only if unreferenced after Step 1), remove it.

- [ ] **Step 3: Add a regression test**

In `tests/test_serve_projects.py` add:

```python
def test_list_renders_snapshot_branch_no_crash(client, tmp_project):
    resp = client.get(f"/api/projects/{tmp_project['id']}/renders")
    assert resp.status_code == 200
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_serve_projects.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add open_edit/serve/projects.py tests/test_serve_projects.py
git commit -m "fix(serve): wire render snapshot listing to RenderSnapshotStore"
```

### Task 0.4: Baseline green test suite

**Files:**
- Test: whole `tests/` directory

- [ ] **Step 1: Run the full suite**

Run: `python3 -m pytest tests/ -q 2>&1 | tail -30`
Expected: 0 failures. For any remaining failure, fix it in this task (they are all Phase-0 fallout — broken imports, wrong class names). Do not skip or mark xfail without writing a comment explaining why.

- [ ] **Step 1a: Guard the strace observation tests (user-approved decision 2026-07-31)**

`tests/test_sandbox_observations.py` fails because `tests/testdata/sandbox/observations/` (strace fixtures) was never committed. Add a module-level skipif to that file:

```python
_OBS_DIR = Path(__file__).parent.parent / "sandbox" / "observations"
pytestmark = pytest.mark.skipif(
    not _OBS_DIR.is_dir(), reason="strace observation fixtures not present in repo"
)
```

(Adjust to the file's actual `OBS_DIR` definition.) The 4 strace tests then skip on any machine without the fixture data.

- [ ] **Step 2: Commit any remaining fixes**

```bash
git add -A
git commit -m "test: restore green test suite after P0 fixes"
```

---

## Phase 1 — Delete Dead Code

### Task 1.1: Delete `serve/_cli_patch.py`

**Files:**
- Delete: `open_edit/serve/_cli_patch.py`
- Test: `tests/test_cli_adapter.py`

**Interfaces:**
- Consumes: nothing (file has zero importers — verified by grep)
- Produces: nothing

- [ ] **Step 1: Verify no importers**

Run: `grep -rn "_cli_patch" --include="*.py" open_edit/ tests/ | grep -v __pycache__`
Expected: no matches outside the file itself.

- [ ] **Step 2: Delete the file**

```bash
git rm open_edit/serve/_cli_patch.py
```

- [ ] **Step 3: Run tests**

Run: `python3 -m pytest tests/test_cli_adapter.py tests/test_cli.py -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git commit -m "chore(serve): delete vestigial _cli_patch.py"
```

### Task 1.2: Delete the three serve shims

**Files:**
- Delete: `open_edit/serve/tool_executor.py`, `open_edit/serve/tool_schemas.py`, `open_edit/serve/render_service.py`
- Modify: `open_edit/serve/agent.py:41,380`, `open_edit/serve/app.py:574`
- Test: `tests/test_serve_module_structure.py` (verify what it asserts first — it may assert the shims exist; update it)

**Interfaces:**
- Consumes: `open_edit.kernel.tool_executor` (`execute_tool`, `execute_trigger_render`), `open_edit.kernel.tool_schemas` (`TOOL_SCHEMAS`, `TOOL_BY_NAME`), `open_edit.kernel.render_service.RenderEnqueueError`
- Produces: no shims

- [ ] **Step 1: Read the shim contents to know the exact re-exported names**

Run: `cat open_edit/serve/tool_executor.py open_edit/serve/tool_schemas.py open_edit/serve/render_service.py`

- [ ] **Step 2: Repoint importers to kernel**

In `open_edit/serve/agent.py:41` change `from .tool_schemas import (...)` → `from open_edit.kernel.tool_schemas import (...)`; at `:380` change `from .tool_executor import (...)` → `from open_edit.kernel.tool_executor import (...)`.

In `open_edit/serve/app.py:574` change `from .render_service import RenderEnqueueError` → `from open_edit.kernel.render_service import RenderEnqueueError`.

- [ ] **Step 3: Delete the shims**

```bash
git rm open_edit/serve/tool_executor.py open_edit/serve/tool_schemas.py open_edit/serve/render_service.py
```

- [ ] **Step 4: Update module-structure tests**

Run: `python3 -m pytest tests/test_serve_module_structure.py -q`
If a test asserts the shims exist, update it to assert they do NOT exist and that `open_edit.kernel.*` is the source.

- [ ] **Step 5: Run the serve tests**

Run: `python3 -m pytest tests/test_serve_agent.py tests/test_serve_errors.py tests/test_serve_render_jobs.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(serve): delete kernel shims, import kernel directly"
```

### Task 1.3: Migrate pydantic_compat users and delete the shim

**Files:**
- Delete: `open_edit/pydantic_compat.py`
- Modify: `open_edit/agent/sandbox_bridge.py:67`, `tests/test_render/test_golden_fixtures.py:8`
- Test: `tests/test_render/test_golden_fixtures.py`

**Interfaces:**
- Consumes: `pydantic.TypeAdapter` (v2, already pinned)
- Produces: no shim

- [ ] **Step 1: Migrate both importers**

`sandbox_bridge.py:67` and `tests/test_render/test_golden_fixtures.py:8`: replace `from open_edit.pydantic_compat import TypeAdapter` with `from pydantic import TypeAdapter`.

- [ ] **Step 2: Delete the shim**

```bash
git rm open_edit/pydantic_compat.py
```

- [ ] **Step 3: Run tests**

Run: `python3 -m pytest tests/test_render/test_golden_fixtures.py tests/test_sandbox_bridge.py -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: delete pydantic_compat shim"
```

### Task 1.4: Delete the legacy render-job registry in app.py

**Files:**
- Modify: `open_edit/serve/app.py:162-264` (delete `_RENDER_JOBS`, `_prune_render_jobs`, `_register_job`, `_RENDER_TASKS`, `_run_render_job`)
- Test: `tests/test_serve_render_jobs.py`

**Interfaces:**
- Consumes: `open_edit.kernel.render_service.DEFAULT_RENDER_SERVICE` (already used elsewhere in app.py)
- Produces: nothing

- [ ] **Step 1: Read the deletion range and its test**

Run: `sed -n '160,270p' open_edit/serve/app.py` and `sed -n '1,200p' tests/test_serve_render_jobs.py`
Confirm the comment at app.py:214-216 ("kept only for tests").

- [ ] **Step 2: Delete the block and fix the route handlers**

Delete the registry block. Find the render-trigger route(s) that used `_register_job` and rewrite them to use `DEFAULT_RENDER_SERVICE.enqueue(...)` and its `get_job`/`public_job` API. Read `kernel/render_service.py` for the exact method names (there is a `public_job` helper — use it).

- [ ] **Step 3: Port the tests**

Rewrite `tests/test_serve_render_jobs.py` to drive `POST /api/projects/{id}/render` (or whatever the trigger route is) and assert against the job-DB state instead of the deleted in-memory registry. Keep the same assertions the old tests made about job lifecycle (created → running → completed) but through `RenderService` methods.

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_serve_render_jobs.py tests/test_serve_agent.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(serve): drop legacy in-memory render job registry"
```

### Task 1.5: Delete `ir/commutativity.py`

**Files:**
- Delete: `open_edit/ir/commutativity.py`, `tests/test_ir/test_commutativity.py`

**Interfaces:**
- Consumes: nothing (verified: only its own test imports `can_swap`; `EditGraphStore.reorder` never consults it)
- Produces: nothing

- [ ] **Step 1: Verify no importers**

Run: `grep -rn "commutativity\|can_swap" --include="*.py" open_edit/ | grep -v __pycache__`
Expected: no matches.

- [ ] **Step 2: Delete**

```bash
git rm open_edit/ir/commutativity.py tests/test_ir/test_commutativity.py
```

- [ ] **Step 3: Run IR tests**

Run: `python3 -m pytest tests/test_ir/ -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git commit -m "chore(ir): delete unused commutativity module"
```

### Task 1.6: Delete orphaned render modules `validators.py` and `ingest.py`

**Files:**
- Delete: `open_edit/render/validators.py`, `open_edit/render/ingest.py`
- Delete: `tests/test_render/test_validators.py`, `tests/test_render/test_ingest.py`
- Modify: `open_edit/qc/gate.py:34` (comment referencing `validate_mlt_loads` — update it)

**Interfaces:**
- Consumes: nothing (zero production callers — verified)
- Produces: nothing

- [ ] **Step 1: Verify no production importers**

Run: `grep -rn "validate_mlt_loads\|ingest_mlt_xml" --include="*.py" open_edit/ | grep -v __pycache__`
Expected: no matches.

- [ ] **Step 2: Delete**

```bash
git rm open_edit/render/validators.py open_edit/render/ingest.py tests/test_render/test_validators.py tests/test_render/test_ingest.py
```

Update the `qc/gate.py:34` comment that explains why `validate_mlt_loads` is not called — delete the reference.

- [ ] **Step 3: Run render + qc tests**

Run: `python3 -m pytest tests/test_render/ tests/test_qc/ -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore(render): delete orphaned validators and ingest modules"
```

### Task 1.7: Trim `style/` to its live surface

**Files:**
- Delete: `open_edit/style/taste_events.py`
- Modify: `open_edit/style/aggregate.py` (delete `rollup`, `check_rollup_trigger`, `record_taste_event`-style helpers; keep `set_pinned`, `get_pinned`-related live functions), `open_edit/style/__init__.py`, `open_edit/style/retrieve.py` (keep `get_slice`)
- Test: `tests/test_style/` (delete tests for deleted functions; keep those for `set_pinned`/`get_slice`)

**Interfaces:**
- Consumes: `open_edit.storage.config` (for profile JSON) — verify current imports before editing
- Produces: `open_edit.style.aggregate.set_pinned`, `open_edit.style.retrieve.get_slice` (unchanged signatures — live consumers: `pyagent_set_pinned_value`, `style_inject`, `get_style_profile` tool)

- [ ] **Step 1: Read the style package**

Run: `cat open_edit/style/__init__.py open_edit/style/aggregate.py open_edit/style/retrieve.py`
Identify every function with zero production callers (grep each name under `open_edit/` excluding tests).

- [ ] **Step 2: Delete `taste_events.py` and dead aggregate functions**

```bash
git rm open_edit/style/taste_events.py
```

In `aggregate.py`, delete `rollup`, `check_rollup_trigger`, and any `append`-feeding helpers (they were verified dead: no production callers). Keep `set_pinned` and everything `retrieve.get_slice` reads. Update `__init__.py` exports.

- [ ] **Step 3: Prune tests**

Delete style tests covering deleted functions; run the rest:

Run: `python3 -m pytest tests/test_style/ -q`
Expected: PASS.

- [ ] **Step 4: Run agent tool tests that touch style**

Run: `python3 -m pytest tests/test_tools.py tests/test_pillar_integration.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(style): trim to live pinned+slice surface"
```

### Task 1.8: Delete production-unused functions

**Files:**
- Modify: `open_edit/serve/visual_verify.py` (delete `log_event` at :441, `project_state_hash` at :316, `build_no_change_tool_result` at :270, `generate_waveform_inspection_image` at :512 — verified test-only), `open_edit/serve/cost.py` (delete `parse_pi_session_usage`), `open_edit/serve/serve_env.py` (delete `get_context_budget_config` at :69), `open_edit/serve/llm.py` (delete `_pi_model` at :406), `open_edit/serve/pi_bridge.py` (delete `_make_should_cancel` at :163)
- Test: `tests/test_visual_verify.py`, `tests/test_visual_verify_waveform.py`, `tests/test_serve_cost.py`, `tests/test_serve_llm_usage.py`, `tests/test_serve_pi_bridge.py`

**Interfaces:**
- Consumes: nothing
- Produces: nothing

- [ ] **Step 1: For each target, verify zero production callers**

For each of the 6 functions run e.g. `grep -rn "log_event\|project_state_hash\|build_no_change_tool_result\|generate_waveform_inspection_image\|parse_pi_session_usage\b\|get_context_budget_config\|_pi_model\|_make_should_cancel" --include="*.py" open_edit/ | grep -v __pycache__` and confirm matches are only definitions and tests.

- [ ] **Step 2: Delete the functions**

Delete each; if a test imports the deleted function, move the test into the test file as a local helper (do not keep production exports).

- [ ] **Step 3: Run affected tests**

Run: `python3 -m pytest tests/test_visual_verify.py tests/test_visual_verify_waveform.py tests/test_serve_cost.py tests/test_serve_llm_usage.py tests/test_serve_pi_bridge.py -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore(serve): delete production-unused helper functions"
```

### Task 1.9: Delete dead kernel→serve imports

**Files:**
- Modify: `open_edit/kernel/tool_executor.py:42,44`
- Test: `tests/test_tool_executor.py`

**Interfaces:**
- Consumes: nothing
- Produces: nothing

- [ ] **Step 1: Verify the imports are dead**

Read `open_edit/kernel/tool_executor.py`. Confirm `_probe_duration` and `RENDER_TIMEOUT_S` appear only in the imports (lines 42, 44), never used in the body.

- [ ] **Step 2: Delete both import lines**

```python
from open_edit.serve.pi_bridge import _probe_duration
from open_edit.serve.serve_env import RENDER_TIMEOUT_S
```

- [ ] **Step 3: Run tests**

Run: `python3 -m pytest tests/test_tool_executor.py tests/test_mcp_server.py -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add open_edit/kernel/tool_executor.py
git commit -m "chore(kernel): drop dead serve imports from tool_executor"
```

### Task 1.10: Delete `_ReadBackBuffer`, stale docstrings, orphaned skill

**Files:**
- Modify: `open_edit/agent/tools/_helpers.py:34-38` (delete `_ReadBackBuffer`), `open_edit/agent/tools/__init__.py` (rewrite stale "phase3_pyagent_core" docstring), `open_edit/agent/tools/pyagent_list_assets.py:3-4` (rewrite stale docstring), `open_edit/serve/__init__.py` (rewrite stale docstring)
- Delete: `skills/REVIEW.md` (verified absent from `mcp/skills.py` `SKILL_FILES` — orphaned)
- Test: `tests/test_tools.py`

- [ ] **Step 1: Delete `_ReadBackBuffer`**

Remove the class; verify with `grep -rn "_ReadBackBuffer" --include="*.py" open_edit/ tests/` that nothing else references it.

- [ ] **Step 2: Rewrite the three stale docstrings**

`tools/__init__.py`: replace the "32 repointed wrappers still live in phase3_pyagent_core" text with the actual description (this package is the registry of agent tools; 19 tools re-exported; `pyagent_timeline_ops` functions reachable via `kernel.pillar_tools`).
`pyagent_list_assets.py`: remove the "phantom list_assets tool" text.
`serve/__init__.py`: describe the actual layout (web shell over `open_edit.kernel`).

- [ ] **Step 3: Delete orphaned skill**

```bash
git rm skills/REVIEW.md
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_tools.py tests/test_mcp_server.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: remove stale docstrings, dead helper, orphaned skill"
```

### Task 1.11: Fix `cli.py` version string

**Files:**
- Modify: `open_edit/cli.py:517`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Read the current print**

Run: `sed -n '510,525p' open_edit/cli.py`

- [ ] **Step 2: Replace hard-coded version**

Replace `print("open_edit 0.1.0")` (or similar) with:

```python
from importlib import metadata

def _version() -> str:
    try:
        return metadata.version("open-edit")
    except metadata.PackageNotFoundError:
        return "0.0.0"
```

(Use the distribution name from `pyproject.toml` — check `[project] name =` first; if it is `open-edit`, use that string.)

- [ ] **Step 3: Add/update a test**

In `tests/test_cli.py`, assert the `--version` output matches `metadata.version("open-edit")`.

- [ ] **Step 4: Run and commit**

Run: `python3 -m pytest tests/test_cli.py -q` → PASS, then:

```bash
git add -A
git commit -m "fix(cli): report version from package metadata"
```

---

## Phase 2 — Fix Layering

### Task 2.1: Move `_list_assets_from_disk` into storage

**Files:**
- Modify: `open_edit/serve/projects.py` (delete `_list_assets_from_disk`), `open_edit/kernel/render_service.py:202` (repoint import)
- Create: nothing — add the function to `open_edit/storage/assets.py`
- Test: `tests/test_storage/test_edit_graph.py` (or nearest storage test), `tests/test_serve_projects.py`

**Interfaces:**
- Consumes: `open_edit.storage.assets` module
- Produces: `open_edit.storage.assets.list_assets_from_disk(project_dir: Path) -> list[dict]` — exact signature copied from `serve/projects.py` current `_list_assets_from_disk`

- [ ] **Step 1: Read the function**

Run: `grep -n "_list_assets_from_disk" open_edit/serve/projects.py` and read its body.

- [ ] **Step 2: Move it into `storage/assets.py`**

Copy the body verbatim, renamed `_list_assets_from_disk` → `list_assets_from_disk` (public). Keep internal helpers together with it.

- [ ] **Step 3: Repoint both consumers**

In `kernel/render_service.py:202` replace `from open_edit.serve.projects import _list_assets_from_disk` with `from open_edit.storage.assets import list_assets_from_disk` (update call site name if the rename requires it).
In `serve/projects.py`, delete the local function and import from `open_edit.storage.assets`.

- [ ] **Step 4: Add a storage-level test**

In the storage tests directory add:

```python
def test_list_assets_from_disk(tmp_path):
    (tmp_path / "assets" / "x.mp4").write_bytes(b"x")
    from open_edit.storage.assets import list_assets_from_disk
    assert len(list_assets_from_disk(tmp_path)) >= 1
```

(Adjust the expected layout to the real asset dir structure from `storage/assets.py`.)

- [ ] **Step 5: Run tests and commit**

Run: `python3 -m pytest tests/test_serve_projects.py tests/test_render_service.py tests/test_storage/ -q` → PASS, then:

```bash
git add -A
git commit -m "refactor(storage): move list_assets_from_disk into storage layer"
```

### Task 2.2: Move the overlay render trigger into kernel

**Files:**
- Create: `open_edit/kernel/render_overlay.py`
- Modify: `open_edit/serve/pi_bridge.py` (delete `_run_trigger_render`, re-export from kernel), `open_edit/kernel/render_service.py:353` (import from `kernel.render_overlay` instead of `serve.pi_bridge`)
- Test: `tests/test_render_service.py`, `tests/test_serve_pi_bridge.py`

**Interfaces:**
- Consumes: `open_edit.serve.html_overlay.render_composited` (kernel imports serve HTML overlay — see Step 2 note)
- Produces: `open_edit.kernel.render_overlay.run_trigger_render(...)` — same signature as today's `serve.pi_bridge._run_trigger_render`

- [ ] **Step 1: Read `_run_trigger_render`**

Run: `grep -n "_run_trigger_render" open_edit/serve/pi_bridge.py` and read its body and its callers (`pi_bridge.py:388,437`, `kernel/render_service.py:353`).

- [ ] **Step 2: Move it**

Create `open_edit/kernel/render_overlay.py` containing the moved function (renamed `run_trigger_render`). Note: it calls `open_edit.serve.html_overlay` — this is a **sanctioned exception**: `html_overlay.py` is pure HTML/ffmpeg composition with no serve state; if moving it wholesale to `render/` is trivial (check its imports first — if it only imports `ffmpeg`/stdlib/render modules, move `html_overlay.py` to `open_edit/render/html_overlay.py` in this same task and import from there), do that; otherwise keep the import and add a `# kernel-ok: html_overlay is a pure compositor` comment. Prefer the move.
Update `kernel/render_service.py:353` to import from `open_edit.kernel.render_overlay` (or `open_edit.render.html_overlay`).
Update `serve/pi_bridge.py` to import `run_trigger_render` from kernel and keep the pi_bridge call sites unchanged.

- [ ] **Step 3: Update tests**

Any test importing `_run_trigger_render` from `serve.pi_bridge` now imports from kernel. Run:

Run: `python3 -m pytest tests/test_render_service.py tests/test_serve_pi_bridge.py tests/test_serve_render_jobs.py -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(kernel): move overlay render trigger out of serve"
```

### Task 2.3: Move `_apply_free_form_code` out of `ir/apply.py`

**Files:**
- Modify: `open_edit/ir/apply.py:763-787` (delete `_apply_free_form_code`), `tests/test_apply_free_form.py`
- Create: `open_edit/agent/free_form.py`
- Test: `tests/test_apply_free_form.py` (repoint imports), `tests/test_ir/test_apply.py`

**Interfaces:**
- Consumes: `open_edit.agent.sandbox_bridge.run_free_form`
- Produces: `open_edit.agent.free_form.run_free_form_code(op, ...)` — same signature as the deleted `_apply_free_form_code`

- [ ] **Step 1: Read the function and its test**

Run: `sed -n '760,800p' open_edit/ir/apply.py` and `grep -rn "_apply_free_form_code\|free_form" tests/test_apply_free_form.py`

- [ ] **Step 2: Move it**

Create `open_edit/agent/free_form.py` with the function body (renamed `run_free_form_code`). Delete from `ir/apply.py`.

- [ ] **Step 3: Repoint the test**

Update `tests/test_apply_free_form.py` imports to `open_edit.agent.free_form.run_free_form_code`.

- [ ] **Step 4: Run tests and commit**

Run: `python3 -m pytest tests/test_apply_free_form.py tests/test_ir/test_apply.py -q` → PASS, then:

```bash
git add -A
git commit -m "refactor(ir): move free-form sandbox execution into agent layer"
```

### Task 2.4: Repair `kernel/__init__.py` exports

**Files:**
- Modify: `open_edit/kernel/__init__.py`
- Test: `tests/test_tool_registry.py` (or new small test below)

**Interfaces:**
- Produces: `open_edit.kernel` facade re-exporting: `DEFAULT_RENDER_SERVICE`, `apply_command`, `EditGraphCommandError`, `build_tool_schemas`, `dispatch_query`, `dispatch_edit`, `dispatch_generate`, `execute_tool`, `execute_trigger_render`, `validate_or_error`, `TOOL_SCHEMAS`

- [ ] **Step 1: Read the current `__init__.py`**

Run: `cat open_edit/kernel/__init__.py`

- [ ] **Step 2: Add real re-exports**

Replace the bare `__all__` with actual imports matching the 11 names above (import each from its module: `kernel.tool_schemas`, `kernel.pillar_tools`, `kernel.tool_executor`, `kernel.render_service`, `kernel.edit_graph_service`, `kernel.schema_validator`, `kernel.tool_registry`).

- [ ] **Step 3: Write the facade test**

Create `tests/test_kernel_facade.py`:

```python
import importlib

def test_kernel_facade_exports():
    import open_edit.kernel as k
    for name in ["DEFAULT_RENDER_SERVICE", "apply_command", "build_tool_schemas",
                 "dispatch_query", "dispatch_edit", "dispatch_generate",
                 "execute_tool", "execute_trigger_render", "validate_or_error",
                 "TOOL_SCHEMAS", "EditGraphCommandError"]:
        assert getattr(k, name) is not None, name

def test_kernel_does_not_import_serve():
    import open_edit.kernel
    assert "open_edit.serve" not in sys.modules or not any(
        m.startswith("open_edit.kernel") and m.endswith(".serve")
        for m in sys.modules)
```

(Simplify the second test to: `import open_edit.kernel; assert not [m for m in sys.modules if m.startswith("open_edit.serve")]` — but note serve may be imported by other tests in the same process; run it in isolation or guard with `sys.modules.pop` first.)

- [ ] **Step 4: Run and commit**

Run: `python3 -m pytest tests/test_kernel_facade.py tests/test_mcp_server.py -q` → PASS, then:

```bash
git add -A
git commit -m "refactor(kernel): make kernel package a real facade"
```

### Task 2.5: Add the layering guard test

**Files:**
- Create: `tests/test_layering.py`
- Test: itself

**Interfaces:**
- Produces: enforcement for the two hard layering rules

- [ ] **Step 1: Write the guard test**

Create `tests/test_layering.py`:

```python
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "open_edit"

def _py_files(pkg: str) -> list[Path]:
    return list((SRC / pkg).rglob("*.py"))

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")

def test_kernel_never_imports_serve():
    offenders = [str(p) for p in _py_files("kernel") if "open_edit.serve" in _read(p)]
    assert offenders == [], f"kernel must not import serve: {offenders}"

def test_ir_never_imports_upper_layers():
    offenders = []
    for p in _py_files("ir"):
        for banned in ("open_edit.agent", "open_edit.storage", "open_edit.serve", "open_edit.kernel"):
            if banned in _read(p):
                offenders.append(f"{p}: {banned}")
    assert offenders == [], f"ir must stay pure: {offenders}"

def test_storage_never_imports_apply_or_api():
    offenders = []
    for p in _py_files("storage"):
        for banned in ("ir.apply", "ir.api", "ir.factory"):
            if banned in _read(p):
                offenders.append(f"{p}: {banned}")
    assert offenders == [], f"storage imports below its boundary: {offenders}"

def test_mcp_never_imports_serve():
    offenders = [str(p) for p in _py_files("mcp") if "open_edit.serve" in _read(p)]
    assert offenders == [], f"mcp must not import serve: {offenders}"
```

- [ ] **Step 2: Run it**

Run: `python3 -m pytest tests/test_layering.py -q`
Expected: PASS (all violations fixed by Tasks 1.9, 2.1–2.4).

- [ ] **Step 3: Commit**

```bash
git add tests/test_layering.py
git commit -m "test: add layering guard tests for kernel/ir/storage/mcp"
```

---

## Phase 3 — Single Dispatcher, Single Validators

### Task 3.1: pi_bridge delegates to kernel tool_executor

**Files:**
- Modify: `open_edit/serve/pi_bridge.py:70-137` (`_run_agent_tool`)
- Test: `tests/test_serve_pi_bridge.py`

**Interfaces:**
- Consumes: `open_edit.kernel.tool_executor.execute_tool(tool_name, args, project_path) -> dict`
- Produces: same `_run_agent_tool` signature, now a thin wrapper

- [ ] **Step 1: Read both implementations**

Run: `sed -n '60,140p' open_edit/serve/pi_bridge.py` and `sed -n '100,170p' open_edit/kernel/tool_executor.py`

- [ ] **Step 2: Rewrite `_run_agent_tool` as a wrapper**

Keep only the serve-specific concerns (project_id injection into args, `cap_tool_result`), then:

```python
    return cap_tool_result(execute_tool(tool_name, args, project_path))
```

Delete the duplicated validation call, pillar dispatch blocks, and `getattr` fallback. Import `execute_tool` from `open_edit.kernel.tool_executor` (module already imports `validate_or_error` from kernel — reuse the existing style).

- [ ] **Step 3: Verify behavior parity**

Check `tests/test_serve_pi_bridge.py` and `tests/test_stream_chat_pi_refactor.py` — run:

Run: `python3 -m pytest tests/test_serve_pi_bridge.py tests/test_stream_chat_pi_refactor.py -q`
Expected: PASS. If a behavioral difference was previously intentional (e.g. `run_script` not validated on the pi path), fix it in Task 4.5 and note it in the commit.

- [ ] **Step 4: Commit**

```bash
git add open_edit/serve/pi_bridge.py
git commit -m "refactor(serve): pi_bridge delegates tool dispatch to kernel executor"
```

### Task 3.2: Delete the dead Pydantic validator

**Files:**
- Modify: `open_edit/kernel/tool_registry.py:134-146` (delete `validate_tool_args`), `open_edit/kernel/tool_schemas.py:28-33` (delete dead imports)
- Test: `tests/test_schema_validator.py`, `tests/test_tool_registry.py`

**Interfaces:**
- Consumes: `open_edit.kernel.schema_validator.validate_tool_args` (the hand-rolled live one — unchanged)
- Produces: one validator

- [ ] **Step 1: Verify dead**

Run: `grep -rn "validate_tool_args" --include="*.py" open_edit/ | grep -v __pycache__`
Confirm the only references are the definition, the dead import in `tool_schemas.py:32`, and tests.

- [ ] **Step 2: Delete definition + dead imports**

Remove `validate_tool_args` from `tool_registry.py`. In `tool_schemas.py` remove the imports of `tool_registry`, `TOOL_REGISTRY`, `validate_tool_args` (lines 28-33) if unused elsewhere in the file (verify).

- [ ] **Step 3: Update tests**

Delete `test_tool_registry.py` cases for `validate_tool_args` if they exist. Run:

Run: `python3 -m pytest tests/test_schema_validator.py tests/test_tool_registry.py tests/test_mcp_server.py -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore(kernel): remove dead pydantic validator, keep single schema_validator"
```

### Task 3.3: Move render-job tool schemas into the registry

**Files:**
- Modify: `open_edit/kernel/tool_registry.py` (add `GetRenderJobArgs`, `CancelRenderJobArgs`), `open_edit/mcp/adapters.py:16-45` (build schemas from registry; use `public_job`, delete `_job_to_dict`), `open_edit/serve/pi_bridge.py:414-415` (`--list-tools` now advertises 6)
- Test: `tests/test_mcp_server.py`, `tests/test_serve_pi_bridge.py`

**Interfaces:**
- Consumes: `open_edit.kernel.tool_registry` patterns (follow the existing 4 models)
- Produces: `GetRenderJobArgs(job_id: str)`, `CancelRenderJobArgs(job_id: str)`; both transports advertise `get_render_job` and `cancel_render_job`

- [ ] **Step 1: Read the adapter schemas**

Run: `sed -n '1,70p' open_edit/mcp/adapters.py`

- [ ] **Step 2: Add the two models to the registry**

Follow the existing model style in `tool_registry.py` (pydantic, `extra="forbid"`). Add them to `build_tool_schemas` output so both MCP and pi_bridge derive from the registry.

- [ ] **Step 3: Update adapters.py**

Replace the inline schema dicts with registry-derived schemas; replace `_job_to_dict` with `public_job` from `kernel.render_service` (verify its exact name in `render_service.py:397`).

- [ ] **Step 4: Update `--list-tools` test**

Update `tests/test_serve_pi_bridge.py` and any `tests/test_mcp_server.py` assertions from 4 advertised tools to 6. Run:

Run: `python3 -m pytest tests/test_mcp_server.py tests/test_serve_pi_bridge.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(kernel): registry-owned schemas for render job tools"
```

### Task 3.4: Consolidate reference validation into `ir/validate.py`

**Files:**
- Modify: `open_edit/ir/validate.py` (extend `validate_op_references` with a `strict: bool = False` mode covering asset existence, effect `param_name` presence, group labels), `open_edit/agent/sandbox_bridge.py:612-849` (delete `_validate_ops_incrementally`, `_load_project_for_validation`, `_load_assets_via_store`, `_effects_for_clip`, `_validate_references`; call the ir validator; raise `OpValidationError` instead of `ReferenceError`)
- Test: `tests/test_sandbox_bridge.py`, `tests/test_ir/test_validate.py`, `tests/test_ir/test_apply.py`

**Interfaces:**
- Consumes: `open_edit.ir.validate.validate_op_references(op, project, strict=False) -> list[str]`
- Produces: `OpValidationError` (existing type in `ir/validate.py`) as the only reference-error type

- [ ] **Step 1: Read both implementations**

Run: `sed -n '250,360p' open_edit/ir/validate.py` and `sed -n '610,860p' open_edit/agent/sandbox_bridge.py`
List the exact checks `_validate_references` performs beyond `validate_op_references` (asset existence, param_name, group labels).

- [ ] **Step 2: Extend `validate_op_references`**

Add the missing checks behind `strict=True`. Where `_validate_references` raises `ReferenceError`, the unified path returns error strings (the ir validator's contract) and the sandbox maps them to `OpValidationError`.

- [ ] **Step 3: Rewire the sandbox**

Replace the deleted cluster with:

```python
    project = _project_from_store(store)  # keep or inline the existing loader
    errors = validate_op_references(op, project, strict=True)
    if errors:
        raise OpValidationError("; ".join(errors))
```

Verify the sandbox call site still wraps this in its existing error-mapping (`_sanitize_for_detail`).

- [ ] **Step 4: Port sandbox validation tests**

Run: `python3 -m pytest tests/test_sandbox_bridge.py -q`
Port any test that asserts `ReferenceError` to assert `OpValidationError`. Add ir-level tests for the new strict checks in `tests/test_ir/test_validate.py`:

```python
def test_validate_op_references_strict_checks_asset(tmp_project): ...
```

(Use the existing fixtures/patterns in `test_ir/test_validate.py`.)

- [ ] **Step 5: Run the IR suite and commit**

Run: `python3 -m pytest tests/test_ir/ tests/test_sandbox_bridge.py tests/test_free_form_libs.py -q` → PASS, then:

```bash
git add -A
git commit -m "refactor(ir): single reference validator with strict mode"
```

---

## Phase 4 — Standardize the Tool Contract

### Task 4.0: Fix agent-loop project_id injection conflict + helper dispatch

**Files:**
- Modify: `open_edit/kernel/tool_executor.py` (`_run_tool`), `open_edit/serve/agent/loop.py` (injection site ~420-421)
- Test: `tests/test_tool_executor.py`, `tests/test_serve_agent.py`, `tests/test_serve_pi_bridge.py`

**Interfaces:**
- Consumes: `validate_or_error` (existing), `TOOL_REGISTRY` names
- Produces: agent-loop calls to registry tools (query_project, edit_project, run_script, trigger_render, get_render_job, cancel_render_job) succeed with injected `project_id`; `get_render_job`/`cancel_render_job` dispatch in kernel via `DEFAULT_RENDER_SERVICE` + `public_job`

- [ ] **Step 1: Reproduce the bug (pre-existing, discovered during Task 3.3 review)**

Run: `python3 -c "from open_edit.kernel.tool_executor import execute_tool; print(execute_tool('query_project', {'query': 'assets', 'params': {}, 'project_id': 'x'}, '/tmp/xyz'))"`
Expected: `{"status": "error", "error": "schema_validation_failed", ...}` — the agent loop injects `project_id` into every tool call (loop.py ~420-421, except search_assets), and all registry schemas are `extra="forbid"`, so every registry tool call from the agent loop fails validation. Pre-existing since the monorepo flatten; verified present at commit 5163ed3.

- [ ] **Step 2: Fix the injection conflict in `_run_tool`**

In `open_edit/kernel/tool_executor.py::_run_tool`, before `validate_or_error(name, args)`: if `name` is a registry-schema tool (derive the set from `TOOL_SCHEMAS` — do NOT hardcode the name list twice; import from `kernel.tool_schemas`), `args = {k: v for k, v in args.items() if k != "project_id"}`. These tools receive `project_path` and do not declare `project_id`. Non-registry tools (getattr fallback) keep receiving the injected field as today.

- [ ] **Step 3: Add helper dispatch**

In `_run_tool`, add branches mirroring `mcp/adapters.py`: `get_render_job` → `DEFAULT_RENDER_SERVICE.get(...)` + `public_job(...)` in a `{"ok": True, ...}` envelope (match the MCP shape exactly); `cancel_render_job` → `DEFAULT_RENDER_SERVICE.cancel(...)`. Read `mcp/adapters.py` at HEAD for the exact call shapes.

- [ ] **Step 4: Write the regression test**

In `tests/test_tool_executor.py`:

```python
def test_registry_tools_accept_injected_project_id():
    res = execute_tool("query_project", {"query": "assets", "params": {}, "project_id": "injected"}, tmp_project_path)
    assert res.get("status") != "error"  # no schema_validation_failed
```

(Use existing fixtures; also assert `get_render_job`/`cancel_render_job` dispatch to the service — with a monkeypatched `DEFAULT_RENDER_SERVICE`.)

- [ ] **Step 5: Run tests and commit**

Run: `python3 -m pytest tests/test_tool_executor.py tests/test_serve_agent.py tests/test_serve_pi_bridge.py tests/test_mcp_server.py -q` → PASS, then:

```bash
git add -A
git commit -m "fix(kernel): agent-loop project_id injection conflict and helper dispatch"
```

## Phase 4 (cont.) — Tool Contract

### Task 4.1: Create the tool contract module

**Files:**
- Create: `open_edit/agent/tools/_contract.py`
- Test: `tests/test_tool_contract.py` (new)

**Interfaces:**
- Produces:

```python
class ToolError(Exception): ...
class ToolRetryableError(ToolError): ...

def tool_result(fn):  # decorator: catches Exception, returns {"status": "error", "error": str(e)}
    ...

def get_asset_or_error(project_path: str, asset_hash: str) -> tuple[Asset | None, dict | None]:
    """Returns (asset, None) or (None, canonical error dict)."""

def require_alignment(asset) -> dict | None:
    """Returns None if aligned, else canonical 'retry' error dict."""
```

Canonical shapes: success `{"status": "ok", ...}`; error `{"status": "error", "error": str(e)}`; retry `{"status": "retry", "error": "..."}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tool_contract.py`:

```python
import pytest
from open_edit.agent.tools._contract import tool_result, ToolError, ToolRetryableError

def test_tool_result_wraps_success():
    @tool_result
    def ok(args, project_path):
        return {"status": "ok", "data": 1}
    assert ok({}, "/tmp") == {"status": "ok", "data": 1}

def test_tool_result_catches_exception():
    @tool_result
    def boom(args, project_path):
        raise ValueError("nope")
    res = boom({}, "/tmp")
    assert res["status"] == "error" and "nope" in res["error"]

def test_tool_result_marks_retryable():
    @tool_result
    def retry(args, project_path):
        raise ToolRetryableError("try later")
    res = retry({}, "/tmp")
    assert res["status"] == "retry" and "try later" in res["error"]

def test_tool_result_logs_exception(caplog):
    @tool_result
    def boom(args, project_path):
        raise ValueError("logged")
    boom({}, "/tmp")
    assert any("logged" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_tool_contract.py -q`
Expected: FAIL (module does not exist).

- [ ] **Step 3: Implement `_contract.py`**

`tool_result` = `functools.wraps` decorator; on `ToolRetryableError` → `{"status": "retry", "error": str(e)}`; on `Exception` → `logger.exception(...)` + `{"status": "error", "error": str(e)}`; pass-through otherwise. `get_asset_or_error` uses `open_edit.agent.tools._helpers.get_asset_store` + `store.get(asset_hash)` and returns the canonical "asset not found" dict. `require_alignment` checks `asset.word_alignment` presence and returns the canonical "alignment pending — retry" dict.

- [ ] **Step 4: Run tests and commit**

Run: `python3 -m pytest tests/test_tool_contract.py -q` → PASS, then:

```bash
git add tests/test_tool_contract.py open_edit/agent/tools/_contract.py
git commit -m "feat(tools): canonical tool result contract and helpers"
```

### Task 4.2: Migrate the 12 simple tools to `@tool_result`

**Files:**
- Modify: `open_edit/agent/tools/pyagent_get_style_profile.py`, `pyagent_set_pinned_value.py`, `pyagent_get_pending_notes.py`, `pyagent_add_marker.py`, `pyagent_analyze_narrative.py`, `pyagent_get_transcript_packed.py`, `pyagent_select_music.py`, `pyagent_place_sfx.py`, `pyagent_propose_silence_cuts.py`, `pyagent_list_assets.py`, `pyagent_ingest_local.py`, `pyagent_run_python.py`
- Test: existing per-tool tests (`tests/test_tools.py`, `tests/test_pyagent_run_python.py`, `tests/test_ingest_local.py`, `tests/test_list_assets_tool.py`, `tests/test_pyagent_import_asset.py`)

**Interfaces:**
- Consumes: `@tool_result` from Task 4.1
- Produces: every migrated tool returns `{"status": "ok"|"error"|"retry", ...}`

- [ ] **Step 1: Migrate one tool as the pattern**

Take `pyagent_add_marker.py`. Replace its body:

```python
def add_marker(args: dict, project_path: str) -> dict:
    try:
        ...work...
        return {"status": "ok", "marker": ...}
    except Exception as e:
        return {"status": "error", "error": str(e)}
```

with:

```python
@tool_result
def add_marker(args: dict, project_path: str) -> dict:
    ...work...
    return {"status": "ok", "marker": ...}
```

(Remove the try/except entirely; the decorator owns error conversion.)

- [ ] **Step 2: Migrate the remaining 11 tools identically**

For `pyagent_get_style_profile.py`, also wrap the bare `get_slice()` return: `return {"status": "ok", "profile": get_slice(...)}`.

- [ ] **Step 3: Run the tool tests**

Run: `python3 -m pytest tests/test_tools.py tests/test_pyagent_run_python.py tests/test_ingest_local.py tests/test_list_assets_tool.py tests/test_pyagent_import_asset.py -q`
Expected: PASS. If a test asserts the old error shape (e.g. `res["ok"] is False`), update it to `res["status"] == "error"`.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(tools): migrate 12 tools to @tool_result contract"
```

### Task 4.3: Migrate asset-fetch boilerplate

**Files:**
- Modify: `pyagent_analyze_narrative.py`, `pyagent_get_transcript_packed.py`, `pyagent_select_music.py`, `pyagent_place_sfx.py`, `pyagent_propose_silence_cuts.py`, `pyagent_generate_visual_for_segment.py`
- Test: existing tests

**Interfaces:**
- Consumes: `get_asset_or_error`, `require_alignment` from Task 4.1
- Produces: uniform "asset not found" / "alignment pending" dicts

- [ ] **Step 1: Replace the 4-line fetch pattern in all 6 files**

```python
store = get_asset_store(project_path)
asset = store.get(args["asset_hash"])
if asset is None:
    return {"status": "error", "error": "asset not found"}
```

becomes:

```python
asset, err = get_asset_or_error(project_path, args["asset_hash"])
if err:
    return err
```

And the 3 duplicated alignment-retry blocks become `err = require_alignment(asset); if err: return err`.

- [ ] **Step 2: Run tests**

Run: `python3 -m pytest tests/test_tools.py tests/test_pyagent_search_assets.py -q`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "refactor(tools): unify asset fetch and alignment boilerplate"
```

### Task 4.4: Migrate timeline_ops and remotion tools to canonical shapes

**Files:**
- Modify: `open_edit/agent/tools/pyagent_timeline_ops.py` (7 functions, replace 7× `{"ok": False, "error": ...}` and `{"ok": True, ...}` with canonical), `pyagent_generate_remotion_composition.py`, `pyagent_init_remotion_project.py`, `pyagent_write_remotion_composition.py`, `pyagent_import_asset.py` (`{"status": "ingested"}` → `{"status": "ok", "result": "ingested"}`), `pyagent_search_assets.py` (`{"error": ..., "results": []}` → `{"status": "ok", "results": [...]}` and error shape canonical), `pyagent_get_pending_notes.py` (`{"notes": ...}` → `{"status": "ok", "notes": ...}`)
- Test: `tests/test_timeline_full.py`, `tests/test_tools.py`, `tests/test_pyagent_import_asset.py`, `tests/test_pyagent_search_assets.py`

**Interfaces:**
- Consumes: `@tool_result`
- Produces: all tools canonical `{"status": ...}`

- [ ] **Step 1: Add `@tool_result` and canonicalize timeline_ops**

Each of the 7 functions: wrap with decorator, change `return {"ok": False, "error": str(e)}` (deleted try/excepts) and `{"ok": True, ...}` → `{"status": "ok", ...}`. Note `apply_silence_gaps` returns `{"ok": True, "applied": ...}` too — canonicalize the same way.

- [ ] **Step 2: Canonicalize the remotion + import/search/notes tools**

Same treatment. `run_script = run_python` alias stays in `pyagent_run_python.py`.

- [ ] **Step 3: Update downstream status checks**

Grep for consumers of the old shapes:

Run: `grep -rn '"ok"\|\["ok"\]\|\.get("ok")' --include="*.py" open_edit/ | grep -v __pycache__`
Update `kernel/tool_executor.py` `_is_error_result` heuristics (lines ~53-56) and `serve/agent.py` tool-result handling (~1310-1312) to the single `status` key.

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_timeline_full.py tests/test_tools.py tests/test_pyagent_import_asset.py tests/test_pyagent_search_assets.py tests/test_tool_executor.py tests/test_serve_agent.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(tools): canonical status shapes for timeline/remotion/asset tools"
```

### Task 4.5: Standardize parameter aliases

**Files:**
- Modify: `open_edit/agent/tools/pyagent_timeline_ops.py` (trim_clip: accept only `out_point_sec`; change_clip_speed: accept only `rate`; update schemas accordingly), `open_edit/agent/tools/pyagent_get_transcript_packed.py` (accept only `pause_threshold_sec`)
- Test: `tests/test_timeline_full.py`, relevant tool tests

**Interfaces:**
- Consumes: none
- Produces: one canonical alias per parameter; alias → canonical mapping deleted

- [ ] **Step 1: Find all alias pairs**

Run: `grep -rn "out_point_sec\|new_out_point_sec\|new_speed\|pause_threshold_s" --include="*.py" open_edit/ | grep -v __pycache__`

- [ ] **Step 2: Delete the legacy aliases**

Keep the canonical key; keep accepting the legacy key ONLY through a deprecation shim if a schema advertises it — otherwise delete outright (user-approved: free to change). Update `kernel/tool_registry.py` / `tool_schemas.py` parameter docs.

- [ ] **Step 3: Run tests and commit**

Run: `python3 -m pytest tests/test_timeline_full.py tests/test_tools.py -q` → PASS, then:

```bash
git add -A
git commit -m "refactor(tools): single canonical alias per tool parameter"
```

### Task 4.6: Replace getattr dispatch with an explicit TOOL_TABLE

**Files:**
- Modify: `open_edit/agent/tools/__init__.py` (build `TOOL_TABLE: dict[str, Callable]`), `open_edit/kernel/tool_executor.py` (consume `TOOL_TABLE`), `open_edit/kernel/pillar_tools.py` (consume `TOOL_TABLE`)
- Test: `tests/test_tool_executor.py`, `tests/test_tool_registry.py`, `tests/test_pillar_tools.py`

**Interfaces:**
- Produces: `open_edit.agent.tools.TOOL_TABLE` mapping every callable tool name → fn (19 re-exported + 7 timeline_ops + `trigger_render` virtual handled by kernel)

- [ ] **Step 1: Build TOOL_TABLE**

In `tools/__init__.py`, after the existing re-exports, add:

```python
TOOL_TABLE: dict[str, Callable] = {
    "add_marker": add_marker,
    ...
    # timeline_ops family
    "add_clip": add_clip, "trim_clip": trim_clip, ...
}
```

(import the timeline_ops functions in this module; the previous `getattr(open_edit.agent.tools, name)` lookups worked only for `__all__` names — timeline_ops was reachable solely via pillar dispatch; now everything is in one table.)

- [ ] **Step 2: Update kernel dispatch**

`kernel/tool_executor.py` and `kernel/pillar_tools.py`: replace `getattr(tools_mod, name)` with `TOOL_TABLE[name]`; pillar routing dicts become lookups into the same table. Unknown names raise `ToolNotFound` (existing type).

- [ ] **Step 3: Add a table-completeness test**

In `tests/test_tool_registry.py`:

```python
def test_every_schema_tool_resolves_in_tool_table():
    from open_edit.agent.tools import TOOL_TABLE
    from open_edit.kernel.tool_schemas import TOOL_SCHEMAS
    for schema in TOOL_SCHEMAS:
        assert schema["name"] in TOOL_TABLE or schema["name"] == "trigger_render"
```

- [ ] **Step 4: Run tests and commit**

Run: `python3 -m pytest tests/test_tool_executor.py tests/test_tool_registry.py tests/test_pillar_tools.py tests/test_mcp_server.py -q` → PASS, then:

```bash
git add -A
git commit -m "refactor(tools): explicit TOOL_TABLE replaces getattr dispatch"
```

---

## Phase 5 — Split God Files

> For each split in this phase: the existing tests are the safety net. Every split task ends with the full suite green and a structural assertion that the old module is gone or thin.

### Task 5.1: Split `serve/agent.py` into `serve/agent/` package

**Files:**
- Create: `open_edit/serve/agent/` with `__init__.py` (re-export `run_agent_turn`, `execute_tool`, existing public names), `loop.py`, `cli_turn.py`, `prompts.py`, `history_store.py`, `cost_sidecar.py`, `verify_stage.py`
- Modify: delete `open_edit/serve/agent.py` after repointing importers (`serve/app.py`, `serve/llm.py`, tests)
- Test: `tests/test_serve_agent.py`, `tests/test_serve_agent_cost.py`, `tests/test_serve_agent_visual_verify.py`, `tests/test_serve_chat_status.py`

**Interfaces:**
- Consumes: internal state from current `agent.py` (module-level `_BG_TASKS`, `_append_counters`, etc. — keep them in the module that owns them)
- Produces: `open_edit.serve.agent.run_agent_turn` (same signature), plus `open_edit.serve.agent.history_store.append_conversation`, `cost_sidecar.save_cost_state_async`, `verify_stage.maybe_verify_render`, `prompts.build_system_prompt`

- [ ] **Step 1: Map the split by line ranges (from analysis)**

1. Lines 93–165 conversation JSONL → `history_store.py`
2. Lines 180–258 cost sidecar → `cost_sidecar.py`
3. Lines 265–362 system prompt → `prompts.py`
4. Lines 415–651 visual verification → `verify_stage.py`
5. Lines 755–930 CLI-owned turn → `cli_turn.py`
6. Lines 937–1521 `run_agent_turn` + 654–735 history building → `loop.py`

Move functions wholesale; keep cross-module imports inside `agent/` package. `__init__.py` re-exports only what external consumers import (grep `from open_edit.serve.agent import` first).

- [ ] **Step 2: Repoint importers**

Run: `grep -rn "serve.agent\|serve import agent" --include="*.py" open_edit/ tests/ | grep -v __pycache__`
Update all to `open_edit.serve.agent.<new_submodule>` or the package facade. Delete `open_edit/serve/agent.py` and its `__pycache__`.

- [ ] **Step 3: Run the serve agent tests**

Run: `python3 -m pytest tests/test_serve_agent.py tests/test_serve_agent_cost.py tests/test_serve_agent_visual_verify.py tests/test_serve_chat_status.py tests/test_stream_contract.py -q`
Expected: PASS.

- [ ] **Step 4: Full suite + commit**

Run: `python3 -m pytest tests/ -q` → green, then:

```bash
git add -A
git commit -m "refactor(serve): split agent god file into serve/agent package"
```

### Task 5.2: Split `serve/app.py` into routers

**Files:**
- Create: `open_edit/serve/routers/` (`__init__.py`, `projects.py`, `renders.py`, `ops.py`, `config.py`, `assets.py`), `open_edit/serve/ws/chat.py`, `open_edit/serve/auth.py`, `open_edit/serve/upload.py`
- Modify: `open_edit/serve/app.py` becomes thin (mount routers, middleware, lifespan, error handlers)
- Test: full serve test battery (`tests/test_serve_*.py`)

**Interfaces:**
- Consumes: existing route handlers (move, don't rewrite)
- Produces: `open_edit.serve.app.app` (same FastAPI instance); routers registered with the same URL prefixes

- [ ] **Step 1: Map routes to routers (from analysis)**

Projects/ingest/notes/thumbnail → `routers/projects.py`; render trigger/poll/cancel/file → `routers/renders.py`; ops CRUD → `routers/ops.py`; llm-config/runtimes/keys → `routers/config.py`; asset streaming → `routers/assets.py`; ws_chat → `ws/chat.py`; auth middleware + rate limiting → `auth.py`; upload helper → `upload.py`.

- [ ] **Step 2: Move code; keep `app` state shared**

Shared state (`state = AppState()` or similar — read the source) lives in `app.py` and is passed to router factories (`create_projects_router(state)` pattern) or attached via `app.state`. Follow whichever pattern the code already uses.

- [ ] **Step 3: Delete the legacy blocks (already done in Task 1.4) and slim app.py**

`app.py` keeps: lifespan, exception handlers, middleware registration, `include_router` calls.

- [ ] **Step 4: Run the serve battery**

Run: `python3 -m pytest tests/test_serve_*.py -q`
Expected: PASS. Fix any import-order test (`test_serve_module_structure.py`) to match the new layout.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(serve): split app.py into routers, auth, upload"
```

### Task 5.3: Split `serve/llm.py` into `serve/llm/` package

**Files:**
- Create: `open_edit/serve/llm/` (`__init__.py` re-exporting `stream_chat`, `StreamEvent`; `dispatcher.py`, `events.py`, `keys.py`, `sdk_anthropic.py`, `sdk_openai.py`, `cli/__init__.py`, `cli/driver.py`)
- Modify: `open_edit/serve/llm.py` deleted; importers repointed; the per-provider `if adapter.name == ...` chain (lines 709–788) replaced by per-adapter normalizer registration
- Test: `tests/test_serve_llm_usage.py`, `tests/test_serve_llm_pi.py`, `tests/test_stream_chat_*.py`, `tests/test_serve_llm_config_api.py`

**Interfaces:**
- Consumes: `open_edit.serve.llm_config`, `open_edit.serve.providers`, `open_edit.serve.cli_adapter`
- Produces: `open_edit.serve.llm.stream_chat(...)` (same signature); `cli_adapter.CLIAdapter` gains `normalize_event(raw_line) -> StreamEvent` so the driver is generic (no name branches)

- [ ] **Step 1: Split by responsibility (from analysis)**

Lines 54–106 events → `events.py`; 113–166 serialization → `dispatcher.py`; 169–251 key/model resolution → `keys.py`; 258–380 dispatcher+retry → `dispatcher.py`; 383–829 CLI driver → `cli/driver.py`; 836–950 → `sdk_anthropic.py`; 957–1116 → `sdk_openai.py`.

- [ ] **Step 2: Make the CLI driver generic**

Move each provider branch body (`pi`, `jcode`, `antigravity`, `opencode`) into the matching `CLIAdapter` subclass in `cli_adapter.py` as a `normalize_event` method; `driver` loops `adapter.normalize_event(line)`. Add the missing `jcode` adapter class (check `providers.py` for its spec; it currently does not exist in `_ADAPTERS` — add it).

- [ ] **Step 3: Delete `serve/llm.py`, repoint importers**

Run: `grep -rn "serve.llm\|serve import llm" --include="*.py" open_edit/ tests/ | grep -v __pycache__`
Update imports to `open_edit.serve.llm` (package facade).

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_serve_llm_usage.py tests/test_serve_llm_pi.py tests/test_serve_llm_config_api.py tests/test_stream_chat_pi_refactor.py tests/test_stream_chat_opencode.py tests/test_stream_contract.py tests/test_providers.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(serve): split llm god file; generic CLI driver with per-adapter normalizers"
```

### Task 5.4: Split `sandbox_bridge.py` into `agent/sandbox/`

**Files:**
- Create: `open_edit/agent/sandbox/` (`__init__.py` re-exporting `run_free_form`, `run_render`, `SandboxUnavailable`; `backends.py`, `staging.py`, `bootstrap.py`, `bridge.py`)
- Modify: delete `open_edit/agent/sandbox_bridge.py`; repoint importers (`ir` no longer imports it — Task 2.3; `agent/tools/pyagent_run_python.py`, `kernel/...`, `tests/...`)
- Test: `tests/test_sandbox_bridge.py`, `tests/test_sandbox_backends.py`, `tests/test_sandbox_observations.py`, `tests/test_free_form_*.py`

**Interfaces:**
- Consumes: nothing new
- Produces: `open_edit.agent.sandbox.run_free_form(code, project_path, ...)` — same signature; `open_edit.agent.sandbox.backends.get_sandbox_backend()`, `resolve_binary(candidates)`; `bootstrap.render_bootstrap(...)`; `staging.stage_and_collect(...)` (shared by both backends)

- [ ] **Step 1: Extract the backend layer**

Move `SandboxBackend`, `BwrapBackend`, `DevSubprocessBackend`, `_resolve_sandbox_bin`, `_resolve_render_binary`, backend selection → `backends.py`. Extract the ~90% duplicated staging/collect/cleanup logic into `staging.py::stage_and_collect` and have both `run()` methods call it. Single `_FlushingBuffer` in `backends.py` (or `staging.py`).

- [ ] **Step 2: Extract bootstrap codegen**

Move `_render_bootstrap` (+ its generated-code `_FlushingBuffer` copy → use the real one) → `bootstrap.py`.

- [ ] **Step 3: Keep thin facades**

`bridge.py` keeps `run_free_form` (orchestration: header preflight → JobLock → backend → error mapping) and `run_render`. `__init__.py` re-exports `run_free_form`, `run_render`, `SandboxUnavailable`.

- [ ] **Step 4: Repoint importers and delete old file**

Run: `grep -rn "sandbox_bridge" --include="*.py" open_edit/ tests/ | grep -v __pycache__`
Update all. Delete `open_edit/agent/sandbox_bridge.py`.

- [ ] **Step 5: Run sandbox tests**

Run: `python3 -m pytest tests/test_sandbox_bridge.py tests/test_sandbox_backends.py tests/test_sandbox_observations.py tests/test_free_form_e2e.py tests/test_free_form_exceptions.py tests/test_pyagent_run_python.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(agent): split sandbox_bridge into agent/sandbox package"
```

### Task 5.5: Split `ir/apply.py`

**Files:**
- Create: `open_edit/ir/apply_clips.py`, `open_edit/ir/apply_effects.py`, `open_edit/ir/apply_audio.py`, `open_edit/ir/derive.py`
- Modify: `open_edit/ir/apply.py` (dispatch only: `apply_operation` with the isinstance tree delegating to the new modules; delete inline handlers, `derive_timeline`, `derive_or_load_timeline`, duplicate import at :851), `open_edit/storage/timeline_cache.py` (new — hosts `derive_or_load_timeline` as storage policy)
- Test: `tests/test_ir/test_apply.py`, `tests/test_ir_api.py`, `tests/test_apply_purity.py`, `tests/test_apply_split.py`, `tests/test_history_compaction.py`, `tests/test_timeline_full.py`

**Interfaces:**
- Consumes: `ir/types`, `ir/validate.TimelineValidationError`
- Produces: `ir.apply.apply_operation(op, timeline) -> Timeline` (unchanged); `ir.derive.derive_timeline(timeline, ops) -> Timeline`; `storage.timeline_cache.derive_or_load_timeline(store, project) -> Timeline`

- [ ] **Step 1: Map handlers to files (from analysis)**

Clips (move/trim/slip/ripple/split/replace/speed) → `apply_clips.py`; effects/keyframes/transitions → `apply_effects.py`; audio (gain/normalize) → `apply_audio.py`. Move each `_apply_*` helper verbatim, importing `TimelineValidationError` from `ir.validate` where used. `apply_operation` keeps its 28-branch tree, importing the helpers from sibling modules.

- [ ] **Step 2: Move derivation**

`derive_timeline` → `ir/derive.py`. `derive_or_load_timeline` → `open_edit/storage/timeline_cache.py` (it is cache policy over `EditGraphStore`; check its imports — `EditGraphStore` is duck-typed via a `store` param, so storage placement is safe; it imports `compute_edit_graph_hash` from `ir.hash`).

- [ ] **Step 3: Delete `_apply_free_form_code` remnants and the duplicate import**

The `_apply_free_form_code` was moved in Task 2.3; delete the leftover `apply.py:851` lazy import of `TimelineValidationError` and the L58 duplicate (keep one).

- [ ] **Step 4: Repoint importers**

Run: `grep -rn "derive_timeline\|derive_or_load_timeline" --include="*.py" open_edit/ | grep -v __pycache__`
`kernel/render_service.py`, `render/orchestrator.py`, `serve/projects.py` import from the new homes.

- [ ] **Step 5: Run tests and commit**

Run: `python3 -m pytest tests/test_ir/ tests/test_apply_purity.py tests/test_apply_split.py tests/test_history_compaction.py tests/test_timeline_full.py tests/test_render_service.py -q` → PASS, then:

```bash
git add -A
git commit -m "refactor(ir): split apply god file into op-family modules and derive"
```

### Task 5.6: Split `storage/edit_graph.py`

**Files:**
- Create: `open_edit/storage/commands.py` (`CommandStore`), `open_edit/storage/ordering.py` (`reorder`, `reorder_all`, `move_arbitrary`, snapshot invalidation), `open_edit/storage/timeline_cache.py` (extend with `TimelineSnapshotStore`)
- Modify: `open_edit/storage/edit_graph.py` (keep: `EditGraphStore` CRUD + revision + status events + project_id + project_meta; delete commands block :238-294 and reorder block :323-442; delete duplicate `new_id` import at :108)
- Test: `tests/test_storage/test_edit_graph.py`, `tests/test_edit_graph_project_id.py`, `tests/test_history_compaction.py`, `tests/test_tool_executor.py`

**Interfaces:**
- Consumes: `open_edit.storage.db.open_conn` (Task 6.2 — see note), shared db file
- Produces: `CommandStore(db_path)` with `record_command`, `command_exists`, `finish_command`, `get_command_result`, `get_command_status`; `ordering.reorder(store, ...)` etc. with same signatures as today's methods; `TimelineSnapshotStore`

Note: if Task 6.2 has not run yet, `CommandStore`/`ordering` take the same `db_path` and use `sqlite3.connect` exactly like `EditGraphStore._conn()` does today (copy the pattern; Task 6.2 replaces it with `open_conn`).

- [ ] **Step 1: Extract CommandStore**

Move the 5 command methods into `commands.py::CommandStore`; `EditGraphStore` composes it (`self.commands = CommandStore(self.db_path)` — or keep method wrappers delegating; choose composition, it is cleaner). Update `kernel/tool_executor.py` call sites if they call `store.record_command(...)` → keep working via delegation first, then repoint in Task 3/6 if desired.

- [ ] **Step 2: Extract ordering**

Move the reorder family into `ordering.py`. **Important:** add snapshot invalidation — `reorder`/`reorder_all`/`move_arbitrary`/`delete_op` must delete `timeline_snapshots` rows for the project (this is the H1 bug fix; the stale-cache fix is Task 6.5 — this task makes the hook point, 6.5 makes it correct).

- [ ] **Step 3: Update tests**

Update tests that call the moved methods via `store.` to the new module functions (or keep delegation wrappers and leave tests alone — prefer wrappers to minimize churn, then delete wrappers in Task 6.5).

- [ ] **Step 4: Run storage tests**

Run: `python3 -m pytest tests/test_storage/ tests/test_edit_graph_project_id.py tests/test_history_compaction.py tests/test_tool_executor.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(storage): extract CommandStore and ordering from EditGraphStore"
```

### Task 5.7: Split `render/orchestrator.py`

**Files:**
- Create: `open_edit/render/timeline_plan.py` (`build_render_plan`, `resolve_asset_paths`), `open_edit/render/melt_runner.py` (`MeltRunner`), `open_edit/render/snapshot_recorder.py` (`record_snapshot_success/failure`)
- Modify: `open_edit/render/orchestrator.py` (slim `render_project`: plan → cache → emit → melt → burn → snapshot → result; single `RenderFailure` factory; delete `_timeline_without_remotion_clips` dead alias at :296)
- Test: `tests/test_render/`, `tests/test_phase567_edit_render.py`, `tests/test_e2e_render.py`

**Interfaces:**
- Consumes: `render.emitter.emit_timeline`, `render.cache.RenderCache`, `storage` stores
- Produces: `render.timeline_plan.build_render_plan(timeline, ops, store, mode) -> RenderPlan` (with `melt_timeline`, `overlay_clips`, `asset_paths`); `render.melt_runner.run_melt(plan, profile, encoder, timeout) -> Path`; `snapshot_recorder.record_*(...)`

- [ ] **Step 1: Extract the plan builder**

Move orchestrator lines 104–127 (asset resolution — collapse the 3 near-identical loops into one `resolve_asset_paths`) and 218–293 (overlay planning + `_timeline_for_melt`) into `timeline_plan.py`.

- [ ] **Step 2: Extract melt execution**

Move command build + subprocess run + timeout + cache put/get into `melt_runner.py`.

- [ ] **Step 3: Extract snapshot recording**

Move `_record_snapshot_success`/`_record_snapshot_failure` (90% identical — merge into one function with a `success: bool` param) into `snapshot_recorder.py`.

- [ ] **Step 4: Slim the orchestrator + single failure path**

`render_project` now: build plan → cache lookup → emit → run melt → burn overlays → record snapshot → return result, with exactly one `_fail(...)` helper producing the 6-field `RenderResult`. Delete `_timeline_without_remotion_clips`.

- [ ] **Step 5: Run render tests**

Run: `python3 -m pytest tests/test_render/ tests/test_phase567_edit_render.py tests/test_e2e_render.py tests/test_remotion_renderer.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(render): split orchestrator into plan/melt/snapshot modules"
```

### Task 5.8: Split `render/remotion.py`

**Files:**
- Create: `open_edit/render/remotion/` (`__init__.py` re-exporting `render_composition`; `safety.py` (`validate_entry_point`, `composition_source_bundle` scanning, `composition_cache_key`), `renderer.py` (`RemotionRunner` + subprocess lifecycle + codec mapping), keep `remotion_bridge.mjs` in place)
- Modify: delete `open_edit/render/remotion.py`; repoint importers (`render/materialize.py`, `render/orchestrator.py`, tests)
- Test: `tests/test_remotion_renderer.py`, `tests/test_remotion_scaffold.py`, `tests/test_render/test_golden_fixtures.py`

**Interfaces:**
- Consumes: `render.remotion_scaffold`
- Produces: `open_edit.render.remotion.render_composition(...)` — same signature; `remotion.safety.validate_entry_point(path)`; `remotion.renderer._build_command(...)` (single argv builder replacing the duplicated `custom_bin` vs `node` construction)

- [ ] **Step 1: Extract safety**

Move `validate_entry_point` (110–126), `composition_source_bundle` (80–102), `composition_cache_key` (129–148) → `safety.py`.

- [ ] **Step 2: Extract the runner**

Move `render_composition` (151–308) + `_terminate_process_group` (311–330) into a `RemotionRunner` class in `renderer.py`; unify the custom_bin/node argv construction into one `_build_command(...)`. Keep codec mapping (42–77, 186–204) with the runner or a small `codecs.py` — pick `renderer.py`.

- [ ] **Step 3: Repoint importers and delete the old file**

Run: `grep -rn "render.remotion\|render import remotion\|from open_edit.render.remotion" --include="*.py" open_edit/ tests/ | grep -v __pycache__`
Update imports. Delete `open_edit/render/remotion.py`.

- [ ] **Step 4: Run tests and commit**

Run: `python3 -m pytest tests/test_remotion_renderer.py tests/test_remotion_scaffold.py tests/test_render/test_golden_fixtures.py tests/test_remotion_ir_materialize.py -q` → PASS, then:

```bash
git add -A
git commit -m "refactor(render): split remotion.py into safety and runner modules"
```

---

## Phase 6 — Deduplicate Shared Infrastructure

### Task 6.1: Create `ir/ids.py` and migrate 22 call sites

**Files:**
- Create: `open_edit/ir/ids.py`
- Modify: `open_edit/ir/types.py` (re-export `new_id`, `now_iso8601` from ids for compat; delete local defs), `open_edit/storage/notes.py` (delete `_new_id` → `new_note_id`), `open_edit/storage/render_snapshots.py` (delete `_new_version_id` → `new_version_id`), `open_edit/storage/edit_graph.py:92` (`_now_iso` → `now_iso8601`), `open_edit/storage/job_lock.py:18` (`_now_iso` → `now_iso8601`), `open_edit/serve/app.py:688`, `open_edit/style/aggregate.py:63` (inline timestamps → `now_iso8601`)
- Test: `tests/test_storage/`, `tests/test_ir/`

**Interfaces:**
- Produces: `open_edit.ir.ids.new_id() -> str` (uuid4 hex), `now_iso8601() -> str`, `new_note_id() -> str` (`note_<hex12>` — same format as today), `new_version_id() -> str` (`v_<hex12>`)

- [ ] **Step 1: Write ids.py**

```python
"""Shared id and timestamp generators."""
import time
import uuid

def new_id() -> str:
    return uuid.uuid4().hex

def now_iso8601() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())

def new_note_id() -> str:
    return f"note_{new_id()[:12]}"

def new_version_id() -> str:
    return f"v_{new_id()[:12]}"
```

(Match the exact format of today's `notes._new_id` and `render_snapshots._new_version_id` — read them first and copy the format precisely.)

- [ ] **Step 2: Update `ir/types.py`**

Replace the local `new_id`/`now_iso8601` definitions with `from open_edit.ir.ids import new_id, now_iso8601` (keeps all existing `from open_edit.ir.types import new_id` imports working).

- [ ] **Step 3: Migrate the local copies**

For each listed module: delete the local generator, import from `ir.ids`. Update call sites (`_new_id()` → `new_note_id()` etc.).

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_storage/ tests/test_ir/ tests/test_job_lock.py tests/test_migrations.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(ir): single ids module; migrate 22 call sites"
```

### Task 6.2: Create `storage/db.py` shared connection helper

**Files:**
- Create: `open_edit/storage/db.py`
- Modify: `open_edit/storage/edit_graph.py` (`_conn` → `open_conn`), `open_edit/storage/notes.py`, `open_edit/storage/render_snapshots.py`, `open_edit/storage/job_lock.py` (delete `_ensure_schema` reach-in to `edit_graph._conn()`)
- Test: `tests/test_storage/`, `tests/test_job_lock.py`, `tests/test_migrations.py`

**Interfaces:**
- Produces: `open_edit.storage.db.open_conn(db_path: str) -> contextmanager[sqlite3.Connection]` — WAL, `foreign_keys=ON`, `row_factory=sqlite3.Row`, same semantics as today's `EditGraphStore._conn()`

- [ ] **Step 1: Write db.py**

```python
import sqlite3
from contextlib import contextmanager

@contextmanager
def open_conn(db_path):
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        yield conn
    finally:
        conn.close()
```

(Read `EditGraphStore._conn()` first and copy its exact PRAGMAs/behavior.)

- [ ] **Step 2: Migrate the four stores**

`EditGraphStore._conn` → use `open_conn(self.db_path)`; `notes.py`, `render_snapshots.py`, `job_lock.py` drop their private connection code and use `open_conn`. `JobLock` no longer touches `edit_graph._conn()`.

- [ ] **Step 3: Run tests**

Run: `python3 -m pytest tests/test_storage/ tests/test_job_lock.py tests/test_migrations.py tests/test_keys_store.py -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(storage): shared sqlite connection helper"
```

### Task 6.3: Consolidate schema DDL into migrations

**Files:**
- Modify: `open_edit/storage/schema.sql` (delete), `open_edit/storage/migrations/__init__.py` (single `ensure_schema` path; remove the legacy re-apply "safety net"), `open_edit/storage/notes.py`, `open_edit/storage/render_snapshots.py` (inline `_SCHEMA` → migrations `0003_notes.sql`, `0004_render_snapshots.sql`), `open_edit/storage/job_lock.py` (jobs index → `0005_job_lock.sql`)
- Test: `tests/test_migrations.py`, `tests/test_storage/`, `tests/test_job_lock.py`

**Interfaces:**
- Produces: one DDL source of truth under `migrations/`; `ensure_schema(db_path)` applies all migrations idempotently

- [ ] **Step 1: Verify DDL equivalence**

Run: `diff open_edit/storage/schema.sql open_edit/storage/migrations/0001_initial.sql` — if not identical, note the diff and reconcile (prefer the migrations version).

- [ ] **Step 2: Move the inline schemas into migrations**

Extract `notes.py:_SCHEMA` → `0003_notes.sql`; `render_snapshots.py:_SCHEMA` → `0004_render_snapshots.sql`; `job_lock.py` partial index → `0005_job_lock.sql`. Stores call `ensure_schema(db_path)` (from `migrations/__init__.py`) on init — remove their local `_SCHEMA` execution.

- [ ] **Step 3: Simplify `ensure_schema`**

Remove the legacy schema.sql re-application; keep `schema_version` tracking or `user_version`-style logic as-is otherwise.

- [ ] **Step 4: Run tests and commit**

Run: `python3 -m pytest tests/test_migrations.py tests/test_storage/ tests/test_job_lock.py tests/test_keys_store.py -q` → PASS, then:

```bash
git add -A
git commit -m "refactor(storage): single DDL source of truth in migrations"
```

### Task 6.4: Single project-path resolution (`ProjectPaths`)

**Files:**
- Create: `open_edit/storage/paths.py` (or extend `agent/tools/_helpers.py` — see note)
- Modify: `open_edit/agent/tools/_helpers.py` (`_db_path`, `_notes_db_path`, `_project_root` → one `ProjectPaths`), `open_edit/kernel/edit_graph_service.py:36-37` (delete `_db_path`, use ProjectPaths), `open_edit/agent/tools/pyagent_generate_remotion_composition.py:42` (hard-coded `.open_edit/edit_graph.db` → ProjectPaths), `open_edit/agent/sandbox_bridge.py`/`sandbox/` workdir validation (use ProjectPaths)
- Test: `tests/test_tools.py`, `tests/test_tool_executor.py`, `tests/test_serve_agent_visual_verify.py`, `tests/test_pyagent_search_assets.py`

**Interfaces:**
- Produces: `open_edit.storage.paths.ProjectPaths(root: Path)` with properties `db_path` (canonical `.open_edit/edit_graph.db` + legacy fallback), `notes_db_path`, `assets_dir`, `workdir`; factory `ProjectPaths.for_project(project_path) -> ProjectPaths`

- [ ] **Step 1: Read the three implementations**

Run: `sed -n '40,70p' open_edit/agent/tools/_helpers.py`, `sed -n '30,45p' open_edit/kernel/edit_graph_service.py`, `sed -n '35,50p' open_edit/agent/tools/pyagent_generate_remotion_composition.py`
Note which variants have the legacy fallback (only `_helpers._db_path` does — preserve that behavior).

- [ ] **Step 2: Implement `ProjectPaths` in `storage/paths.py`**

Copy `_helpers._db_path` logic (canonical + legacy fallback) as the single source; `storage/` may define it (storage owns the on-disk layout). `agent/tools/_helpers.py` keeps thin delegating functions (`db_path`, `notes_db_path`, `project_root`) for backward compat or update the ~10 importers directly (prefer direct update; grep importers first).

- [ ] **Step 3: Migrate the four call sites**

`edit_graph_service` imports `ProjectPaths` (kernel→storage is legal); `generate_remotion_composition` uses `paths.workdir / "edit_graph.db"`; sandbox workdir validation derives from `ProjectPaths`.

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_tools.py tests/test_tool_executor.py tests/test_serve_agent_visual_verify.py tests/test_pyagent_search_assets.py tests/test_pillar_tools.py tests/test_edit_graph_project_id.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(storage): single ProjectPaths layout resolver"
```

### Task 6.5: Fix the edit-graph hash bug and snapshot invalidation

**Files:**
- Modify: `open_edit/ir/hash.py` (order-sensitive hash), `open_edit/storage/edit_graph.py` `load_all()` (populate `sequence_num` from the DB), `open_edit/storage/ordering.py` (invalidate `timeline_snapshots` on reorder/delete — hook created in Task 5.6), `open_edit/storage/timeline_cache.py`
- Test: `tests/test_history_compaction.py`, `tests/test_ir_api.py`, new regression test

**Interfaces:**
- Consumes: `EditGraphStore.load_all() -> list[Operation]` (now with `sequence_num` set)
- Produces: `compute_edit_graph_hash(ops)` that changes when op ORDER changes; reorder/delete invalidate the timeline snapshot cache

- [ ] **Step 1: Write the failing regression test**

Add to `tests/test_history_compaction.py` (or a new `tests/test_graph_hash_order.py`):

```python
def test_hash_changes_when_order_changes():
    from open_edit.ir.hash import compute_edit_graph_hash
    from open_edit.storage.edit_graph import EditGraphStore
    # build store with two ops via api/fixtures, then reorder them
    # and assert hash differs; also assert derive_or_load_timeline
    # reflects the reordered timeline (not stale cache)
    ...
```

Use the existing fixtures in `tests/test_storage/test_edit_graph.py` to build a store with 2 clips, compute hash, call the store's reorder API, recompute — assert changed. Also assert `derive_or_load_timeline` returns the reordered order (proves snapshot invalidation).

- [ ] **Step 2: Populate sequence_num in load_all**

`load_all()` SELECTs `sequence_num` and sets it on each op (read the schema — `edits.sequence_num` column exists; check `0001_initial.sql`).

- [ ] **Step 3: Make the hash order-sensitive**

`compute_edit_graph_hash`: sort ops by the populated `sequence_num` (fall back to `edit_id` for stability when equal), and include the sequence in the payload (e.g. hash the concatenation `sequence_num:edit_id:op_json`). Keep the canonical JSON dump format.

- [ ] **Step 4: Invalidate snapshots on reorder/delete**

In `ordering.py`, every mutation (`reorder`, `reorder_all`, `move_arbitrary`, `delete_op`) deletes `timeline_snapshots` rows for the project. (The snapshot lookup path in `storage/timeline_cache.py` then rebuilds.)

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest tests/test_history_compaction.py tests/test_ir_api.py tests/test_storage/ tests/test_ir/ tests/test_render_service.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "fix(ir): order-sensitive graph hash and snapshot invalidation on reorder"
```

### Task 6.6: Unify render caching on the ir hash

**Files:**
- Modify: `open_edit/render/cache.py` (key cache on `compute_edit_graph_hash`; delete `canonical_json_hash`; make TTL configurable via `OPEN_EDIT_RENDER_CACHE_TTL_SEC`, default e.g. 86400), `open_edit/render/materialize.py` (fold JSON-file composition cache into `RenderCache`), `open_edit/render/orchestrator.py` (use `compute_edit_graph_hash`)
- Test: `tests/test_render/test_cache.py` (or nearest), `tests/test_remotion_ir_materialize.py`

- [ ] **Step 1: Update cache.py**

Replace `canonical_json_hash` with `compute_edit_graph_hash` from `ir.hash` for key derivation; TTL from env with sane default (1 hour is too short — analysis finding; use 24h default, `OPEN_EDIT_RENDER_CACHE_TTL_SEC` override).

- [ ] **Step 2: Fold the materialize cache**

Replace materialize's JSON-file cache with `RenderCache` entries under a distinct key prefix (e.g. `materialize:<composition_id>:<hash>`).

- [ ] **Step 3: Run tests**

Run: `python3 -m pytest tests/test_render/ tests/test_remotion_ir_materialize.py tests/test_phase567_edit_render.py -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(render): single graph-hash authority for render caches"
```

### Task 6.7: Single encoder-spec source

**Files:**
- Modify: `open_edit/render/encoder.py` (produce `EncoderSpec(vcodec, melt_args, ffmpeg_args)`), `open_edit/render/profiles.py:69-102` (consume `EncoderSpec.melt_args`, delete duplicated tables), `open_edit/render/graphics_overlay.py` (consume `EncoderSpec.ffmpeg_args`); delete dead `RenderProfile.encoder_backend` field (`render/profiles.py:21,52`)
- Test: `tests/test_render_encoder.py`, `tests/test_render_service.py`, `tests/test_graphics_overlay.py`

- [ ] **Step 1: Read both tables**

Run: `sed -n '1,60p' open_edit/render/encoder.py` and `sed -n '60,105p' open_edit/render/profiles.py`
Map each melt-dialect value to its ffmpeg counterpart (same policy: nvenc p5 10M/14M/20M, etc.).

- [ ] **Step 2: Emit EncoderSpec from encoder.py**

`select_encoder(profile)` returns the spec; `profiles.py` builds melt args from `spec.melt_args`; `graphics_overlay.py` uses `spec.ffmpeg_args`.

- [ ] **Step 3: Delete the dead field**

Remove `encoder_backend` from `RenderProfile` and its read site.

- [ ] **Step 4: Run tests and commit**

Run: `python3 -m pytest tests/test_render_encoder.py tests/test_graphics_overlay.py tests/test_render_service.py -q` → PASS, then:

```bash
git add -A
git commit -m "refactor(render): single EncoderSpec source for melt and ffmpeg args"
```

### Task 6.8: Single silence-detection implementation

**Files:**
- Create: `open_edit/render/ffmpeg_probe.py` (or `open_edit/qc/_ffmpeg.py` — pick `render/ffmpeg_probe.py`): `detect_silence_spans(path, threshold_db, min_s) -> list[tuple[float, float]]`, `probe_duration(path) -> float`
- Modify: `open_edit/render/silence_compress.py` (delete local `detect_silences`, use shared), `open_edit/qc/silence.py` (delete `_parse_silence`/`list_silence` ffmpeg parsing, use shared), `open_edit/serve/pi_bridge.py` (`_probe_duration` if still needed — it was deleted from kernel in Task 1.9 but pi_bridge may keep its own; unify on `ffmpeg_probe.probe_duration`)
- Test: `tests/test_silence_compress.py`, `tests/test_qc/`, `tests/test_visual_verify_waveform.py`

**Interfaces:**
- Produces: `open_edit.render.ffmpeg_probe.detect_silence_spans(path, threshold_db=-35.0, min_s=0.2) -> list[tuple[float, float]]` (keeps qc's 1.0s default via caller argument), `probe_duration(path) -> float`

- [ ] **Step 1: Read the two implementations**

Run: `sed -n '30,70p' open_edit/render/silence_compress.py` and `sed -n '80,165p' open_edit/qc/silence.py`
Copy the more complete regex; parameterize `min_s`.

- [ ] **Step 2: Create ffmpeg_probe.py and rewire**

Both modules import from it; delete their local parse logic. Preserve each caller's default (`silence_compress` uses min_s=0.2, `qc` uses 1.0 — pass explicitly).

- [ ] **Step 3: Unify probe_duration**

Replace any remaining local `probe_duration` implementations (grep for `def probe_duration`).

- [ ] **Step 4: Run tests and commit**

Run: `python3 -m pytest tests/test_silence_compress.py tests/test_qc/ tests/test_visual_verify_waveform.py -q` → PASS, then:

```bash
git add -A
git commit -m "refactor: single ffmpeg probe module for silence and duration"
```

### Task 6.9: Disambiguate the two project_meta systems

**Files:**
- Modify: `open_edit/storage/config.py:47,62` (rename `get_project_meta`/`set_project_meta` → `get_user_project_meta`/`set_user_project_meta`, or move the file-based meta under `style/` — pick the rename)
- Test: `tests/test_style/`, grep callers

- [ ] **Step 1: Find callers**

Run: `grep -rn "get_project_meta\|set_project_meta" --include="*.py" open_edit/ | grep -v __pycache__`

- [ ] **Step 2: Rename the file-based pair**

`config.py` functions → `get_user_project_meta`/`set_user_project_meta`; update callers (likely `style/` and `serve/project_meta.py`). The SQLite `EditGraphStore.get_project_meta`/`set_project_meta_field` keeps its name (it is the canonical store).

- [ ] **Step 3: Run tests and commit**

Run: `python3 -m pytest tests/test_style/ tests/test_serve_projects.py -q` → PASS, then:

```bash
git add -A
git commit -m "refactor(storage): disambiguate file-based vs sqlite project meta"
```

### Task 6.10: Derive provider metadata from the registry

**Files:**
- Modify: `open_edit/serve/providers.py` (canonical `PROVIDERS` — unchanged), `open_edit/serve/cli_adapter.py:96-285` (adapter classes derive `models`/defaults from `PROVIDERS`; add missing `jcode` adapter), `open_edit/serve/runtimes/keys_store.py:86-95` (derive env-key map from `ProviderSpec.env_keys`)
- Test: `tests/test_providers.py`, `tests/test_runtimes_registry.py`, `tests/test_runtimes_keys_store.py`, `tests/test_llm_config.py`

**Interfaces:**
- Consumes: `open_edit.serve.providers.PROVIDERS`
- Produces: one place that lists models/env keys; `get_adapter("jcode")` works

- [ ] **Step 1: Make adapters data-driven**

Each `CLIAdapter` subclass becomes a thin class holding only CLI-specific behavior (command construction, event normalization — added in Task 5.3); models/defaults come from `PROVIDERS[provider_id]`. Add `JcodeAdapter`.

- [ ] **Step 2: Derive keys_store env map**

Replace the hardcoded `provider → env var` dict with a comprehension over `PROVIDERS`.

- [ ] **Step 3: Add a consistency test**

In `tests/test_providers.py`:

```python
def test_every_provider_has_adapter_and_env_keys():
    from open_edit.serve.providers import PROVIDERS
    from open_edit.serve.cli_adapter import get_adapter
    from open_edit.serve.runtimes.keys_store import env_map
    for pid in PROVIDERS:
        assert get_adapter(pid) is not None, pid
        assert pid in env_map, pid
```

- [ ] **Step 4: Run tests and commit**

Run: `python3 -m pytest tests/test_providers.py tests/test_runtimes_registry.py tests/test_runtimes_keys_store.py tests/test_llm_config.py tests/test_serve_llm_pi.py -q` → PASS, then:

```bash
git add -A
git commit -m "refactor(serve): derive provider metadata from single registry"
```

### Task 6.11: Extract cost-aggregation helpers in the agent loop

**Files:**
- Modify: `open_edit/serve/agent/loop.py` and `open_edit/serve/agent/cli_turn.py` (extract `accumulate_usage(event, ctx)` and `emit_cost_update(...)`; replace the duplicated usage block at old agent.py 855–867 vs 1135–1152 and the 5 `cost_update` emit sites)
- Test: `tests/test_serve_agent_cost.py`, `tests/test_serve_cost.py`, `tests/test_serve_agent.py`

- [ ] **Step 1: Extract the helpers**

Add to `cost_sidecar.py` (from Task 5.1): `accumulate_usage(event, state)` (merges usage with `_SOURCE_PRIORITY`), `emit_cost_update(state)` (single cost_update event + `_save_cost_state_async` call).

- [ ] **Step 2: Replace the 5 call sites**

Each of the 5 duplicated blocks becomes one `emit_cost_update(...)` call; the CLI-owned turn uses the same helpers.

- [ ] **Step 3: Run tests and commit**

Run: `python3 -m pytest tests/test_serve_agent_cost.py tests/test_serve_cost.py tests/test_serve_agent.py tests/test_stream_contract.py -q` → PASS, then:

```bash
git add -A
git commit -m "refactor(serve): single cost aggregation path in agent loop"
```

### Task 6.12: Collapse result capping into one implementation

**Files:**
- Modify: `open_edit/serve/result_capper.py` (canonical `cap_tool_result`), `open_edit/serve/context_budget.py:140-158` (delete `summarize_tool_result` or make it delegate to `cap_tool_result`)
- Test: `tests/test_result_capper.py`, `tests/test_context_budget.py`, `tests/test_serve_agent.py`

- [ ] **Step 1: Compare the two**

Run: `sed -n '1,60p' open_edit/serve/result_capper.py` and `sed -n '130,170p' open_edit/serve/context_budget.py`
Confirm overlap (stdout/stderr/error caps, list caps at 20).

- [ ] **Step 2: Delete or delegate**

Delete `summarize_tool_result` and repoint its caller (agent.py:731 → the agent/ package) to `cap_tool_result`, or make `summarize_tool_result` a one-line call into `cap_tool_result`.

- [ ] **Step 3: Run tests and commit**

Run: `python3 -m pytest tests/test_result_capper.py tests/test_context_budget.py tests/test_serve_agent.py -q` → PASS, then:

```bash
git add -A
git commit -m "refactor(serve): single tool-result capping implementation"
```

---

## Phase 7 — Wire Orphaned Features + Final Polish

### Task 7.1: Wire the QC gate into the server render path

**Files:**
- Modify: `open_edit/kernel/render_service.py` (`_run` runs `run_qc_gate` after success; attach `qc_report` to the job result), `open_edit/serve/visual_verify.py` (consume deterministic spans as evidence for the LLM verdict), `open_edit/qc/gate.py` (implement the 6 documented checks from `skills/qc-standards.md`: streams, duration, audio_sync, black_frames, frozen_frames, overlays_burned — currently gate has 5 different checks; add ffprobe-based `streams`/`duration`/`frozen_frames` checks; move `no_word_split_check` → `open_edit/agent/skills/silence_cutter.py`)
- Test: `tests/test_qc/`, `tests/test_render_service.py`, `tests/test_visual_verify.py`

**Interfaces:**
- Consumes: `open_edit.qc.gate.run_qc_gate(path, ...) -> dict` (extend to return all 6 checks)
- Produces: `qc_report` dict on render job results; `visual_verify` receives spans

- [ ] **Step 1: Read qc-standards.md and gate.py**

Run: `cat skills/qc-standards.md` and `cat open_edit/qc/gate.py`
List the documented checks vs implemented checks; implement the missing ffprobe checks (they are cheap: `ffprobe -show_streams`, `-show_format` duration, frozen-frame via repeated frame extraction or scene-detect threshold).

- [ ] **Step 2: Move `no_word_split_check`**

Move to `agent/skills/silence_cutter.py` (its cut-policy logic); keep a thin re-export if `qc/gate.py` tests import it directly (update tests to the new home).

- [ ] **Step 3: Run QC in RenderService._run**

After a successful subprocess render, call `run_qc_gate(output_path)` and store the result on the job row (add a `qc_report` TEXT column via a migration `0006_render_job_qc.sql` — follow the migrations pattern from Task 6.3).

- [ ] **Step 4: Consume in visual_verify**

`visual_verify` builds LLM evidence from the deterministic spans (black frames, silence, duration) instead of sampling blind frames.

- [ ] **Step 5: Run tests and commit**

Run: `python3 -m pytest tests/test_qc/ tests/test_render_service.py tests/test_visual_verify.py tests/test_serve_render_jobs.py -q` → PASS, then:

```bash
git add -A
git commit -m "feat(qc): wire deterministic QC gate into server render path"
```

### Task 7.2: Wire `silence_compress` into the silence-cuts flow

**Files:**
- Modify: `open_edit/agent/tools/pyagent_propose_silence_cuts.py` (add `compress: bool = False` param; when true, call `open_edit.render.silence_compress.compress_silence(...)` for the proposed gaps), `open_edit/render/silence_compress.py` (delete unused `workers` param at :175)
- Test: `tests/test_silence_compress.py`, `tests/test_tools.py`

**Interfaces:**
- Consumes: `open_edit.render.silence_compress.compress_silence(input_path, gaps, output_path) -> Path`
- Produces: `propose_silence_cuts(args, project_path)` supporting `{"compress": true}`

- [ ] **Step 1: Read propose_silence_cuts**

Run: `cat open_edit/agent/tools/pyagent_propose_silence_cuts.py`

- [ ] **Step 2: Add the compress path**

When `args.get("compress")`, run `compress_silence` on the asset with the proposed gap spans, ingest the result as a new asset (reuse `AssetStore.ingest`), and return the new asset hash in the payload (`{"status": "ok", "compressed_asset_hash": ...}`).

- [ ] **Step 3: Remove the `workers` param**

Delete it from `compress_silence` and its call sites/tests.

- [ ] **Step 4: Run tests and commit**

Run: `python3 -m pytest tests/test_silence_compress.py tests/test_tools.py -q` → PASS, then:

```bash
git add -A
git commit -m "feat(tools): silence-cut compression via propose_silence_cuts"
```

### Task 7.3: Rename `kernel/render_service.py` → `kernel/render_jobs.py`

**Files:**
- Rename: `open_edit/kernel/render_service.py` → `open_edit/kernel/render_jobs.py`; class `RenderService` → `RenderJobService`; `DEFAULT_RENDER_SERVICE` → `DEFAULT_RENDER_JOB_SERVICE`
- Modify: importers (`serve/app.py`, `serve/agent/`, `mcp/adapters.py`, `kernel/tool_executor.py`, `kernel/__init__.py`, `serve/projects.py`, tests)
- Test: `tests/test_render_service.py` (rename to `tests/test_render_jobs.py`), full suite

**Interfaces:**
- Produces: `open_edit.kernel.render_jobs.RenderJobService`, `DEFAULT_RENDER_JOB_SERVICE`; keep module-level `public_job`, `RenderEnqueueError`

- [ ] **Step 1: Rename with git mv**

```bash
git mv open_edit/kernel/render_service.py open_edit/kernel/render_jobs.py
git mv tests/test_render_service.py tests/test_render_jobs.py
```

- [ ] **Step 2: Rename the class and the default instance**

`RenderService` → `RenderJobService`, `DEFAULT_RENDER_SERVICE` → `DEFAULT_RENDER_JOB_SERVICE` (both usages). Update all importers (grep).

- [ ] **Step 3: Run the full suite**

Run: `python3 -m pytest tests/ -q`
Expected: green.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(kernel): rename render_service to render_jobs (scheduler vs engine)"
```

### Task 7.4: Sync skills with code (harness_skills + qc-standards + remotion_motion)

**Files:**
- Modify: `open_edit/mcp/skills.py` (SKILL_FILES list — add any missing), `open_edit/harness_skills/` (sync the 8 advertised skills), `skills/qc-standards.md` (now accurate to gate.py from Task 7.1), `skills/remotion_motion.md` (sync forbidden-import list with `remotion_scaffold.py`)
- Test: `tests/test_mcp_server.py`, `tests/test_skill/`

**Interfaces:**
- Produces: wheel install exposes all 8 advertised skills; docs match code

- [ ] **Step 1: Sync harness_skills**

Copy the 8 `MCP_SKILL_STEMS` files from `skills/` into `open_edit/harness_skills/` (README, open-edit-mcp, open-edit-mcp-reference, tool_surface, edit-planning, remotion_motion, qc-standards, freeform_and_effects). Add a comment in both dirs: "generated — edit skills/ only".

- [ ] **Step 2: Reconcile the two skill docs**

Update `skills/qc-standards.md` to describe the actual 6-check gate (post Task 7.1); update `skills/remotion_motion.md` forbidden-import list to match `remotion_scaffold.py` (including `node:http`, `Function(` if present).

- [ ] **Step 3: Run tests**

Run: `python3 -m pytest tests/test_mcp_server.py tests/test_skill/ -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "docs(skills): sync harness skills and qc/remotion docs with code"
```

### Task 7.5: Final verification pass

**Files:**
- Test: entire repo

- [ ] **Step 1: Full test suite**

Run: `python3 -m pytest tests/ -q`
Expected: all green.

- [ ] **Step 2: Layering guards**

Run: `python3 -m pytest tests/test_layering.py -v`
Expected: 4/4 PASS.

- [ ] **Step 3: Dead-import sweep**

Run: `grep -rn "open_edit.serve" open_edit/kernel/ open_edit/mcp/ open_edit/ir/ | grep -v __pycache__` → empty.
Run: `grep -rn "sandbox_bridge\|pydantic_compat\|_cli_patch\|from \.render_service\|from \.tool_executor\|from \.tool_schemas" --include="*.py" open_edit/ | grep -v __pycache__` → empty.

- [ ] **Step 4: Module-size sanity**

Run: `find open_edit -name "*.py" | xargs wc -l | sort -rn | head -15`
Expected: no file above ~700 lines (allow `serve/agent/loop.py` near that bound; anything larger should be re-split in this task).

- [ ] **Step 5: Update docs and commit**

Update `README.md` and `docs/MCP.md` only where they reference deleted modules/features (grep for the deleted names). Update the repo-level `graphify-out` graph if regenerating is cheap:

```bash
git add -A
git commit -m "chore: final restructure verification and doc refresh"
```

- [ ] **Step 6: Report**

Summarize for the user: total lines deleted, files before/after, test count before/after, remaining known issues (if any).

---

## Post-Plan Note

After Task 7.5, the project graph should be re-extracted (`graphify extract . --code-only --global --as mlt-pipeline`) so the knowledge graph reflects the new structure — community count and god-node fan-in should drop substantially. Optionally store the new graph stats as a memory for future sessions.
