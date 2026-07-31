# OpenEdit — Graph-Grounded Architecture & Plan

**Source of truth:** `open_edit/graphify-out/graph.json` (AST-extracted, no LLM
guessing) — 4,199 nodes / 10,398 edges / 202 communities, built 2026-07-28 from
commit `79f303eb`. Scope: `open_edit/` only (the actual product), with
`.venv/`, caches, `.agents/` orchestration scratch, `.open_edit/` runtime
state, `plans/`, `docs/`, and the `o-2`/`test` external symlinks excluded via
`open_edit/.graphifyignore` — this is the functional codebase, not the
surrounding scaffolding.

Re-run after future edits with:
```bash
cd open_edit && graphify update . --no-cluster   # fast, no LLM, AST only
graphify cluster-only . --no-label --no-viz       # refresh communities
```
Query it any time with the `graphify` MCP tools (`query_graph`, `god_nodes`,
`get_neighbors`, `get_community`) pointed at `project_path:
/home/ah64/apps/mlt-pipeline/open_edit`.

---

## 1. What OpenEdit actually is

`open_edit/` is a Python, AI-native video editor prototype (explicitly
labeled experimental relative to the repo's Go/MLT production pipeline in
`cmd/`/`internal/`). It has its own full stack:

- **FastAPI server + static browser UI** (`open_edit/serve/`) — chat-driven
  editor with a built-in agent loop, or a "review-only" mode with no LLM.
- **Standalone MCP stdio server** (`open_edit/mcp/`) — lets an external agent
  host (Cursor, Claude Code, MCP Inspector) drive the same project directly,
  bypassing the FastAPI server's own agent loop.
- **Canonical IR / edit graph** (`open_edit/ir/`, `open_edit/storage/`) — a
  Pydantic operation model (`AddClipOp`, `TrimClipOp`, `AddEffectOp`, …)
  replayed into a `Timeline`, persisted as an append-only op log in SQLite
  (`EditGraphStore`).
- **Render pipeline** (`open_edit/render/`) — MLT/`melt` XML emission,
  Remotion composition materialization, ffmpeg graphics burn-in, GPU/CPU
  encoder selection, render caching and snapshotting.
- **Sandbox** (`sandbox/`, Rust) — a bubblewrap/seccomp/cgroup jail binary
  that the Python side (`agent/sandbox_bridge.py`) shells out to for
  free-form agent-written Python (`run_script`).
- **Agent tool surface** (`open_edit/agent/`) — ~20 `pyagent_*` tools (ingest,
  transcript packing, silence cuts, narrative analysis, music/SFX, Remotion
  scaffolding) plus reusable "skills" they call into.

### Graph-derived "god nodes" (the real core abstractions)

| Node | Edges | Role |
|---|---:|---|
| `EditGraphStore` (`storage/edit_graph.py`) | 219 | SQLite-backed append-only op log; single source of truth for every mutation |
| `AddClipOp` (`ir/types.py`) | 173 | Most-referenced operation type |
| `Timeline` (`ir/types.py`) | 150 | Derived, replay-computed view of the graph |
| `Project` (`ir/types.py`) | 142 | Root container (assets + tracks + ops) |
| `AssetStore` (`storage/assets.py`) | 96 | Content-addressed media store |
| `apply_operation()` (`ir/apply.py`) | 94 | The op-replay function that builds `Timeline` from ops |
| `IR` (`ir/api.py`) | 77 | Fluent op-builder API used by tools and `run_script` |

This confirms the architecture is genuinely **event-sourced**: nothing
mutates `Timeline` directly — every change is an `Operation` appended to
`EditGraphStore`, and `Timeline` is always *derived* via `derive_timeline()` /
`apply_operation()`. That single fact should discipline every future change:
if a feature needs new editor behavior, it needs a new `Operation` subtype +
`apply_operation()` handler, not a side-channel mutation.

