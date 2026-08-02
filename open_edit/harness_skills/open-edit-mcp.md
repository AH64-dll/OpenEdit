---
name: open-edit-mcp
description: >-
  Drive Open Edit video projects via the MCP pillar tools (query_project,
  edit_project, run_script, trigger_render, get_render_job, cancel_render_job).
  Use when ingesting media, building timelines, cutting silence, Remotion/
  overlays, rendering proxy/final/preview-chunks, or reading review notes.
  Prefer these tools over exploring Open Edit source code.
---

# Open Edit MCP — agent playbook

**Harness-agnostic.** Any host (Cursor, Claude Code, Pi, custom agents) that
speaks MCP should follow this file. Source of truth: `skills/open-edit-mcp.md`.

**Stop exploring.** Do **not** grep/read `open_edit/**`, `pillar_tools.py`,
`silence_cutter.py`, or long docs to rediscover tools. Call the Open Edit MCP
tools immediately. Only open source when debugging Open Edit itself.

Project path is pinned when the MCP process starts (`--project` /
`OPEN_EDIT_PROJECT`). Never pass `project_path` as a tool argument.

## Tools (complete list)

| Tool | Use for |
|---|---|
| `query_project` | All reads |
| `edit_project` | Mutations + creative generate |
| `run_script` | Multi-step IR edits pillar ops cannot express |
| `trigger_render` | Proxy / final / overlay / preview-chunks render |
| `get_render_job` | Poll a job by `job_id` |
| `cancel_render_job` | Cancel queued/running job |

Use the host's MCP client to call these tools. Do not re-implement with shell
`ffmpeg` / `melt`.

## Priority order

1. `query_project` — learn state
2. `edit_project` — change state / generate proposals
3. `run_script` — only if step 2 cannot express the edit
4. `trigger_render` — preview (`proxy`) then deliver (`final`)

## `query_project` queries

| `query` | Params | When |
|---|---|---|
| `list_assets` | `{}` | First step; get `asset_hash`, duration |
| `get_transcript_packed` | `asset_hash` optional | Silence/cut planning |
| `get_pending_notes` | often needs `project_id` | Review-UI notes |
| `get_style_profile` | `op_type` | Style before generating ops |
| `analyze_narrative` | `asset_hash` | Segment structure |
| `search_assets` | `query` text | Search durable provider cascade (Pexels/Freesound → Openverse → Wikimedia Commons) |

## `edit_project` operations (immediate)

| `operation` | `params` | When |
|---|---|---|
| `ingest_local` | `{paths: ["/abs/..."], transcribe?: true}` | Import any readable local media path; symlinks are resolved and copied into the project CAS |
| `import_asset` | tool-specific | Import into CAS when not using ingest_local |
| `add_marker` | timing + text | Agent note / marker |
| `set_pinned_value` | key/value | Pin style overrides |
| `apply_generated_ops` | `{ops: [...]}` | Commit reviewed generated ops |
| `add_clip` | `{asset_hash, track_id, position_sec, in_point_sec?, out_point_sec, track_kind?}` | Place clip (prefer over `run_script`) |
| `trim_clip` | `{clip_id, in_point_sec?, out_point_sec}` | Trim source in/out |
| `replace_clip_source` | `{clip_id, new_asset_hash}` | Swap clip media |
| `change_clip_speed` | `{clip_id, rate}` | Retime clip |
| `remove_clip` | `{clip_id}` | Remove a clip |
| `set_audio_gain` | `{clip_id, gain}` | Mute / set gain (0.0 = mute) |
| `apply_silence_gaps` | `{clip_id, gaps: [{start_sec, end_sec}, ...]}` | Apply silence-cut gaps via trim/split |

## `edit_project` generate (proposals — review then apply)

| `generate` | `generate_params` | When |
|---|---|---|
| `silence_cuts` | `{asset_hash, threshold_ms?, min_segment_s?}` | Cut dead air — **never** hand-roll `ffmpeg silencedetect` |
| `sfx` / `music` / `visual` | segment params | Creative beds / fills |
| `init_remotion` | `{}` | Scaffold `.open_edit/remotion/` |
| `write_remotion` | composition write params | Write TSX under remotion src |
| `remotion` | composition props + timing | Append `AddRemotionCompositionOp` |

Silence cuts return gaps; apply with `operation=apply_silence_gaps` (or
`trim_clip` for a single gap), not a separate audio-only silenceremove pass.

Before generating visual, music, or SFX assets, search first with
`search_assets` and use `import_asset` when licensed provider stock is a
suitable fit. Search responses preserve provider provenance and survive
server restarts.

## Render

Open Edit has three distinct preview/delivery products. Keep their names
separate:

| Mode | Resolution | Use |
|---|---|---|
| `preview-chunks` | ~640x360, project FPS | Background, range-limited cache with independent video/audio/playback artifacts |
| `proxy` | ~720p | Complete-timeline, whole-file review artifact; Remotion materialize + burn-in |
| `final` | ~1080p | Delivery export |
| `overlay` | — | HyperFrames HTML only — **not** Remotion |

