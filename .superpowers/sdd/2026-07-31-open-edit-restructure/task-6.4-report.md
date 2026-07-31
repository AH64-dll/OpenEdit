# Task 6.4 Report — Single project-path resolution (`ProjectPaths`)

**Status: DONE**
**Commit: `886e6c8`** — `refactor(storage): single ProjectPaths layout resolver`

## Implementation

Created `open_edit/storage/paths.py` — the single source of truth for the on-disk layout:

```python
class ProjectPaths:
    root: Path                      # project ROOT dir (contains .open_edit/)
    for_project(project_path)       # root itself, or a file inside it (.kdenlive legacy)
    for_workdir(workdir)            # sandbox workdir: <root>/.open_edit (canonical) or <root> (legacy)
    db_path                         # canonical + legacy fallback — copied verbatim from _helpers._db_path
    notes_db_path                   # <root>/notes.db
    assets_dir                      # <root>/.open_edit/assets
    workdir                         # db_path.parent — the dir directly containing edit_graph.db
```

`_db_path` semantics preserved exactly (canonical wins for creation; legacy read-only fallback when the canonical file is absent and `.open_edit/` doesn't exist).

## Migration table

| Call site (before) | Resolution used (before) | After |
|---|---|---|
| `agent/tools/_helpers.py` `_db_path`/`_notes_db_path`/`_project_root` | canonical + legacy fallback (the reference impl) | Thin delegating wrappers → `ProjectPaths` (kept for backward compat; `tests/test_agent_loop_stability.py` pins them) |
| `kernel/edit_graph_service.py` `_db_path` (def) | canonical only (drift: no legacy fallback) | Local def deleted; `open_store` uses `ProjectPaths.for_project(...).db_path` (kernel→storage is legal) |
| `agent/tools/pyagent_generate_remotion_composition.py:42` | hardcoded `project / ".open_edit" / "edit_graph.db"` | `ProjectPaths.for_project(project_path)`; scaffold at `paths.root`, db at `paths.db_path` (now also finds legacy layouts) |
| `agent/sandbox/bridge.py` `_validate_workdir` | hand-rolled `workdir/edit_graph.db` existence check | Derives root via `ProjectPaths.for_workdir`; requires the resolved `paths.db_path == workdir / "edit_graph.db"` and exists — same accept-set for every reachable layout |
| `agent/sandbox/staging.py` `_assets_dir_for_workdir` | hand-rolled `<workdir>/assets` vs `<workdir>/.open_edit/assets` | Legacy `<workdir>/assets` honored when present; canonical fallback via `ProjectPaths.for_workdir(workdir).assets_dir` |
| `kernel/tool_executor.py` (3× `_db_path`) | `_helpers._db_path` | `ProjectPaths.for_project(...).db_path` |
| `agent/tools/pyagent_run_python.py` | `_db_path` + `Path(db_path).parent` | `paths.db_path` + `paths.workdir` (identical) |
| `agent/tools/pyagent_add_marker.py` / `pyagent_get_pending_notes.py` | `_notes_db_path` | `ProjectPaths.for_project(...).notes_db_path` |
| `agent/tools/pyagent_generate_visual_for_segment.py` | `_project_root` (passed to render sandbox, which requires `workdir/edit_graph.db` — latent canonical-layout bug) | `ProjectPaths.for_project(...).workdir` (db-containing dir) — fixes the canonical-layout render path, identical for legacy |

Untouched by design: `agent/style_inject.py` (keeps the thin `_helpers` wrappers — style-adjacent, zero churn), `serve/` (its inline canonical paths are the canonical convention the resolver documents), `cli.py` (CLI resolves `.open_edit` dirs directly).

## Tests

`pytest tests/test_tools.py test_tool_executor.py test_serve_agent_visual_verify.py test_pyagent_search_assets.py test_pillar_tools.py test_edit_graph_project_id.py test_free_form_e2e.py test_sandbox_bridge.py -q` → **167 passed, 1 skipped** (pre-existing bwrap/dev-backend env skip).

`pytest tests/test_layering.py -q` → **4/4**. Also ran `test_agent_loop_stability.py` (10/10 — pins `_helpers` wrapper behavior), `test_sandbox_backends.py`, `test_cli_free_form.py` (11/11) — all pass.

Grep `def _db_path|def _project_root|def _notes_db_path` → only the three thin delegating wrappers in `_helpers.py` remain (allowed); zero local definitions elsewhere. A `ProjectPaths` smoke test confirmed canonical/legacy/default-for-creation/`.kdenlive`/`for_workdir` round-trips.

## Concerns

1. `_validate_workdir` is now marginally stricter on a pathological mixed layout: a legacy workdir (`<root>`) that ALSO has a `.open_edit/` directory (but the db only at root) is rejected, because `ProjectPaths.db_path` prefers the canonical branch when `.open_edit/` exists. No in-tree caller can produce this state (`pyagent_run_python`/`generate_visual_for_segment` pass `db_path.parent`, which is already canonical-biased); I judge the explicit rejection of an ambiguous layout safer than silent guessing.
2. `serve/projects.py:403` still constructs `IRProject(workdir=path)` with the project ROOT, while the sandbox `_validate_workdir` requires the db-containing dir — for canonical-layout projects `run_free_form_code` via serve would fail validation today. Pre-existing, in `serve/` (out of scope this wave); flagging for the serve track.
3. `storage/assets.py:88-92` has its own legacy `project_path/assets` read-fallback in `_scan`; left as-is (read-only inventory path, not one of the four drift sites). Could fold into `ProjectPaths.assets_dir` later.
4. Committed only the 11 changed tracked files; the worktree root still has untracked junk (`open_edit/open_edit/`, desktop files, plans) that predates this task — not staged.
