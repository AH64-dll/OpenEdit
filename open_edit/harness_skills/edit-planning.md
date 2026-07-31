---
name: edit-planning
description: How to plan an edit against the real Open Edit pipeline — EditGraph + IR ops + the 4-pillar tools (query_project / edit_project / run_script / trigger_render). Use this skill before issuing any edit_project or run_script call.
---

# Edit planning

You are turning raw assets (video + word-level alignment) into an
**EditGraph**: an ordered set of clips, transitions, effects, overlays,
and audio ops that match the user's creative brief. There is no
separate "EDL" structure or `save_edl` tool — the plan lives directly
in the EditGraph as IR ops, committed via `edit_project
apply_generated_ops` (or `run_script` for the free-form escape hatch).

This is pure LLM reasoning. You inspect the project state with
`query_project`, decide what ops to emit, and commit them with
`edit_project` (or `run_script` when `edit_project` cannot express the
goal). Render happens via `trigger_render`.

## Input

You receive (via `query_project`):

- `list_assets` — every asset with its hash, path, duration, and
  whether word-level alignment is available.
- `get_transcript_packed` — word-level alignment for a specific asset
  (or the whole timeline).
- `get_pending_notes` — notes the user attached to the project
  (requires `project_id`).
- `get_style_profile` — style guidance for a given op type (requires
  `op_type`).
- `analyze_narrative` — rule-based narrative segments for an asset.
- `search_assets` — text search across transcripts.

Plus a one-line creative brief (e.g. "60-second highlight reel",
"tight 30s teaser for social", "calm 90s mood piece").

## Output

A sequence of IR ops committed to the EditGraph:

- `AddClipOp` — place a slice of a source asset on the timeline. The
  `inSec`/`outSec` you choose IS the silence cut: there is no separate
  `silenceremove` step downstream, and audio + video are re-timed
  together by construction.
- `AddTransitionOp` — `cut` (default), `fade`, or `dissolve` (all
  supported by the catalog).
- `AddEffectOp` — apply a catalog effect (brightness, contrast,
  saturation, luma, eq, gain, volume, panner, delay, music_bed, sfx).
- `HtmlOverlay` / `AddHtmlOverlayOp` — simple HyperFrames HTML lower-thirds
  / banners (`{{var}}` templates). Burned only when `mode=overlay`.
- `AddRemotionCompositionOp` — React/Remotion motion graphics (titles,
  charts, kinetic type). Materialized to CAS before melt; visible in
  **proxy and final** (not overlay-mode-only). Prefer
  `edit_project generate=remotion|init_remotion|write_remotion`.
  See `skills/remotion_motion.md`.
- `NormalizeAudioOp` — first-class audio normalization.
- `RawMltXmlOp` — escape hatch for goals the catalog cannot express
  (zoom/affine, denoise, compression, fades). Embeds raw MLT XML.
- `FreeFormCodeOp` — escape hatch for arbitrary Python that emits IR
  ops at apply time.

See `freeform_and_effects.md` for when to escape to free-form.

## Rules

### Match the target duration

- Aim for the requested duration. ±10% is fine; ±20% is too much.
- If you cannot hit the target with quality material, prefer the
  target over padding with weak shots — note this in your response.

### Cut dead air on sense boundaries, not raw gaps

- Use `edit_project generate=silence_cuts` to get *policy-filtered*
  cut candidates. The wrapper already drops breaths, merges gaps
  separated by a tiny speech fragment, and refuses to produce sub-2s
  speech fragments. Do NOT hand-roll `ffmpeg silencedetect` — that
  bypasses the alignment that was already computed server-side.
- Set clip `inSec`/`outSec` to skip the proposed silence gaps. There
  is no separate "remove silence" step; the plan IS where this
  happens.
- Prefer cutting on **sense boundaries** (end of a sentence, end of a
  thought) over cutting at the raw gap midpoint. The
  `analyze_narrative` tool gives you sentence-aligned segments with
  `gap_after_s` — segments with a large `gap_after_s` are natural cut
  candidates.