### Two front doors, one kernel (by design — confirmed via graph traversal)

```
Browser UI ──WS/HTTP──▶ serve/app.py ──▶ serve/agent.py (built-in loop)
                                              │
Cursor/Claude ──stdio──▶ mcp/server.py ──▶ mcp/adapters.py
                                              │
                                              ▼
                              open_edit/kernel/{pillar_tools,tool_executor,
                              tool_registry,tool_schemas,schema_validator,
                              edit_graph_service,render_service}.py
                                              │
                                              ▼
                         ir/{types,api,apply,validate}.py + storage/*.py
                                              │
                                              ▼
                         render/{orchestrator,emitter,materialize,remotion,
                                 graphics_overlay,encoder,cache}.py
```

Both entry points now dispatch through `open_edit/kernel/` — this is a
**recent, in-progress consolidation** (see §2.1) that unifies "AI edits the
project through chat" and "Cursor edits the project through MCP" onto one
tool implementation, which is the correct direction and should be finished,
not re-litigated.

---

## 2. Specific points the graph surfaced (concrete, file-level)

### 2.1 The `kernel/` migration is real but incomplete — finish it, then delete the shims

Git status + the graph agree: `open_edit/kernel/` (new, untracked, 1,320
lines across `edit_graph_service.py`, `pillar_tools.py`, `render_service.py`,
`schema_validator.py`, `tool_executor.py`, `tool_registry.py`,
`tool_schemas.py`) is the **new canonical home** for tool dispatch. The old
`open_edit/serve/{tool_executor,pillar_tools,tool_registry,tool_schemas,
schema_validator,edit_graph_service,render_service}.py` are now 2-line
compatibility shims (`from open_edit.kernel.X import *`).

The graph shows the migration is **not fully cut over**:

- `open_edit/serve/pi_bridge.py:36,414` still imports
  `open_edit.serve.schema_validator` / `open_edit.serve.tool_schemas`
  directly (old path) instead of `open_edit.kernel.*`.
- `open_edit/serve/pi_extension/extension.ts:67` still references
  `open_edit.serve.tool_schemas` in a generated Python one-liner.
- 21 references across `tests/` still import from the old `serve.*` shim
  paths.

**Action:** repoint `pi_bridge.py`, the pi extension script, and the 21 test
imports at `open_edit.kernel.*`, run the full suite, then delete the 7 shim
files in `serve/`. Until that happens, don't add a *third* place that
imports either path — always import from `kernel/`.

### 2.2 Two divergent implementations of the same skill — one orphaned, one live and weaker

`silence_cutter.py` and `narrative_analyzer.py` each exist in **two
places** with materially different logic, and the *better* version is not
wired into the runtime at all:

| | Wired in? | Behavior |
|---|---|---|
| `open_edit/open_edit/agent/skills/silence_cutter.py` | **Yes** — imported by `agent/tools/pyagent_propose_silence_cuts.py:49` | Simple gap detection, flat `min_segment_s` merge only |
| `/skills/silence_cutter.py` (repo-root docs folder) | No | Adds breath-keep policy (`keep_breath_ms`), boundary min-segment protection, `gap_after_s` — this is the version documented in `STABILIZATION_REPORT.md §7.1` as the "more sophisticated version" |
| `open_edit/open_edit/agent/skills/narrative_analyzer.py` | **Yes** — imported by 4 tools (`pyagent_analyze_narrative`, `pyagent_generate_visual_for_segment`, `pyagent_select_music`, `pyagent_place_sfx`) | Naive fixed 5-second window segmentation |
| `/skills/narrative_analyzer.py` | No | Sentence-aligned segmentation (punctuation + pause-based), `gap_after_s` per segment |

Because `narrative_analyzer` feeds 4 downstream tools, this single stale
module is a multiplier: fixing it once upgrades silence cuts, visual
placement, music selection, and SFX placement simultaneously.

