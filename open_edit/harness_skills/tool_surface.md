# Tool-surface reference — the 4-pillar tools

**Quick start for all harnesses:** read [`open-edit-mcp.md`](open-edit-mcp.md)
first (shorter playbook + recipes). This file is the longer reference.

The editing agent has exactly four tools (+ render job helpers on MCP). Use
them in priority order; do not hand-roll bash / ffmpeg when a pillar tool
covers the job.

## 1. `query_project` (read-only)

Inspect project state. Sub-queries:

| Name | Required params | Returns |
|---|---|---|
| `list_assets` | — | All known assets with hash, path, duration, alignment status. |
| `search_assets` | `query` (text) | Durable internet stock cascade across Pexels/Freesound, Openverse, and Wikimedia Commons. |
| `get_pending_notes` | `project_id` | Notes the user attached to the project. |
| `get_style_profile` | `op_type` | Style guidance for the given op type (cut, transition, effect, etc.). |
| `analyze_narrative` | `asset_hash` | Rule-based narrative segments. |
| `get_transcript_packed` | `asset_hash` (or omit for whole timeline) | Word-level alignment in a compact form. |
| `get_graphics_view` | Optional `clip_id`, `include_source` | Compact graphics revision, worker readiness and last good preview; source on request. |
| `get_authoring_view` | Optional `include_source` (default false) | Revision and compact Diffusion media summary; literal JSX only on request. |

**Common mistake:** calling these without the required params and then
concluding the tool is broken. Read the error — it tells you which
param is missing. Re-issue with the param rather than grepping source
or skipping the call.

## 2. `edit_project` (mutations + creative generation)

Mutations:

- `add_marker` — annotate a timeline point.
- `set_pinned_value` — pin a value (e.g., aspect ratio) for downstream ops.
- `import_asset` — bring a new asset into the project.
- `ingest_local` — ingest any readable absolute local media path; symlinks are
  resolved and copied into the project CAS.
- `add_clip` / `trim_clip` / `replace_clip_source` / `change_clip_speed` —
  everyday timeline placement (prefer over `run_script`).
- `add_hyperframes_overlay` — add native HTML/CSS/JS motion graphics using a
  project-local template and timing.
- `remove_clip` / `set_audio_gain` / `apply_silence_gaps` — remove, mute,
  and apply silence-cut proposals without `run_script`.
- `apply_generated_ops` — commit a list of IR ops (`AddClipOp`,
  `AddEffectOp`, `AddTransitionOp`, `HtmlOverlay`, `RawMltXmlOp`,
  `FreeFormCodeOp`, `NormalizeAudioOp`).
- `apply_authoring_edit` — optional Diffusion media authoring: provide
  `expected_revision` from `get_authoring_view` and exactly one of full JSX
  `source` or native `edits` (`set`, `remove`, `move`, using source IDs such as
  `index.tsx:c-hero`). Supports media add/remove/move/trim/source replacement and
  absolute `volume` in dB and constant playbackRate 0.125..8 (checked CAS bake). Literal props, existing CAS assets and
  non-overlapping tracks only; preserves other graph features. Stale or invalid
  batches append nothing. Requires the optional pinned Node worker installed
  with `python -m open_edit.integrations.diffusion.setup`.

- `rewrite_graphics_source` — use `source`, `edits` and `expected_revision` to
  rewrite literal graphics properties through stable `index.tsx:ID` addresses.
  This prepares a draft; it does not mutate the graph.
- `commit_graphics` — apply a succeeded `mode=graphics` job with its
  `expected_revision`, optional `clip_id`, `track_id` and `position_sec`.
  Only complete CAS output with passing QC can enter the graph.
- `retime_asset` — bake a CAS asset's `source_in`, `source_out`, `playback_rate`
  or `segments=[{source_in,source_out,rate}]`, optionally `fps`. Returns a
  checked asset URL without graph mutation. Existing speed ops retain their
  old semantics; interpolated speed ramps are not mapped automatically.

For graphics, install `python -m open_edit.integrations.diffusion.setup
--graphics --chromium`, query `get_graphics_view` with `include_source=true`,
then `trigger_render` with `mode=graphics`, `expected_revision` and
`graphics={source,duration_sec,fps}`. Poll normally; commit only after review.
The same six MCP tools remain; optional integrations are loaded on request.

Creative generation (use these INSTEAD of hand-rolling):

- `generate=silence_cuts` — produces policy-filtered silence-cut
  suggestions from an asset's word-level alignment. **Prefer this over
  `ffmpeg silencedetect`.** The wrapper drops breaths, merges gaps
  separated by tiny speech fragments, and refuses to produce sub-2s
  leftovers.
- `generate=visual` — moviepy template motion graphic → CAS clip.
- `generate=init_remotion` — scaffold `.open_edit/remotion/` starter.
- `generate=write_remotion` — write a Remotion TSX file (imports limited
  to remotion/react; no `fs` / `child_process` / npm install).
- `generate=remotion` — append `AddRemotionCompositionOp`. Materializes
  to a CAS clip on the next **proxy/final** render (not `mode=overlay`).
  Prefer Remotion for kinetic titles / charts; prefer HyperFrames HTML
  overlays for simple `{{var}}` lower thirds. See `skills/remotion_motion.md`.
- `generate=sfx` — produce a sound effect.
- `generate=music` — produce a music bed.

**Search before generate:** Before `generate=visual`, `generate=music`, or
`generate=sfx`, prefer `search_assets` followed by `import_asset` when
licensed provider stock is a suitable fit. Generate only when stock does not
meet the brief or licensing requirements.

