# Open Edit pipeline architecture map

Updated: 2026-10-08

## Product boundary

Open Edit is primarily a local stdio MCP server. External harness owns LLM loop. Open Edit owns project-scoped edits, durable render jobs, and an included editing/review workspace. Built-in chat/provider handling is an optional, lazily loaded extension.

```text
External AI harness
  │ MCP stdio
  ▼
open_edit/mcp/server.py
  ├─ list_tools -> kernel/tool_registry.py -> 6 schemas
  ├─ call_tool -> mcp/adapters.py -> kernel/tool_executor.py
  ├─ resources/prompts -> mcp/skills.py -> skills/*.md
  ▼
open_edit/kernel
  ├─ pillar_tools.py       query/edit/generate routing
  ├─ tool_executor.py      schema validation, idempotency, render enqueue
  ├─ render_jobs.py        durable SQLite jobs, cancellation, QC
  └─ tool_registry.py      LLM-visible tool schema registry
  ▼
IR + storage
  ├─ ir/types.py, apply.py, derive.py
  ├─ storage/history.py     atomic action Undo/Redo, shared by UI/CLI/MCP
  ├─ storage/edit_graph.py
  ├─ storage/assets.py
  └─ storage/timeline_cache.py
```

## MCP tool contract

| MCP tool | Dispatch | Responsibility |
|---|---|---|
| `query_project` | `pillar_tools.dispatch_query` | Read-only project, authoring, graphics and history queries |
| `edit_project` | `pillar_tools.dispatch_edit/dispatch_generate` | Timeline mutations and creative generation |
| `run_script` | `TOOL_TABLE` / sandbox bridge | Complex IR-only edits |
| `trigger_render` | `execute_trigger_render` | Enqueue proxy, final, overlay, or preview-chunks |
| `get_render_job` | `RenderJobService.get` | Poll durable job |
| `cancel_render_job` | `RenderJobService.cancel` | Stop queued/running job |

Project path is injected at server startup and never exposed as model input. Guide skills are available through MCP initialize instructions, resources, prompts, and packaged `skills/` copies.

## Current render paths

### Proxy/final

```text
trigger_render
  -> RenderJobService.enqueue
  -> python -m open_edit.cli render --json
  -> render_project
  -> derive timeline
  -> deliverable cache lookup
  -> Remotion materialize/cache or experimental frame pull
  -> build_render_plan
  -> emit MLT
  -> melt rawvideo | ffmpeg overlay/encode
  -> source repair
  -> cache/snapshot
  -> durable QC attachment
```

Proxy is a full-timeline 640x360 review-artifact MP4. Final is a full-quality original-source export. GPU path is host-only: optional CUDA decode probe, NVENC/QSV/etc encoder selection. Free-form sandbox never owns render GPU processes.

### Preview chunks

```text
trigger_render(mode=preview-chunks)
  -> durable job
  -> preview_chunks worker
  -> dirty range selection
  -> independent video/audio planes
  -> melt/ffmpeg chunk artifacts
  -> manifest and cache
```

Current preview-chunk video renderer materializes legacy Remotion compositions through `materialize_remotion_compositions()` before MLT emission. Native HyperFrames overlays use the shared HyperFrames materializer seam.

### HyperFrames overlay

```text
trigger_render(mode=overlay)
  -> kernel/render_overlay.py
  -> render/html_overlay.py
  -> generate HTML
  -> hyperframes CLI / headless Chrome / FFmpeg
  -> separate FFmpeg composite with background render
```

This is already HTML/CSS/JS based. Native HyperFrames overlays also use the shared materializer seam for proxy, final, and preview-chunk paths; `mode=overlay` remains a legacy compatibility branch.

## Remotion integration surface to replace

| Area | Files |
|---|---|
| IR model | `open_edit/ir/types.py`, `ir/apply.py`, `ir/derive.py`, `ir/api.py`, `ir/validate.py` |
| Agent operations | `agent/tools/pyagent_generate_remotion_composition.py`, `pyagent_init_remotion_project.py`, `pyagent_write_remotion_composition.py` |
| Scaffold | `render/remotion_scaffold.py` |
| Rendering | `render/remotion/renderer.py`, `render/remotion/safety.py`, `render/materialize.py`, `render/remotion/frame_engine.py`, `render/remotion/frame_feeder.py` |
| Orchestration | `render/orchestrator.py`, `render/timeline_plan.py`, `render/preview_video_renderer.py` |
| Docs/tests | `skills/remotion_motion.md`, `docs/REMOTION_LICENSE.md`, `tests/test_remotion_*.py`, render/orchestrator tests |

Safe migration requires preserving operation replay and timeline semantics while changing the composition payload from React entry points to HyperFrames HTML composition references. Do not delete Remotion files until no runtime imports, schema names, tests, or stored graph operations depend on them.

## Source navigation

Use the package contracts in `architecture/BLUEPRINT.md` and the source files
listed above. Generated graph indexes are local artifacts and are not shipped.

## Navigation rules for agents

1. Load `skills/open-edit-mcp.md` before source exploration.
2. Use `query_project` for state; use `edit_project` for mutations.
3. Use `trigger_render` plus `get_render_job` for renders.
4. Load `skills/remotion_motion.md` only for legacy Remotion migration or existing composition inspection.
5. Load `skills/hyperframes_native.md` for HTML composition work.
6. Read only files named by this map and the active guide; do not scan repository-wide.

## Workspace and optional runtimes

Review/Graphics/Code views share selection inspectors and the timeline. The
browser subscribes to revision snapshots and schedules dirty-range previews,
retaining checked chunks during updates and cancelling obsolete UI-owned jobs.
The durable renderer remains the authority for invalidation, QC and caching.
See [EDITING_WORKSPACE.md](EDITING_WORKSPACE.md).

Diffusion is the default editable graphics path, HyperFrames serves advanced
HTML overlays, and pinned Remotion/React replay is an independent compatibility
package. `integrations/readiness.py` and `open_edit doctor` report missing tools;
explicit `open_edit setup` commands install optional packages. Normal startup
never downloads dependencies. The Python wheel excludes all node_modules.
