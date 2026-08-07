# KERNEL / STORAGE AUDIT — RAW EVIDENCE

Audit of `/home/amr/Videos/video` (E2E OpenEdit project) + `/home/amr/apps/mlt-pipeline`.
Method: read-only inspection via repo venv `python3.14` (`/home/amr/apps/mlt-pipeline/.venv/bin/python3` = 3.14.6) and shell. Nothing modified; no renders/servers started.
Captured 2026-08-06 ~15:13 local (+03:00).

---

## 1. RENDER JOBS DB — `/home/amr/Videos/video/.open_edit/render_jobs.db`

File: 122,880 B; mtime 2026-08-06 14:35:19. Sidecars: `render_jobs.db-shm` (32,768 B, mtime 15:11:12), `render_jobs.db-wal` (0 B).

### Tables (sqlite_master)
```
render_jobs  table
```

### Schema (verbatim)
```sql
CREATE TABLE render_jobs (
    job_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('proxy', 'final', 'overlay', 'preview-chunks')),
    status TEXT NOT NULL CHECK (status IN
      ('queued', 'running', 'cancelling', 'cancelled', 'succeeded', 'failed', 'orphaned')),
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    output_path TEXT,
    error TEXT,
    result_json TEXT,
    qc_report TEXT,
    graph_revision INTEGER,
    edit_graph_hash TEXT,
    params_json TEXT
);
```

**Row count: 19.** Columns: job_id, project_id, mode, status, created_at, updated_at, output_path, error, result_json, qc_report, graph_revision, edit_graph_hash, params_json. NOTE: schema has **no `started_at`/`finished_at`/`elapsed`/stdout/stderr columns**; elapsed below = `updated_at - created_at`; no stdout/stderr is stored in this DB.

### All 19 rows (summary)
```
job_id                             mode            status     created(UTC+3)      updated(UTC+3)       elapsed_s  graph_rev
ef3ae642f2ab4c67976120acd7d0dbee   preview-chunks  succeeded  2026-08-04 19:14:13  2026-08-04 19:14:14     0.648     0
29267f50f8084c2ba2225dc907a264b8   proxy           cancelled  2026-08-04 19:14:50  2026-08-04 19:14:51     1.015     1
237716472be14414a774e50971c04b07   proxy           cancelled  2026-08-04 19:17:23  2026-08-04 19:17:24     1.018     2
0ee961e1bd274118b20c3e704f8cb8d6   preview-chunks  cancelled  2026-08-04 19:18:51  2026-08-04 19:18:52     1.015     3
875fb632dae04e29816f1c824dfcf3a7   preview-chunks  succeeded  2026-08-04 19:19:58  2026-08-04 19:19:58     0.644     3
cf9fa54edcb94b0d970e078e747f804a   preview-chunks  failed     2026-08-04 19:20:32  2026-08-04 19:20:33     0.232     4
de5c5db290934c4ba2872668cdd76d79   preview-chunks  failed     2026-08-04 19:21:44  2026-08-04 19:21:44     0.224     4
bb4cc04261f943339ed4cab9c617455f   preview-chunks  succeeded  2026-08-04 19:26:29  2026-08-04 19:26:34     4.415     9
562a9788601e4dd6b9a87e059e62e43d   preview-chunks  cancelled  2026-08-04 19:26:45  2026-08-04 19:26:46     1.014    10
0f3f582577964830885a030906359389   preview-chunks  succeeded  2026-08-04 19:27:21  2026-08-04 19:27:22     0.662    10
493b7f90d3224381b3750ba5d520a842   proxy           failed     2026-08-04 19:29:49  2026-08-04 19:29:57     8.475    14
0ecda9000cf64a838902b54ca601f67e   proxy           failed     2026-08-04 19:31:30  2026-08-04 19:31:31     0.260    16
a7440141d184474b8839790b7e2c1674   proxy           succeeded  2026-08-04 19:32:43  2026-08-04 19:32:50     7.770    22
c97fb277c2744ecd9e54f65514053092   final           succeeded  2026-08-04 19:32:50  2026-08-04 19:33:02    11.379    22
97426776fc5d49a29cd162000b3630ad   proxy           failed     2026-08-04 20:01:43  2026-08-04 20:01:46     3.144    26
5d48b827399d4b798dc658561bd0affb   proxy           succeeded  2026-08-04 20:05:00  2026-08-04 20:05:08     7.824    30
92251933c7844ea3acf29c86be3938a7   final           succeeded  2026-08-04 20:05:08  2026-08-04 20:05:20    11.598    30
84b40034097d43f8a660dfacc335cc96   preview-chunks  cancelled  2026-08-04 20:06:10  2026-08-04 20:06:11     1.019    34
0c06145c44db4eeb8151a9c79ce4250a   proxy           succeeded  2026-08-06 14:23:33  2026-08-06 14:35:17   704.342    37
```

### Key per-row fields (non-null extras)

