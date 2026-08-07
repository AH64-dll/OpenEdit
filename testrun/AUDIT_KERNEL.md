# AUDIT_KERNEL — Render-Performance Investigation: Kernel Evidence Report

Date: 2026-08-06 (UTC+14 h; server local). Server: `open_edit.cli serve --review-only --port 8000` at http://127.0.0.1:8000.
Project audited: `/home/amr/Videos/video` (API id `9dc089c70c5f`). Repo: `/home/amr/apps/mlt-pipeline` (venv Python 3.14).

Live state: 1 asset (`untitled_cl.mp4`, 2211.34 s, 29.97 fps, 1920×1080 h264), edit graph rev **37**, 19 ops (1 applied `add_clip` + 18 reverted), timeline duration **2211.34 s**.
Latest render: proxy `project_fe5214616f5a.mp4` = 1,096,296,584 B (1.02 GiB), 640×360 h264/yuv420p 29.97 fps, video bitrate ~3.88 Mbps (ffprobe), duration 2211.24 s, took **704.3 s** wall (job row 0c06145c: created 1786015413.19 → updated 1786016117.54) ≈ **3.1× realtime**.

---

## 1. PREVIEW CHUNKS PIPELINE

### 1.1 Worker entrypoint & lifecycle
- Entry: `open_edit/render/preview_chunks.py:1205` `render_preview_chunks(...)` — a synchronous worker that is executed **as a subprocess**:
  `open_edit/kernel/render_jobs.py:564-568` builds `[sys.executable, "-m", "open_edit.cli", "preview-chunks", "--job-id", job_id, "--json"]` and `:599` spawns it with `asyncio.create_subprocess_exec` (start_new_session on POSIX). No thread-pool, no in-process render: each job is one CLI subprocess owned by the serve process.
- `open_edit/cli.py:177-226` `cmd_preview_chunks` loads the job row by job_id, calls `render_preview_chunks(project_id=job.project_id, ...)`, prints JSON result.
- Concurrency: `render_jobs.py:84` `OPEN_EDIT_RENDER_CONCURRENCY` default **1** (asyncio.Semaphore) + one asyncio.Lock per project (`:377`); timeout default 14400 s (`:88-91`); cancel = SIGTERM process group (`:352-371`); jobs interrupted by server restart are marked `orphaned` (`:163-172`).
- **Job state machine (render_jobs.db):** `queued → running → cancelling → cancelled | succeeded | failed | orphaned` (`render_jobs.py:55-56`). No progress %, no speed_x, no per-stage columns — timings live only in `result_json` diagnostics.

### 1.2 Chunk geometry, resolution, codec
- Chunk size: **1 second** by default. `preview_invalidation.py:93-94` `chunk_frames = max(1, round(fps_num/fps_den))`; optional `chunk_frames` param (`preview_chunks.py:314-326`). FPS defaults to first asset fps (29.97 → 30000/1001).
- Profile: `profiles.py:83-98` `preview_chunk_profile` = **640×360, libx264, aac 96k, quality "fast"**, geometry hard-fixed (`preview_pipe.py:64-68` rejects overrides).
- Encoder: `encoder.py` gpu backend → **h264_nvenc** fast spec (`-preset p4 -rc constqp -cq 20 -profile:v high`); manifest on disk shows `enc=gpu`.
- Per-chunk invocation (video): `preview_pipe.py:90-142` — `melt <xml> -consumer avformat:pipe: f=rawvideo vcodec=rawvideo pix_fmt=nv12 s=640x360 ...` piped into `ffmpeg -f rawvideo -i - [-i overlay...] -vf trim=start_frame=..:end_frame=.. -c:v <encoder> -frames:v <core_frames>`; audio: `melt ... video_off=1 format=wav | ffmpeg -af atrim -c:a aac -b:a 96k` (`:145-173`); mux: `ffmpeg -c:v copy -c:a copy -shortest` (`:182-198`).
- Each chunk renders with a slice of the timeline (`_slice_and_emit`, `preview_chunks.py:638-683`): `slice_timeline` + `build_render_plan` + `emit_timeline(..., hwaccel=True)`; overlay/remotion/hyperframes are materialized and burned as overlay clips (`preview_video_renderer.py` `HostPreviewVideoRenderer.render`). Render range may be wider than core to cover transitions; crops applied in ffmpeg trim.
- **Measured artifacts** (`/home/amr/Videos/video/.open_edit/preview_chunks/video/`): `480ef6aa….mp4` = 264,752 B and `83e3f41c….mp4` = 161,038 B, both exactly 1.001 s, 640×360 h264 yuv420p 30000/1001 (ffprobe) ≈ 2.1 / 1.3 Mbps.
- **Measured cost**: job `bb4cc042` (rev 9, media=video, 2 chunks): `elapsed_sec.video = 3.733 s` → **~1.87 s per 1 s chunk** on GPU. Extrapolated full 2211-chunk pre-bake ≈ 69 min.

