# Video-Use Merge — what was ported and why

Status: implemented + tested (2026-08-06). Source of the merge:
[browser-use/video-use](https://github.com/browser-use/video-use), studied in
depth by two sub-agents (reports: `video-use/STUDY_REPORT.md`,
`docs/OPENEDIT_INTERNAL_STUDY.md`).

## Findings that shaped the merge

1. **OpenEdit's MLT effects were silently broken on melt ≥ 7.22.** The XML
   emitter wrote `service="..."` (the parser reads `mlt_service`), keyframes
   used `<kf>` elements (no longer parsed; animations are `frame=value;`
   property strings), and catalog param names did not match MLT filter
   properties (`brightness.value` vs `level`; volume `level` is dBFS, not
   amplitude). Verified empirically with melt 7.40: filters failed to load,
   micro-fades were no-ops. **Fixed** in `render/emitter.py` + catalog.
2. **No color grading existed.** video-use's `grade.py` auto mode is a
   bounded, per-clip signalstats analysis — ported wholesale.
3. **Filler-word cutting existed only as "silence gaps".** video-use treats
   fillers as LLM judgment over verbatim word timestamps; we added a code
   level filler detector + word-boundary snapping + padding.
4. **The transcript-first reading mechanism** (packed transcript + on-demand
   timeline-view composite) was half-built: `get_transcript_packed` existed;
   the waveform/visual layer had been deleted from production. Ported
   `timeline_view` back as a query.
5. **Overlays** were primitive-only; video-use drives data-rich animations.
   Added JSON variable payloads + a second built-in template.

## What was implemented

### A. Render pipeline correctness (reliability)
- `render/emitter.py`: emit `mlt_service` (keep `service`), keyframes as
  animated property strings (`0=0.5;!30=1.0`), micro-fades in dBFS
  (`-80 → 0 → -80`). Catalog-driven property + service resolution.
- Catalog fixes: `brightness` (value→level), `contrast`/`saturation`
  (→ MLT `avfilter.eq` with `av.*` properties).

### B. Auto color grading (new)
- `render/color_grade.py` — port of video-use `grade.py`:
  `_sample_frame_stats` (signalstats, bit-depth normalized),
  `auto_grade_params` (bounded ±8% contrast/gamma/saturation decisions),
  presets `subtle/neutral_punch/warm_cinematic/none`.
- `ir/catalog/effects/color_grade.yaml` — `color_grade` → MLT `avfilter.eq`.
- `edit_project operation=auto_color_grade` — per-clip analysis →
  `AddEffectOp`s; accepts `clip_ids`, `preset`, `params` overrides.
- Preview-chunk invalidation covers `color_grade`.

### C. Filler + dead-space cutting (improved)
- `agent/skills/silence_cutter.py`: `FILLER_WORDS` vocabulary,
  `find_filler_spans` (contextual fillers gated by pauses),
  `propose_cuts(include_fillers=True)`.
- `apply_silence_gaps` gains `padding_ms` (30–200 guidance) +
  `snap_to_words` (code-enforced word-boundary snapping, tolerance 60 ms).
- New query `get_silence_gaps` — structured gaps + filler spans.

### D. Transcript-first video reading (new query)
- `render/timeline_view.py` — filmstrip + waveform (ffmpeg showwavespic) +
  word labels + silence shading + time ruler composite PNG (video-use layout).
- New query `get_timeline_view` — `asset_hash` (CAS) or project-relative
  `path` (e.g. render output for self-eval); returns PNG path.
- Deps: `pillow` added to pyproject.

### E. Overlays (more powerful)
- `render/html_overlay.py`: non-primitive variables become
  `window.__open_edit_vars_<overlayId>` JSON payloads (no more error).
- New built-in template: `caption_card.html` (animated caption bar).

### F. Agent playbook
- `skills/edit-planning.md` (and wheel copy): transcript-first cutting &
  grading section — reading view, timeline drill-down, cut craft rules,
  auto-color usage, JSON-variable overlays.

## Tests
New/updated: `tests/test_render_emitter.py` (MLT format), `tests/test_color_grade.py`
(decision rules), `tests/test_skill/test_silence_cutter.py` (fillers/snap/pad),
`tests/test_render/test_timeline_view.py`, `tests/test_html_overlay.py` (JSON vars),
`tests/test_agent_tool_table_coverage.py` (registry). Full suite: ~1450 tests green.

## Not ported (by design)
- ElevenLabs Scribe cloud API (OpenEdit uses local faster-whisper; word-level
  verbatim timestamps are the only contract needed). Audio-event tags
  (`(laughter)`) and diarization remain unavailable — speaker tags stay unset.
- Parallel sub-agent animation generation (Rule 10) — OpenEdit's overlay
  materialization is sequential; the IR/overlay seams support parallel
  layers if a host worker is added later.
- LLM-vision self-eval loop — OpenEdit now has the tooling
  (`get_timeline_view` on render outputs + ffprobe duration in the QC gate);
  the loop itself is agent procedure (see edit-planning.md).

## Usage cheatsheet
```jsonc
// grade every video clip automatically
{"operation": "auto_color_grade", "params": {"preset": "auto"}}
// cut a clip: filler+silence gaps, word-snapped, 60ms padding
{"operation": "apply_silence_gaps",
 "params": {"clip_id": "...", "gaps": [...],
            "snap_to_words": true, "padding_ms": 60}}
// inspect before cutting / after rendering
{"query": "get_timeline_view",
 "params": {"asset_hash": "...", "start_sec": 10, "end_sec": 20}}
{"query": "get_timeline_view",
 "params": {"path": ".open_edit/renders/project_xxx.mp4", "start_sec": 4, "end_sec": 7}}
```