- `ef3ae642…` preview-chunks succeeded, graph_rev 0, hash `e3b0c44…` (empty-graph sha256), params `{"media": "both", "priority": "interactive", "ranges": [{"end_sec": 2.0, "start_sec": 0.0}]}`, result: counts.total_chunks=0, cache hits=0 misses=0, elapsed_sec all 0.0, bytes_written all 0.
- `875fb632…` preview-chunks succeeded graph_rev 3: total_chunks=2, processed=2, selected=2, cache misses=2 (video), video elapsed 0.0s in result but bytes_written 0; evictions removed 1 file/1109 B.
- `bb4cc042…` preview-chunks succeeded graph_rev 9: **elapsed video 3.733s, bytes_written video 425,790; misses 2; evictions 6 files/430,228 B removed**; selected_ranges [0.0–1.001].
- `cf9fa54e…` / `de5c5db2…` preview-chunks **failed, error=`renderer exited 1`** (graph_rev 4).
- `493b7f90…` proxy failed — full error verbatim:
```
Traceback (most recent call last):
  File "<frozen runpy>", line 203, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "/home/ah64/apps/mlt-pipeline/open_edit/cli.py", line 712, in <module>
    sys.exit(main())
  File "/home/ah64/apps/mlt-pipeline/open_edit/cli.py", line 708, in main
    return args.func(args)
  File "/home/ah64/apps/mlt-pipeline/open_edit/cli.py", line 243, in cmd_render
    result = render_project(project_id=project_dir.parent.name, ... encoder_backend=getattr(args, "encoder", None))
  File "/home/ah64/apps/mlt-pipeline/open_edit/render/orchestrator.py", line 1116, in render_project
    cache.put(cache_key, output_mp4)
  File "/home/ah64/apps/mlt-pipeline/open_edit/render/cache.py", line 273, in put
    with tempfile.NamedTemporaryFile(dir=dest.parent, prefix=f".{dest.name}.", delete=False) as tmp:
  File "/usr/lib/python3.14/tempfile.py", line 603, in NamedTemporaryFile
    file = _io.open(dir, mode, buffering=buffering, ...)
  File "/usr/lib/python3.14/tempfile.py", line 600, in opener
    fd, name = _mkstemp_inner(dir, prefix, suffix, flags, output_type)
  File "/usr/lib/python3.14/tempfile.py", line 255, in _mkstemp_inner
    fd = _os.open(file, flags, 0o600)
OSError: [Errno 36] File name too long: '/home/ah64/Videos/video/.open_edit/renders/render_cache/.0297d4bd062f41d587d15b955d5eff480ac4203cad45db24a52a1a34ff4a2fa9_fast_proxy_q=fast_enc=gpu_4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945_hyperframes=f65022b559f8273d8d716f22e3d615d54c525076dbc970c15fbc05656d561a6d_source-repair-v5-eo-overlay.mp4.tslwhbhk'
```
  (That legacy cache key = 260 chars; temp filename = 274 chars > 255-byte NAME_MAX. The **current** `render_cache_key()` in this repo caps at 180 chars — verified by computing it with the repo venv: `0297d4bd062f41d587d15b955d5eff48_fast_proxy_q=fast_enc=gpu_hyperframes=f65022b559f8273d8d716f22_source-repair-v5-eo-overlay_19dfeb2f…` (180 chars).)

- `0ecda900…` proxy failed: error `Overlap on track v1: clip 'd77f5346-dcef-4964-a43d-3eb6282a9df4' spans [0.000, 2.000] but clip 'a21dc917-bd32-4fcb-910f-e54fa05f1b68' starts at 0.000.`
- `97426776…` proxy failed: error `hyperframes non-zero exit (1): stderr=`
- Succeeded proxy/final rows: `cache_hit` **false in all 5 succeeded jobs** (a7440141, c97fb277, 5d48b827, 92251933, 0c06145c); `render_cache_lookup` stage elapsed 0.0004–0.44 s; content_fingerprint pattern `4f53cda18c…|hyperframes=…`; cache_content_fingerprint adds `|source-repair-v5-eo-overlay`.

#### a7440141 (proxy 2.0s timeline, 2026-08-04): diagnostics
```json
elapsed_sec 2.632, pipe_elapsed_sec 2.593, duration_sec 2.0, profile fast_proxy 640x360 q=fast enc=gpu, source_media_policy original
stages: derive_timeline 0.0043s | render_cache_lookup 0.0004s hit=false | hyperframes_materialize 3.005s (cache_hit=false, content_hash b51af961…, output .../hyperframes/out/proxy/overlay_b51af9613d84f07edf502416.mov) | remotion_materialize ~0s bytes=1,509,202 worker_count=2 | emit_mlt 0.0003s 1210B | melt_video ~0s 1210B | melt_audio 0.714s 390,478B | ffmpeg_encode 1.878s 470,517B | source_repair 0.039s changed=false | qc 0.047s policy=light
```
#### c97fb277 (final 2.0s, 2026-08-04): elapsed 3.586s; ffmpeg_encode 2.823s 3,406,046B; melt_audio 0.704s; qc 0.844s policy=full passed; profile 1080p30 1920x1080 q=standard enc=gpu; output .../renders/project_8d6aff3837c7.mp4

#### 0c06145c (SLOW proxy, 2026-08-06, duration_sec 2211.34 — the 36.8-min render)
```json
result.elapsed_sec 700.80, diag.elapsed_sec 700.801, decode_backend "cuda", cuda_fastpath {used:true, elapsed_sec 77.89, speed_x 28.39, output .../renders/project_fe5214616f5a.mp4}
profile fast_proxy 640x360 q=fast enc=gpu; product review_artifact 640x360; source_media_policy original; emission review-artifact
stages:
  derive_timeline 0.0007s (duration_sec 2211.342)
  render_cache_lookup 0.439s hit=false
  hyperframes_materialize 0.0s skipped (no_html_overlays)
  remotion_materialize ~0s bytes=0 worker_count=2
  emit_mlt 0.0004s 1124B; melt_video ~0s 1124B
  melt_audio 19.33s 424,576,078 B (405 MB wav)
  ffmpeg_encode 77.89s 1,096,296,584 B (1.10 GB mp4)
  source_repair 579.06s changed=true  <-- dominant stage
  qc 0.064s policy=light passed
repair: policy source-repair-v5-eo-overlay, detector_timeout_s 900.0, detector_windows: 23 windows, repaired_black_spans: 22 spans (all source_asset_hash c9ee35fe…), repaired_frozen_spans: (list present), ok=true
source_baseline cache hit file: .../render_cache/source_baseline/c9ee35fede09ac39-c9ee35fede09ac39-2211.342.json (black: 18 spans, frozen: present)
qc_report: 8 checks (render_completed, proxy_render, streams, duration, audio_sync, ...) all passed
```

