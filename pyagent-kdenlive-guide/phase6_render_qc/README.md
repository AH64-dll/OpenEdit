# Phase 6 — Render & Quality Control

Phase 6 closes the gap between "the .kdenlive file is edited" and
"watchable video" using melt (render) and ffmpeg/ffprobe (QC). Per the
PHASE_6 plan, PyAgent itself only ever sees small text-and-thumbnail
sized signals; humans get the real video.

## Architecture

```
LLM tool call (pi extension)
  -> callPhase6(module, args)
       -> spawnSync: python3 -m phase6_render_qc.<module> ...
            -> render / thumbnails / audio / black_frames
                 -> melt | ffmpeg | ffprobe
       <- JSON result on stdout
```

The LLM calls each tool individually for fine control, following the
recommended conversation flow from PHASE_6 §"The conversational QC loop":
run the cheap deterministic checks (black frames, silence, audio
levels) first, only pull a thumbnail if anything is flagged.

## Tools

| Tool | Module | Mode | What it returns |
|---|---|---|---|
| `pyagent_render` | `render` | proxy / final | rendered MP4 + profile used + elapsed time |
| `pyagent_get_thumbnail` | `thumbnails` | thumbnail | JPEG ≤480px long edge, q70, <250KB |
| `pyagent_get_qc_crop` | `thumbnails` | crop | same caps, with `region={x,y,w,h}` |
| `pyagent_list_black_frames` | `black_frames` | range | spans where luma < threshold for ≥ min_sec |
| `pyagent_list_silence` | `audio` | range | spans where audio < threshold_db for ≥ min_sec |
| `pyagent_get_audio_levels` | `audio` | range | RMS + peak dB for the range |

All six are registered in `phase3_pyagent_core/extension.ts` (tools 13–18).

## Render modes

- **`proxy`** — 640x360, 30 fps, progressive. Sub-2s for a 4s clip.
- **`final`** — uses the project's own `<profile>` (width/height/fps/color).

The `proxy` and `final` modes both pass the full project profile
attributes (`progressive=1`, `frame_rate_num`, `sample_aspect_num`, etc.)
to the melt consumer. Without these, melt's default consumer profile is
interlace + weightp, which is incompatible with the local libx264 and
causes the encode to stall at flush time. The `render` function does this
transparently; call sites do not need to know.

## File map (post-2026-07-19 cleanup)

| File | Purpose | Lines |
|---|---|---|
| `render/__init__.py` | `pyagent_render` (proxy / final melt invocation) | 193 |
| `thumbnails/__init__.py` | `pyagent_get_thumbnail` + `pyagent_get_qc_crop` (size/quality caps) | — |
| `audio/__init__.py` | `pyagent_list_silence` + `pyagent_get_audio_levels` (env-driven timeout, structured JSON on timeout) | — |
| `black_frames/__init__.py` | `pyagent_list_black_frames` (handles string vs float threshold from LLM) | — |

The 2026-07-19 cleanup consolidated the previously-fragmented
`qc_loop` orchestration and fixed two bugs (audio `TimeoutError`
emitting unstructured error instead of `{kind: "timeout", ...}`;
black-frames parser failing when the LLM sent `luma_threshold` as
the string `"0.04"` instead of a number).

## CLI

```bash
# Render
python3 -m phase6_render_qc.render \
  --project /tmp/x.kdenlive --output /tmp/proxy.mp4 --mode proxy

# Thumbnail
python3 -m phase6_render_qc.thumbnails \
  --video /tmp/proxy.mp4 --timestamp-sec 1.5 --output /tmp/thumb.jpg

# QC crop
python3 -m phase6_render_qc.thumbnails \
  --video /tmp/proxy.mp4 --timestamp-sec 1.5 \
  --region '{"x":100,"y":100,"w":400,"h":300}' --output /tmp/crop.jpg

# Black frames
python3 -m phase6_render_qc.black_frames --video /tmp/proxy.mp4

# Silence / audio levels
python3 -m phase6_render_qc.audio silence --video /tmp/proxy.mp4
python3 -m phase6_render_qc.audio levels --video /tmp/proxy.mp4
```

Each prints a single JSON object to stdout and exits 0 on success, 1 on
error — so it slots straight into the `callPhase6` JSON-parser in the
extension.

## Acceptance criteria (per PHASE_6 §Acceptance)

- [x] `render(mode="proxy")` on the demo fixture (one transition, 4s)
      produces a valid 640x360 H.264 MP4 in <2s.
- [x] `render(mode="final")` uses the project's own profile (1920x1080
      30fps) — verified via ffprobe.
- [x] `list_black_frames` correctly flags the deliberately-black demo
      fixture (single 4s span), and the parser unit-tests cover
      empty-input cases.
- [x] `get_thumbnail` and `get_qc_crop` both respect the size/quality
      caps — verified in `test_get_thumbnail_respects_caps` via actual
      output file size + JPEG magic bytes + max(w,h) ≤ 480.

## Tests

```bash
cd pyagent-kdenlive-guide
PYTHONPATH=. python3 -m pytest phase6_render_qc
# 30 passed
```

Per-test-file:

| File | Tests | Purpose | Deps |
|---|---|---|---|
| `test_parsers.py` | 21 | Unit tests (no external deps) | none |
| `test_render_integration.py` | 8 | End-to-end render / thumbnail / QC | melt, ffmpeg, demo fixture |
| `test_e2e_pipeline.py` | 1 | The "render → QC → report" full pipeline | melt, ffmpeg, demo fixture |
