# PERF_PIPELINE — Render pipeline internals: stage-by-stage, where the 12 minutes went

Author: coordinator (explorer-1 died to daemon crashes twice; stage data compiled from render_jobs.db job 0c06145c44db, /tmp/render_proxy_video.log, benchmark_logs/, SALVAGE_EXPLORER.txt, and source reading of open_edit/render/*).

## 1. The render pipeline (what actually runs for `trigger_render(mode=proxy)`)

1. **Job service** (`kernel/render_jobs.py`): durable job row created; subprocess `python -m open_edit.cli render --mode proxy`; per-project lock; coalescing on identical (project, mode, hash, params).
2. **Orchestrator** (`render/orchestrator.py`): derive timeline -> whole-file cache lookup (miss) -> hyperframes/remotion materialize (none) -> `build_render_plan` -> **collect_source_baseline** (black+freeze detection on the SOURCE, cached per asset) -> emit MLT -> video pass -> **source_repair** (detect on OUTPUT, possibly re-encode whole file) -> mux audio -> cache.put -> QC.
3. **Video pass**: `cuda_fastpath.py` (eligible: single full-length clip, no overlays) — one ffmpeg: `-hwaccel cuda -hwaccel_output_format cuda -vf scale_cuda=640:360 -c:v h264_nvenc`. Measured 77.9 s (28.4x). For effect timelines: melt (CPU composition) measured 4.8x — ~8x slower fallback.
4. **Audio pass** (`melt_audio`): full 36.9-min WAV (424 MB) rendered every time: 19.3 s.
5. **source_repair** (`render/source_repair.py`): baseline had 18 black + 16 frozen spans in the source; detectors re-run on the output (23 windows); `changed=true` -> `_repair_stream` decodes the ENTIRE 66,273-frame output to raw RGB24 via a **Python per-frame loop** and re-encodes with **libx264 veryfast crf18 (CPU)**. Measured: 579.1 s — **83% of the render**.
6. **Mux + QC**: seconds.

## 2. Stage table (proxy job 0c06145c44db, wall 700.8 s)

| Stage | Wall (s) | % | Notes |
|---|---|---|---|
| cuda_fastpath (video) | 77.9 | 11% | CUDA decode + NVENC, 28.4x — the fast part |
| melt_audio (wav) | 19.3 | 3% | 424 MB WAV, regenerated every render |
| source_repair (detect + whole-file CPU re-encode) | 579.1 | 83% | THE problem |
| qc/emit/plan/derive | <1 | <1% | |
| **Total** | **700.8** | | |

## 3. Root-cause chain

- Repair re-encode: Python rawvideo frame pump (4.2x vs 9.2x direct pipe) + libx264 CPU + whole-file scope -> 579 s for a 37-min proxy. GPU (NVENC) and segment-local scope both unused.
- Render cache: default cap 1 GiB < proxy output 1.1 GB -> `put()` copies then `evict()` deletes the just-put entry -> every render is a full miss (`cache_hit=false` in all 5 jobs).
- No incremental path in use: preview-chunks engine (1 s chunks, ~1.3 s fixed ffmpeg overhead each, serial) would take ~49 min for this project; UI never calls it.
- Preview file layout: moov at 94.3% (62 MB tail), no faststart, 3.9 Mbps, 3.1 s median GOP -> slow first frame + scrub.
- Source proxies exist in code but `source_media_policy=original` always -> every render decodes 1.46 GB 1080p (78 s decode floor).
- Audio wav not cached; UI full-state polls; no render progress columns; server shutdown hangs on open video stream.

## 4. Fixes (see PERF_MODPLAN.md for the full plan; implemented in this session: cache cap/evict, faststart+GOP, verify-based proxy repair, NVENC repair, segment-local repair, wav cache)

Target: 700.8 s -> <120 s (proxy), first frame <100 ms, identical re-render ~1 s.
