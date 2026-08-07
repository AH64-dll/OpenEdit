# Open Edit Pipeline Architecture Review

Updated: 2026-08-04

## Verdict

Open Edit has a sound MCP-first kernel and durable render-job boundary. MCP tool discovery is centralized and project-scoped. Native HyperFrames overlays now share proxy, final, and preview materialization; legacy Remotion compositions still use a separate React/Chromium compatibility path. `mode=overlay` remains legacy compatibility.

HyperFrames is technically feasible as the native HTML/CSS/JS graphics engine. Local package `0.7.65` successfully linted and rendered a deterministic 1-second MP4 fixture on this host. It requires Node 22+, FFmpeg, and Chromium; local rendering uses Puppeteer/headless Chrome and supports bounded workers and optional GPU encoding. It does not currently provide a drop-in replacement for MLT's multi-track A/V timeline, audio graph, source trimming, and existing rawvideo pipe contract.

Recommendation: replace Remotion as the graphics authoring and materialization engine, keep MLT plus FFmpeg as the base A/V compositor during migration, and use HyperFrames for both preview graphics and final graphics. Do not replace MLT wholesale until A/V, timing, alpha, cancellation, and long-form performance parity are measured.

## Current MCP integration

`open_edit/mcp/server.py` registers six LLM-visible tools from `open_edit/kernel/tool_registry.py`. `open_edit/mcp/adapters.py` injects the pinned project path and dispatches into `open_edit/kernel/tool_executor.py`. The executor validates schemas, routes the four pillar tools, records idempotent commands, and delegates renders to `RenderJobService`.

Guide skills already load through MCP initialize instructions, resources, prompts, and packaged copies. The new `hyperframes_native` guide adds a direct navigation route for native composition authoring and Remotion migration. The architecture map is `docs/PIPELINE_ARCHITECTURE_MAP.md`.

Current verification found:

- Six MCP schemas are present and exclude `project_path`.
- The 28 callable runtime tools are covered through the canonical `TOOL_TABLE`.
- MCP SDK smoke is blocked by local package shadowing: importing `mcp` resolves to `open_edit/mcp/__init__.py` because the editable install adds `open_edit/` itself to `sys.path`. The existing test skips this case. The production install must use the repository root as the editable package root and expose the external MCP SDK.
- Focused MCP, render, materialization, overlay, and orchestrator tests pass; one MCP server test skips for the shadowing condition.
- Real MCP test against `/home/ah64/Videos/video/untitled_cl.mp4` succeeded: source 1920x1080 H.264/AAC, 2211.34s; 2s preview chunks succeeded; native HyperFrames proxy succeeded at 640x360 with A/V sync QC; native HyperFrames final succeeded at 1920x1080 with full QC and GPU backend selection. Render cache filename overflow was found and fixed with bounded readable hash keys.

## Current rendering data flow

### Proxy and final

```text
MCP trigger_render
  -> RenderJobService
  -> python -m open_edit.cli render --json
  -> render_project
  -> EditGraphStore / derive_or_load_timeline
  -> deliverable RenderCache lookup
  -> Remotion materialization or experimental Remotion frame pull
  -> build_render_plan
  -> emit MLT
  -> melt rawvideo + separate audio
  -> FFmpeg graphics overlay and encode
  -> source repair
  -> cache and snapshot
  -> durable QC
```

`proxy` is a complete 640x360 review-artifact MP4, not interactive playback. `final` uses canonical original sources and the production profile. GPU work is host-worker only; the sandbox remains IR-only.

### Preview chunks

Preview chunks use dirty-range invalidation, independent video/audio planes, and manifest-backed artifacts. Legacy Remotion compositions still use `materialize_remotion_compositions()` for overlapping ranges. Native HyperFrames overlays use the shared HyperFrames materializer seam.

### HyperFrames today

Native HyperFrames overlays are materialized through a content-addressed host seam and reused by proxy, final, and preview-chunk paths. `mode=overlay` remains a legacy compatibility branch: it generates temporary HTML, runs the HyperFrames CLI, then composites the MOV over a separately rendered background with FFmpeg.

## Remotion migration boundary

Remotion dependencies and runtime paths are concentrated in:

- `open_edit/ir/types.py`, `ir/apply.py`, `ir/derive.py`, `ir/api.py`, and `ir/validate.py`.
- `open_edit/agent/tools/pyagent_generate_remotion_composition.py`, `pyagent_init_remotion_project.py`, and `pyagent_write_remotion_composition.py`.
- `open_edit/render/remotion_scaffold.py`, `render/remotion/`, `render/materialize.py`, `render/orchestrator.py`, `render/timeline_plan.py`, and `render/preview_video_renderer.py`.
- Remotion-specific guide, license documentation, package pins, and tests.

