---
name: open-edit-editing
description: >-
  Editing craft for Open Edit: transcript-first cutting, silence and filler
  removal, pacing, transitions, the effect catalog, raw MLT escapes, color
  grading, and how to read and fix a failing render QC report. Load when
  planning or revising a cut.
---

# Editing craft

The plan lives in the edit graph as IR ops; there is no separate EDL. Clip
`in_point_sec`/`out_point_sec` *are* the cut: audio and video are sliced
together, so sync holds by construction.

## Transcript-first cutting

- Read `get_transcript_packed` (silence markers inline) and `get_silence_gaps`
  (`include_fillers: true` adds um/uh spans). Look at frames only at decision
  points: `get_timeline_view {asset_hash, start_sec, end_sec}`.
- Cut candidates: `generate=silence_cuts` drops breaths under `keep_breath_ms`
  (600) and refuses speech fragments under `min_segment_s` (2.0). Don't lower
  these without a reason; then `apply_silence_gaps {clip_id, gaps,
  snap_to_words: true, padding_ms: 50}`. Filler spans from `get_silence_gaps`
  can be passed directly as `gaps`.
- Silence tiers: ≥400 ms clean cut; 150–400 ms check visually; <150 ms is mid-phrase.
- Prefer sense boundaries (sentence ends, large `gap_after_s` in
  `analyze_narrative`) over raw gap midpoints.

## Pacing and selection

- Hit the requested duration within ±10%; prefer dropping weak material to padding.
- Vary shot length: mostly 2–6 s, occasional 1 s punches and 8–12 s holds.
  Front-load the strongest moment; build to a peak around 60–70%.
- Silent B-roll needs music or voiceover under it, or drop it. Drop shaky or
  dark shots unless they are the only take of a key moment.
- Validate before writing: `out_point_sec > in_point_sec`, both within the
  asset's `duration_s`, `asset_hash` from `list_assets`, transitions join
  existing clips.

## Transitions and effects

Transitions (`ir.add_transition(a, b, type, duration_sec)`): `cut` (default),
`fade` (section breaks), `dissolve`, `wipe`, `luma`.

Catalog effects (`ir.add_effect("clip"|"track", id, effect_type, params)`):

| Purpose | effect_type (params) |
|---|---|
| Grade | `color_grade` (`contrast`, `gamma`, `saturation`, 0.5–1.5; keyframable). Prefer `edit_project operation=auto_color_grade`; don't stack brightness/contrast/saturation for grading |
| Basic video | `brightness`, `contrast`, `saturation`, `luma` |
| Audio level | `gain`, `volume`, `panner`, `delay`, `eq` (EQ needs MLT ≥ 7.28; readiness reports it) |
| Audio fades | `audio_fade_in`, `audio_fade_out` (`duration` seconds) |
| Enrichment | `music_bed`, `sfx` (usually produced by `generate=music|sfx`) |

Also `ir.normalize_audio(target_kind, target_id, target_dbfs)` and
`ir.set_keyframe(effect_id, param, [(time_sec, value, "linear"), ...])` for animated params.

## Escape hatches (no validation until render)

The catalog cannot express these; emit them through `run_script`:

| Goal | Op |
|---|---|
| Zoom / camera move | `ir.raw_mlt_xml(xml, description)` with an `affine` filter, keyframed geometry |
| Denoise / compression | `raw_mlt_xml` with `avfilter.afftdn` / `avfilter.acompressor` |
| Ops computed from runtime data | `ir.free_form_code(...)` |

Raw ops skip reference checks and fail only at render, so proxy-render right
after adding one. Cursor-following zoom is impossible (no pointer telemetry);
offer a keyframed move instead.

## QC after a render

`get_render_job` returns `qc_report {passed, complete, policy, checks}`.
`complete=false` (warm-cache skip or detector timeout) is not proof of passing.

| Check fails | Likely cause → fix |
|---|---|
| `streams` | silent clip with no fill, or undecodable asset → add music/VO or drop clip; re-check `list_assets` |
| `duration` (±1 s of brief) | skipped/short clip or untrimmed dissolve overlap → adjust in/out points |
| `audio_sync` (±200 ms) | source A/V mismatch or a raw audio filter changing length → check the raw op |
| `black_frames` (≥0.5 s) | trimmed past content end → tighten `out_point_sec` |
| `frozen_frames` (≥1 s) | static shot held too long → shorten, drop, or add a zoom |
| `overlays_burned` | informational; review overlays visually |

Fix only the offending op (the graph is editable; undo exists), re-render proxy,
then final.
