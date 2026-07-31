---
name: qc-standards
description: What "passing" means after a trigger_render call, and how to interpret a failure on the real Open Edit render path.
---

# QC standards

A render is "passing" only if every check below succeeds. The render
path is `trigger_render` → `open_edit render --mode {proxy, final,
overlay}`.

Since the 7.1 restructure, the deterministic QC gate
(`open_edit.qc.gate.run_qc_gate`) runs automatically on every
successful server-side render: `render_service._run` runs the gate on
the finished MP4 and attaches the report to the job result as
`qc_report` (also persisted in the `qc_report` column of
`render_jobs.db`). The CLI (`open_edit render`) prints the same gate
result. The agent sees a `qc_report` summary in the `trigger_render`
tool result and should treat a failing gate as a signal to revise the
EditGraph rather than ship.

There is still no separate `qc_check` tool; the gate is a post-render
diagnostic. If any check fails, the user can decide whether to ship
anyway, re-render, or revise the EditGraph.

The gate runs the six documented checks below plus pipeline-internal
diagnostics (`render_completed`, `proxy_render`, `silence`,
`thumbnail`); the report `passed` flag is the AND of all checks.

## Checks (and what to do about a failure)

### `streams`

- **Pass:** the output has at least one video stream AND at least one
  audio stream.
- **Fail:** the output has no audio (a silent B-roll clip was
  concatenated without a music/voiceover fill), or no video (the
  EditGraph referenced an asset hash that ffmpeg can't decode).
- **Fix:** revise the EditGraph. Either add a music bed (`AddEffectOp`
  with `music_bed`) or drop the silent clip. If a video stream is
  missing, re-check the asset's path with `query_project list_assets`.

### `duration`

- **Pass:** rendered duration is within ±1.0s of the target the user
  asked for in the brief.
- **Fail:** rendered video is too short (a clip was skipped at compose
  time, or an asset reference resolved to a shorter file than
  expected) or too long (a `dissolve` transition's overlap wasn't
  trimmed, or trailing silence wasn't cut).
- **Fix:** revise the clip `inSec`/`outSec`. If a `dissolve`
  transition is involved and the duration is too long, tighten the
  outgoing clip's `outSec` by the dissolve duration.

### `audio_sync`

- **Pass:** video stream duration and audio stream duration agree
  within ±200ms.
- **How it holds:** silence cuts in this pipeline are expressed as
  `AddClipOp` `inSec`/`outSec` — audio and video are sliced together,
  so they stay in sync by construction. There is no separate
  `silenceremove` applied to audio only.
- **Fail:** audio is truncated or extended relative to video. This
  usually points to a source asset with mismatched A/V durations
  upstream, or a free-form `RawMltXmlOp` audio filter that changed
  audio length without re-timing video.
- **Fix:** check the source asset's A/V durations with
  `query_project list_assets`. If a free-form audio op is involved,
  verify its output length matches the video.

### `black_frames`

- **Pass:** no interval ≥0.5s of near-black video detected.
- **Fail:** a clip was trimmed past its real end-of-content (the
  source had trailing black) or the source itself has a black gap.
- **Fix:** re-trim the clip with a tighter `outSec`.

### `frozen_frames`

- **Pass:** no interval ≥1.0s where the video didn't change.
- **Fail:** a static image or screen-recording clip was kept too long.
- **Fix:** shorten the clip, drop it, or cover it with a `RawMltXmlOp`
  affine zoom so the frame is no longer visually static.

### `overlays_burned`

- **Pass:** either no HTML overlays were requested, or the overlays
  are visible in the rendered output. (We can't OCR the burned output;
  visual review is the real check.)
- **Gate behavior:** informational — the gate cannot OCR. In
  `overlay` mode the check passes with "visual review required"; in
  other modes it passes with "overlays not requested in this render
  mode". Treat the LLM visual-verification stage as the real check for
  overlay visibility.
- **Fail:** overlays were requested but did not appear. Re-render with
  `trigger_render --mode overlay` (overlays are burned only in overlay
  mode), or re-issue the `HtmlOverlay` op if it was dropped.

## Real-world failure modes (watch for these)

These are the failure modes we have actually hit in practice. None of
them are caught by the per-stream checks above; the agent has to look
for them explicitly.

### Asset-reference failures at append

- **Symptom:** `edit_project apply_generated_ops` returns an error
  referencing an asset hash that doesn't exist in the store.
- **Cause:** the agent guessed an asset hash instead of reading it
  from `query_project list_assets`.
- **Fix:** always read asset hashes from `list_assets`. Never guess.
  Never use a path like `demo_project/1.mp4` — the real path is under
  `.open_edit/assets/<hh>/<hash>` and is exposed by `list_assets`.

### Untranscribed assets

- **Symptom:** `edit_project generate=silence_cuts` or
  `analyze_narrative` returns `{"status": "error", "retry": True}`.
- **Cause:** server-side background transcription is still running.
  This is NOT a "no transcript" condition — it is a "try again in a
  few seconds" condition.
- **Fix:** wait briefly and retry. Do NOT fall back to hand-rolled
  `ffmpeg silencedetect` on the raw asset file — that bypasses the
  alignment that is about to become available and produces gaps that
  are not breath-filtered or min-segment-protected.

### Stale server code

- **Symptom:** a tool returns an error referencing a function or
  schema that doesn't match the current `TOOL_USAGE_GUIDE`.
- **Cause:** the Open Edit server is running an older version of the
  code than the agent's skill files describe.
- **Fix:** restart the server with the current code before retrying.

### Over-aggressive cut density

- **Symptom:** the rendered edit feels choppy, with many sub-2s speech
  fragments.
- **Cause:** the silence-cut policy was overridden
  (`keep_breath_ms` or `min_segment_s` set too low), or the agent cut
  on raw gaps instead of using `generate=silence_cuts`.
- **Fix:** re-run `generate=silence_cuts` with the defaults
  (`keep_breath_ms=600`, `min_segment_s=2.0`) and re-cut on the
  returned gaps.

## Re-running after a failure

The gate report (including a `qc_report` dict on the render job) tells
you which check failed and the span details. Re-running is explicit:

1. Read the failure detail (from the `qc_report` on the job, the render
   output, or the `apply_generated_ops` response).
2. Decide which op is at fault (a clip, a transition, an effect, an
   overlay, a free-form op).
3. Re-issue just the offending op via `edit_project` (or `run_script`
   for free-form). The EditGraph is mutable; you do not need to
   rebuild from scratch.
4. Re-render with `trigger_render --mode proxy` first (fast), then
   `--mode final` once the proxy passes.