### `.open_edit/` full top-level listing (size + mtime)
```
assets            DIR   mtime 2026-07-27 12:31:00
benchmark_logs    DIR   mtime 2026-08-04 23:47:07
edit_graph.db     159,744 B   mtime 2026-08-04 20:07:47   (+ -shm 32,768 B @14:46:25, -wal 0 B)
hyperframes       DIR   mtime 2026-08-04 20:24:51
preview_chunks    DIR   mtime 2026-08-04 20:06:10
remotion          DIR   mtime 2026-08-04 19:32:50
render_jobs.db    122,880 B   mtime 2026-08-06 14:35:19   (+ -shm 32,768 B @15:11:12, -wal 0 B)
render_snapshots.db 131,072 B mtime 2026-08-06 14:35:17
renders           DIR   mtime 2026-08-06 14:35:16
timeline_views    DIR   mtime 2026-08-06 14:18:38
```
**notes.db: NOT present** in `.open_edit/` (or anywhere under `/home/amr/Videos/video` up to depth 3). A `notes` table exists inside edit_graph.db (0 rows).

---

## 2. RENDER CACHE

Location: `/home/amr/Videos/video/.open_edit/renders/render_cache/` (only cache dir in the project).

### Renders dir tree
```
renders/
  project_fe5214616f5a.audio.wav   424,576,078 B  mtime 2026-08-06 14:23:55
  project_fe5214616f5a.mlt                1,124 B  mtime 2026-08-06 14:23:35
  project_fe5214616f5a.mp4        1,096,296,584 B  mtime 2026-08-06 14:35:16   (1.02 GiB)
  render_cache/   (dir, mtime 2026-08-06 14:35:17)
    .meta/        (EMPTY dir, 0 B)
    source_baseline/
      c9ee35fede09ac39-c9ee35fede09ac39-2211.342.json   2,789 B  mtime 2026-08-05 00:00:46
      c9ee35fede09ac39-deadbeef-2211.json                 194 B  mtime 2026-08-04 23:48:51
      c9ee35fede09ac39-deadbeef-300.json                  323 B  mtime 2026-08-04 23:49:00
```
Cache key filename format (from code, see below): `<edit_graph_hash>_<profile_fingerprint>_<content_fingerprint>` joined with `|`→`_`, digested with sha256 if >180 chars, truncated to 180. **No cached render MP4s exist in render_cache/ (`.meta` empty, no `*.mp4` files)** — every completed render was `cache_hit: false`.

### source_baseline JSON contents (verbatim, abridged)
`c9ee35fede09ac39-c9ee35fede09ac39-2211.342.json`:
```json
{"version": 1, "asset_hash": "c9ee35fede09ac390e310c649bccacc311c7251247990fbc88906df4ffc105e8", "source_hash": "c9ee35fede09ac390e310c649bccacc311c7251247990fbc88906df4ffc105e8", "source_end_sec": 2211.342467, "black": [{"start_sec": 142.8427, "end_sec": 143.710233, "duration_sec": 0.867533}, ... 18 spans total ...], "frozen": [{"start_sec": 346.579567, "end_sec": 349.282267, "duration_sec": 2.7027}, ...]}
```
`c9ee35fede09ac39-deadbeef-2211.json`: `{"version": 1, "asset_hash": "c9ee35fe…", "source_hash": "deadbeef", "source_end_sec": 2211.0, "black": [{"start_sec": 1.0}], "frozen": []}`
`c9ee35fede09ac39-deadbeef-300.json`: same shape, source_end_sec 300.0, black = first 2 spans, frozen [].

### Key-computation code — `open_edit/render/cache.py` (repo, quoted verbatim)
```python
def render_cache_key(
    graph_hash: str,
    profile_fingerprint: str,
    content_fingerprint: str = "",
) -> str:
    """Return a stable, filesystem-safe cache key under filename limits."""
    parts = [graph_hash, profile_fingerprint]
    if content_fingerprint:
        parts.append(content_fingerprint)
    raw = "|".join(parts).replace("|", "_")
    if len(raw) <= 180:
        return raw
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    markers: list[str] = []
    for marker in ("source_proxy_", "hyperframes=", "source-repair-", "emission="):
        match = re.search(rf"{re.escape(marker)}[^|]*", raw)
        if match:
            markers.append(match.group(0)[:36])
    readable = "_".join(markers)
    profile = profile_fingerprint.replace("|", "_")[:64]
    key = f"{graph_hash[:32]}_{profile}_{readable}_{digest}"
    return key[:180] if len(key) > 180 else key
```
```python
# hit decision — RenderCache.get()
def get(self, key: str, ext: str = "mp4") -> Path | None:
    path = self._cache_path(key, ext)
    if not path.is_file():
        return None
    metadata_path = self._metadata_path(key, ext)
    if metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if not isinstance(metadata, dict):
                return None
            expected = str(metadata.get("source_hash") or "")
            if not expected or _file_hash(path) != expected:
                return None
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return None
        ...  # refresh atime + metadata, return path
    return path  # legacy entries without metadata remain readable
```
Freshness: `is_fresh()` uses mtime age < TTL, TTL = `OPEN_EDIT_RENDER_CACHE_TTL_SEC` (default 86,400 s = 24 h). Byte cap: `OPEN_EDIT_RENDER_CACHE_MAX_BYTES` (default 1 GiB); eviction is LRU by `last_accessed_at`.