Safe removal cannot be a blind file deletion because existing SQLite graphs may contain `add_remotion_composition` operations. Migration must first add a compatibility reader and a deterministic conversion record. Arbitrary TSX-to-HTML conversion cannot be guaranteed mechanically; the HyperFrames project ships a dedicated Remotion-port workflow, so conversion requires an agent-authored HTML composition followed by frame-parity validation.

## HyperFrames feasibility

### Strengths

- Native HTML/CSS/JavaScript authoring with no React requirement.
- Deterministic frame stepping through headless Chrome and FFmpeg.
- Native preview CLI with live browser reload.
- Lint/check/benchmark/doctor commands suitable for CI and AI navigation.
- Bounded render workers and optional GPU encoder/browser-GPU controls.
- Apache-2.0 licensing.

### Limits

- Local CLI is a subprocess boundary today; native Python APIs are not part of this repository's dependency contract.
- Each render captures browser frames and encodes media. It is not guaranteed to be real-time playback for arbitrary effects.
- GPU acceleration is optional and split between Chrome capture and FFmpeg encode; it is not a universal zero-copy pipeline.
- Audio mixing and timeline media support exist in HyperFrames, but replacing MLT would require proving trim, transitions, effects, A/V sync, source proxy semantics, cancellation, and long-form output parity.
- HyperFrames requires Node 22+, while the Python package supports Python 3.11 as its language floor. This is an independent host dependency, not a sandbox dependency.
- The repository pins `0.7.65` while npm currently reports newer releases. Keep the pin until an explicit upgrade is linted, rendered, and compared.

## Approved implementation sequence

1. Keep MCP surface stable. Native HyperFrames guide, architecture map, and schema/tool routing now target HyperFrames HTML for new graphics.
2. Use `AddHtmlOverlayOp` as the first-class HyperFrames composition operation. Preserve legacy Remotion operation reading while rejecting new Remotion authoring.
3. Use the host-only HyperFrames materializer with content-addressed cache, bounded output size, cleanup, cancellation-compatible jobs, and FFmpeg composite output.
4. Route proxy, final, and preview-chunk graphics through the shared materializer seam. Keep base timeline emission and audio in MLT/FFmpeg.
5. Add Remotion-to-HyperFrames migration tooling and frame-parity fixtures. Migrate the bundled starter and guides. Remove Remotion package/runtime dependencies only after no active graph or code path requires them.
6. Add end-to-end MCP smoke: initialize, list tools/resources, query, edit, enqueue preview, poll, enqueue proxy, poll, enqueue final, poll, cancel.
7. Rebuild Graphy after structural changes and update the architecture map.
8. Benchmark preview cold/warm, one-overlay edit, alpha overlay, long-form composition, GPU/CPU encode, and A/V sync. Decide separately whether MLT replacement is justified.

## Acceptance gates

- Every MCP schema discovers a reachable implementation and returns structured errors.
- Native HyperFrames operation round-trips through SQLite, timeline derivation, preview chunks, proxy, and final paths.
- No new Remotion operation is authored by guide or tool routes.
- Existing Remotion graphs either migrate explicitly or fail with a bounded migration-required result; they never disappear silently.
- Final render uses canonical originals and retains QC.
- Preview uses dirty ranges and never requires a full-timeline encode for a one-overlay change.
- HyperFrames and all GPU/native render processes remain outside `run_script` sandbox.
- `f=rawvideo`, audio-plane behavior, cancellation, and process cleanup remain green.
- Graphy output and architecture map identify current modules and no longer describe a stale Remotion-only graphics path.

## Rollback

The migration is reversible while legacy graph readers and the MLT base path remain. Disable native HyperFrames authoring through the guide/tool route, leave existing legacy render code untouched, and remove only the new HyperFrames operation records from test fixtures. Do not delete source CAS files or canonical assets during cache cleanup.

## External evidence

- HyperFrames repository and architecture: https://github.com/heygen-com/hyperframes
- HyperFrames package and CLI requirements: https://www.npmjs.com/package/hyperframes
- Kdenlive timeline preview model: https://docs.kdenlive.org/en/tips_and_tricks/tips_and_tricks/timeline_preview_rendering.html
- Shotcut GPU and preview limitations: https://www.shotcut.org/FAQ/
