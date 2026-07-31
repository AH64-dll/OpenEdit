# Task 6.1 Report — Create `ir/ids.py` and migrate id/timestamp generators

**Status:** DONE_WITH_CONCERNS
**Commit:** `c628f28` (`refactor(ir): single ids module; migrate id/timestamp generators`)
**Tests:** 302 passed (217 storage/ir/job_lock/migrations + 81 serve_projects/serve_agent/style/sandbox_bridge + 4 layering), 0 failed.

## Generator → migration table

| Generator | Migrated from | Migrated to | Call sites updated |
|---|---|---|---|
| `new_id()` (`str(uuid.uuid4())`) | `open_edit/ir/types.py:16` | `open_edit/ir/ids.py:14` | re-exported via `types.py` import (all existing `from open_edit.ir.types import new_id` imports keep working, incl. `edit_graph.py`, `sandbox_bridge.py` inspect.inlining) |
| `now_iso8601()` (`datetime.now(timezone.utc).isoformat()`) | `open_edit/ir/types.py:21` | `open_edit/ir/ids.py:19` | re-exported via `types.py` import (default factories at `types.py` 141/382) |
| `new_note_id()` (`note_<hex12>`) | `open_edit/storage/notes.py::_new_id` | `open_edit/ir/ids.py:24` | `notes.py` `ReviewNote.note_id` default_factory |
| `new_version_id()` (`v_<hex12>`) | `open_edit/storage/render_snapshots.py::_new_version_id` | `open_edit/ir/ids.py:29` | `render_snapshots.py` `RenderSnapshot.version_id` default_factory |
| `now_iso8601` (was `_now_iso`) | `open_edit/storage/edit_graph.py:95` (staticmethod) | `open_edit/ir.ids.now_iso8601` | `edit_graph.py` 2 sites (append event, update_status event) |
| `now_iso8601` (was `_now_iso`) | `open_edit/storage/job_lock.py:18` (module fn) | `open_edit/ir.ids.now_iso8601` | `job_lock.py` 3 sites (try_acquire, release, stale-lock release) |
| `now_iso8601` (was `_now_iso`) | `open_edit/storage/commands.py:45` (staticmethod) | `open_edit/ir.ids.now_iso8601` | `commands.py` record_command |
| `now_iso8601` (was `_now_iso`) | `open_edit/storage/timeline_cache.py:55` (staticmethod) | `open_edit/ir.ids.now_iso8601` | `timeline_cache.py` save_timeline_snapshot |
| `now_iso8601` (was inline lambda / inline call) | `open_edit/storage/notes.py:73, 208` | `open_edit/ir.ids.now_iso8601` | `ReviewNote.created_at` default_factory, `mark_processed` |
| `now_iso8601` (was inline lambda) | `open_edit/storage/render_snapshots.py:32` | `open_edit/ir.ids.now_iso8601` | `RenderSnapshot.created_at` default_factory |
| — | `open_edit/agent/sandbox_bridge.py` labels | updated provenance labels | `INLINED: open_edit/ir/types.py:new_id|now_iso8601` → `ir/ids.py` (source-inlining behavior unchanged; `inspect.getsource` resolves through the import to ids.py, output byte-identical since defs kept verbatim) |

## Format decisions (real formats govern, brief's sample was wrong)

- `new_id()` is **`str(uuid.uuid4())`** (hyphenated), NOT `uuid.uuid4().hex` as the brief's sample shows — copied from `types.py`.
- `now_iso8601()` is **`datetime.now(timezone.utc).isoformat()`** (microseconds + `+00:00`), NOT `time.strftime` — copied from `types.py`. Kept as-is because `sandbox_bridge` source-inlines it into the sandbox bootstrap and tests exercise that path.
- `new_note_id()` / `new_version_id()` use `uuid4().hex[:12]` (brief sample correct) — verified against `notes.py`/`render_snapshots.py` originals.

## Drift findings (brief lines no longer valid)

- `serve/app.py:688` and `style/aggregate.py:63`: **no inline timestamps remain** in either file (verified with rg for `strftime|isoformat|time.`). Nothing to migrate — parallel-track safe, no edits needed.
- `render/ingest.py` (Task 1.6) and `style/taste_events.py` (Task 1.7): confirmed deleted.
- `edit_graph.py:92` → `_now_iso` was at line 95; `job_lock.py:18` → was correct at 18.

## Unmigrated duplicates (out of scope — left for parallel track / later tasks)

- `serve/routers/projects.py:198` — inline `datetime.now(timezone.utc).isoformat()`; in `serve/`, not authorized this wave (parallel track owns serve/).
- `serve/agent/history_store.py:101` (`uuid4().hex`), `serve/routers/projects.py:101,192`, `kernel/render_service.py:258`, `agent/tools/pyagent_run_python.py:24` (`pyagent_<hex12>`), `job_lock.py:32` (`str(uuid.uuid4())` inline for job_id) — format-specific IDs, not in the 22 call-site list; step-7 grep does not cover them.

## Verification

- Step 7 grep (`def _new_id|def _new_version_id|def _now_iso|def new_id|def now_iso8601` in open_edit/ + tests/): **only `ir/ids.py` matches** — PASS.
- Import/format sanity check: all 4 generators + `ReviewNote`/`RenderSnapshot` defaults verified (prefixes, lengths, ISO shape, `uuid.UUID(new_id())`).
- `test_layering.py`: 4/4 PASS.
- Unused imports removed (uuid/datetime/timezone) from all migrated storage modules; `job_lock.py` and `notes.py` keep `datetime` for the stale-lock cutoff / retention cutoff.

## Concerns

1. `serve/routers/projects.py:198` remains a duplicated inline timestamp (out of scope this wave — serve/ owned by track-serve2). Recommend follow-up task.
2. `test_job_lock.py` collection error hit earlier was caused by a transient broken edit (line-join) in `edit_graph.py`, fixed before commit; not present in the commit.