### Cache hit decision in orchestrator (`render/orchestrator.py` lines 545–572)
```python
cache = RenderCache(workdir / "render_cache")
cache_content_fingerprint = (f"{content_fingerprint}|{SOURCE_REPAIR_POLICY_VERSION}")
if source_proxy_profile_fingerprint:
    cache_content_fingerprint = (... f"|emission={requested_emission_profile}" ...)
cache_key = render_cache_key(graph_hash, fingerprint, cache_content_fingerprint)
if force or remotion_invalidation_requested:
    cached = None; reason = "force_requested" ...
else:
    cached = cache.get(cache_key)
    cache_hit = bool(cached and cache.is_fresh(cached))
```

### Preview cache key/ID code — `open_edit/render/preview_cache.py` (quoted)
Artifact IDs are opaque `key` strings passed to `commit_artifact`; files stored as `<root>/<plane>/<artifact_id>.<ext>`; resolution requires the ID to be in `.artifact_index.json` AND content sha256-verified:
```python
def resolve_artifact(self, artifact_id: str) -> Path | None:
    ...  # _safe_component(artifact_id) then:
    entry = self._index.get(artifact_id)
    if entry is None:
        self._load_index(); entry = self._index.get(artifact_id)
    if entry is None: return None
    try:
        path = self._path_for_relative(str(entry["relative_path"]))
        if not path.is_file() or path.is_symlink(): return None
        stat = path.stat()
        if stat.st_size <= 0 or stat.st_size != int(entry["bytes"]): return None
        if _file_hash(path) != str(entry["sha256"]): return None
    except (KeyError, OSError, TypeError, ValueError): return None
    return path
```
Planes: `video|audio|playback`; defaults: max_bytes 512 MiB (`OPEN_EDIT_PREVIEW_CACHE_MAX_BYTES`), max_age 7 days, min_free 512 MiB. Artifact ID in the observed manifest is the 64-hex sha256 of chunk content (e.g. `480ef6aa…`), keyed in `.artifact_index.json`.

### Canonical hash authority — `open_edit/ir/hash.py`
```python
def compute_edit_graph_hash(ops: list) -> str:
    ...  # sort by (sequence_num, edit_id); digest of "seq:edit_id:canonical-json" parts
    parts.append(f"{seq}:{edit_id}:{json.dumps(data, sort_keys=True, separators=(",", ":"))}")
    return hashlib.sha256("".join(parts).encode()).hexdigest()
```

---

## 3. BENCHMARK LOGS

`/home/amr/Videos/video/.open_edit/benchmark_logs/` (5 JSON files):
```
full_final.json              26,428 B  mtime 2026-08-04 21:17:38
full_proxy.json              26,339 B  mtime 2026-08-04 20:21:34
gpu_proxy_cached_final.json   1,578 B  mtime 2026-08-04 23:47:07
gpu_proxy_result.json         1,579 B  mtime 2026-08-04 22:57:59
proxy.json                      308 B  mtime 2026-08-04 20:05:49
```

### proxy.json (verbatim)
```json
{"mode": "proxy", "returncode": 1, "elapsed_sec": 0.23546958900078607,
 "stdout": "{\"ok\": false, \"error\": \"empty edit graph; nothing to render\", \"mode\": \"proxy\"}\n",
 "stderr": "",
 "result": {"ok": false, "error": "empty edit graph; nothing to render", "mode": "proxy"}}
```

### full_proxy.json — top-level keys: `mode, returncode, elapsed_sec, stdout, stderr, result`
`mode=proxy, returncode=0, elapsed_sec=826.57` (file-level); `result.elapsed_sec=704.48, duration_sec=2211.342, cache_hit=false, ok=true`, output `.../renders/project_fe5214616f5a.mp4`.
`result.diagnostics.stages` (verbatim, seconds):
```json
derive_timeline       0.0048   completed  duration_sec 2211.342
render_cache_lookup   0.0      skipped     reason force_requested
hyperframes_materialize 0.0    skipped     reason no_html_overlays
build_render_plan     0.00009  completed
remotion_materialize  0.00001  completed  bytes 0 worker_count 2 cache_hits 0 cache_misses 0
emit_mlt              0.00027  completed  bytes 1222
source_repair         209.29   completed  changed false   <-- 209 s with NO changes
melt_audio            14.99    completed  bytes 424,576,078
melt_video            0.000002 completed  bytes 1222
ffmpeg_encode         480.20   completed  bytes 590,018,265
qc                    0.0      skipped    reason not_reached
audio                 14.99    completed  bytes 424,576,078
```
`decode_backend` absent from this file; `source_media_policy=original`, profile `fast_proxy 640x360 q=fast enc=gpu`, product `review_artifact`, repair: changed=false elapsed 209.29s detector_timeout_s 900.0 detector_windows 16 repaired_black 0, policy `source-repair-v5-eo-overlay`.

