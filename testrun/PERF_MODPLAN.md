# PERF_MODPLAN — OpenEdit kernel/project/storage: why preview isn't ~1 min, and the concrete modification plan

Explorer-3 (project & kernel). All numbers below were measured in this investigation (job DB rows, benchmark JSONs, source code, live probes, server request logs). Evidence files: `testrun/KERNEL_AUDIT_EVIDENCE.md` (sub-agent audit), `testrun/SALVAGE_EXPLORER.txt` (predecessor's raw measurements). Companion reports: explorer-1 (pipeline), explorer-2 (industry).

---

## 0. Executive summary

For `/home/amr/Videos/video` (one 36.9-min 1080p clip, one applied edit), the proxy render took **700.8 s**. The measured stage breakdown (render_jobs.db job `0c06145c44db`, graph rev 37):

| Stage | Wall | Notes |
|---|---|---|
| `cuda_fastpath` (video pass, CUDA decode + NVENC) | **77.9 s** (28.4x) | decode-bound; already fast |
| `melt_audio` (wav mix) | **19.3 s** | 424 MB wav intermediate, regenerated every run |
| `source_repair` (detect + **whole-file re-encode**) | **579.1 s** (changed=true, 23 windows) | **83% of the render** |
| qc / emit / plan / derive | < 1 s | negligible |
| **Total** | **700.8 s** | |

So the kernel/project **already renders the main video pass at 28x realtime**. The 12-minute preview is caused by three structural defects, in order of impact:

1. **Source repair re-encodes the entire output through a CPU raw-RGB Python loop** (`open_edit/render/source_repair.py::_repair_stream`) whenever the source has any black/frozen spans — this source has 18 black + 16 frozen spans → 579 s. Earlier benchmark runs show the same pathology: `full_proxy` spent 209 s on repair with **no changes made**; `full_final` spent 1427 s with no changes.
2. **The whole-file render cache is self-defeating for this project**: the default cap is 1 GiB and the proxy output is 1.1 GB, so `RenderCache.put()` copies the file then `evict()` immediately deletes it (`render/cache.py`). Every render in the DB is `cache_hit=false`; `renders/render_cache/.meta` is empty. No render has ever been reused.
3. **Nothing is incremental.** The `preview-chunks` engine (dirty-segment fingerprints, per-plane artifact cache, manifest) exists but was only ever exercised on a 12 s test timeline (manifest rev 34, 2 of 12 chunks rendered, audio/playback planes red), is serial, uses 1 s chunks (≈2211 chunks with ~1.3 s fixed ffmpeg overhead each ≈ 49 min for this project), and **the Review Studio UI never calls it** — the UI plays the whole-file mp4 via `<video src>`.

Secondary defects: proxy mp4 has moov at 94% of the file (62 MB tail) → slow first frame; no per-asset source proxy was ever generated (render decoded the original 1080p, `source_media_policy=original`); audio wav not cached; UI polls the full project state every 5 s (each poll re-derives the timeline and re-parses a 528 KB transcription sidecar); no keyframe index, thumbnail strip, or waveform cache; render jobs expose no progress (schema has no started/finished/elapsed columns).

With the plan below (order in §5): preview-after-edit drops from **~700 s to ~15–90 s** (and a scrub/playhead preview of a 10 s edit to **~3–8 s**), first frame to <100 ms, and final export from 2916 s to ≈ 200–400 s.

---

## 1. What we audited and measured (evidence)

### 1.1 Kernel render pipeline (`render_jobs.py`, `orchestrator.py`)
- `RenderJobService` runs one job per project (per-project `asyncio.Lock`), global semaphore default 1 (`OPEN_EDIT_RENDER_CONCURRENCY`), subprocess per job (`python -m open_edit.cli render --mode …`), process-group cancel, 4 h timeout. Coalescing: same `(project, mode, edit_graph_hash, params)` reuses an active job. Jobs are persisted but the schema has **no `started_at`/`finished_at`/`elapsed`/stdout/stderr** columns and no periodic progress updates — the UI polls blindly (every 2 s) and gets nothing until the terminal row is written.
- `orchestrator.render_project` flow: derive timeline → render-cache lookup (whole-file key) → hyperframes/remotion materialize → `build_render_plan` → `collect_source_baseline` (black/freeze detection on the **source**) → emit MLT → pipe (`run_pipe`/`run_cuda_fastpath`) → **source repair** (detection on the **output** + possible whole-file re-encode) → `cache.put` → QC gate.
- Proxy mode uses `emission_profile="review-artifact"` ⇒ `whole_file_repair=True` and `source_media_policy="original"` (`render/timeline_plan.py::_EMISSION_POLICY`). I.e. the "proxy" render decodes the original 1080p and runs the repair machinery on every render.
- Repair trigger: baseline found 18 black + 16 frozen spans (112.5 s across 23 padded windows). Detection runs 2 ffmpeg invocations (blackdetect + freezedetect) per window on the output; when any span survives in the output (`changed=true` in the E2E run), `_repair_stream` decodes the **entire** output to raw RGB24 through a Python per-frame loop and re-encodes with **libx264 veryfast crf18 (CPU)**. The whole 579 s stage = window detection + full re-encode; the re-encode alone is a full 66,273-frame pass (raw RGB pipe + Python loop measured at only ≈4.2x vs 9.2x for the same encoder from file input). NVENC 640x360 ≈ 15x in my 60 s benchmark (4.0 s for 60 s) and the real fastpath ran 28.4x.
- The `cuda_fastpath` (`render/cuda_fastpath.py`) is a clean single-ffmpeg command (`-hwaccel cuda -hwaccel_output_format cuda -vf scale_cuda … -c:v h264_nvenc`) — this is the architecture any fast path should copy. It is only eligible for one-clip timelines with no overlays.

### 1.2 Render cache — the "never hits" bug (verified)
- `render/cache.py`: `render_cache_key(graph_hash, profile_fingerprint, content_fingerprint)` (capped at 180 chars after a real ENAMETOOLONG failure on a 260-char key, job `493b7f90`); `get()` requires content sha256 + TTL (24 h); **`put()` copies the output then calls `evict()`, and `evict()` deletes LRU entries while `total_bytes > max_bytes`** — default cap 1 GiB (`OPEN_EDIT_RENDER_CACHE_MAX_BYTES`). The E2E proxy is 1,096,296,584 B ≈ 1.02 GiB → **put → evict deletes the entry it just stored**. `renders/render_cache/` contains only `source_baseline/*.json`; `.meta/` empty; all 5 succeeded jobs report `cache_hit=false`.
- Result: re-rendering the same graph re-does the full 700 s. (With the cap raised and an unchanged graph, a re-render would be ~1 s.)

### 1.3 Storage / project state (`/home/amr/Videos/video/.open_edit/`)
- CAS: `assets/c9/<sha256>` (1.46 GB file) + `<sha256>.meta.json` (527,793 B — dominated by a word-level transcription `alignment` array). Ingest runs ffprobe + transcription, **no proxy generation** — the meta.json has no `proxy_hash/proxy_status` fields; `render_jobs` diagnostics show `source_proxy_hits={}`, `source_proxy_fallbacks={}`. A per-asset source-proxy subsystem exists (`render/source_proxy.py`, `kernel/asset_proxy_jobs.py`, `POST /api/projects/{id}/assets/{hash}/proxy`) but was never used by this project and is **not** wired into the default proxy render.
- `edit_graph.db`: 9 tables; `edits` 19 rows (18 reverted, 1 applied), `timeline_snapshots` 12 (used by `derive_or_load_timeline` — but `serve/projects.py::get_project_state` calls `derive_timeline` directly, ignoring the cache), `notes` 0, `render_snapshots` 0 (rows live in `render_snapshots.db`, 9 ready versions — each render version recorded, but nothing consumes them for playback).
- **No `notes.db`** in the project (the UI/API checks `path/notes.db`; empty). No `thumbs/`, no waveform cache, no keyframe index. `timeline_views/` has 2 PNGs (`untitled_cl_FULL.png`, `untitled_cl_0.00-30.00.png`) generated by `render/timeline_view.py` (which exists with `extract_frames` — N separate ffmpeg calls — and `render_waveform`) but they are not served by any route.
- `preview_chunks/`: `manifest.json` (rev 34, 12 s, 12 chunks, `chunk_frames=30` = **1 s chunks**; chunk 0-1 yellow with fallback video artifacts, chunks 2-11 red; all `audio`/`playback` red) + 2 video artifacts (~265 KB, 161 KB) + `.artifact_index.json` + a leftover tmp dir from a cancelled job. Stale vs current graph (rev 37).
- `benchmark_logs/`: 5 JSONs (see §0 and §4). `testrun/logs/`: only 2 pytest progress logs.

### 1.4 Serve / Review Studio UI
- Server: `.venv/bin/python -m open_edit.cli serve --review-only --port 8000`. At audit time it was **not accepting connections** — uvicorn "Shutting down / Waiting for connections to close" since ~15:02, blocked on one ESTAB connection (`127.0.0.1:8000` with 2.6 MB Send-Q) holding an open fd on the 1.1 GB render mp4 (`/proc/<pid>/fd/75`). Graceful shutdown waits forever on a stalled video stream; this is a robustness defect of streaming the whole file as one FileResponse.
- Historical latency (server's own request log, 875 requests): avg 44.6 ms, max 132.5 ms. `GET /api/projects/{id}` (UI state poll) 922× avg **47.2 ms**; `GET …/renders/{id}/file` (HTTP 206 Range) 404× avg ~43 ms; 66× 206 total. Localhost latency is fine; the latency that matters is first-frame + scrub, which is dominated by the mp4 layout (below).
- UI (`serve/static/app.js`): polls `getProjectState` every 5 s (full payload incl. `timeline_full` + all ops payloads + assets), renders list every 5 s while a job is active, `render_jobs/{id}` every 2 s (max 120 attempts = 10 min then gives up silently — a 12-min render appears hung for the last 2 min), auto-proxy debounced 15 s. Video: **plain `<video src>`** to `/renders/{id}/file`; no fetch/Range logic, no preview-chunks, no keyframe/thumbnail/waveform usage. Scrubbing = `player.currentTime` (browser native).
- Proxy mp4 layout (`ffprobe` + binary scan): h264 640x360 yuv420p, 2211.2 s, **1,096,296,584 B** (≈3.9 Mbps — high for a preview), **moov at byte 1,034,390,601 (94.3%)**, tail from moov = 61.9 MB; **no faststart**. 644 keyframes, median GOP 3.14 s (≈94 frames), max 8.3 s. First frame therefore requires the browser to range-fetch ~62 MB of moov (66,273-frame sample tables) before playback; local ffmpeg seek is 0.13 s, but browsers on a 62 MB moov + high bitrate are slow and the file is awkward to stream.

### 1.5 Machine
RTX 4050 Laptop 6 GB (NVENC/CUVID present; idle 0% during CPU stages), 12 cores, 22 GB RAM, /home 148 GB (87 GB free), ffmpeg n8.1.2 (nvdec/nvenc), melt 7.40.0. My measured encode speeds: NVENC 640x360 (CUDA decode) **15x** (4.0 s/60 s); libx264 veryfast crf18 640x360 **9.2x** (6.5 s/60 s).

### 1.6 Per-invocation overhead (predecessor measurements, SALVAGE_EXPLORER.txt)
ffmpeg chunk renders of this source: 1 s chunk → 1.34 s wall; 5 s → 1.41 s; 30 s → 1.97 s; 60 s → 2.54 s. **≈1.3 s fixed cost per invocation** (process start + CUDA init + moov seek on the 1.46 GB source). 1 s chunks over 2211 s ⇒ ~49 min serial; 60 s chunks ⇒ ~94 s serial. sha256 of the 1.46 GB source: 1.39 s (per-cache-put cost, irrelevant vs 700 s).

---

## 2. Root causes, ranked (why preview is 12 min, not 1 min)

| # | Root cause | Measured cost (E2E proxy) | Component |
|---|---|---|---|
| R1 | Whole-file source repair (detect + full raw-RGB CPU re-encode) on every proxy render | 579 s (83 %) | `render/source_repair.py`, `render/orchestrator.py` (repair enabled for `review-artifact`) |
| R2 | Render cache self-evicts >1 GiB outputs; no cache reuse ever | up to 700 s on identical re-render | `render/cache.py::evict` + 1 GiB default |
| R3 | No incremental/parallel segment rendering in the default path; preview-chunks engine unused by UI, serial, 1 s chunks | ~49 min for a full chunk preview; any single edit re-renders everything | `kernel/render_jobs.py`, `render/preview_chunks.py`, `serve/static/app.js` |
| R4 | Preview file layout: moov at end, 3.9 Mbps, 3.1 s GOP, 1.1 GB | slow first frame + sluggish scrub; blocks server shutdown | `render/cuda_fastpath.py`/`melt_runner.py` mux (no faststart), encoder args |
| R5 | No per-asset source proxy in the default path; every render decodes 1080p source | decode-bound floor ≈ 78 s | `render/timeline_plan.py::_EMISSION_POLICY`, `storage/assets.py` ingest |
| R6 | Audio wav (424 MB) regenerated every render; no waveform cache | 19.3 s + disk | `render/melt_runner.py`, `render/timeline_view.py` |
| R7 | UI full-state polling with per-poll timeline re-derivation + 528 KB sidecar parse; no progress feedback | 47 ms/poll now, linear in timeline size; no progress UX for 12 min | `serve/projects.py::get_project_state`, `serve/static/app.js` |
| R8 | No keyframe index / thumbnail strip / preview-chunks UI | scrub/seek UX absent | serve + static |

---

## 3. Concrete modification plan

### (a) One-time proxy/transcode at ingest (or first open) into a fast I-frame-friendly intermediate at preview res — **M**

- **Files**: `open_edit/storage/assets.py` (ingest hook), `open_edit/kernel/asset_proxy_jobs.py` + `serve/routers/assets.py` (queue + endpoints already exist), `open_edit/render/source_proxy.py` (profile), `open_edit/render/timeline_plan.py` (`_EMISSION_POLICY`), `open_edit/serve/projects.py` (auto-enqueue on project open).
- **What**: after CAS ingest, enqueue an `asset_proxy_job` (already implemented) that transcodes the asset once with the CUDA fastpath recipe: `-hwaccel cuda -hwaccel_output_format cuda -vf scale_cuda=640:360 -c:v h264_nvenc -preset p4 -cq 28 -g 30 -keyint_min 30 -sc_threshold 0 -movflags +faststart` (all verified working on this machine; NVENC 15x). Store as a second CAS object, record `proxy_hash/proxy_status=ready` in the meta.json (fields already exist on the `Asset` model). If NVENC unavailable, fall back to libx264 veryfast with the same GOP/faststart flags.
- **How it works**: one-time cost ≈ 2–4 min for a 37-min 1080p source (background, queue-backed, resumable), after which **every** proxy render, preview chunk, and scrub decodes 360p instead of 1080p: decode-bound pass drops from ~78 s to ~10–20 s; memory/IO drop 9x. Wire `review-artifact` (or at least `preview-chunk`) to use the proxy when `proxy_status==ready` (the plumbing in `build_render_plan`/`source_proxy` already exists — only the default policy and the enqueue-at-ingest are missing).
- **Effort**: M. Most modules exist; work is policy wiring + one background job at ingest + meta.json plumbing.

### (b) Incremental/smart rendering: dirty segments only; segment cache keyed by (asset_hash, effect chain, in/out); stitch — **L** (engine exists, needs completion)

- **Files**: `open_edit/render/preview_invalidation.py` (chunk size + fingerprints), `open_edit/render/preview_chunks.py` (`run_preview_pipe` serial loop), `open_edit/render/preview_cache.py` (cache), `open_edit/render/preview_manifest.py`, `open_edit/render/orchestrator.py` (whole-file path), new `open_edit/render/segment_stitch.py`.
- **What/How**:
  1. **Chunk size**: `make_chunk_windows` defaults to 1 s; make it adaptive — `chunk_frames = clamp(duration_frames/64, 1s, 30s)` (e.g. 30 s for this project → 74 chunks). With the measured 1.3 s fixed overhead, 60 s chunks cost 2.54 s each; 74 × 2.54 s ≈ 3 min serial, <1 min parallel. Keep 1 s chunks only for short timelines.
  2. **Segment cache key**: extend `compute_chunk_fingerprints`/`_chunk_plane_key` so the artifact key includes (asset_hash + per-clip/effect-chain hash + in/out + profile fingerprint) — the code already hashes per-clip effects and ops; make the key not depend on the **global** graph hash so an edit at t=600 s doesn't invalidate chunks at t=0. (Current manifest keys are content-sha256-based and already content-verified; the fingerprinting layer already localizes ops to windows via `select_dirty_windows` — verify/strengthen the localization.)
  3. **Stitch**: when a contiguous span of chunks is fully green, concat their mp4s with `ffmpeg -f concat -c copy` into a whole-file preview (all chunks must share encoder settings + faststart/GOP; enforce via the profile fingerprint). Serve the stitched file through the existing `/renders/{id}/file` 206 path; UI keeps working unchanged while the engine becomes incremental.
  4. For the final render, apply the same segment machinery when the timeline is long (reuse chunk workers, then stitch with matching encoder settings).
- **Effort**: L (engine exists — chunk windows, fingerprints, dirty selection, manifest, cache with sha256 verify are all implemented and tested — but chunk sizing, parallelism, key localization, stitching, and UI consumption are missing).

### (c) Parallel segment rendering (NVENC) — **M**

- **Files**: `open_edit/render/preview_chunks.py` (worker loop), `open_edit/kernel/render_jobs.py` (per-project lock currently allows only one render; preview-chunks could get a segmented worker pool), new `open_edit/render/segment_pool.py`.
- **What**: replace the serial per-chunk loop with an `asyncio`/`ThreadPoolExecutor` pool of subprocess workers (default `min(4, OPEN_EDIT_RENDER_CHUNK_CONCURRENCY)`). Each worker runs one ffmpeg per chunk with CUDA decode + NVENC (verified on this machine: RTX 4050 6 GB, idle; 12 CPU cores idle during the decode-bound pass). GPU can sustain 2–3 concurrent CUVID/NVENC sessions; CPU-decode fallback parallelizes across the 12 cores.
- **How it works**: dirty chunks are batched by `select_dirty_windows` (already returns prioritized indexes), dispatched to N workers, artifacts committed to the preview cache as they finish, manifest published when the requested ranges are green. Interactive playhead range renders first (the code already prioritizes `requested_ranges`).
- **Evidence**: predecessor chunk timing (60 s chunk = 2.54 s), NVENC 15x measured, 12 cores idle, GPU idle. 37 chunks × 2.5 s / 4 workers ≈ 25 s for a full 37-min preview; a 10 s edit ≈ 3 dirty chunks ≈ 2–4 s.
- **Effort**: M.

### (d) Preview serving: byte-range streaming + I-frame-only scrub + first-frame-fast (keyframe index) — **S/M**

- **Files**: `open_edit/render/cuda_fastpath.py` + `open_edit/render/melt_runner.py` (mux args), `open_edit/render/pipe_builder.py` (encoder args for preview), new `open_edit/render/keyframe_index.py`, `open_edit/serve/routers/renders.py` (endpoint), `open_edit/serve/static/app.js` (scrub).
- **What**:
  1. **First-frame-fast**: add `-movflags +faststart` to every preview/proxy mux (second pass over moov only; seconds of cost) **and** set `-g 30 -keyint_min 30 -sc_threshold 0` (1 s GOP) on preview encodes. Faststart alone removes the 62 MB tail fetch; 1 s GOP makes browser seeks land ≤1 s from target. Optionally use `-movflags frag_keyframe+empty_moov` for the preview-chunk playback path (fMP4: tiny moov, per-keyframe moof, ideal for scrub; keep regular mp4 for whole-file/final).
  2. **Keyframe index**: after a render, build `<render>.kf.json` once with `ffprobe -skip_frame nokey -show_entries frame=pts_time` (measured: 0.1–0.3 s for this file) → list of keyframe PTS. Serve `GET /api/projects/{id}/renders/{rid}/keyframes`. UI scrub (`seekToSec`) snaps to the nearest keyframe index (browser decodes ≤1 s of delta frames; at 30 fps that's trivially fast) and shows a keyframe marker strip.
  3. **Byte-range**: already works (FileResponse, 206 observed) — keep, but use the keyframe index to serve "seek previews" (first I-frame of a requested range) if thumbnail-strip rendering is not yet done.
- **Effort**: S (faststart + GOP flags) + M (keyframe index endpoint + UI scrub). Impact: first frame <100 ms on localhost; scrub feels instant.

### (e) Skip source-repair when the source decodes cleanly; make it verify-based / opt-in — **M**

- **Files**: `open_edit/render/source_repair.py`, `open_edit/render/orchestrator.py` (repair policy block), `open_edit/qc/policy.py` (resolve_qc_policy), `open_edit/render/encoder.py` (repair encoder).
- **What** (in order of preference):
  1. **Segment-local repair (recommended)**: `repair_render_output` already computes the exact defect windows (23 windows ≈ 112.5 s) and confirms them on the output. Instead of `_repair_stream` decoding the whole file, re-encode **only the confirmed windows** (input-seek `-ss`/`-t` + NVENC or libx264 with matching settings) and splice via concat `-c copy` (windows are frame-aligned; GOP must match). Cost drops from ~525 s to ≈ 23 windows × ~3 s ≈ 70 s, or ~10 s with NVENC.
  2. **Make repair opt-in for previews**: `resolve_qc_policy` should treat proxy/review-artifact repair as `verify` by default (run detectors, report findings in `qc_report`, never re-encode), with an explicit env/API opt-in (`OPEN_EDIT_REPAIR=1` or `repair: true`) for deliverables. The detection-only cost is 209 s in `full_proxy` (changed=false) — still too much for a preview; add a detection budget for proxy (`detector_timeout_s` already exists; bound total windows scanned to e.g. 60 s of timeline per proxy render, full scan only for final).
  3. **Use NVENC for the repair re-encode** when it does run (current `libx264 veryfast` CPU; NVENC measured 1.6x faster at equal rate, plus no Python raw-RGB pipe: replace the rawvideo pipe with `-vf trim`/segment input so ffmpeg does the whole pass in one process — the Python per-frame loop is the actual bottleneck: 4.2x vs 9.2x for the same encoder).
  4. **Cache the source baseline better**: `collect_source_baseline` has a per-(asset_hash, source_hash, extent) disk cache that works, but a fresh live run re-scanned the whole source (9+ min of freezedetect observed in `ps`). Ensure the cache dir is stable across harness/CLI invocations and skip re-scan when the cached baseline is fresh.
- **Effort**: M (item 1-3 are localized changes; item 4 is wiring). **This is the single biggest lever**: 209–579 s → <90 s.

### (f) Audio: waveform cache + separate fast audio mix pass — **S/M**

- **Files**: `open_edit/render/orchestrator.py` / `melt_runner.py` (cache the wav), new `open_edit/render/waveform_cache.py`, `open_edit/render/timeline_view.py` (reuse `render_waveform`), `open_edit/serve/routers/renders.py` + static UI.
- **What**: (1) cache the 424 MB `*.audio.wav` keyed by graph hash (the mix only depends on the edit graph's audio chain — `melt_audio` 19.3 s and 424 MB disk are pure waste on re-render); reuse the cached wav in the mux pass. (2) Per-asset waveform cache: one `ffmpeg astats`/`showwavespic` pass per asset (or per chunk during preview render), store min/max peaks as JSON next to the CAS meta; serve `GET …/waveform`; UI renders the audio track from cache. `render_waveform` exists but re-runs ffmpeg per call with no cache.
- **Effort**: S (wav cache) / M (waveform cache + UI). Impact: −19 s per re-render; instant waveform on open.

### (g) UI + API: lightweight timeline state (delta updates), thumbnail strip cache — **M**

- **Files**: `open_edit/serve/projects.py` (new `GET /api/projects/{id}/state?since_rev=N`), `open_edit/serve/static/app.js` (poll the light endpoint; use the existing `js/ws.js` for push), `open_edit/render/timeline_view.py` (thumbnail strip), new `open_edit/serve/routers/thumbnails.py`, `open_edit/serve/routers/preview_chunks.py` (already exists — UI must consume it).
- **What**:
  1. **Lightweight state**: split `get_project_state` into (a) a summary payload `{graph_revision, edit_graph_hash, timeline_status, render_jobs, active_job}` for the 5 s poll, and (b) heavy payloads (`timeline_full`, ops) only on demand or when `graph_revision` changes (the UI already skips repaint when revision is unchanged — the server should skip re-derivation too: use `derive_or_load_timeline`'s snapshot cache, which `get_project_state` currently bypasses). Also stop re-parsing the 528 KB transcription sidecar on every poll (`list_assets_from_disk` reads/validates every meta.json per call).
  2. **Thumbnail strip**: generate once per (render/asset, width, count) — replace `extract_frames`' N ffmpeg calls with a single `ffmpeg -vf "fps=1/10,scale=160:-1,tile=10x1"` pass, cache under `.open_edit/thumbs/`, serve via a route, render in the timeline ruler. Both building blocks exist (`timeline_view.py`, `thumbs` used by QC gate).
  3. **Progress**: add `started_at`/`finished_at`/`stage`/`progress` columns to `render_jobs` (schema migration is already handled by `_ensure_schema` ALTERs) and update a `progress` field on stage transitions; UI shows real progress instead of blind 2 s polling that gives up at 10 min (fix `maxAttempts` too — currently silently stops polling after 10 min even though the render continues for 12).
  4. **Wire preview-chunks into the UI**: `GET /api/projects/{id}/preview-chunks` (manifest + active job + proxy fallback) already exists; the UI should trigger `mode=preview-chunks` with the current playhead range after an edit (auto-preview), render chunks incrementally, and fall back to the whole-file proxy (`proxy_fallback` in the response) for playback until green. This is the step that makes "edit → preview in ~1 min" real.
- **Effort**: M overall (1-2 are S; 3 S; 4 M).

---

## 4. Effort/impact table and recommended order

| # | Change | Effort | E2E proxy impact | Final impact | Depends on |
|---|---|---|---|---|---|
| 1 | (e1) Segment-local + verify-based source repair; NVENC repair; bounded proxy detection | M | 579 s → 60–90 s (or ~0 s when opted out of re-encode) | 1427 s → ~100–200 s | — |
| 2 | (b1/R2) Fix render cache: raise cap (default ≥ 8 GiB or no cap for render_cache) + don't evict the just-put entry | S | identical re-render 700 s → ~1 s | same | — |
| 3 | (d1) faststart + 1 s GOP on proxy/preview encodes | S | first frame <100 ms; scrub ≤1 s | n/a | — |
| 4 | (f1) cache audio wav per graph hash | S | −19 s per re-render, −424 MB | same | — |
| 5 | (a) ingest/first-open source proxy (360p, I-frame friendly), use for review-artifact | M | video pass 78 s → ~15–20 s | decode floor down | 3 (same encoder recipe) |
| 6 | (b2/c) adaptive chunk size + parallel chunk workers | M | full 37-min preview ~25–60 s; 10 s edit ~3–8 s | segment parallelism | 5 (source proxy helps chunks) |
| 7 | (e4) baseline cache stability (skip re-scan) | S | −0–9 min on cache miss | same | — |
| 8 | (g1) light state endpoint + snapshot-cached derive | S | poll 47 ms → ~5 ms; scales | same | — |
| 9 | (g3) render job progress columns + UI progress | S | UX (12 min progress) | same | — |
| 10 | (d2) keyframe index + UI I-frame scrub | M | scrub instant | same | 3 |
| 11 | (f2) waveform cache + UI | M | instant waveform | same | — |
| 12 | (b3) segment stitching into whole-file mp4 | M | whole-file incremental preview | stitch-based final | 6 |
| 13 | (g4) UI preview-chunks consumption (auto-preview on edit) | M | "edit → preview ≈ 1 min" | — | 6, 12 |
| 14 | (g2) thumbnail strip cache + timeline UI | M | visual scrub | same | — |
| 15 | (R4b) graceful-shutdown/streaming robustness (bounded streaming, disconnect detection, `Connection: close` after render file) | S | no stuck server | same | — |

**Recommended order** (each step is independently shippable):
1. **Week 1 (S, high ROI, low risk):** 2 (cache fix), 3 (faststart/GOP), 4 (wav cache), 7 (baseline cache), 8-9 (state + progress), 15 (server shutdown).
2. **Week 2-3 (M):** 1 (repair rework — the biggest single win), 5 (source proxy at ingest + policy), 10 (keyframes), 11 (waveform).
3. **Week 3-5 (M/L):** 6 (chunk sizing + parallel workers), 12 (stitch), 13 (UI preview-chunks consumption), 14 (thumbnail strip).

With 1–5 done, the E2E proxy goes from **700 s → ≈ 60–120 s** (decode 15–20 s + audio 0 s cached + repair ≤90 s or skipped + mux faststart) and preview-after-small-edit lands in the **sub-minute** range once 6/12/13 land. The hard floor for this machine/project is the 1080p decode (~78 s at 28x with CUDA) — that's why step 5 (source proxy) is what removes the last "decode the whole 37-min file" cost.

---

## 5. Appendix — raw evidence pointers

- Stage breakdown & repair: `render_jobs.db` job `0c06145c44db…` (`result_json`), `benchmark_logs/full_proxy.json`, `full_final.json`, `gpu_proxy_result.json`, `gpu_proxy_cached_final.json`.
- Cache self-evict: `open_edit/render/cache.py` (`DEFAULT_RENDER_CACHE_MAX_BYTES = 1024**3`, `put()` → `evict()`, `evict()` deletes while `total_bytes > max_bytes`); `renders/render_cache/` empty `.meta`; job `493b7f90…` ENAMETOOLONG traceback (260-char key, since capped at 180).
- Repair re-encode: `open_edit/render/source_repair.py::_repair_stream` (rawvideo rgb24 pipe, Python frame loop, libx264 veryfast crf18).
- Fast path: `open_edit/render/cuda_fastpath.py` (`-hwaccel cuda -hwaccel_output_format cuda -vf scale_cuda … -c:v h264_nvenc`), measured 28.4x in E2E, 15x in my 60 s benchmark.
- Preview chunks: `preview_chunks/manifest.json` (12 chunks, 2 rendered, audio/playback red), `open_edit/render/preview_invalidation.py::make_chunk_windows` (1 s default), `open_edit/kernel/tool_executor.py` (`MAX_PREVIEW_RANGES = 64`), `open_edit/serve/routers/preview_chunks.py` (manifest/file routes exist).
- UI: `open_edit/serve/static/app.js` (5 s state poll, 2 s job poll, 120 attempts, plain `<video src>`, no chunk/scrub/keyframe usage); `open_edit/serve/projects.py::get_project_state` (full sync rebuild, `derive_timeline` direct, `_REGISTRY.lock` serialization).
- mp4 layout: `grep -abo moov` → 1034390601 / 1093884918; `ffprobe -skip_frame nokey` → 644 keyframes, median GOP 3.14 s; no faststart.
- Machine: `nvidia-smi` (RTX 4050 6 GB, idle), `nproc` 12, `ffmpeg` n8.1.2 (nvdec/nvenc), `melt` 7.40.0.
- Per-invocation overhead & seek: `testrun/SALVAGE_EXPLORER.txt` (1 s chunk 1.34 s … 60 s chunk 2.54 s; local `-ss` frame extract 0.13 s; sha256 1.46 GB in 1.39 s; blackdetect 60 s window 1.51 s; freezedetect 60 s window 0.76 s).
- Server/API: `/tmp/openedit_serve.log` (875 requests avg 44.6 ms; 922× state polls avg 47.2 ms; 66× HTTP 206; stuck-shutdown ESTAB with 2.6 MB Send-Q on the render mp4).