### 1.3 Cache keying & hit/miss
- Keys are **per-plane hashes**, computed in `preview_invalidation.py:542-660` (`compute_chunk_fingerprints`) and `:732-758` (`_chunk_plane_key`). `video_key`/`audio_key` = sha256 of: `plane`, `core_range [start_frame,end_frame]`, `render_range`, `profile_fingerprint`, `content_fingerprint`, **sliced timeline value** (`_key_timeline_value`), and localized `operation_markers`. Note comment at `:555-559`: graph hash is deliberately NOT in the key (audio edit must not flush video).
- `content_fingerprint` (`preview_chunks.py:360-407`): per-asset `asset_hash, content_hash, proxy_hash, proxy_profile, proxy_status` + remotion reference fingerprint → asset re-encode/swap invalidates everything.
- Artifact id == key (`preview_cache.py:262,277-286`), stored as `<plane>/<key>.<ext>`; index in `.artifact_index.json`; every `resolve_artifact` re-verifies sha256 (`:337-363`) — full-file hashing on every resolve.
- Hit/miss: dirty flags from old-vs-new timeline key comparison + operation-interval overlap (`:611-645`); **unknown ops (`raw_mlt_xml`, `free_form_code`) or missing old timeline ⇒ conservative full dirty** (`:414-446`, `:575-582`). Plane states: green=current artifact usable; yellow=fallback artifact; red=nothing (`preview_chunks.py:475-511`). `select_dirty_windows` (`:663-729`) picks only **dirty chunks overlapping requested ranges + their ±1 neighbors**; `priority=background` picks **all dirty**.
- **Cache policy**: `preview_cache.py:51-83` — default max 512 MiB (`DEFAULT_PREVIEW_CACHE_MAX_BYTES`), age limit default (`preview_cache_max_age_sec`), min-free reserve; LRU prune of unreferenced/expired artifacts after each job (`prune`, `:365-510`); temp dirs cleaned only by prune (SIGTERM-cancelled jobs leave `tmp/<job>/` behind — observed: `preview_chunks/tmp/84b40034…/chunk-000000-video.mlt`).

### 1.4 Serving to the UI
- `serve/routers/preview_chunks.py:109-121` `GET /api/projects/{id}/preview-chunks` returns `{manifest, active_job, proxy_fallback}`; manifest URLs are rewritten to `/api/projects/{id}/preview-chunks/files/{artifact_id}` (`:56-88`); file route `:123-142` streams via `FileResponse` with `Accept-Ranges: bytes` → **Range/206 supported** (measured: 206, `content-range: bytes 0-1023/264752`, 77 ms).
- `proxy_fallback` (`:146-208`): newest whole-file proxy render with `stale` flag — currently returns `project_fe5214616f5a` with `"stale": true` (manifest is 3 revisions behind, see 1.6).
- **The shipped UI never calls any preview-chunks endpoint**: `static/app.js` has **0 hits** for `preview-chunks`/`manifest`/`active_job`/`proxy_fallback`; preview player uses whole-file proxy MP4 via `loadRenderInPreview` (`app.js:1560-1563`).