### full_final.json — `mode=final, returncode=0, elapsed_sec=3041.63`; `result.elapsed_sec=2916.42, duration_sec=2211.342, cache_hit=false`
```json
source_repair         1427.42  completed  changed false   <-- 23.8 min, NO changes
melt_audio            15.30    completed  bytes 424,576,078
ffmpeg_encode         1473.69  completed  bytes 2,780,386,338
qc                    0.0      skipped    reason not_reached
profile 1080p30 1920x1080 q=standard enc=gpu; product final_export
```

### gpu_proxy_result.json (verbatim full)
```json
{"ok": true, "elapsed_total": 557.4, "elapsed_sec": 429.09967779400176,
 "decode_backend": "cuda",
 "cuda_fastpath": {"used": true, "elapsed_sec": 76.08897194499878, "speed_x": 29.06,
  "output_path": "/home/ah64/Videos/video/.open_edit/renders/project_fe5214616f5a.mp4"},
 "error": "None", "output": "/home/ah64/Videos/video/.open_edit/renders/project_fe5214616f5a.mp4",
 "stages": {"derive_timeline": {"status": "completed", "elapsed_sec": 0.0},
  "render_cache_lookup": {"status": "skipped", "elapsed_sec": 0.0},
  "hyperframes_materialize": {"status": "skipped", "elapsed_sec": 0.0},
  "build_render_plan": {"status": "completed", "elapsed_sec": 0.0},
  "remotion_materialize": {"status": "completed", "elapsed_sec": 0.0},
  "emit_mlt": {"status": "completed", "elapsed_sec": 0.0},
  "source_repair": {"status": "completed", "elapsed_sec": 312.7},
  "melt_audio": {"status": "completed", "elapsed_sec": 17.6},
  "melt_video": {"status": "completed", "elapsed_sec": 0.0},
  "ffmpeg_encode": {"status": "completed", "elapsed_sec": 76.1},
  "qc": {"status": "skipped", "elapsed_sec": 0.0},
  "melt": {"status": "completed", "elapsed_sec": 0.0},
  "ffmpeg": {"status": "completed", "elapsed_sec": 76.1},
  "audio": {"status": "completed", "elapsed_sec": 17.6}}}
```

### gpu_proxy_cached_final.json (verbatim full)
`{"ok": true, "elapsed_total": 495.5, "elapsed_sec": 368.9973141979999, "decode_backend": "cuda", "cuda_fastpath": {"used": true, "elapsed_sec": 73.74051940100003, "speed_x": 29.99, "output_path": .../project_fe5214616f5a.mp4}, "error": "None", stages: source_repair 255.4, melt_audio 15.2, ffmpeg_encode 73.7, qc skipped, rest 0.0}`

### `/home/amr/apps/mlt-pipeline/testrun/logs/` (contents + sizes)
```
pytest_r1_venv.log  2,421 B  mtime 2026-08-06 08:03:56
pytest_r2.log       2,421 B  mtime 2026-08-06 08:03:56
```
Both are pytest progress logs (29 lines; first line `....` progress dots, last line `SKIPPED [1] tests/test_sandbox_observations.py:38: strace observation fixtures not present in repo`).

---

## 4. API LATENCIES (server state)

**The OpenEdit serve process exists but is NOT accepting new connections** — live curl to both ports failed:
```
$ curl -sS -m 3 -o /dev/null -w 'port8000 HTTP %{http_code} total=%{time_total}s ttfb=%{time_starttransfer}s' http://localhost:8000/api/projects
port8000 HTTP 000 total=0.000170s ttfb=0.000169s   (curl: (7) Failed to connect to localhost:8000 after 0 ms)
$ curl -sS -m 3 -o /dev/null -w ... http://localhost:5173/
port5173 HTTP 000 total=0.000210s ttfb=0.000206s   (curl: (7) Failed to connect)
```
Process state (`ps aux`):
```
amr  424323  3.6  0.5  .venv/bin/python -m open_edit.cli serve --review-only --port 8000
      started 14:23, stat SNl (nice), 18 threads, cwd /home/amr/apps/mlt-pipeline, stdout/stderr -> /tmp/openedit_serve.log
```
`ss -tlnp`: **no LISTEN socket on 8000/5173**. But there IS one ESTABLISHED connection:
```
ESTAB 0 2614253  127.0.0.1:8000  127.0.0.1:53544  users:(("python",pid=424323,fd=74))
  ^ 2,614,253 B Send-Q queued (server -> client, client not reading)
/proc/424323/fd: 74 -> socket (the ESTAB connection), 75 -> /home/amr/Videos/video/.open_edit/renders/project_fe5214616f5a.mp4 (open file)
```
Server log `/tmp/openedit_serve.log` (2,628 lines) — first lines:
```
INFO: Started server process [424323]
INFO: Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
... 14:23:37 GET /api/projects 200 (26.355 ms)
... last lines:
INFO: Shutting down
INFO: Waiting for connections to close. (CTRL+C to force quit)
```
So the server stopped accepting at ~15:02 and is blocked in shutdown waiting on the stuck mp4-stream connection (2.6 MB unsent; holds the 1.1 GB render file open).

