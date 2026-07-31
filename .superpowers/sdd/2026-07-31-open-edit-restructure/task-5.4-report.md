# Task 5.4 Report: Split `sandbox_bridge.py` into `agent/sandbox/`

**Status: DONE_WITH_CONCERNS** (one cross-track dependency, see Concerns)

**Commit:** `9bcf6ab refactor(agent): split sandbox_bridge into agent/sandbox package` (branch `open-edit-restructure`)

## Function → new home

| Function / symbol | Old home | New home |
|---|---|---|
| `run_free_form` | `agent/sandbox_bridge.py` | `agent/sandbox/bridge.py` (re-exported from `agent/sandbox/__init__.py`) |
| `run_render` | `agent/sandbox_bridge.py` | `agent/sandbox/bridge.py` (re-exported) |
| `SandboxUnavailable` | `agent/sandbox_bridge.py` | `agent/sandbox/backends.py` (re-exported) |
| `MAX_FREEFORM_TIMEOUT_SEC`, `MAX_FREEFORM_MEM_MB` | `agent/sandbox_bridge.py` | `agent/sandbox/bridge.py` |
| `_validate_workdir` | `agent/sandbox_bridge.py` | `agent/sandbox/bridge.py` |
| `SandboxBackend` (ABC) | `agent/sandbox_bridge.py` | `agent/sandbox/backends.py` |
| `BwrapBackend` | `agent/sandbox_bridge.py` | `agent/sandbox/backends.py` |
| `DevSubprocessBackend` | `agent/sandbox_bridge.py` | `agent/sandbox/backends.py` |
| `get_sandbox_backend` | `agent/sandbox_bridge.py` | `agent/sandbox/backends.py` |
| `_resolve_sandbox_bin` | `agent/sandbox_bridge.py` | `agent/sandbox/backends.py` |
| `_resolve_render_binary` | `agent/sandbox_bridge.py` | `agent/sandbox/backends.py` |
| `resolve_binary` (new, shared by both resolvers) | — | `agent/sandbox/backends.py` |
| `_looks_like_bwrap_unavailable` | `agent/sandbox_bridge.py` | `agent/sandbox/backends.py` |
| `_sanitize_for_detail`, `_DETAIL_MAX_LEN` | `agent/sandbox_bridge.py` | `agent/sandbox/backends.py` |
| `PINNED_PYTHON_BIN`, `EXPECTED_PY_VERSION` | `agent/sandbox_bridge.py` | `agent/sandbox/backends.py` |
| `SANDBOX_BACKEND_ENV`, `_DEFAULT_SANDBOX_BACKEND` | `agent/sandbox_bridge.py` | `agent/sandbox/backends.py` |
| `_render_bootstrap` → `render_bootstrap` | `agent/sandbox_bridge.py` | `agent/sandbox/bootstrap.py` |
| `stage_and_collect` (new, shared by both `run()` bodies) | — | `agent/sandbox/staging.py` |
| `_validate_ops_incrementally` | `agent/sandbox_bridge.py` | `agent/sandbox/staging.py` |
| `_load_project_for_validation` | `agent/sandbox_bridge.py` | `agent/sandbox/staging.py` |
| `_load_assets_via_store` | `agent/sandbox_bridge.py` | `agent/sandbox/staging.py` |
| `_assets_dir_for_workdir` | `agent/sandbox_bridge.py` | `agent/sandbox/staging.py` |
| `_FlushingBuffer` | `agent/sandbox_bridge.py` | `agent/sandbox/staging.py` |
| `AssetStore` import | `agent/sandbox_bridge.py` | **dropped** (was unused) |

## Design notes

- **`stage_and_collect` contract** (`staging.py`): owns scratch-dir lifecycle
  (mkdir → write `code.py`/`_bootstrap.py` → executor → ops.jsonl validation →
  `shutil.rmtree` in `finally`, 6a). The backend passes a `render_bootstrap(ops_path)`
  callable (dev backend overrides `OPS_FILE` with the real scratch path) and an
  `execute(scratch, code_path, ops_path, bootstrap_path)` callable returning
  `(override_result | None, duration_s)`. Both `run()` bodies are now thin; the
  ~90%-duplicated staging/collect/cleanup exists once.
- **`render_bootstrap`** now inlines `inspect.getsource(_FlushingBuffer)` (the
  real class from `staging.py`) instead of a literal template copy, so the
  generated bootstrap cannot drift; added `from pathlib import Path` to the
  generated imports (the real class coerces `Path(ops_file)`).
- `resolve_binary(candidates, stem)` is the shared H5/P8 allow-list scanner;
  `_resolve_sandbox_bin` / `_resolve_render_binary` are thin wrappers (repo-root
  candidate path depth updated for the new package: 4 parents).
- `bridge.py` calls `backends.get_sandbox_backend()` / `backends._resolve_render_binary()`
  via module reference so tests can patch at the definition site (as they did before).
- `__init__.py` re-exports `run_free_form`, `run_render`, `SandboxUnavailable`
  plus the backend classes / `get_sandbox_backend` for test imports.
- `open_edit/agent/sandbox_bridge.py` deleted; all importers repointed
  (cli.py, agent/free_form.py, agent/tools/pyagent_run_python.py,
  agent/skills/motion_graphics/engine.py, plus 11 test files). Docstring/comment
  mentions updated in ir/validate.py, agent/exceptions.py, test_apply_free_form.py,
  test_ir/test_originating_note_id.py.

## Tests

- `tests/test_sandbox_bridge.py tests/test_sandbox_backends.py tests/test_sandbox_observations.py tests/test_free_form_e2e.py tests/test_free_form_exceptions.py tests/test_free_form_libs.py tests/test_pyagent_run_python.py tests/test_apply_free_form.py -q` → **PASS** (5 skipped: 4 strace fixtures absent, 1 dev-backend ro-bind e2e).
- `tests/test_layering.py -q` → **4/4 PASS**.
- Blast-radius extras: `test_windows_mcp.py test_cli_free_form.py test_pillar_headers.py test_sandbox/test_render_sandbox.py test_ir/test_originating_note_id.py test_skill/test_motion_graphics_templated.py test_health_diagnostics.py test_diagnostics.py test_tools.py test_serve_asset_stream.py test_serve_errors.py test_serve_projects.py test_serve_render_jobs.py` → **PASS** (all 79).
- Import sanity: package + all submodules import directly; generated bootstrap still execs with a custom globals dict.

## Concerns

1. **`open_edit/serve/diagnostics.py:89-91` still imports `open_edit.agent.sandbox_bridge`** — serve/ is owned by track-serve2 this wave (do-not-touch). It degrades gracefully (`except Exception: return False` → diagnostics reports sandbox unavailable on POSIX), and `test_windows_mcp.py`/`test_health_diagnostics.py` still pass, but it **must be repointed by track-serve2** (to `open_edit.agent.sandbox.backends._resolve_sandbox_bin`) or the merge leaves a broken reference. This is the only remaining `sandbox_bridge` reference in tracked `open_edit/` + `tests/`.
2. **`open_edit/tests/` (untracked legacy directory)** — a worktree-local, untracked copy of old tests (`open_edit/tests/test_windows_mcp.py` referenced `sandbox_bridge`). I updated its 4 references for grep cleanliness, but it is **not committed** (it is untracked; also references deleted modules like `render.orchestrator`, so it is already dead code). Do not `git add -A` in this worktree — it would sweep it in.
3. **Remaining `sandbox_bridge` substring hits** (all benign): the test *file name* `tests/test_sandbox_bridge.py` itself (kept — the brief's test list references it) and a docstring in `test_apply_free_form.py` pointing at that file name.