### 1.5 Prefetch / warmup
**None.** No background warm-up on project open; `auto_proxy=false`, `auto_preview=false` in `/api/ui-config` (measured). Chunks render only when a job is explicitly enqueued (POST /render or MCP tool) and only the dirty∩range windows (+neighbors). No predictive lookahead, no low-priority full pre-bake (only explicit `priority=background`).

### 1.6 Invalidation
- `preview_invalidation.py:818-915` maps each op kind to affected intervals (`add_clip` → clip interval, `set_effect_param` → effect interval, …); `group_edits`/`ungroup_edits`/`remove_transition`/`set_transition_property`/`remove_html_overlay`/unknown kinds → **full timeline** (`_FULL_TIMELINE_KINDS`).
- `_check_graph` guard aborts the worker mid-bake if graph revision/hash changed (`preview_chunks.py:795-801`, called at every stage); manifest publish is atomic + optimistic (`_publish`, `:1098-1115`), stale workers can't clobber newer manifests.
- **Observed staleness**: on-disk `manifest.json` = graph_revision **34**, hash `750935c2…`, duration 12 s, 12 chunks of 30 frames; current graph is rev 37 / 2211 s. Only chunks 0–1 carry video `fallback` artifacts (from rev-9 hash `ece20daf…`); all `audio` and `playback` planes are **red** — no audio/mux artifact was ever produced by any job in the DB (9 preview-chunks rows: 4 succeeded but 3 processed 0 chunks, 2 processed 2, rest cancelled/failed). Manifest `job_id` = cancelled job `84b40034…` (cancel interrupted cleanup).

### 1.7 Gaps vs professional NLE preview
1. **No I-frame/keyframe index** — manifest has no GOP/keyframe metadata; chunks are fixed 1 s windows (frame-aligned, not scene-aware). Scrubbing = switching chunk files; no per-frame seek support.
2. **No scrub thumbnails/sprite sheets** — nothing generates contact sheets or per-second thumbnails for the timeline.
3. **No prefetch/warmup** (1.5).
4. **Audio/playback planes never exercised** in practice (all red in real data).
5. **No UI integration** — the preview-chunks API is dead code from the frontend's perspective.
6. Chunk encode ~1.9 s per 1 s chunk (gpu) → full pre-bake of this project ≈ 69 min, and there is no persistent background worker to do it.
7. Conservative invalidation for unknown ops ⇒ whole-timeline re-render.
8. Manifest is only rewritten per-chunk (`_publish` after each chunk, `:1388-1397`) — 12 rewrites for 12 chunks with fsync'd index writes (`preview_cache.py:296-321`) each time.

---

## 2. RENDER CACHE + SOURCE REPAIR + ASSET PROXY

