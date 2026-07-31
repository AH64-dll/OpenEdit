# Open Edit Blueprint (fixed)

Verified against `open_edit/` + `graphify-out/` (2026-08-01).
Graph: ~4815 nodes · ~11233 edges · god node `EditGraphStore` ≈ **211** edges.
Layering enforced by `tests/test_layering.py` (passes).

The whole product is one package: **`open_edit/`**.
Dependencies flow **downward**. Lower packages never import higher ones
(with one documented exception in QC).

---

## Package map (not “exactly 4 layers”)

Think in **bands**, not a rigid 4-box stack. Eight product packages + a small style helper:

```
ENTRY / ADAPTERS
  open_edit/cli.py
  open_edit/serve/app.py          ← FastAPI process
  open_edit/mcp/server.py         ← IDE MCP (stdio)
  open_edit/serve/pi_bridge.py    ← Pi / CLI tool bridge (lives under serve/)

PRESENTATION / IO
  open_edit/serve/                FastAPI, WS, auth, upload, routers, cost
    routers/  ws/  agent/loop.py  llm/  auth  upload  projects  visual_verify

DISPATCHER + TOOLS  (converge here)
  open_edit/kernel/               ONE dispatcher, schemas, render jobs
  open_edit/agent/                free_form, sandbox/, tools/ (TOOL_TABLE), skills/

DOMAIN + SIDE EFFECTS  (siblings; render depends on storage)
  open_edit/ir/                   pure timeline math — no files/network
  open_edit/storage/              SQLite: edit graph, assets, notes, paths, cache
  open_edit/render/               timeline_plan → melt / remotion / ffmpeg
  open_edit/qc/                   post-render quality gate
  open_edit/style/                style profile retrieve / pin (used by agent tools)
```

### Hard rules (`tests/test_layering.py`)

| Package   | Must not import                                      |
|-----------|------------------------------------------------------|
| `ir`      | `agent`, `storage`, `serve`, `kernel`                |
| `kernel`  | `serve`                                              |
| `mcp`     | `serve`                                              |
| `storage` | `ir.apply`, `ir.api`, `ir.factory`                   |
|           | (allowed: `ir.types`, `ir.ids`, `ir.hash`, `ir.derive`, `ir.validate`) |

`ir` = pure domain. Everything else may call downward into it.
`render` → `storage` is expected (assets, edit graph, timeline cache).
`qc` → `render.ffmpeg_probe` is expected.

**Exception:** `qc/gate.py` re-exports `no_word_split_check` from
`agent.skills.silence_cutter` for backward compatibility. Real detectors
(`frozen_frames`, `black_frames`, `silence`) stay inside `qc/`.

---

## Layered architecture (corrected)

```
                    ┌──────────────────────────────────────────────┐
    ENTRY           │  cli.py   serve/app.py   mcp/server.py       │
                    │  serve/pi_bridge.py                          │
                    └───────────────────┬──────────────────────────┘
                                        │
                    ┌───────────────────▼──────────────────────────┐
    PRESENTATION    │  open_edit/serve/                            │
                    │  routers/  ws/  agent/loop.py  llm/  auth    │
                    │  upload  cost  projects  visual_verify       │
                    └───────────────────┬──────────────────────────┘
                                        │ tool calls
                    ┌───────────────────▼──────────────────────────┐
    DISPATCHER      │  open_edit/kernel/                           │
                    │  tool_executor  schema_validator  pillar_    │
                    │  tools  render_jobs  edit_graph_service      │
                    └───────────────────┬──────────────────────────┘
                                        │ TOOL_TABLE lookup
                    ┌───────────────────▼──────────────────────────┐
    AGENT TOOLS     │  open_edit/agent/                            │
                    │  tools/ (27 TOOL_TABLE callables) free_form  │
                    │  sandbox/  skills/ (silence, music, sfx…)    │
                    │  style/ + skills/style-memory.md             │
                    │  search_assets → Pexels/Freesound/Openverse  │
                    └─────────┬───────────────────┬────────────────┘
                              │                   │
              ┌───────────────▼──────┐   ┌────────▼─────────────────┐
              │ open_edit/ir         │   │ open_edit/storage         │
              │ PURE DOMAIN          │   │ SQLite persistence        │
              │ types apply_* derive │   │ edit_graph.py (god node)  │
              │ hash validate ids    │   │ assets notes paths db     │
              └──────────────────────┘   │ ordering timeline_cache   │
                                         └────────────▲──────────────┘
                                                      │ uses
                                         ┌────────────┴──────────────┐
                                         │ open_edit/render          │
                                         │ timeline_plan melt remotion│
                                         │ orchestrator ffmpeg_probe │
                                         └────────────┬──────────────┘
                                                      │ after render
                                         ┌────────────▼──────────────┐
                                         │ open_edit/qc              │
                                         │ gate frozen/black/silence │
                                         └───────────────────────────┘
```

---

## Two runtime flows (same tools)

### Editing session (web UI)

```
browser
  → serve/ WS
  → serve/agent/loop.py
  → kernel/tool_executor.execute_tool   ← ONE dispatcher
  → agent/tools/*  (TOOL_TABLE)
  → ir / storage / render / qc
  ← reply via loop + serve/llm/
```

