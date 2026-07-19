# pyagent — pi extension for Kdenlive editing

A pi extension that gives pi 13 video-editor tools, backed by Phase 2's
`KdenliveFileBackend`. pi handles the LLM; this extension just bridges
LLM tool calls to file edits.

## Install

```bash
cd pyagent-kdenlive-guide/phase3_pyagent_core
make install
```

This:
1. Symlinks the extension into `~/.pi/agent/extensions/pyagent/` so pi
   auto-discovers it.
2. Installs the Python runtime in editable mode so `python3 -m
   phase3_pyagent_core` is importable from anywhere.

## Use

```bash
export PYAGENT_PROJECT=/path/to/your.kdenlive
export PYAGENT_AUTO_APPROVE=false    # default; prompts before each mutating tool
pi    # the pyagent_* tools appear in the tool palette
```

## File map (post-2026-07-19 cleanup)

| File | Purpose | Lines |
|---|---|---|
| `extension.ts` | Thin pi-extension loader (re-exports `register` from `runtime.py`'s `json_schema` of every tool) | ~120 |
| `runtime.py` | The bridge: JSON-RPC handler + `Type.Object` schema assembly (the BUG 11 fix lives here) | 192 |
| `phase3_types.py` | Typed dicts used by the JSON-RPC payload | 31 |
| `__main__.py` | `python3 -m phase3_pyagent_core` entry: `run_op`, `help`, `humanize` | 31 |
| `catalog_slice.py` | Loads `phase1_knowledge_base/catalog.json` and exposes a search/filter API | 50 |
| `tools/bin.py` | `pyagent_import_media` definition | 20 |
| `tools/clips.py` | 5 clip op definitions (`insert_clip`, `append_clip`, `move_clip`, `trim_clip`, `delete_clip`) | 78 |
| `tools/transitions.py` | `pyagent_add_transition` definition | 26 |
| `tools/effects.py` | `pyagent_apply_effect` definition | — |
| `tools/markers.py` | `pyagent_add_marker` definition | 37 |
| `tools/project.py` | 3 read-only project queries (`get_project_info`, `get_timeline_summary`, `list_catalog`) | 56 |
| `tools/catalog.py` | Catalog-list tool | 24 |
| `tools/render_qc.py` | 6 Phase 6 tool definitions (re-exported from `phase6_render_qc`) | 81 |

19 tools total: 13 file-mode edit tools (3 of which also support
live-mode D-Bus) + 6 render/QC tools.

## Test

```bash
make test                                # 41 passed, 1 skipped
```

Per-test-file:

| File | Tests | Purpose |
|---|---|---|
| `test_runtime.py` | 16 | JSON-RPC dispatch, schema, error mapping |
| `tests/test_golden_io.py` | 6 | 19 tool JSON I/O outputs are locked (golden-file) |
| `test_extension.py` | 6 | pi-extension registration |
| `test_catalog_slice.py` | 6 | catalog load + filter |
| `tests/test_tools.py` | 3 | per-tool dispatcher |
| `tests/test_runtime.py` | 3 | runtime-level smoke |
| `test_integration.py` | 1 | full crossfade chain end-to-end (skips if no LLM provider) |

The integration test needs an LLM provider configured (e.g.,
`OPENAI_API_KEY` or `GEMINI_API_KEY`) and will skip if none is set.

## See also

- `DESIGN.md` — the design spec
- `system_prompt.md` — the prompt fragment the LLM sees for this extension
- `../BUGS_FIXED.md` — full list of 13 phase-3-related bugs fixed during
  the 2026-07-19 cleanup (Type.Object schema binding, thin-loader
  rewrite, golden-file I/O tests, etc.)