### 2.1 RenderCache (`open_edit/render/cache.py`)
- Key: `render_cache_key(graph_hash, profile_fingerprint, content_fingerprint)` (`:45-66`); graph hash = `open_edit.ir.hash.compute_edit_graph_hash` (single hash authority). In the orchestrator the content fingerprint folds in the repair policy: `orchestrator.py:548-555` `cache_content_fingerprint = f"{content_fingerprint}|{SOURCE_REPAIR_POLICY_VERSION}"` (+`emission=…|source_proxy=…` when a proxy profile is used).
- Entries: `<key>.mp4` + `.meta/<key>.mp4.json`; `get()` re-verifies **full sha256 of the file** on every hit (`:196-229` — for a 1 GiB file that's a ~1 s read per lookup), touches LRU metadata; `put()` atomic temp+rename; TTL default **24 h** (`DEFAULT_TTL_SEC`, `is_fresh` `:390-399`); byte cap default 1 GiB with LRU evict (`:324-355`).
- Project cache at `/home/amr/Videos/video/.open_edit/renders/render_cache/` contains only `.meta/` (empty) + `source_baseline/*.json`. **No deliverable mp4 is cached** — every render so far was a cache miss (or forced); the whole-file cache is effectively unused.

### 2.2 The three source_baseline JSON files (semantics)
Path template: `source_baseline/<asset_hash[:16]>-<source_hash[:16]>-<extent>.json` (`source_repair.py:73-83`). The analysis is keyed by (asset_hash, source_hash, analyzed extent = max clip out_point) and skips the CPU black/freeze re-scan on a match (`:85-110`, `:207-246`).

1. `c9ee35fede09ac39-c9ee35fede09ac39-2211.342.json` (2,789 B, mtime 2026-08-05T00:00:46Z) — **the real, complete baseline**: asset_hash == source_hash (sha256 of the actual CAS file), extent 2211.342 s, contains 18 black spans + 16 frozen spans mapped into timeline seconds (e.g. black 142.8427–143.7102, frozen 346.5796–349.2823). Produced by the current code path.
2. `c9ee35fede09ac39-deadbeef-2211.json` (194 B) — **sentinel/placeholder**: `source_hash: "deadbeef"`, extent 2211.0, `black: [{"start_sec": 1.0}]`, frozen empty. That `{"start_sec": 1.0}` stub is NOT producible by the current detector code (which writes full spans or nothing).
3. `c9ee35fede09ac39-deadbeef-300.json` (323 B) — same `deadbeef` source hash, extent 300.0, with 2 *real* black spans (142.8427–143.7102, 162.6959–163.2297) — i.e. a partial scan limited to the first 300 s, written under an unknown source identity.

Meaning: `deadbeef` = **"source identity unknown/unverified"** key. `git grep deadbeef` across the repo+history finds it **only in tests** (`tests/test_serve_projects.py:114`, `test_serve_asset_stream.py:283`), never in production code — so current code cannot generate these hashes. They are stale artifacts from an earlier build/session (written ~12 min before the real baseline; likely during the failed rev-16 proxy attempt). They are **inert today**: `_load_baseline_cache` compares `payload.source_hash != source_hash` → mismatch → cache miss → re-scan (or write of the true-hash file). No correctness impact; just dead disk entries. (Also note the project_meta `folder` value still points to the old home `/home/ah64` — see §4.3.)

### 2.3 The 'source-repair-v5-eo-overlay' pass (`source_repair.py:33`)
- `SOURCE_REPAIR_POLICY_VERSION = "source-repair-v5-eo-overlay"` — a policy version constant folded into the render-cache key (so a changed overlay-protection rule can't reuse an old proxy) and into every repair result.
- **What it does**: `collect_source_baseline` (runs **before** the main melt render, `orchestrator.py:738-751`) scans each video source with CPU detectors (`qc/black_frames.list_black_frames`, `qc/frozen_frames.list_frozen_frames`), maps defect spans through clip trims into timeline seconds, caches per-asset results. Then, **after** the main render succeeds (`orchestrator.py:1102-1128`), `repair_render_output` re-runs the detectors **on the rendered output** (only in windows around the source spans, `_repair_windows`), and a defect is repaired only if it *survived the render* (`source_repair.py:860-882` — "A source defect only needs repair when it survived the render. This avoids a full RGB decode/encode pass…"). Repair = streamed decode→replace-black/interpolate-frozen→encode with audio copied (`:425-450`, `:509-597`); overlay intervals are protected from interpolation (`:884-888`, "eo-overlay" = overlays are the final transformation).
- **When it runs**: only for whole-file emissions — `orchestrator.py:513-515` `whole_file_repair = requested_emission_profile in {"final","review-artifact"}`. Proxy/preview-chunk emissions get a stub baseline and `skip` (`:1167-1171`).
- **Is it skippable / verify?** Yes, three layers: (a) `skip_if_no_source_defects=True` short-circuits with `reason="no_source_baseline_spans"` before any decode (`:802-809`); (b) default flags `repair_source_black=True`, `repair_source_frozen=False`, `repair_intentional_black=False` (`:750-755`) — frozen defects are NOT repaired by default; (c) the output-side detector re-check (above) decides per-span. There is no *separate* mandatory decode-check: the decision is detector-based on the rendered output (a decode pass only happens when a confirmed defect overlaps). Detector timeout budget is bounded by `_repair_budget` (`orchestrator.py:173-240`).
- **Observed cost driver**: the full 2211 s baseline scan (CPU black+freeze) is the expensive part of whole-file renders; the real baseline file exists, so repeat renders of the same source now skip the scan.

### 2.4 Per-asset proxy pipeline (`kernel/asset_proxy_jobs.py`, `render/source_proxy.py`)
Yes — a per-asset transcode pipeline exists:
- Profile `DEFAULT_SOURCE_PROXY_PROFILE` (`source_proxy.py:31-40`): `source_proxy_360_v1`, **360p, libx264, crf 28, preset veryfast, aac 96k, version 1**. ffmpeg command at `:195-225` (`scale=w='if(gt(ih,360),-2,iw)':h='min(ih,360)'`, `-movflags +faststart`), output stored back in the asset CAS (`store_derived`), asset metadata updated (`proxy_hash/profile/status`).
- Skipped when asset is not video / has alpha / already ≤360p (`:131-149`, status `not_needed`).
- Job service: durable SQLite (`asset_proxy_jobs.db` — separate from render_jobs.db, schema `:61-80`), runs `generate_asset_proxy` in a **ThreadPoolExecutor** (`:119-129`, `OPEN_EDIT_ASSET_PROXY_CONCURRENCY` default 1), per-asset flock (`:91-113`), coalescing + partial unique index on (asset_hash, profile) for active/succeeded (`:77-79`), statuses `queued/running/succeeded/failed/orphaned` (`:37-41`).
- Triggered via `POST /api/projects/{id}/assets/{hash}/proxy` (`serve/routers/assets.py:118-140`) or the MCP tool; **not** auto-triggered by renders — `preview_chunks.py:666` and `preview_video_renderer.py` call `build_render_plan(..., enqueue_missing_proxies=False)`.
- **Live state**: asset `proxy_status: "none"`, `proxy_hash: null` — no per-asset proxy was ever produced for this project. The "proxy" renders in render_jobs.db are *whole-timeline* fast renders (mode=proxy), not per-asset proxies.

---

## 3. DB SCHEMAS (sqlite3 dumps, row counts)

### 3.1 `edit_graph.db` (159,744 B) — the edit-graph authority
| table | rows | key columns |
|---|---|---|
| edits | **19** | edit_id PK, parent_id FK, kind, author, timestamp, status CHECK(applied/reverted/superseded), sequence_num, payload |
| edit_status_events | **37** | event_id PK, edit_id, from_status, to_status, command_id, reason, changed_at |
| timeline_snapshots | **12** | edit_graph_hash PK, project_id, timeline_json, created_at (used by preview worker to diff old/new timelines, `preview_chunks.py:274-290`) |
| project_meta | 4 | key/value: folder=/home/ah64/… (stale), ingested_count=1, project_id=0c7627e1-9795-4e04-a6c5-07e78e3d0df5, graph_revision=37 |
| commands, jobs, notes, notes_archive, render_snapshots | 0 | — |
Indexes: unique partial `idx_jobs_one_running ON jobs(status) WHERE status='running'`; others on project/status/sequence.

### 3.2 `render_jobs.db` (122,880 B) — durable render jobs
- Table `render_jobs` (19 rows: **9 succeeded, 5 cancelled, 5 failed**; modes: proxy 8, final 2, preview-chunks 9). Columns: job_id PK, project_id, mode CHECK(proxy/final/overlay/preview-chunks), status CHECK(queued/running/cancelling/cancelled/succeeded/failed/orphaned), created_at/updated_at REAL (unix epoch), output_path, error, result_json, qc_report, graph_revision, edit_graph_hash, params_json.
- **No timing columns, no speed_x, no progress** — stage timings only inside `result_json.diagnostics` (e.g. `elapsed_sec.video`, `counts`, `cache.hits/misses`, `evictions`). QC report attached for proxy/final (`_attach_qc`, `render_jobs.py:401-543`), skipped for preview-chunks (`:382-383`).
- Representative rows: `bb4cc042` preview-chunks succeeded in 4.41 s (2 chunks, video stage 3.733 s); `0c06145c` proxy succeeded 704.3 s → 1.096 GB file; `84b40034` preview-chunks cancelled (manifest left stale, §1.6).
- **Polling only, no push**: the only WebSocket is `/api/chat/{project_id}` (chat streaming, disabled in review-only — `ws/chat.py:29`). UI polls `GET …/renders` every 5 s while active (`app.js:497`) and `GET /api/projects/{id}` every 5 s (`app.js:959-987`). `pollRenderJob` polls `GET …/render_jobs/{job_id}` every 2 s (`app.js:922-951`).

### 3.3 `render_snapshots.db` (131,072 B)
- Full copy of the edit_graph schema (all tables present, 0 rows) + `render_snapshots` with **9 rows**, all `status='ready'` (CHECK rendering/ready/failed), columns version_id PK, project_id, edit_graph_hash, render_path, created_at, label. All rows point at `/home/ah64/…` paths except the newest (`v_de86dfb8fc78`, 2026-08-06, `/home/amr/…`). These are versioned whole-file render snapshots (labels v1..v7), separate from preview chunks.

---

## 4. API LATENCY MEASUREMENTS (live server, curl -w, 3× per endpoint, median)

| endpoint | median total | median TTFB | median bytes | codes |
|---|---|---|---|---|
| GET /api/projects | 54.3 ms | 53.9 ms | 174 B | 200 |
| GET /api/projects/{id} (state+ops+timeline_full) | **62.5 ms** | 62.3 ms | **11,860 B** | 200 |
| GET /api/projects/{id}/renders | 58.1 ms | 57.9 ms | 5,319 B | 200 |
| GET /api/projects/{id}/preview-chunks | 60.7 ms | 60.5 ms | 234 B | 200 |
| GET /api/projects/{id}/render_jobs/{job_id} | 55.9 ms | 55.7 ms | 66 B | **404** |
| GET /index.html | 2.4 ms | 2.0 ms | 16,429 B | 200 |
| GET /app.js | 2.2 ms | 1.8 ms | 69,283 B | 200 |
| GET /style.css | 1.6 ms | 1.4 ms | 36,017 B | 200 |
| GET /api/health | 1.2 ms | — | 15 B | 200 |
| GET /diagnostics | 2.0 ms | — | 550 B | 200 |

Key observations:
- **Every project-scoped /api endpoint has a ~55–62 ms floor** (project list, state, renders, preview-chunks, render_jobs) while static/health endpoints are ~1–2 ms. The floor is server-side work in `get_project_state` (asset dir scan incl. 1.46 GB CAS stat, sqlite load of all ops, `derive_timeline` on **every** call — `serve/projects.py:333-449`), executed under a global registry lock, plus `list_assets_from_disk` in `get_projects`.
- **Body-size question answered: YES, the UI re-fetches the full ops list + full timeline every poll.** `GET /api/projects/{id}` returns `ops` (19 items, 11,241 B — full edit history incl. 18 reverted ops with full payloads, some containing HTML overlay source) + `timeline_full` (412 B today) + assets (427 B), and `app.js` polls it **every 5 s** (`app.js:959-987`). The renders list (5,319 B, incl. the 1.096 GB row) is polled every 5 s while any job is active (`app.js:490-517`). Polling is unbounded client-side (no ETag/If-None-Match usage; server computes the full state each time). As ops grow (hundreds of edits), this is O(ops) JSON + O(derive_timeline) per 5 s per open tab.
- **Range requests: supported for MP4s.** `GET …/renders/project_fe5214616f5a/file` with `Range: bytes=0-1023` → **206 Partial Content**, `content-range: bytes 0-1023/1096296584`, `accept-ranges: bytes`, 27.7 ms (Starlette FileResponse). Preview-chunk files: 206, `0-1023/264752`, 77 ms.
- **Broken endpoints discovered live:**
  1. `GET /api/projects/{id}/assets/{hash}/file` → **404 "asset bytes missing"** even though the CAS file exists (1,464,991,632 B at `/home/amr/Videos/video/.open_edit/assets/c9/…`). Cause: sidecar `.meta.json` stores `stored_path: "/home/ah64/Videos/video/…"` (old home) — `serve/routers/assets.py:99-101` checks `Path(asset.stored_path).exists()` → false. Same stale-home problem in `project_meta.folder` and all render_snapshots rows. The UI's asset preview would break; only the whole-file render MP4 is streamable.
  2. `GET /api/projects/{id}/render_jobs/{job_id}` → **404 for every historical job** because `render_jobs.project_id` = project *name* `"video"` (CLI-created) while the API id is `9dc089c70c5f`; `renders.py:160-161` requires `job.project_id == project_id`. `app.js:931` treats `!r.ok` as stop-polling → job polling silently dies for CLI-created jobs (UI falls back to the 5 s renders-list poll).

---

## 5. CONSOLIDATED GAPS vs A PROFESSIONAL PREVIEW (for the modification plan)

1. **No realtime preview architecture**: preview = whole-file proxy MP4 (1.02 GiB, 3.9 Mbps, 640×360) streamed with Range; chunk system exists server-side but is unused by the UI and stale (rev 34 vs 37), with zero audio/playback artifacts ever produced.
2. **Chunk pipeline**: 1 s fixed windows, no I-frame/keyframe index, no scene-aware chunking, no scrub thumbnails, no prefetch/warmup, no background pre-bake worker, ~1.9 s per 1 s chunk at 640×360 (≈69 min for 2211 s).
3. **Invalidation** is solid (op-interval + timeline-slice keying, green/yellow/red fallback) but conservative for unknown ops; manifest rewrites are per-chunk (fsync-heavy); cancelled jobs can leave stale manifests + tmp dirs.
4. **Render cache**: whole-file only, 24 h TTL, 1 GiB cap, sha256 re-verify on every get (1 GiB file ≈ +1 s per lookup); currently unused (all misses). Source-baseline cache works but contains inert `deadbeef` entries from an older build.
5. **Source repair** is post-render, output-confirmed, overlay-protected, skippable — well designed; its main cost is the CPU baseline scan of long sources (cached per asset hash).
6. **Per-asset proxies** exist (360p crf28 veryfast) but are never auto-enqueued (`enqueue_missing_proxies=False`) and none exist in this project.
7. **DB/jobs**: no push channel (polling 5 s/2 s), no progress/speed metadata, no per-stage columns; job lookups break for CLI-created jobs (project_id mismatch); asset streaming broken by home-dir migration in sidecars.
8. **API**: project state endpoint recomputes timeline + serializes full op history on every 5 s poll (~62 ms, 11.9 KB today, growing with op count); no ETag/conditional GET; ~55 ms floor on all project endpoints.

## 6. KEY FILE:LINE INDEX
- Worker: `open_edit/render/preview_chunks.py:1205`, bake `:845`, slice/emit `:638`, publish `:1098`, selection `:1325`
- Fingerprints: `open_edit/render/preview_invalidation.py:542`, plane key `:732`, windows `:76`, select `:663`
- Cache: `open_edit/render/preview_cache.py:137,249,337,365`; render cache `open_edit/render/cache.py:45,196,231,390`
- Pipes: `open_edit/render/preview_pipe.py:76,145,182`; profile `open_edit/render/profiles.py:83`; encoder `open_edit/render/encoder.py`
- Serve: `open_edit/serve/routers/preview_chunks.py:109,123`; `renders.py:55,135,170`; `assets.py:60,118`; `projects.py:333,465`; `app.py` static mount; UI `open_edit/serve/static/app.js:497,959,922`
- Jobs: `open_edit/kernel/render_jobs.py:50,163,236,373,545`; `open_edit/kernel/asset_proxy_jobs.py:61,116,213,362`; `open_edit/render/source_proxy.py:31,103`
- Repair: `open_edit/render/source_repair.py:33,151,745`; `open_edit/render/orchestrator.py:513,545,738,1102`
- Policy: `open_edit/storage/cache_policy.py:46,105,274,410`