`apply_generated_ops` validates structured ops and rejects the batch
on the first failure. `RawMltXmlOp` and `FreeFormCodeOp` BYPASS this
validation — see `freeform_and_effects.md` for the dry-run workflow.

## 3. `run_script` (free-form Python)

Use ONLY when `edit_project` cannot express what you need. Typical
uses:

- Emitting `RawMltXmlOp` for zoom / denoise / compression / fades
  (see `freeform_and_effects.md`).
- Emitting `FreeFormCodeOp` for dynamic op generation.
- Bulk-rebuilding parts of the EditGraph from a script.

`run_script` skips the structured validation that `edit_project`
provides, so be extra careful: dry-run with `trigger_render --mode
proxy` before committing.

## 4. `trigger_render`

Renders the current EditGraph. Modes:

- `preview-chunks` — feature-gated, background range cache with independent
  video/audio/playback artifacts.
- `proxy` — fast, complete-timeline **whole-file** review artifact; use for
  validation and review, not as a chunk stream.
- `final` — full quality delivery export.
- `overlay` — burns HTML overlays (subscribe cards, captions) into the
  proxy render.

### `preview-chunks` job contract

Use the existing render tool for chunked timeline preview; do not invent a
second enqueue tool:

```json
{
  "mode": "preview-chunks",
  "ranges": [{"start_sec": 12.0, "end_sec": 20.0}],
  "media": "both",
  "priority": "interactive",
  "wait": false
}
```

`ranges` is optional and uses project seconds. `media` is `video`, `audio`, or
`both`; the two planes are independent and `playback` is their cheap mux.
`priority` is `interactive` or `background`. The server normalizes and bounds
range requests, while chunk geometry/profile remain server policy.

Preview generation is **on by default**. Set `OPEN_EDIT_PREVIEW_CHUNKS=0` to
disable it; this does not change `proxy` or `final`. With the default
`wait=false`, save the returned durable `job_id` and poll
`get_render_job({"job_id": "<job-id>"})`. The job result is manifest-oriented;
it is not a whole-file MP4. Manifest states are red/yellow/green:
yellow preserves a playable exact **same-range** artifact while the current
one bakes, and red means no current or same-range artifact is usable. A
whole-file proxy may be reported as an explicitly stale fallback.

The project-scoped routes are:

```text
GET    /api/projects/{project_id}/preview-chunks
GET    /api/projects/{project_id}/preview-chunks/files/{artifact_id}
DELETE /api/projects/{project_id}/preview-chunks
```

The file route resolves only indexed artifact IDs and supports byte ranges;
the wipe route removes preview cache entries only. M3 consumers use
sequential self-contained MP4 chunks by default. MSE/fMP4 is optional, and
free-form `run_script` never renders preview media or writes preview files.
Live MLT is not an M3 consumer; it remains an M4 decision.

QC after render is the agent's responsibility — see `qc-standards.md`.

## Priority order (always follow this)

1. `query_project` to understand state.
2. `edit_project` (with `generate` for creative ops) to make changes.
3. `run_script` only when `edit_project` can't express the goal.
4. `trigger_render` to render and verify.

Do not jump to `run_script` / raw bash before exhausting
`edit_project`. The structured path gives you validation and undo for
free.

## Common mistakes (do not repeat these)

- **Hand-rolled `ffmpeg silencedetect` on raw asset files.** This
  reinvents a wrapped tool, uses wrong paths initially
  (`demo_project/1.mp4` instead of `.open_edit/assets/<hh>/<hash>`),
  and ignores that `generate=silence_cuts` already produces the same
  gaps from the asset's alignment — breath-filtered and
  min-segment-protected.
- **Guessed asset paths / hashes.** Always read them from
  `query_project list_assets`. The real path is under
  `.open_edit/assets/<hh>/<hash>`; do not guess.
- **Concluded "no transcript" prematurely.** Server-side background
  transcription may still be running. If `analyze_narrative` or
  `generate=silence_cuts` returns `{"status": "error", "retry":
  True}`, wait a few seconds and retry.
- **Skipped `get_style_profile` / `get_pending_notes`.** The agent
  failed these once (missing `op_type` / `project_id`) and then
  skipped them, missing guidance that could have improved cut
  decisions. Read the error, add the param, retry.
- **Planned against phantom tools.** Earlier versions of
  `edit-planning.md` / `qc-standards.md` described `save_edl`,
  `FootageManifest`, `qc_check`, `state.json` — none of these exist.
  The current versions of those skills describe the real pipeline;
  trust them, not the old ones.

## Authoritative source

`open_edit/kernel/tool_schemas.py` — `TOOL_USAGE_GUIDE`. If anything
in this file disagrees with `TOOL_USAGE_GUIDE`, the guide wins.

## Relevant source (read these in the real codebase)

- `open_edit/kernel/tool_schemas.py` — `TOOL_USAGE_GUIDE` (authoritative)
- `open_edit/kernel/pillar_tools.py` — the dispatch layer:
  - `dispatch_query` (maps the 6 query names)
  - `dispatch_edit` (`add_marker` / `set_pinned_value` / `import_asset` / `ingest_local` / `apply_generated_ops` / timeline ops: `add_clip` / `trim_clip` / `replace_clip_source` / `change_clip_speed` / `remove_clip` / `set_audio_gain` / `apply_silence_gaps`)
  - `dispatch_generate` (`sfx` / `music` / `visual` / `silence_cuts` / `remotion` / `init_remotion` / `write_remotion`)
  - `_apply_generated_ops` (commits generated ops)
