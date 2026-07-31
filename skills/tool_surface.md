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
| `search_assets` | `query` (text) | Internet stock search across Pexels/Freesound/Openverse (video, photo, and audio). |
| `get_pending_notes` | `project_id` | Notes the user attached to the project. |
| `get_style_profile` | `op_type` | Style guidance for the given op type (cut, transition, effect, etc.). |
| `analyze_narrative` | `asset_hash` | Rule-based narrative segments. |
| `get_transcript_packed` | `asset_hash` (or omit for whole timeline) | Word-level alignment in a compact form. |

**Common mistake:** calling these without the required params and then
concluding the tool is broken. Read the error — it tells you which
param is missing. Re-issue with the param rather than grepping source
or skipping the call.

## 2. `edit_project` (mutations + creative generation)

Mutations:

- `add_marker` — annotate a timeline point.
- `set_pinned_value` — pin a value (e.g., aspect ratio) for downstream ops.
- `import_asset` — bring a new asset into the project.
- `ingest_local` — ingest absolute local media paths (project dir or
  `OPEN_EDIT_INGEST_ALLOWLIST`).
- `add_clip` / `trim_clip` / `replace_clip_source` / `change_clip_speed` —
  everyday timeline placement (prefer over `run_script`).
- `remove_clip` / `set_audio_gain` / `apply_silence_gaps` — remove, mute,
  and apply silence-cut proposals without `run_script`.
- `apply_generated_ops` — commit a list of IR ops (`AddClipOp`,
  `AddEffectOp`, `AddTransitionOp`, `HtmlOverlay`, `RawMltXmlOp`,
  `FreeFormCodeOp`, `NormalizeAudioOp`).

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
licensed Pexels/Freesound/Openverse stock is a suitable fit. Generate only when stock
does not meet the brief or licensing requirements.

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

- `proxy` — fast, low-quality; use for validation.
- `final` — full quality; use for the deliverable.
- `overlay` — burns HTML overlays (subscribe cards, captions) into the
  proxy render.

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
