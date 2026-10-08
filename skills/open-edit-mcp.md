---
name: open-edit-mcp
description: >-
  Drive Open Edit video projects via the MCP pillar tools (query_project,
  edit_project, run_script, trigger_render, get_render_job, cancel_render_job).
  Use when ingesting media, building timelines, cutting silence, HyperFrames
  graphics, legacy Remotion migration, rendering proxy/final/preview-chunks,
  or reading review notes. Prefer these tools over exploring source code.
---

# Open Edit MCP — agent playbook

**Harness-agnostic.** Any host that speaks MCP should follow this file.

**Stop exploring.** Do not grep/read `open_edit/**` to rediscover tools. Call
MCP tools immediately. Only open source when debugging Open Edit itself.

Project path is pinned when MCP starts. Never pass `project_path` as a tool
argument.

## Tools

| Tool | Use |
|---|---|
| `query_project` | All reads |
| `edit_project` | Mutations + creative generation |
| `run_script` | Multi-step IR edits pillar ops cannot express |
| `trigger_render` | Proxy / final / preview-chunks render |
| `get_render_job` | Poll a job |
| `cancel_render_job` | Cancel a job |

## Priority

1. `query_project`
2. `edit_project`
3. `run_script` only when structured operations cannot express the edit
4. `trigger_render`
5. Poll with `get_render_job`

## Motion graphics

Default to Diffusion for editable titles, shapes and supported animations:
query `get_graphics_view` with `include_source`, author the literal JSX,
`trigger_render mode=graphics`, review the checked preview, then explicitly
`commit_graphics` with the expected revision. Use HyperFrames for advanced
HTML/CSS/JS compositions. Ordinary users choose a graphics action, not a backend.
Optional installation is `open_edit setup graphics` or `open_edit setup html`.

Use `edit_project` operation `add_hyperframes_overlay` for new HTML/CSS/JS
motion graphics. Parameters:

```json
{
  "template_path": "templates/title.html",
  "variables": {"title": "Hello"},
  "position_sec": 0,
  "duration_sec": 3
}
```

Template paths stay inside the pinned project. HyperFrames composition roots
use `data-composition-id`, `data-start`, `data-duration`, `data-width`,
`data-height`, and `data-fps`. Timed elements use stable `id`, `class="clip"`,
`data-start`, `data-duration`, and `data-track-index`. Register seekable
animation in `window.__timelines`, or use `data-no-timeline` for static content.
Run HyperFrames lint before rendering.

Existing `remotion` generation is migration-only. Do not create new Remotion
operations. Install compatibility only when needed with `open_edit setup legacy-remotion`. Port old compositions to supported Diffusion or advanced HTML, preserve timing and alpha,
then compare representative frames before deleting legacy source or graph ops.

## Editing history

`query_project query=get_history` returns grouped actions and graph revision.
`edit_project operation=undo|redo` requires `params.expected_revision`; it reverses
one complete committed batch. New edits clear the redo branch. Formatting-only
source saves do not add an editing action. Legacy status/reorder APIs form a safe
history barrier; use grouped history for ordinary Undo/Redo.

## Render products

| Mode | Use |
|---|---|
| `preview-chunks` | Dirty range cache, independent video/audio/playback artifacts |
| `proxy` | Complete, whole-file 640x360 review-artifact MP4 |
| `final` | Full-quality export from canonical originals |

Preview chunks use native HyperFrames graphics on the host render worker.
M3 uses sequential self-contained MP4 chunks by default; each yellow chunk
keeps an exact same-range fallback while it bakes. Proxy and final use
HyperFrames graphics plus MLT/FFmpeg base A/V during migration. `run_script`
never renders media or writes preview files. GPU and Chromium run on the render worker. A live MLT consumer remains a later M4 decision.

## Token rule

Load only the guide needed for the current operation. Use the tools to discover
project state. Read source only when debugging Open Edit itself.

`list_assets` returns at most 50 assets by default (maximum 500). Follow
`next_offset` using `params.offset`. `get_transcript_packed` returns at most
500 words by default (maximum 2000); follow its `next_offset` the same way.

## Common reads

- `query_project list_assets`
- `query_project get_transcript_packed`
- `query_project get_pending_notes` (see also skill `review-notes`)
- `query_project get_style_profile`
- `query_project analyze_narrative`
- `query_project search_assets`

## Review notes

Users place notes on the timeline (including audio-targeted notes). Always
call `get_pending_notes` before guessing. Honor `anchor.track_kind` as a hint,
but fix audio **or** picture from the same note when the text asks for it.

## Common edits

- `ingest_local`
- `add_clip`
- `trim_clip`
- `add_hyperframes_overlay`
- `apply_silence_gaps`
- `set_audio_gain`

Search stock assets before generating music, SFX, or visuals. Do not hand-roll
ffmpeg silence detection when `generate=silence_cuts` exists.

## Render workflow

Use `trigger_render` with `wait=false` by default. Save `job_id`, poll
`get_render_job` for status and QC. Set `include_details=true` when debugging
render diagnostics; only run `final` after review.
