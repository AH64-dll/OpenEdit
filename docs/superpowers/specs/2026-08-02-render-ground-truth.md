# Open Edit Render Ground Truth — Phase 0 (2026-08-02)

> Investigation only. No product behavior changed. Claims below are code-backed; unknowns are explicit.

## What’s actually true

- **Spine confirmed.** `render_project()` loads the edit graph, derives/caches a timeline, materializes Remotion → plan → emit MLT XML → melt→ffmpeg frame-server pipe → optional source-repair → render cache + snapshot. Entry: `open_edit/render/orchestrator.py:97–338`.
- **Proxy = full-timeline MP4 encode (same pipeline, cheaper profile). YES.** Same `render_project` path for `mode="proxy"` and `"final"`. Proxy defaults to `fast_proxy` 640×360 + quality `fast`; final to `1080p30` + `standard` (`profiles.py:98–120`, `orchestrator.py:114–115,121`). Plan building is mode-independent (`timeline_plan.py:28–29`); Remotion materialize uses lower spatial res for proxy (`renderer.py:129–147`).
- **Review Studio plays rendered MP4 files**, not live MLT. `<video id="preview-player">` (`index.html:118`); `loadRenderInPreview` sets `src` to `/api/projects/.../renders/{id}/file` (`app.js:1509–1518`); route streams MP4 with Range (`renders.py:128–140`). Seek = HTML5 `currentTime` (`app.js:1558–1563`). No SDL/OpenGL MLT consumer in serve/static (search found none). Fallback can play raw source asset only when no proxy/final exists (`app.js:1415–1440`).
- **GPU today (partial).** Default backend is `gpu` → prefer `h264_nvenc` (`encoder.py:1–22,224–237,41–49`). Melt producers may get `hwaccel=cuda` when GPU backend + probe succeed (`orchestrator.py:67–94,228–230`; `emitter.py:202–204`); one CPU retry on melt failure (`orchestrator.py:258–265`). Remotion CLI has **no** `--gl` / Chromium GPU flags; concurrency defaults to CPU cores−1 (`renderer.py:218–221,323–334`). Frame pipe itself is CPU rawvideo yuv420p (`pipe_builder.py:119–130`).
- **Remotion cache.** Per-composition key via `composition_cache_key` (source+props+profile+alpha+duration+refs) → `materialize:<id>:<hash>` under remotion `out/cache` (`materialize.py:29–36,79–96`; `safety.py:219–245`). Cache hit → re-ingest; miss → `render_composition`. `force=True` only skips **final MP4** `RenderCache` (`orchestrator.py:217–225`); Remotion materialize always runs first and still honors its own cache — **no rematerialize-force flag**.
- **Alpha / ProRes.** `resolve_alpha_mode`: auto → VP8 if probe proves alpha, else ProRes (`renderer.py:42–108`). Alpha path: ProRes 4444 → `.mov` with `yuva444p10le`, or VP8/VP9 → `.webm` (`renderer.py:191–216`; `materialize.py:88–94`). Overlay burn uses `format=rgba` + `filter_complex` when `ov.alpha` (`pipe_builder.py:79–94,145–150`).
- **Sandbox vs worker.** Free-form IR: `run_free_form` / bwrap + `ops.jsonl` (`agent/sandbox/bridge.py`). Main proxy/final: host worker — `RenderJobService._launch` runs `sys.executable -m open_edit.cli render` (`render_jobs.py:418–453`), which calls `render_project` on the host. Separate `bridge.run_render` bwrap path is for motion-graphics skill codegen, **not** the main job path (`bridge.py:250–305`; used from `motion_graphics/engine.py`).
- **QC / repair.** `repair_render_output` is on the orchestrator success path before cache put (`orchestrator.py:275–301`). Job service always attaches QC after success; QC never flips job status (`render_jobs.py:366–416`). CLI `--json` path skips printing QC; non-JSON CLI runs QC (`cli.py:186–210`).
- **Historical issues (status).**
  - `f=rawvideo` pipe corruption: **fixed** (`pipe_builder.py:115–118`).
  - Alpha opaque VP8: **mitigated** by probe + ProRes fallback (`renderer.py:42–108`).
  - v1.4 preview / missing asset stream: **addressed** (asset file route + UI comments `assets.py` / `state.js:68–72`); Review Studio still depends on successful proxy MP4.
  - “Missing orchestrator”: **closed** — `render_project` is the live entry (`cli.py:168–174`; jobs → CLI).
  - No open `TODO`/`FIXME` in `open_edit/render/` or `render_jobs.py` (scan 2026-08-02).