- Keep natural breaths (< ~600ms). The wrapper's default
  `keep_breath_ms=600` already does this; lower it only for very tight
  pacing.
- Avoid sub-2s speech fragments. The wrapper's default
  `min_segment_s=2.0` already enforces this; do not override it lower
  without a specific reason.

### Use quality signals to drop weak shots

- A shot with no usable audio (silent source) MUST be covered by music
  or voiceover, or dropped.
- A shaky or underexposed shot is salvageable only if it is the only
  usable take of a key moment; otherwise drop.
- Never include a shot that has no recoverable content.

There is no structured `qualityFlags` field on `Asset` in the current
codebase — derive these signals from `list_assets` (alignment status,
duration) and from your own visual review of the source.

### Shot variety

- Vary shot lengths. A sequence of five 2-second cuts is exhausting; a
  single 30-second static shot is boring.
- Aim for a mix: most cuts 2-6s, occasional 1s punch cuts for energy,
  occasional 8-12s held shots for breathing room.

### Pacing

- Front-load the strongest material. The first 5 seconds decide
  whether someone keeps watching.
- Build to a peak roughly 60-70% of the way through, then resolve.

### Transitions

- Default: `cut` (free, looks clean).
- Use `fade` at clear narrative breaks (scene change, end of section).
- `dissolve` IS supported by the catalog (`dissolve.yaml`) and may be
  used between sections for a softer handoff. The previous blanket
  "do NOT emit dissolve" ban was wrong for this codebase — it has been
  lifted.

### Color, audio, overlays — the free-form escape hatch

The structured catalog CANNOT express:

- **Zoom / camera move** — needs `RawMltXmlOp` with an MLT `affine`
  filter (keyframed `cx` / `cy` / `scale`).
- **Audio denoise** — needs `RawMltXmlOp` with `afftdn`.
- **Audio compression** — needs `RawMltXmlOp` with `acompressor`.
- **Audio fade in/out** — needs `RawMltXmlOp` with `afade`.
- **Cursor-following zoom** — IMPOSSIBLE. The asset model has no
  pointer-track / mouse-movement telemetry. Do NOT promise the user
  "the camera will follow the cursor." Offer a keyframed camera move
  on a fixed trajectory instead.

For everything else (brightness, contrast, eq, gain, volume, music
bed, sfx, dissolve, normalize), prefer the structured catalog — it
gives you validation and undo for free. Use `run_script` only to emit
the `RawMltXmlOp` / `FreeFormCodeOp` cases above.

See `freeform_and_effects.md` for the full reference.

### Sanity-validate before committing

For every `AddClipOp`:

- `outSec > inSec`.
- Both `inSec` and `outSec` are within that source asset's duration
  (read from `list_assets`).
- `sourceFile` (or `asset_hash`) exactly matches a known asset.

For every `AddTransitionOp`:

- The two clips it joins actually exist on the timeline.

For every `AddEffectOp` / `HtmlOverlay` / `RawMltXmlOp`:

- The target clip exists.
- The effect parameters are within the catalog's schema (for catalog
  effects) or the MLT XML is well-formed (for `RawMltXmlOp`).

`edit_project apply_generated_ops` validates structured ops and will
reject the batch on the first failure. Free-form ops
(`RawMltXmlOp` / `FreeFormCodeOp`) BYPASS this validation — they only
fail at render time. Always dry-run a free-form op with
`trigger_render --mode proxy` before committing it to a real project.

### Tool priority (always follow this)

1. `query_project` — inspect state. Read `TOOL_USAGE_GUIDE` in
   `open_edit/kernel/tool_schemas.py` for the authoritative schema.
2. `edit_project` — make changes (mutations + `generate` for creative
   suggestions like `silence_cuts` / `sfx` / `music` / `visual`).
3. `run_script` — ONLY when `edit_project` cannot express the goal
   (zoom, denoise, compression, fades, dynamic op generation).
4. `trigger_render` — render and verify.

Do not jump to `run_script` / raw bash before exhausting
`edit_project`. See `tool_surface.md` for the full reference.