### MCP session (IDE)

```
editor
  → mcp/server.py
  → mcp/adapters.dispatch_mcp_tool
  → kernel/tool_executor.execute_tool   ← same dispatcher
  → agent/tools/*  (same TOOL_TABLE)
```

Pi / extension path is the same idea: `serve/pi_bridge.py` → `execute_tool`.

Fixing a tool in `agent/tools/` fixes web UI, MCP, and Pi together.

### Tool surface

| Surface | Count | Where |
|---------|-------|--------|
| `TOOL_TABLE` callables | **27** | 20 `pyagent_*.py` (incl. `capture_style_hint`) + 7 timeline ops |
| Kernel-handled (not in table) | 5 | `query_project`, `edit_project`, `trigger_render`, `get_render_job`, `cancel_render_job` |
| MCP / Pi pillar schemas | 6 registry names | `kernel/tool_registry.py` (+ render job helpers) |

Pillars (`query_project` / `edit_project`) route into `TOOL_TABLE` via `kernel/pillar_tools.py`.

**Agent-tools rules:** keep sandbox (set `OPEN_EDIT_SANDBOX_BACKEND=dev` for local productivity if bwrap fails); **search before generate**; capture confirmed style via `capture_style_hint` / pins (`skills/style-memory.md`).

---

## Debugging each subsystem

| # | Package | What it does | Key files |
|---|---------|--------------|-----------|
| 1 | `ir/` | Timeline model, apply ops, hash, validate, derive | `apply.py`, `apply_clips.py`, `apply_effects.py`, `apply_audio.py`, `derive.py`, `hash.py`, `validate.py`, `types.py` |
| 2 | `storage/` | SQLite persistence | `edit_graph.py` (**EditGraphStore**, ~211 edges), `db.py`, `assets.py`, `notes.py`, `ordering.py`, `paths.py`, `timeline_cache.py` |
| 3 | `kernel/` | Dispatcher + envelopes + render queue + edit-graph commands | `tool_executor.py`, `schema_validator.py`, `pillar_tools.py`, `render_jobs.py`, **`edit_graph_service.py`** |
| 4 | `agent/` | Free-form parse, sandbox, 27 tools, skills | `free_form.py`, `sandbox/`, `tools/`, `skills/` |
| 4b | `style/` + `skills/style-memory.md` | Style profile pins/hints for agents | `aggregate.py`, `retrieve.py`, `style_inject.py`, `capture_style_hint` |
| 5 | `render/` | Timeline → melt/ffmpeg/Remotion | `timeline_plan.py`, `melt_runner.py`, `orchestrator.py`, `snapshot_recorder.py`, `ffmpeg_probe.py`, `remotion/` |
| 6 | `qc/` | Post-render gate | `gate.py`, `frozen_frames.py`, `black_frames.py`, `silence.py` |
| 7 | `serve/` | HTTP/WS, chat loop, LLM, cost, auth | `app.py`, `agent/loop.py`, `llm/dispatcher.py`, `cost.py`, `routers/` |
| 8 | `mcp/` | IDE tool/skill surface | `server.py`, `adapters.py`, `skills.py` |

Also: `cli.py` for local commands without the server.

---

## Symptom → where to look

| Symptom | Go to |
|---------|--------|
| Timeline wrong after an edit | `ir/apply*` → `ir/derive.py` → `storage/edit_graph.py` (commands via `kernel/edit_graph_service.py`) |
| Edit lost after restart | `storage/db.py`, `storage/edit_graph.py`, `storage/ordering.py` |
| Video missing / black / wrong duration | `render/timeline_plan.py` → `render/melt_runner.py` → `render/orchestrator.py` |
| Frozen / black frame / silence flagged | `qc/` (`frozen_frames.py`, `black_frames.py`, `silence.py`, `gate.py`) |
| Tool call errors in chat | `kernel/tool_executor.py` → specific `agent/tools/pyagent_*.py` |
| Chat loop / tokens / cost weird | `serve/agent/loop.py` → `serve/llm/dispatcher.py` → `serve/cost.py` |
| API 404 / 500 | `serve/routers/*.py` (assets, ops, projects, renders, config) |
| LLM not responding / bad provider | `serve/llm/keys.py`, `serve/providers.py`, `serve/llm_config.py` |
| Python tool won’t run in agent | `agent/sandbox/bootstrap.py`, `agent/sandbox/bridge.py` |
| IDE doesn’t show tools | `mcp/server.py`, `mcp/adapters.py` |
| Style profile wrong / pins ignored | `style/`, `skills/style-memory.md`, `capture_style_hint` / `set_pinned_value` |
| Stock search bad / generates instead of search | `agent/tools/pyagent_search_assets.py` (Pexels/Freesound/Openverse) |
| Sandbox / run_script unavailable | `serve/diagnostics.py` → set `OPEN_EDIT_SANDBOX_BACKEND=dev` |

---

## Mental model (one sentence)

**serve/mcp/cli talk to users → kernel dispatches → agent tools mutate IR and storage → render builds video → qc checks it.**
