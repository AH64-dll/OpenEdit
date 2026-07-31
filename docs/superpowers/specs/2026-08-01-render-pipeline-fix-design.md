# Render Pipeline Fix — Design (2026-08-01)

Status: approved (brainstormed with user, 2026-08-01)

## Problem

The render pipeline has four issues, confirmed by measurement on the dev
machine (RTX 4050, melt 7.x, ffmpeg with NVENC):

1. **Double encode on overlay projects.** `render_project` (orchestrator.py)
   runs melt to a base MP4 (encode #1, final-quality args), then
   `burn_overlays` (graphics_overlay.py) decodes and re-encodes the entire
   video to burn Remotion overlays (encode #2). The same content is encoded
   twice; quality degrades generationally. Benchmark: 12 s of 1080p30 through
   melt+NVENC = 3.67 s; melt's compose cost dominates — the encoder itself
   runs at 240x realtime (0.05 s). A two-pass overlay render therefore pays
   ~2x melt's processing cost.
2. **No control over output size/quality.** `RenderProfile` (profiles.py) is
   fixed resolution/fps; `EncoderSpec` (encoder.py) has a fixed `final`/`proxy`
   policy. No CRF, bitrate, preset, scale, or codec knobs anywhere. CLI
   exposes only `--profile/--mode/--encoder`; REST only `mode`/`encoder`.
3. **Cache-key bug.** The render cache is keyed on the edit-graph hash alone
   (orchestrator.py:106-121). A request for 480p or a different quality can be
   served a cached file rendered at another resolution/quality/encoder.
4. **No hardware decode.** melt decodes sources on CPU. Measured
   `hwaccel=cuda` on producers: ~15% melt-pass speedup (1.25 s -> 1.06 s per
   6 s clip at 1080p30).

## Goals

- Single-pass rendering for all projects (overlay and plain) via a
  melt -> ffmpeg frame-server pipe.
- Named quality tiers plus raw overrides (CRF, bitrate, preset, scale,
  codec), with today's output bit-identical by default.
- Cache key includes profile identity (resolution + quality + overrides +
  encoder).
- Hardware decode when GPU backend is active, with CPU fallback.
- Surfaces: CLI flags, REST `RenderRequest` fields (persisted in
  `render_jobs`), and a new `pyagent_render` agent tool.
- No behavior change unless the user asks for one: `proxy` mode = 720p30
  `fast`, `final` mode = 1080p30 `standard` — numerically the values melt and
  ffmpeg already receive today.

## Non-goals

- No frontend (static/index.html) changes.
- No segment-parallel rendering (future work if renders are still slow).
- No changes to the QC gate.
- No changes to Remotion materialization.

## Architecture

### New pipeline (all projects)

```
melt (one process)
  - video: compose timeline frames -> rawvideo pipe (stdout, yuv420p, WxH, fps)
  - hwaccel=cuda on producers when GPU backend (retry once on CPU if melt fails)
audio.wav
  - second melt run, audio-only (-consumer avformat:audio.wav -format wav
    video_off=1) — video_off skips video processing entirely, so this pass
    is cheap

ffmpeg (one process)
  - inputs: rawvideo pipe (-f rawvideo -s WxH -r fps -pix_fmt yuv420p -i -),
    overlay clips (same inputs as graphics_overlay today), audio.wav
  - filter graph: overlay windows (existing logic, moved into the pipe path)
  - output: ONE final encode per EncoderSpec -> output.mp4
```

- melt and ffmpeg run concurrently; `run_pipe` (new, in melt_runner.py)
  replaces `subprocess.run`. Either process failing kills the other; stderr
  from BOTH is captured and merged into `RenderResult.error` (today only
  melt's stderr surfaces).
- No intermediate MP4 on disk. No `burn vs rename` fork (orchestrator.py:161)
  — one code path.
- Rate balance: melt ~3.3x RT, ffmpeg ~240x RT; pipe never backs up.
- Windows: rawvideo pipes work; hwaccel=cuda probed and skipped when absent.
- Failure diagnostics: ffmpeg reports truncated frame count when melt dies;
  QC duration check still guards silent truncation.

### Quality model

Named tiers replace the implicit `final`/`proxy` quality policy in
`EncoderSpec`:

| Tier      | NVENC                     | libx264            | Audio |
|-----------|---------------------------|--------------------|-------|
| fast      | cq 23, constqp, p4        | crf 23, veryfast   | 160k  |
| standard  | 10M VBR, max 14M, p5      | crf 18, medium     | 320k  |
| high      | 18M VBR, max 24M, p6      | crf 16, slow       | 320k  |
| archival  | 25M VBR, max 32M, p6      | crf 14, slow       | 320k  |

- `EncoderSpec` becomes per-`(vcodec, tier)`; `_SPECS` stays the single source
  for quality values, rendered in both dialects (melt `key=value` and ffmpeg
  flags).
- Raw overrides applied on top of a tier: `crf`, `vb`, `preset`, `scale`
  (e.g. `1440x810`), `codec` (`h264`/`hevc`/`av1` -> NVENC or libx265/SVT
  variants), `acodec`, `ab`. Overrides win over tier values.
- Validation (one place): crf in 0..51, known codec for the backend, valid
  scale; rejects nonsense at the API boundary.
- `mode` stays orthogonal: it selects the resolution profile (`proxy` ->
  720p30, `final` -> 1080p30); `quality` selects encode quality.
- Defaults: `proxy -> fast`, `final -> standard` — numerically identical to
  today's args.

### Cache key

`cache_key = canonical_json_hash(payload) + "|" + profile_fingerprint` where
profile_fingerprint = profile name + quality + all raw overrides + encoder
backend. Old entries (graph-hash-only) become unreachable; cache dir is
disposable.

### Hardware decode

When backend is `gpu`, `emit_timeline` emits `<property name="hwaccel">cuda</property>`
(+ `hwaccel_device`) on every avformat producer. `run_pipe` retries once
with CPU decode **only when** melt exited nonzero AND the XML had hwaccel
emitted. Non-NVIDIA platforms: probe once at first render (reuse the
existing `_probe_encoder` mechanism in encoder.py), remember the result in a
module-level flag, emit nothing.

### Surfaces

| Surface | Change |
|---|---|
| CLI `open_edit render` | `--quality --crf --vb --preset --scale --codec` flags -> `render_project` |
| REST `POST /api/projects/{id}/render` | `RenderRequest` gains the same fields; `render_jobs` gains `params_json` column (same ALTER-TABLE migration pattern as render_jobs.py:110); `_launch` passes params to the CLI |
| Agent tool | New `pyagent_render` in `agent/tools/` (mode, profile, quality, overrides, encoder) -> enqueue via `DEFAULT_RENDER_JOB_SERVICE` (layering-legal: agent -> kernel), poll, return job status/output; registered in `TOOL_TABLE` + `tool_schemas` |

## Error handling

- Merged stderr from both pipe processes.
- `MeltTimeoutError` unchanged (kills both processes).
- hwaccel failure -> one CPU-decode retry.
- QC gate unchanged (runs after success, diagnostic only).
- Agent tool returns canonical envelope per `agent/tools/_contract.py`
  (`{"status": "ok" | "error" | "retry"}`).

## Components

- `open_edit/render/melt_runner.py` — new `run_pipe` (concurrent melt+ffmpeg
  subprocesses, merged stderr, kill-on-partner-failure, timeout).
- `open_edit/render/pipe_builder.py` (new) — builds melt rawvideo args and the
  ffmpeg command for a given profile/spec/overlays (extracted from
  graphics_overlay's filter logic).
- `open_edit/render/encoder.py` — `_SPECS` keyed by (vcodec, tier); tier
  resolution + override application; validation.
- `open_edit/render/profiles.py` — `RenderProfile` gains quality + override
  fields; default resolution selection unchanged.
- `open_edit/render/emitter.py` — emits `hwaccel` producer properties when
  GPU backend.
- `open_edit/render/orchestrator.py` — one pipe path for all renders;
  cache key includes profile fingerprint; passes resolved spec through.
- `open_edit/kernel/render_jobs.py` — `params_json` column + migration;
  persist/forward quality params in `_launch`.
- `open_edit/serve/routers/renders.py` — `RenderRequest` fields + validation.
- `open_edit/cli.py` — render flags.
- `open_edit/agent/tools/pyagent_render.py` (new) + `tool_schemas.py` +
  `tool_registry.py` (TOOL_TABLE entry).

## Testing

Unit (no melt/ffmpeg needed):
- Tier resolution + override validation; defaults bit-identical to today
  (assert resolved specs equal current args for proxy/final with gpu and cpu
  backends).
- Cache-key distinctness (same graph, different quality/scale/encoder ->
  different keys).
- `run_pipe` with fake melt/ffmpeg scripts: success, melt failure, ffmpeg
  failure, partner-kill, timeout.
- Emitter hwaccel on/off.
- REST params persistence through enqueue -> CLI command.
- `pyagent_render` contract: ok envelope, error envelope, validation.

Integration (skip if melt or ffmpeg missing):
- Tiny 2-clip timeline: one encode path, correct duration, audio muxed.
- hwaccel retry path (fail first melt, succeed CPU retry).

Regression: full suite + `tests/test_layering.py` stay green.

## Future (explicitly deferred)

- Segment-parallel rendering.
- Web UI quality selector.
- HEVC/AV1 default policies beyond codec override.