**Action:** treat `/skills/*.py` as the reference implementation, port it
into `open_edit/agent/skills/`, update the 4+ call sites' expectations, add
regression tests pinned to the new signature (`asset_duration_s=`,
`keep_breath_ms=`, `min_segment_s=`), then either delete the root `skills/`
`.py` copies or make them thin re-exports so there is exactly one
implementation. Also delete the two stray compiled `skills/*.cpython-312.pyc`
files checked into that folder — they're build artifacts, not source.

### 2.3 JCode is still half-registered (unresolved since the last stabilization pass)

`open_edit/serve/providers.py:190` registers a full `jcode` `ProviderSpec`
(label, default model, binary name), but `open_edit/serve/cli_adapter.py` has
no `jcode` entry — `get_adapter("jcode")` still raises `KeyError`. This
matches `STABILIZATION_REPORT.md` limitation #2, which was never closed.

**Action:** per `OpenEdit_Repair_Plan.md` OE-P0-001/002: either implement and
test a real `_JCodeAdapter` in `cli_adapter.py`, or delete `jcode` from
`providers.py` and every registry until it's ready. Leaving it half-wired is
worse than either extreme — a user can select it in the UI and get an
unhandled `KeyError` at runtime.

### 2.4 MCP server is correctly wired, not dead code

Verified end-to-end: `pyproject.toml:45` registers the `open-edit-mcp`
console script → `open_edit.mcp.server:main`; `cli.py:367` also exposes
`open_edit mcp` as a subcommand; `mcp/adapters.py` calls
`kernel/tool_registry.py:build_tool_schemas()` and dispatches through
`kernel/pillar_tools.py`. `docs/MCP.md` documents the same tool surface the
graph shows (`query_project`, `edit_project`, `run_script`,
`trigger_render`, `get_render_job`, `cancel_render_job`). This subsystem is
new (this week, per file mtimes) but structurally sound — no orphaned code
here, just needs the real-Cursor-client smoke test in §3.

### 2.5 Render pipeline is fully wired, multi-backend, and is the most complex single subsystem

`render/orchestrator.py:render_project()` is the actual fan-in point: it
calls `ir/apply.py:derive_or_load_timeline()`, strips Remotion-only clips
(`_timeline_without_remotion_clips()`), materializes Remotion compositions to
CAS clips (`render/materialize.py`), emits MLT XML
(`render/emitter.py:emit_timeline()`), builds the `melt` command
(`_build_melt_command()`), then burns HTML/Remotion graphics on top via
ffmpeg (`render/graphics_overlay.py:burn_overlays()`), with GPU/CPU encoder
selection (`render/encoder.py`) and content-hash render caching
(`render/cache.py`, `storage/render_snapshots.py`). This confirms README's
"three motion-graphics backends" claim (MLT tracks, HyperFrames overlays,
Remotion → CAS clip) is real and implemented, not aspirational — but it is
also the subsystem with the most moving parts and the most external-process
dependencies (`melt`, `ffmpeg`, `node`/Remotion CLI, optionally GPU codecs),
which is where most of the "known experimental limits" in `README.md`
concentrate.

### 2.6 The old `OpenEdit_Repair_Plan.md` is ~70% executed — don't re-run it blind

Cross-checking `STABILIZATION_REPORT.md` against the current graph: OE-P0-001
(provider registry), OE-P0-002 (agent_mode), OE-P0-003/OE-P1-010 (multi-file
ingest), OE-P0-004 (WS auth), OE-P1-005 (TOML preservation), OE-P1-009
(durable `RenderService` — now further consolidated into
`kernel/render_service.py`), OE-P1-011/012/013 (project init, timeline
summary, optimistic concurrency) are all reported fixed with passing
regression commands. Test collection today (`pytest --collect-only`) is
clean across all 147 test files / 138 modules with zero import errors, so
the kernel/mcp work sitting on top hasn't broken that baseline.