### Measured latencies from the server's own request log (no live timing possible)
All 875 logged requests: avg 44.59 ms, min 0.483 ms, max 132.487 ms. Status codes: 200 x658, 206 x66, 404 x151.
Endpoint hit counts and per-endpoint avg duration (from log):
```
922x  GET /api/projects/9dc089c70c5f                          avg 47.2 ms  (max 132.5 ms)  -- UI poll every ~5 s
294x  GET /api/projects/9dc089c70c5f/renders                  (refreshRendersList 5 s interval)
276x  GET /api/projects/9dc089c70c5f/renders/5d48b827…/file   206 (Range) avg ~43 ms
128x  GET /api/projects/9dc089c70c5f/renders/0c06145c…/file   206 (Range) avg ~43 ms
  26x  GET /api/projects
  12x  GET /api/projects/9dc089c70c5f/preview-chunks          35.8–60.2 ms
   8x  GET /api/projects/9dc089c70c5f/render_jobs/0c06145c…   (pollRenderJob)
   6x  GET /api/projects/9dc089c70c5f/assets/c9ee35fe…/file    (source preview, 206)
   6x  GET /api/health;  4x GET /api/projects/9dc089c70c5f/preview-chunks/files/480ef6aa…;  4x /api/ui-config;  4x /api/projects/video;  2x /openapi.json;  2x /api/projects/video/renders;  2x /api/projects/video/preview-chunks;  2x /api/projects/9dc089c70c5f/timeline;  2x /api/projects/9dc089c70c5f/renders/project_fe5214616f5a/file
```
Sample verbatim lines (render file streaming = HTTP 206, ~46 ms each):
```
{"ts": "2026-08-06T14:35:20+0300", "level": "INFO", "logger": "open_edit.serve.request", "message": "request end", "request_id": "7cb37d21f9b84052ada333049f97a384", "method": "GET", "path": "/api/projects/9dc089c70c5f/renders/0c06145c44db4eeb8151a9c79ce4250a/file", "status": 206, "duration_ms": 46.49}
{"ts": "2026-08-06T15:01:22+0300", ..., "path": "/api/projects/9dc089c70c5f", "status": 200, "duration_ms": 98.954}
```

---

## 5. SYSTEM

```
nvidia-smi (610.57.04, CUDA UMD 13.3): NVIDIA GeForce RTX 4050 Laptop, 6,141 MiB total,
   51C, P8, 4W/35W, 40 MiB used, 0% util — only kwin_wayland (7 MiB) on GPU. (idle at audit time)
nproc: 12
free -h: total 22 GiB, used 11 GiB, free 4.3 GiB, shared 3.6 GiB, buff/cache 11 GiB, available 11 GiB; swap 22 GiB (2.6 GiB used)
df -h: /home 148G (62G used, 87G avail, 42%); /tmp tmpfs 12G (4.2G used, 7.3G avail, 37%)
ffmpeg: n8.1.2, gcc 16, config includes --enable-cuda-llvm --enable-nvdec --enable-nvenc --enable-libx264 ...
melt: /usr/bin/melt 7.40.0 (MLT framework)
```

---

## 6. PREVIEW CHUNKS + ASSETS

### `/home/amr/Videos/video/.open_edit/preview_chunks/`
```
.artifact_index.json     1,046 B  mtime 2026-08-04 20:06:10
manifest.json            5,312 B  mtime 2026-08-04 20:06:10
audio/     (empty dir)   mtime 2026-08-04 19:14:13
playback/  (empty dir)   mtime 2026-08-04 19:14:13
video/
  480ef6aa0901690b117bd68b40808651d15d75a24d60cec26c0b00618c6a3f22.mp4   264,752 B  mtime 2026-08-04 19:26:32
  83e3f41c990923892724908c996239d72ab74316c9f7c73d989c4dea3cdb99d2.mp4   161,038 B  mtime 2026-08-04 19:26:34
tmp/
  84b40034097d43f8a660dfacc335cc96/   (leftover cancelled-job dir)
    chunk-000000-video.mlt   1,109 B  mtime 2026-08-04 20:06:10
```
`manifest.json` header: `schema_version 1, project_id video, graph_revision 34, edit_graph_hash 750935c2…, duration_frames 360, duration_sec 12.0, fps 30000/1001, chunk_frames 30, profile preview_chunk 640x360 vcodec libx264 acodec aac ab=96k enc=gpu, job_id 84b40034…, updated_at 1785863170.4`.
12 chunks (000000-000030 … 000330-000360): chunk 0 `status yellow` (video fallback 480ef6aa…, 264,752 B, sha256 a6955c3f…, graph_hash ece20daf…), chunk 1 `yellow` (fallback 83e3f41c…), chunks 2–11 `red`. All `current: null`, all audio/playback `red`.
`.artifact_index.json`: `schema_version 1` + 2 artifacts keyed by the same 64-hex IDs (fields: artifact_id, bytes, graph_hash, key, mime video/mp4, relative_path, sha256).

### `/home/amr/Videos/video/.open_edit/assets/`
Single prefix dir `c9/` containing:
```
c9ee35fede09ac390e310c649bccacc311c7251247990fbc88906df4ffc105e8             1,464,991,632 B (1.36 GiB)  mtime 2026-07-27 11:57:57
c9ee35fede09ac390e310c649bccacc311c7251247990fbc88906df4ffc105e8.meta.json       527,793 B  mtime 2026-07-27 12:37:10
```
Hash filename = sha256 of content; meta.json sidecar example (top-level fields, verbatim):
```json
{"asset_hash": "c9ee35fede09ac390e310c649bccacc311c7251247990fbc88906df4ffc105e8",
 "original_path": "/home/ah64/Videos/video/untitled_cl.mp4",
 "stored_path": "/home/ah64/Videos/video/.open_edit/assets/c9/c9ee35fede09ac390e310c649bccacc311c7251247990fbc88906df4ffc105e8",
 "type": "video", "duration_sec": 2211.342467, "fps": 29.97002997002997,
 "width": 1920, "height": 1080, "codec": "h264", "has_audio": true,
 "alignment": [ {"word": " سينا", "t_start": 0.0, "t_end": 0.72, "confidence": 0.1378..., "speaker": null}, ... ]}
```
(`alignment` = word-level transcript, ~thousands of entries — this is the bulk of the 528 KB sidecar; all fields: asset_hash, original_path, stored_path, type, duration_sec, fps, width, height, codec, has_audio, alignment, license, attribution.)

