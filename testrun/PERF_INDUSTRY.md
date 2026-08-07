
---

## 1. What OpenEdit has today (inventory, all verified from source + measurements)

### 1.1 Whole-file proxy render (the E2E path)
- `open_edit/kernel/render_jobs.py` (durable job service), `open_edit/render/orchestrator.py` (stage pipeline), `open_edit/render/cuda_fastpath.py` (pure-ffmpeg fast path).
- **CUDA fastpath** (`cuda_fastpath.py`): for a *simple* timeline (one full-length clip, no effects/transitions/overlays/remotion/audio) it runs `ffmpeg -hwaccel cuda -hwaccel_output_format cuda -vf scale_cuda -c:v h264_nvenc -an`. Measured: 59.3 s / 37.6× (this machine, idle); 77.9 s / 28.4× in E2E.
- Everything else goes through **melt** (`melt_runner.py`): measured 60-s window at 640×360 + NVENC = 12.5 s ⇒ **~4.8× realtime** (≈ 7.7 min for the full 37-min file) — melt's CPU decode/composition is the ~8× slower fallback.
- After the video pass, **source_repair** (`source_repair.py`) runs: it detects black/frozen defects in the *source* (baseline, cached per asset hash + extent under `renders/render_cache/source_baseline/`), re-detects them in the *output* windows, and if any survived, `_repair_stream` **decodes the entire output to raw RGB through a Python per-frame loop and re-encodes with libx264 veryfast crf 18** (CPU). Measured: cold baseline scan ≈ 215 s (blackdetect 113.3 s + freezedetect 101.6 s @360p full source); `_repair_stream` full-file ≈ 268 s (8.3× realtime, measured on 120-s sample: 14.5 s). In the E2E the source has 16–18 real black spans ⇒ `changed=true` ⇒ the 579-s stage.
- **melt_audio**: renders the full 36.9-min WAV (424.6 MB, 16-bit 48 kHz stereo) in 15–19 s every render; then muxes AAC into the MP4.
- **Whole-file render cache** (`render/cache.py`): keyed by edit-graph hash + profile fingerprint, TTL 24 h, max 1 GiB. Any edit ⇒ new graph hash ⇒ cache miss ⇒ full re-render. `renders/render_cache/` in the E2E project contains only `source_baseline/` entries (no deliverable cache).

### 1.2 Preview-chunks system (the interactive path)
- `open_edit/render/preview_manifest.py` (manifest schema), `preview_chunks.py` (worker), `preview_invalidation.py` (fingerprints/dirty windows), `preview_pipe.py` (melt→rawvideo→ffmpeg commands), `preview_video_renderer.py` (HostPreviewVideoRenderer), `serve/routers/preview_chunks.py` (REST: manifest + artifact files + wipe).
- **Chunking**: default chunk = **1 s** (`make_chunk_windows`, `chunk_frames = fps`), frame-aligned, each chunk rendered as its own MP4 (640×360, `preview_chunk` profile; manifest says `vcodec=libx264`; the profile field is libx264 and `resolve_encoder_args` would pick NVENC when backend=gpu — a metadata inconsistency worth noting).
- **Invalidation is genuinely per-plane and localized**: `compute_chunk_fingerprints` keys each chunk's video/audio planes on the *sliced timeline + profile + content + localized operation markers*, so an audio-only edit dirties only overlapping audio chunks; `select_dirty_windows` then bakes only dirty chunks intersecting requested ranges. This is real incremental-render machinery (green/yellow/red statuses, fallback artifacts, atomically published manifest).
- **Serving**: `/api/projects/{id}/preview-chunks` returns manifest + active job + whole-file proxy fallback; artifacts streamed with Range support. The static Review Studio UI (`serve/static/app.js`) **does not use this API** — it loads the whole-file proxy render (`loadRenderInPreview` → `/renders/{id}/file`) and shows a toast "Render proxy to preview changes".
- **E2E reality**: the single preview-chunks job in `render_jobs.db` (`84b40034…`, range 0–2 s, media video) was **cancelled after 1.2 s**; only 2 of 360 chunks (12-s manifest, 30-frame chunks) have video artifacts, all "yellow" (fallback only), audio/playback planes red. The E2E then ran the whole-file proxy render instead.

### 1.3 Source proxies (ingest-time transcodes)
- `open_edit/render/source_proxy.py` + `open_edit/kernel/asset_proxy_jobs.py` + `serve/routers/assets.py` (`POST /assets/{hash}/proxy`): a per-asset proxy job service exists, with a default profile (`DEFAULT_SOURCE_PROXY_PROFILE`).
- In the E2E project: `source_proxy_profile_fingerprint: None`, `source_proxy_hits: []`, `source_proxy_fallbacks: []` — **no source proxy was ever generated or used**; `source_media_policy: original` everywhere. The proxy render decodes the original 1080p source directly (which is fine for CUDA decode, but the mechanism is unused).