**Still genuinely open** from that plan (confirmed still true today, not
just historically):
- JCode (§2.3 above).
- Golden end-to-end workflow (`STABILIZATION_REPORT.md §6`: "Not yet
  implemented") — no Playwright/browser E2E found in the graph's community
  breakdown; UI tests are all Node-DOM-stub unit tests (`Community 38, 64,
  80, 106, 107, 111` etc.), not real-browser tests.
- Phase 8 (Go/Python contract parity) — out of scope for `open_edit/` itself
  by definition, but still listed as required for the plan's "Definition of
  Done".

---

## 3. Recommended plan (dependency-ordered)

**P0 — Finish what's mid-flight before adding anything new**

1. Cut `pi_bridge.py`, `pi_extension/extension.ts`, and the 21 test files
   over from `serve.*` shim imports to `kernel.*` (§2.1). Delete the 7 shim
   files. Run `pytest tests/ -q` clean.
2. Resolve JCode one way or the other (§2.3): implement `_JCodeAdapter` with
   a capability test, or strip it from `providers.py` /
   `runtimes/registry.py` / the UI until implemented.
3. Port the improved `silence_cutter.py` / `narrative_analyzer.py` from
   `/skills/` into `open_edit/agent/skills/`, update all 5 call sites, add
   regression tests for the new signatures, remove the stale duplicates and
   the stray `.pyc` files (§2.2).

**P1 — Prove the new subsystems end-to-end**

4. MCP server smoke test with a real MCP client (not just
   `test_mcp_server.py` unit coverage): `query_project` → `edit_project` →
   `trigger_render` (proxy) → `get_render_job` against a real project,
   through `open-edit-mcp` as Cursor would spawn it.
5. Render pipeline integration test that exercises all three motion-graphics
   backends in one project (MLT clip, `AddHtmlOverlayOp`,
   `AddRemotionCompositionOp`) end-to-end through `render_project()`,
   verified with `ffprobe` on the output (duration, streams, nonzero size) —
   this is the single most complex fan-in point in the graph and currently
   only has module-level unit tests, not one full-pipeline test.
6. Sandbox binary regression: `sandbox/` (Rust) has its own test suite
   (`tests/integration.rs`, `tests/render_integration.rs`) — confirm it's
   built and exercised in CI, since `agent/sandbox_bridge.py` fails closed
   without it (`OPEN_EDIT_SANDBOX_BACKEND=dev` is the documented weaker
   fallback).

**P2 — Close the remaining items from `OpenEdit_Repair_Plan.md`**

7. Golden end-to-end workflow (create → ingest → edit → AI edit → render →
   cancel → restart → reload → render final) as one automated test, per
   `OpenEdit_Repair_Plan.md §6`.
8. Real-browser (Playwright) coverage for at least the golden workflow's UI
   surface — current frontend tests are Node-DOM-stub unit tests only.

**Ongoing hygiene**

9. Re-run `graphify update open_edit --no-cluster` after significant
   structural changes (new modules, deleted shims, finished migrations) and
   diff `god_nodes` / `graph_stats` to confirm the shim removal and skill
   consolidation actually reduced duplication rather than just moving it.

---

## 4. How to keep using the graph

- `graphify query "<question>" --graph open_edit/graphify-out/graph.json` (or
  the `query_graph` MCP tool with `project_path` set to the `open_edit`
  directory) for "how does X call Y" questions before reading source.
- `graphify god-nodes` to re-check which abstractions are gaining/losing
  centrality as the kernel migration completes.
- `graphify cluster-only . --no-label --no-viz` after `update` to refresh the
  202 communities without spending LLM tokens (community *names* are
  placeholders — the communities themselves are a real structural signal
  from AST connectivity, e.g. Community 19 = agent tools, Community 20 =
  Remotion materialize path, Community 27 = graphics overlay burn path,
  Community 0/1 = IR types + apply).