---

## 7. EDIT GRAPH DB — `edit_graph.db`

159,744 B. Tables (9): `commands, edit_status_events, edits, jobs, notes, notes_archive, project_meta, render_snapshots, timeline_snapshots` (full CREATE TABLE statements identical to the 8 tables above plus `render_snapshots`; the `edits`, `jobs`, `notes`, `timeline_snapshots`, `project_meta`, `edit_status_events`, `commands`, `notes_archive` DDL is shared — quoted verbatim in section for render_snapshots.db below).

Row counts: `commands 0, edit_status_events 37, edits 19, jobs 0, notes 0, notes_archive 0, project_meta 4, render_snapshots 0, timeline_snapshots 12`.

`project_meta` rows:
```
folder          /home/ah64/Videos/video
ingested_count  1
project_id      0c7627e1-9795-4e04-a6c5-07e78e3d0df5
graph_revision  37
```
`edits` (19 rows): all `add_clip` / `add_html_overlay`, author `ai`, all but one `status=reverted`; seq 0–17 reverted, seq 18 (`408bc57d…` add_clip) `applied`. All add_clip payloads reference `asset_hash c9ee35fede09ac39…` (the single ingested asset), track `v1`. add_html_overlay templates seen: `templates/mcp_smoke_title.html`, `mcp_hyperframes_smoke.html`, `mcp_smoke_title.html`, `mcp_animation.html`, `latency_smoke.html`. Example payload head (seq 18): `{"kind":"add_clip","edit_id":"408bc57d…","parent_id":null,"author":"ai","timestamp":"2026-08-04T17:07:33.465164+00:00","status":"applied","originating_note_id":null,"asset_hash":"c9ee35fe…","track_id":"v1","track_kind":…}`
`timeline_snapshots` (12 rows): keyed by edit_graph_hash; project_id alternates `video` and uuid strings (26943b43…, faa76874…, b742f0df…, 3c67ecfa…, a22bf1ed…, 896f55f6…, 743b7bdd…) — i.e., snapshots from other projects/tests also live in this DB. First row: empty timeline `{"tracks":[],"overlays":[],"remotion_compositions":[],"duration_sec":0.0}` (hash e3b0c44…, rev 0). Last snapshot `750935c2…` (rev 34, 2026-08-04T17:06:10) has clips on v1. `edit_status_events`: 37 rows (sample: `23fec715…` edit 53a4c41c… None->applied reason=append 2026-08-04T16:14:50).

---

## 8. RENDER SNAPSHOTS

`render_snapshots` is a **DB file**, not a directory: `/home/amr/Videos/video/.open_edit/render_snapshots.db` (131,072 B). It contains the same 9-table schema (quoted below), with only `render_snapshots` populated: **9 rows, all `status=ready`**:
```
version_id        project_id  edit_graph_hash                    render_path                                        created_at (UTC)          label
v_a3f88853a29c    video       8d6aff3837c7…                     .../renders/project_8d6aff3837c7.mp4                  2026-08-04T16:32:50      v1
v_848297aef789    video       8d6aff3837c7…                     .../renders/project_8d6aff3837c7.mp4                  2026-08-04T16:33:01      v2
v_f9e34a30b163    video       b91d0d5862bc…                     .../renders/project_b91d0d5862bc.mp4                  2026-08-04T17:05:08      v3
v_75eafe6dbc0b    video       b91d0d5862bc…                     .../renders/project_b91d0d5862bc.mp4                  2026-08-04T17:05:19      v4
v_baf9bdffa79d    video       fe5214616f5a…                     .../renders/project_fe5214616f5a.mp4                  2026-08-04T17:21:34      v5
v_2f5517fc69c8    video       fe5214616f5a…                     .../renders/project_fe5214616f5a.mp4                  2026-08-04T18:17:38      v6
v_b99dbb46c4e6    untitled_cl fe5214616f5a…                     .../renders/project_fe5214616f5a.mp4                  2026-08-04T19:57:59      v1
v_8952b86521f8    untitled_cl fe5214616f5a…                     .../renders/project_fe5214616f5a.mp4                  2026-08-04T20:47:07      v2
v_de86dfb8fc78    video       fe5214616f5a…                     /home/amr/Videos/video/.open_edit/renders/project_fe5214616f5a.mp4  2026-08-06T11:35:17  v7
```

---

## 9. UI STATIC — `open_edit/serve/static/`

### Static dir listing
```
app.js          69,283 B  mtime 2026-08-03 02:41:52
index.html      16,429 B  mtime 2026-08-03 00:43:55
style.css       36,017 B  mtime 2026-07-31 14:18:38
js/api.js        4,828 B  mtime 2026-07-31 14:18:38
js/assets.js     2,932 B  mtime 2026-07-31 14:18:38
js/chat.js      24,268 B  mtime 2026-07-31 14:18:38
js/dom.js        2,782 B  mtime 2026-07-31 14:18:38
js/state.js      5,811 B  mtime 2026-07-31 14:18:38
js/ws.js         7,251 B  mtime 2026-07-31 14:18:38
```
Served with cache-busting query strings observed in the log: `style.css?v=20260728-gpu-encoder`, `app.js?v=20260729-preview-rev`.

