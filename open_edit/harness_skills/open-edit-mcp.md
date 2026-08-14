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
operations. Port old compositions to HyperFrames, preserve timing and alpha,
then compare representative frames before deleting legacy source or graph ops.

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
never renders media or writes preview files. GPU and Chromium stay outside the
sandbox. A live MLT consumer remains a later M4 decision.

## Token rule

Read this playbook, then only `docs/PIPELINE_ARCHITECTURE_MAP.md` and files it
names for the active operation. Never scan the repository to rediscover tools.

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
`get_render_job`, inspect diagnostics and QC, and only run `final` after review.
