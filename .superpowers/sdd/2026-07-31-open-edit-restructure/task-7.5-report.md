# Task 7.5 Report — Final verification pass

**Date:** 2026-07-31
**Branch:** `open-edit-restructure`
**Commit:** `cf4703c` — `chore: final restructure verification — deferred-minor test cleanups`

## 1. Full test suite

```
PATH=<venv>/bin:$PATH python -m pytest tests/ -o addopts="" -q
```
**Result: 1119 passed, 6 skipped, 0 failed (47.0s).**

The 8 known environmentally-failing tests (test_cli*, test_cli_notes*, test_mcp_server) from the task preamble **all passed** in this run — zero failures, zero env issues detected. No regression classification needed.

## 2. Layering guards

```
pytest tests/test_layering.py -v
```
4/4 PASSED:
- `test_kernel_never_imports_serve` PASSED
- `test_ir_never_imports_upper_layers` PASSED
- `test_storage_never_imports_apply_or_api` PASSED
- `test_mcp_never_imports_serve` PASSED

## 3. Dead-import sweep

**Sweep 1** — `grep -rn "open_edit.serve" open_edit/kernel/ open_edit/mcp/ open_edit/ir/ | grep -v __pycache__` → **empty** (exit 1 = no matches). Kernel/MCP/IR never reference the serve layer.

**Sweep 2** — `grep -rn "sandbox_bridge\|pydantic_compat\|_cli_patch\|from \.render_service\|from \.tool_executor\|from \.tool_schemas" --include="*.py" open_edit/ | grep -v __pycache__` → 4 hits, **all false positives**:

| Location | Match | Verdict |
|---|---|---|
| `open_edit/kernel/schema_validator.py:11` | `from .tool_schemas import TOOL_BY_NAME` | Valid — `kernel/tool_schemas.py` exists (tracked, git ls-files ✓) |
| `open_edit/kernel/__init__.py:15` | `from .tool_executor import execute_tool, ...` | Valid — `kernel/tool_executor.py` exists (tracked ✓) |
| `open_edit/kernel/__init__.py:17` | `from .tool_schemas import TOOL_SCHEMAS` | Valid — see above |
| `open_edit/open_edit/kernel/schema_validator.py:11` | same | **UNTRACKED JUNK** — nested `open_edit/open_edit/` dir, 0 tracked files, stale pre-restructure copy (commit `9cd9189` deleted it; re-created on disk, untracked) |

The `tool_executor`/`tool_schemas` patterns target the *serve-layer* variants that were deleted; the kernel modules legitimately survive. **No dead imports of deleted modules anywhere in tracked code.**

## 4. Module-size sanity

```
find open_edit -name "*.py" | xargs wc -l | sort -rn | head -15
```

| # | Lines | File |
|---|---|---|
| 1 | 668 | `open_edit/serve/projects.py` |
| 2 | 615 | `open_edit/serve/agent/loop.py` |
| 3 | 610 | `open_edit/render/html_overlay.py` |
| 4 | 588 | `open_edit/serve/cli_adapter.py` |
| 5 | 580 | `open_edit/ir/validate.py` |
| 6 | 537 | `open_edit/cli.py` |
| 7 | 497 | `open_edit/ir/api.py` |
| 8 | 448 | `open_edit/agent/tools/pyagent_search_assets.py` |
| 9 | 446 | `open_edit/kernel/render_jobs.py` |
| 10 | 433 | `open_edit/serve/visual_verify.py` |
| 11 | 411 | `open_edit/agent/sandbox/backends.py` |
| 12 | 377 | `open_edit/ir/types.py` |
| 13 | 371 | `open_edit/open_edit/kernel/render_service.py` (untracked junk copy) |
| 14 | 335 | `open_edit/kernel/tool_executor.py` |
| — | 28,051 | total |

**No tracked file exceeds 700 lines.** Largest tracked file is `serve/projects.py` at 668. `serve/agent/loop.py` (615) is inside the allowed bound. No splitting needed.

## 5. Deferred-minor triage

Ledger items from the plan — all three actionable items were trivial and safe, fixed in this task:

- **(a) `testdata/README.md:72` pydantic_compat snippet** — **already fixed**, no action. The regenerate snippet now uses pydantic 2.x (`from pydantic import TypeAdapter`, `model_dump(mode='json')`); `grep pydantic_compat testdata/README.md` → no matches.
- **(b) unused `import pytest`** — **fixed** in `tests/test_style/test_notes_archive.py`, `tests/test_style/test_aggregate.py`, `tests/test_style/test_style_inject.py` (each had exactly one `pytest` occurrence = the import itself). Import blocks re-sorted per isort in test_notes_archive.py.
- **(c) dead `h =` assignment** — **fixed**. Was at `test_visual_verify.py:516` (ledger said :451, line drifted; the F841 flag confirmed it). Removed `h = _project_state_hash(...)`; test still passes.
- **(d) SIM117 nested `with`** — **fixed** in `test_serve_render_jobs.py:82` (`mock.patch` + `TestClient` combined into a single parenthesized `with`; body dedented accordingly).

**Lint verification:** `ruff check` on all touched files — errors went from 25 (at plan-start HEAD) → 18, **zero net-new findings**; remaining 18 are pre-existing UP017 (datetime.UTC) / E401 / RUF002 findings present before this task. All touched tests pass (47/47).

## 6. Docs

`grep -rn "sandbox_bridge\|_cli_patch\|tool_schemas\|render_service\|pydantic_compat\|commutativity\|schema\.sql" README.md docs/MCP.md` → **no matches**. Neither doc references any deleted module/feature; **no doc changes needed**.

## 7. Commit

`git add -u` only (untracked junk deliberately excluded, per brief). Commit `cf4703c` — 5 files changed, +34/−31.

**Known env note (not committed, informational):** the worktree root contains an untracked nested `open_edit/open_edit/` directory — a stale pre-restructure copy of the package (0 tracked files; re-created on disk since commit `9cd9189`). It is excluded from the commit and does not affect test collection (full suite green). A `graphify extract` run or fresh clone will not carry it; consider deleting it from the worktree if it lingers.

## Verdict

All verification steps pass. Suite fully green (1119/6/0 — the previously expected 8 env failures did not reproduce in this worktree). Layering guards 4/4. No dead imports, no oversized modules, docs already consistent, deferred minors cleared. **DONE.**
