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
successful server-side render: `render_jobs._run` runs the gate on
the finished MP4 and attaches the report to the job result as
`qc_report` (also persisted in the `qc_report` column of
`render_jobs.db`). The CLI (`open_edit render`) prints the same gate
result. `open_edit render` exits 1 when the QC gate fails — diagnostic
only; the server render path is unaffected. The agent sees a
`qc_report` summary in the `trigger_render`
tool result and should treat a failing gate as a signal to revise the
EditGraph rather than ship.

There is still no separate `qc_check` tool; the gate is a post-render
diagnostic. If any check fails, the user can decide whether to ship
anyway, re-render, or revise the EditGraph.

The gate runs the six documented checks below plus pipeline-internal
diagnostics (`render_completed`, `proxy_render`, `silence`,
`thumbnail`); the report `passed` flag is the AND of all checks.

## Render products and emission policy

Open Edit has three distinct preview/delivery products. Do not use
"proxy" as shorthand for all of them:

- `mode=proxy` is a complete-timeline **review artifact**. It uses the
  `fast_proxy` profile at 640x360, produces one review MP4, and is not an
  interactive scrub or timeline-chunk stream.
- A **source proxy** is a low-resolution CAS sibling for one source asset.
  The host-side `generate-asset-proxy` job creates it and `AssetInfo` reports
  `proxy_hash`, `proxy_profile`, and `proxy_status`; operators must not guess
  a proxy filesystem path. Source proxies are selected only by the
  `proxy-edit` and `preview-chunk` emission profiles.
- **preview chunks** are a separate future/M3 interactive product. They are
  not produced by `mode=proxy` and must not be described as a review MP4.

The explicit source-media mapping is:

- `final` and `review-artifact` use canonical original CAS sources.
- `proxy-edit` and `preview-chunk` may use a ready source proxy, with a
  canonical-source fallback while the proxy is `queued`, `running`, missing,
  or failed.

`mode=proxy` defaults to the `review-artifact` profile, so a source proxy
being ready does not change the meaning of the review render. `mode=final`
is the final export path and always uses canonical originals, even when a
source proxy is available. Materialized Remotion/render derivatives are
separate regenerable cache entries.

## QC policy, completeness, and budgets

A successful render and a complete QC pass are separate states. The MCP
result and durable render job expose a `qc_report` with:

- `policy`: `full`, `light`, or `skip`;
- `complete`: whether the checks provide complete QC evidence;
- `passed`: the result of the checks that were run.

Proxy warm-cache hits may report `policy=skip` or `policy=light` depending
on operator configuration. Inspect `qc_report.complete` before treating a
proxy as fully QC'd; `passed=true` for deliberately skipped checks is not
evidence that those checks decoded the file. Final QC remains available and
is always `full` for `final` and `overlay`.

The QC controls are:

- `OPEN_EDIT_PROXY_QC_MODE` controls cold `mode=proxy` renders (default
  `light`).
- `OPEN_EDIT_PROXY_WARM_QC_MODE` controls a warm proxy deliverable-cache hit
  (default `skip`; `light` is available when a partial recheck is preferred).
- `OPEN_EDIT_PROXY_QC_POLICY` is the M1 compatibility override. When set,
  use `always`, `skip_on_hit`, or `never`; it takes precedence for proxy
  policy (`skip_on_hit` means full QC on a cold render and skip on a hit).
- `OPEN_EDIT_FINAL_QC_BUDGET_SEC` sets the total final/overlay QC budget
  (default 900 seconds).
- `OPEN_EDIT_QC_BLACKDETECT_MAX_SEC` caps duration-aware black-frame
  detection (default 900 seconds).

A detector timeout is incomplete diagnostic evidence: it must leave
`qc_report.complete=false` (and can leave `passed=false`), not become
permission to ship the final export blindly. QC is diagnostic and does not
retroactively turn an otherwise successful render job into a failed job.

## Cache policy and operator budgets

Cache eviction is content-aware and best effort:

- Canonical source CAS objects and their sidecars are protected.
- Active jobs and the newest final deliverables/review artifacts are
  protected.
- Regenerable source proxies, Remotion materialize outputs, render-cache
  entries, and orphaned temporary files may be removed when their budgets or
  disk-pressure thresholds require it.
- When a source proxy is evicted, its source metadata is cleared; the next
  proxy-backed emission can regenerate it.

The cache controls are byte/second budgets. Invalid or non-positive values
fall back to the defaults:

- `OPEN_EDIT_RENDER_CACHE_MAX_BYTES=1073741824`
- `OPEN_EDIT_REMOTION_CACHE_MAX_BYTES=536870912`
- `OPEN_EDIT_SOURCE_PROXY_MAX_BYTES=1073741824`
- `OPEN_EDIT_CACHE_MAX_AGE_SEC=86400`
- `OPEN_EDIT_CACHE_MIN_FREE_BYTES=536870912`

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