### 1.4 GPU & hardware (measured on this machine)
- `nvidia-smi`: **RTX 4050 Laptop, 6 GB VRAM, 35 W TDP**, CUDA 13.3, idle 4 W.
- `lscpu`: **AMD Ryzen 5 8645HS, 6 cores/12 threads, Zen 4, up to 5.0 GHz, AVX-512**.
- ffmpeg n8.1.2 with `h264_nvenc`, `hevc_nvenc`, `av1_nvenc`, `h264_amf`, `h264_qsv`, `h264_vaapi`, `cuda`/`vdpau`/`vaapi`/`vulkan` hwaccels. Encoder probe order in code: h264_nvenc → h264_amf → h264_qsv → h264_vaapi → libx264 (`encoder.py`).
- Measured encode speeds (this machine, full 2211-s source):
  - 640×360 NVENC p4 constqp cq20 + CUDA decode: **59.3 s (37.6×)** — E2E measured 77.9 s (28.4×).
  - 1920×1080 NVENC p5 vbr 10M: **6.6 s per 60 s (9.0×)** ⇒ full file ≈ 244 s, with or without CUDA decode (CPU decode is not the bottleneck at 1080p on this CPU).
  - libx264 veryfast crf18 640×360 (repair encoder): 8.8 s per 120 s (13.6×) ⇒ full ≈ 163 s in a direct pipe; 268 s through the Python frame pump.
  - melt 640×360 + NVENC: 12.5 s per 60 s (4.8×) ⇒ full ≈ 460 s.

---

## 2. The five industry techniques, and the gap per technique

> Industry side of each item is documented in §3 (with citations from `testrun/INDUSTRY_RESEARCH.md`); this section is the OpenEdit gap analysis.

### 2.1 Proxies transcoded ONCE at ingest
**Pros:** generate small proxies (ProRes Proxy / DNxHR LB / H.264) in the background at import; edit on proxies, conform to originals at export; switching proxy↔original is instant and non-destructive.
**OpenEdit:** source-proxy jobs exist (`asset_proxy_jobs.py`) but are **never used by the render pipeline** — `source_media_policy: original` in every E2E run, zero `source_proxy_hits`. The "proxy" that exists is a *render output* profile (fast_proxy 640×360), not an ingest-time source proxy.
**Gap:** no ingest/asset-proxy-first workflow; every render re-reads the 1.46-GB 1080p source. (Mitigated today by CUDA decode, but the asset proxy would let melt/CPU paths and future GPU contention run ~9× fewer pixels.)

### 2.2 Smart/incremental rendering (only dirty segments)
**Pros:** per-segment render cache; red/yellow/green or blue bar per segment; edits dirty only overlapping segments; cached segments play instantly from disk; final conform reuses cache.
**OpenEdit:** two partial mechanisms —
- whole-file deliverable cache keyed on graph hash (`render/cache.py`): all-or-nothing;
- preview-chunk cache keyed per-plane/per-chunk with localized invalidation (`preview_invalidation.py`): this is the right shape, but (a) chunks are 1-s/30-frame, (b) each chunk render pays ~1.3-s fixed melt/ffmpeg startup (measured 1.34 s for a 1-s chunk), (c) the UI doesn't use it, (d) the E2E cancelled it.
**Gap:** chunk cache exists but is unusably granular + unused; no smart pass-through of unchanged segments in the whole-file path.

### 2.3 I-frame-friendly intermediates for frame-accurate preview
**Pros:** ProRes/DNxHR/CineForm (intra-frame) or All-I H.264: any frame decodes alone ⇒ instant seek/scrub; long-GOP H.264 requires decoding from the previous keyframe (0.5–2 s) ⇒ visible seek latency and CPU spikes.
**OpenEdit:** preview artifacts are **long-GOP H.264 MP4s** (chunk files and proxy render); seeking in the browser player = server-side byte-range + decoder seek within GOP. No intra-frame intermediate anywhere in the pipeline.
**Gap:** chunk-per-file masking partially compensates (seeking between chunks = file switch), but scrubbing inside a chunk and proxy scrubbing are long-GOP-limited; no ProRes/DNxHR/All-I option; no HLS/DASH segment streaming.

### 2.4 GPU effects + encoders
**Pros:** Mercury/Resolve/FCP move decode, scaling, transforms, color, blending, and *encode* to GPU; NVENC/QuickSync/AMF are 5–40× faster than x264.
**OpenEdit:** decode+encode GPU fastpath exists **only for the trivial single-clip case** (`cuda_fastpath.py`); everything else (melt composition, chunk pipe, source-repair re-encode) is CPU; `_repair_stream` re-encodes with **libx264** even though NVENC sits idle. Encoder selection (`encoder.py`) does prefer NVENC for melt/ffmpeg, but melt's composition and the rawvideo pipe are the CPU bottleneck (4.8× vs 37.6×).
**Gap:** no GPU-composited fallback for effect timelines; repair pass ignores the GPU entirely.

### 2.5 Parallel/segmented rendering + background ingest
**Pros:** render cache segments in parallel worker processes/threads, GPU+CPU together, background priority; ingest/proxy generation runs during editing.
**OpenEdit:** single-process pipeline (one melt video + one melt audio + one repair + one mux, all sequential); no segment parallelism; no background ingest queue in use; the only "background" notion is the job queue priority tag in preview-chunks. The audio pass (15–19 s) and repair pass (215–579 s) run serially after video.
**Gap:** zero parallelism; wall time = sum of stages, and the biggest stage (repair) is also the one that should be skipped/cached.

---

## 3. Industry reference (from `testrun/INDUSTRY_RESEARCH.md` — see that file for citations)

> (populated from the industry-researcher sub-agent brief — merged below when delivered)

---