### Polling intervals (app.js, 1,942 lines)
```javascript
// line 497 — renders list poll, only while a job is active:
state.renderPollTimer = setInterval(() => refreshRendersList(), 5000);
// line 959 — edit graph state poll, always:
state.editGraphRefreshTimer = setInterval(async () => { ... api.getProjectState(...) ... }, 5000);
// lines 922–952 — per-job poll after POST /render:
const maxAttempts = 120; // 10 min at 5s polling
... const r = await fetch(`/api/projects/${...}/render_jobs/${jobId}`);
... if (job.status === 'succeeded') { ... loadRenderInPreview(job.job_id, mode); return; }
... setTimeout(poll, 2000);   // on queued/running, and on network error
setTimeout(poll, 1000);       // first poll 1 s after submit
// lines 969–975 — auto-proxy debounce on graph_revision change:
state._autoProxyDebounce = setTimeout(() => { if (!state.proxyRenderInFlight) triggerRender('proxy'); }, 15000);
```
Endpoints polled by the UI: `GET /api/projects` (list), `GET /api/projects/{id}` (state, every 5 s), `GET /api/projects/{id}/renders` (every 5 s while active), `GET /api/projects/{id}/render_jobs/{jobId}` (every 2 s), `POST /api/projects/{id}/render`; preview file via `GET /api/projects/{id}/renders/{renderId}/file`.

### Video playback: no fetch-streaming/Range logic in app.js — plain `<video src>`
```javascript
// loadRenderInPreview (line 1563):
const url = api.renderFileUrl(state.currentProjectId, renderId);   // /api/projects/{id}/renders/{renderId}/file
player.setAttribute('src', url); player.src = url; player.style.display = 'block'; player.load();
// maybeLoadSourcePreview (line 1470): url = asset.url || `/api/projects/${id}/assets/${assetHash}/file`; same src pattern
// server side (routers/renders.py line 170): FileResponse(mp4, media_type="video/mp4", headers={"Accept-Ranges": "bytes"}) — Range handled by Starlette; observed as HTTP 206 in log
// api.js: renderFileUrl = `/api/projects/${projectId}/renders/${renderId}/file`
```
No `fetch()`/streaming of video bytes in app.js; no `Range` header is set by the UI JS — the browser's native `<video>` element issues the Range requests (observed 66 x HTTP 206 in the server log).

### Scrubbing logic
```javascript
// line 1076: previewPlayer.addEventListener('timeupdate', () => { state.playheadSec = previewPlayer.currentTime || 0; ... })
// seekToSec (line 1614): player.currentTime = clamped;  // timeline ruler click/drag -> HTML5 video seek
// timeline zoom: TL_BASE_PPS * tlZoom; fitTimelineToWindow caps visible range ~470 s (line 1643 comment)
```

---

## APPENDIX — render_snapshots.db schema (same 9 tables as edit_graph.db; full DDL of the shared tables)
```sql
CREATE TABLE project_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE edits (edit_id TEXT PRIMARY KEY, parent_id TEXT, kind TEXT NOT NULL, author TEXT NOT NULL, timestamp TEXT NOT NULL, status TEXT NOT NULL CHECK (status IN ('applied','reverted','superseded')), sequence_num INTEGER NOT NULL, payload TEXT NOT NULL, FOREIGN KEY (parent_id) REFERENCES edits(edit_id));
CREATE TABLE jobs (job_id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL CHECK (status IN ('running','completed','failed')), started_at TEXT NOT NULL, finished_at TEXT, error TEXT);
CREATE TABLE edit_status_events (event_id TEXT PRIMARY KEY, edit_id TEXT NOT NULL, from_status TEXT, to_status TEXT NOT NULL, command_id TEXT, reason TEXT, changed_at TEXT NOT NULL);
CREATE TABLE commands (command_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, tool_name TEXT NOT NULL, status TEXT NOT NULL CHECK (status IN ('pending','done','failed')), created_at TEXT NOT NULL, payload_hash TEXT, result_json TEXT);
CREATE TABLE timeline_snapshots (edit_graph_hash TEXT PRIMARY KEY, project_id TEXT NOT NULL, timeline_json TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE notes (note_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, anchor_type TEXT NOT NULL CHECK (anchor_type IN ('timestamp','region','op')), anchor TEXT NOT NULL, text TEXT NOT NULL DEFAULT '', source TEXT NOT NULL CHECK (source IN ('typed','voice','region','agent','form_correction')), status TEXT NOT NULL CHECK (status IN ('pending','processed','dismissed')), created_at TEXT NOT NULL, processed_at TEXT, commit_token TEXT, resulting_op_ids TEXT NOT NULL DEFAULT '[]');
CREATE TABLE notes_archive (note_id TEXT PRIMARY KEY, ... same columns ...);
CREATE TABLE render_snapshots (version_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, edit_graph_hash TEXT NOT NULL, render_path TEXT NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL CHECK (status IN ('rendering','ready','failed')), label TEXT NOT NULL DEFAULT '');
```

## APPENDIX — /tmp render logs (first/last lines)
`/tmp/cli_render.log` (847 B, 13 lines): first `Render failed: melt (rc=1): x7f7bac2015c0] The "dc" option is deprecated...`, last `[aac @ 0x5585674abdc0] Qavg: 65521.051` / `Conversion failed!`.
`/tmp/render_proxy_video.log` (815 B, 1 line): `RENDER_RESULT {…cuda_fastpath: {elapsed_sec 77.89, speed_x 28.39}, decode_backend: cuda, elapsed_sec 700.80…}` (the 2026-08-06 proxy render result).
`/tmp/openedit_serve.log` (2,628 lines) — server request log, quoted in section 4.