- **Python.** Pin is floor `requires-python = ">=3.11"` + mypy `python_version = "3.11"` (`pyproject.toml:5,82–83`). **This venv runtime is 3.14.5**, not 3.11-only.

### Explicit statement

**Is proxy today a full-timeline MP4 encode?** **Yes.** Evidence: `render_project` always emits/runs melt→ffmpeg to `project_<hash>.mp4` for both modes (`orchestrator.py:227–249,331–337`); Review Studio plays that file (`app.js:1509–1518`). Proxy differs by resolution/quality tier and Remotion profile size, not by skipping encode.

## Ordered code path (proxy/final)

1. Enqueue: MCP/REST/`execute_trigger_render` → `RenderJobService.enqueue` (`tool_executor.py:295–373`; `render_jobs.py:230–299`)
2. Worker: `_run` → `_launch` → `python -m open_edit.cli render --mode …` (`render_jobs.py:358–470`)
3. CLI: `cmd_render` → `render_project` (`cli.py:162–185`)
4. `EditGraphStore.load_all` (`orchestrator.py:124–127`)
5. `derive_or_load_timeline` → `derive_timeline` / snapshot (`timeline_cache.py:62–88`; `ir/derive.py`)
6. `materialize_remotion_compositions` → `remotion/safety.py`, `remotion/renderer.py` (`materialize.py:39–138`)
7. `build_render_plan` → `timeline_for_melt` + overlay clips (`timeline_plan.py:20–41,128–149`)
8. `collect_source_baseline` (`orchestrator.py:164–166`; `source_repair.py`)
9. Cache key: `canonical_json_hash` + `profile_fingerprint` + Remotion content fingerprint + repair policy (`orchestrator.py:191–216`; `cache.py:34–47`) — hit may return early
10. `emit_timeline` (+ optional `hwaccel=cuda`) (`emitter.py`; `orchestrator.py:227–234`)
11. `build_pipe_commands` → `run_pipe` (melt audio; melt rawvideo | ffmpeg overlays+encode) (`pipe_builder.py:99–171`; `melt_runner.py:103+`)
12. `repair_render_output` if ok (`orchestrator.py:275–301`)
13. `RenderCache.put` + `record_snapshot` (`orchestrator.py:331–332`)
14. Job: `_attach_qc` / `run_qc_gate` (`render_jobs.py:385–416`)
15. UI: stream MP4 via `get_render_file` → `<video>` (`renders.py:128–140`; `app.js:1509–1518`)

**Overlay mode (HyperFrames):** separate branch — `_launch` → `kernel/render_overlay.run_trigger_render` → `render/html_overlay` (`render_jobs.py:420–433`). Not the melt frame-server spine.

## What’s still unknown

- Whether `_gpu_decode_available()` / NVENC probe succeed on **this** host at runtime (code present; not re-probed in Phase 0).
- Remotion Chromium actual GPU vs software GL on this machine (no flags set; OS/Chrome defaults unknown).
- Wall-clock split Remotion vs melt vs ffmpeg vs repair vs QC on timeline-test (Phase 1).
- Whether UI badge “Proxy 720p” (`app.js:1526`) vs default `fast_proxy` 640×360 (`profiles.py:85,114`) is intentional override via params or a label drift.
- Disk eviction / size caps for remotion `out/` + `render_cache` (behavior observed in ops memory; policy code not fully audited here).
- Exact HyperFrames overlay critical-path cost vs proxy (out of main spine).

## In-scope vs N/A for later phases

| Topic | Phase scope |
|---|---|
| Measure Remotion / melt / ffmpeg / repair / QC; cache hit rates | Phase 1 — **in** |
| Same-pipeline proxy speedups; Remotion reuse; skip redundant QC | Tier investigation — **in** |
| Chunked timeline preview cache / interactive MLT scrub | Product gap — **in** as architecture proposal only after Phase 0–1 |
| Per-asset source proxies (≠ output `mode=proxy`) | Industry gap — **in** to evaluate |
| Vulkan / Metal / full GPU compositor / zero-copy MLT↔ffmpeg | **N/A** until measured need + Hard Constraints on sandbox/worker |
| Changing free-form bwrap/seccomp IR sandbox for GPU sharing | **N/A** unless proposal explicitly breaks Hard Constraint |
| HyperFrames `mode=overlay` | Separate path — profile if claimed bottleneck; don’t conflate with proxy/final |
| Remotion alpha/ProRes correctness redesign | Closed enough for Phase 0; optimize cost in Phase 1+ |
| Interactive Review Studio without full MP4 | **Missing today** — Phase 2+ architecture, not a tweak |