`mode=proxy` is one whole-file MP4 review artifact, not a timeline chunk
stream and not a per-asset source proxy. `mode=final` remains the full-quality
delivery path and uses canonical sources. A source proxy is a separate
per-asset optimization; it does not change the meaning of either mode.

### Chunked timeline preview

`trigger_render` accepts a feature-gated `mode=preview-chunks` job for a
requested timeline window:

```json
{
  "mode": "preview-chunks",
  "ranges": [{"start_sec": 12.0, "end_sec": 20.0}],
  "media": "both",
  "priority": "interactive",
  "wait": false
}
```

`ranges` is optional: an empty list asks the worker to process all dirty
chunks in manifest order. Each range is in project seconds. `media` is
`video`, `audio`, or `both`; video and audio are independent cache planes,
with a cheap muxed `playback` artifact for synchronized browser playback.
`priority` is `interactive` or `background`: interactive jobs prioritize the
requested window, while background jobs may cover all dirty ranges.

Preview generation is disabled unless the host sets
`OPEN_EDIT_PREVIEW_CHUNKS=1`. The default remains disabled; this gate does not
change `proxy` or `final`. `trigger_render` is non-blocking by default
(`wait=false`) and returns a durable `job_id`. Poll it with
`get_render_job`:

```json
{"job_id": "<job-id>"}
```

The terminal job result is manifest-oriented, not a playable whole-file MP4.
Read the manifest's red/yellow/green chunk status and independent
`video.status` / `audio.status` values. `green` means the current artifact is
ready; `yellow` means the current range is baking or dirty but an exact
**same-range** prior artifact can play; `red` means neither current nor
same-range prior media is usable. If no chunk is playable, use the newest
whole-file proxy as an explicitly stale fallback when one exists—never
substitute a neighboring time range.

The project-scoped HTTP routes expose the browser-safe artifact surface:

```text
GET    /api/projects/{project_id}/preview-chunks
GET    /api/projects/{project_id}/preview-chunks/files/{artifact_id}
DELETE /api/projects/{project_id}/preview-chunks
```

The manifest response contains `manifest`, `active_job`, and
`proxy_fallback`; it projects indexed artifact IDs to URLs and never exposes
filesystem paths. The file route accepts only an indexed `artifact_id` and
supports `Accept-Ranges: bytes`. The wipe route removes preview artifacts
only—it does not remove the Edit Graph or proxy/final renders.

M3 uses self-contained MP4 chunks with sequential HTML5 playback by default.
MSE/fMP4 is an optional future strategy, not an M3 correctness requirement.
Free-form `run_script` remains sandboxed IR editing: it never renders preview
media or writes preview cache files. A live MLT SDL/OpenGL/shared-memory
consumer is out of scope until a later M4 decision.

Typical whole-file workflow remains: edit → `trigger_render` `mode=proxy`
(non-blocking by default) → poll `get_render_job` → user reviews → more edits
→ `final`.

**Token rule:** `trigger_render` defaults to **non-blocking** (`wait=false`).
Returns `job_id` immediately — poll with `get_render_job`. Pass `wait=true`
only when you must block.

**Assets rule:** `list_assets` hides Remotion rematerialized CAS by default.
Pass `params.include_derivatives: true` only when needed. Compact by default
(hash/filename/duration); pass `params.detail: true` for full metadata.

**Failure scripts:** Ignore any `.open_edit/tmp/` file marked
`FAILURE SCRIPT / RUINED SCRIPT`. Do not run them.

## Common recipes

### Ingest + put clips on timeline

1. `edit_project` `operation=ingest_local` with absolute paths
2. `query_project` `list_assets` → hashes + `duration_sec`
3. `edit_project` `operation=add_clip` with asset_hash / track / timing
4. `trigger_render` `proxy` (then `get_render_job`)

### Cut silence

1. `list_assets` / `get_transcript_packed`
2. `edit_project` `generate=silence_cuts` with `asset_hash`
3. If `retry: true` (no alignment yet), wait and retry — do not ffmpeg
4. `edit_project` `operation=apply_silence_gaps` with clip_id + gaps, then proxy

### Remotion title

1. `generate=init_remotion` → `write_remotion` → `generate=remotion`
2. `trigger_render` `proxy` (not `overlay`)

### Respond to review notes

1. `query_project` `get_pending_notes`
2. Edit / revert / re-render

## Hard rules (token savers)

- **No codebase tours** for editing tasks.
- **No guessed asset paths** — only hashes from `list_assets`.
- **No ffmpeg silence / melt DIY** when a pillar tool exists.
- **Do not invent tools** (`save_edl`, `qc_check`, etc. do not exist).
- On tool errors: read the message, fix params, retry.

## Related project skills

| File | Role |
|---|---|
| `skills/open-edit-mcp-reference.md` | IR ops + `run_script` recipes |
| `skills/tool_surface.md` | Longer pillar reference + mistakes |
| `skills/edit-planning.md` | Edit planning rules |
| `skills/remotion_motion.md` | Remotion vs HyperFrames |
| `skills/qc-standards.md` | Post-render QC |
| `skills/freeform_and_effects.md` | Catalog vs free-form escape |

MCP hosts can also fetch these via resources
`open-edit://skills/<name>` or prompts `open-edit-playbook` /
`open-edit-reference` (see MCP server).
