# PERF_RESULTS — Preview/render performance: before → after

Date: 2026-08-06. Project: /home/amr/Videos/video (37-min 1920x1080 clip, single track).
Measured via `trigger_render(mode=proxy, wait=True)` through the OpenEdit MCP integration.

## The headline

| Scenario | Before (Aug 4/6 baseline) | After (fixes) | Speedup |
|---|---|---|---|
| Cold proxy render (full 37-min) | **700.8 s** (~12 min) | **66.7 s** | **10.5×** |
| Identical re-render (no edits) | 700.8 s (cache never hit!) | **3.5 s** | **200×** |
| Video pass (encode) | 77.9 s (28.4×, full-res source) | 17.4 s (126.6×, 360p source proxy) | 4.5× |
| Audio pass | 19.3 s every render | ~0 s (wav cached by graph hash) | ∞ (second run) |
| source_repair stage | 579.1 s (83% of render, CPU whole-file re-encode) | **0 s** (verify-only for previews) | ∞ |

## Why it was 12 minutes (root causes, verified)

1. **source_repair re-encoded the entire output on CPU** (579 s): the source has 18 black + 16
   frozen spans; the old policy detected them in the output and ran a whole-file
   Python rawvideo + libx264 CPU re-encode — for a *preview*. New policy: previews are
   verify-only (spans reported, file untouched); full re-encode only for `final`
   deliverables, and even then NVENC + segment-local spans.
2. **The whole-file render cache never hit**: default cap 1 GiB < 1.1 GB proxy output →
   put() then evict() deleted the entry. Raised to 32 GiB → identical re-renders are 3.5 s.
3. **No source proxies**: every render decoded the 1.46 GB 1080p original. Now the
   asset-proxy service generates a 360p proxy per asset (once) and review-artifact
   renders decode/scale from it (126× realtime on this laptop's RTX 4050).
4. **Audio wav regenerated every render** (19.3 s, 424 MB): now cached by edit-graph hash.
5. **Slow first frame**: moov was at the file tail; faststart + 1-s GOP (sc_threshold 0)
   now applied on the CUDA fast path.
6. **Not incremental / no parallelism**: preview-chunks engine upgraded: adaptive chunk
   size (≈64 chunks, 1–30 s clamp), parallel chunk bake (ThreadPoolExecutor ≤ 4),
   per-plane dirty fingerprints (already present) — with the UI wired to the manifest.

## What was implemented (files)

- open_edit/render/source_repair.py — v6 verify-preview policy, NVENC repair, segment-local spans
- open_edit/render/orchestrator.py — audio wav cache, source-proxy emission, cache-fingerprint v6, repair policy gating
- open_edit/render/cache.py — 32 GiB default cap, LRU eviction fix, size parsing
- open_edit/render/cuda_fastpath.py — faststart, 1-s GOP, mux from cached wav
- open_edit/render/source_proxy.py + kernel/asset_proxy_jobs.py — asset proxy generation + durable queue + drain
- open_edit/render/timeline_plan.py — review-artifact → source_media_policy=proxy
- open_edit/render/preview_chunks.py — adaptive chunk size, parallel bake (shared-state lock), chunk_frames param
- open_edit/render/preview_invalidation.py — adaptive chunk windows (in sync)
- open_edit/render/preview_pipe.py — hwaccel on chunk emit
- Regression fixes this session: frozen-dataclass audio-cache assignment (dataclasses.replace → local var),
  nested non-reentrant lock deadlock in parallel bake, asset-proxy drain UNIQUE-key recovery.
- Tests: **1495 passed, 7 env skips, exit 0**.

## Industry context (summary)

Premiere/DaVinci preview in ~1 min because: proxies at ingest (✓ now), incremental
segment caches with dirty-region invalidation (✓ preview-chunks), I-frame-friendly
intermediates (partially: chunk-per-file masks long-GOP; faststart+GOP-1s ✓),
GPU everywhere (✓ CUDA+NVENV fast path; melt CPU fallback remains for effect
timelines — next target), parallel/segmented rendering (✓ ≤4 workers).

## Reproduction

    OPEN_EDIT_PROJECT_DIR=/home/amr/Videos/video python /tmp/bench_final.py
    # cold: ~67 s; warm: ~3.5 s


## Editing-loop measurements (real, on /home/amr/Videos/video, 37-min project)

| Action | Time |
|---|---|
| Apply an edit op via MCP (`set_audio_gain`) | ~1-2 s |
| **Audio-only edit → full proxy preview** (was 288 s → now 79 s; video pass 56× realtime via CUDA) | **79 s** |
| Visual edit (cut/color/overlay) → full proxy preview (melt CPU ~4.8×; incremental chunk path not yet in UI) | ~5-8 min |
| No-change re-render (render cache) | **3.5 s** |

Bonus fix this round: `cuda_fastpath.timeline_supports_cuda_fastpath` now ALLOWS audio-only
effects (volume/gain) — they are applied by the melt-audio pass, so they no longer force
the whole-file melt CPU render. Audio edits went 288 s → 79 s. Video-affecting effects
still require melt. Regression tests added (tests/test_cuda_fastpath.py).
Suite: 1497 passed / 7 skipped / exit 0.
