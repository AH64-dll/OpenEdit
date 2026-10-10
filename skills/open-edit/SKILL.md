---
name: open-edit
description: >-
  Entry playbook for editing video with the Open Edit MCP tools (query_project,
  edit_project, run_script, trigger_render, get_render_job, cancel_render_job).
  Use for any Open Edit task: ingest, cut, silence removal, graphics, review
  notes, rendering. Load the linked reference skills only when needed.
---

# Open Edit playbook

The six MCP tools are the whole interface. Do not grep or read `open_edit/**`,
`node_modules/**` or vendor bundles to learn APIs; this skill set and the tool
errors are the contract. The project is pinned at server start; never pass
`project_path`.

## Workflow

1. **Readiness (once per session, or after any dependency error):**
   `query_project {query: get_readiness}`. Act on each `needs_setup[].fix`;
   don't guess install steps.
2. **Understand:** `list_assets` (paged, `offset`/`limit`), `get_pending_notes`,
   `get_style_profile {op_type: "AddClip"}`, `get_transcript_packed {asset_hash}`.
3. **Edit:** `edit_project` operations (see `open-edit-ops`). Use `run_script`
   only for ops no operation covers (move/split/transition/effect/raw MLT).
4. **Review:** `trigger_render {mode: proxy}` → poll `get_render_job {job_id}`
   until terminal; check `qc_report.passed` and `qc_report.complete`.
5. **Deliver:** `trigger_render {mode: final}` only after the user approves.

Read state before writing: asset hashes come from `list_assets`; clip and track
IDs from `get_editing_context {include_timeline: true}` (compact index). Writes
that take `expected_revision` need the current `graph_revision` from the last
read or write; on a stale-revision error, re-read and retry once.

## Defaults that matter

- **Silence:** `edit_project {generate: silence_cuts, generate_params: {asset_hash}}`
  then `operation: apply_silence_gaps`. Never run ffmpeg `silencedetect`.
- **Graphics:** Diffusion first (titles, shapes, lower thirds, animated text);
  HyperFrames only for advanced HTML/CSS/JS; Remotion is migration-only.
  See `open-edit-graphics`.
- **Stock before generate:** `search_assets` + `import_asset` before
  `generate: music|sfx|visual`.
- **Renders are async:** `trigger_render` returns `job_id`; one render at a time.

## Errors and recovery

| Response | Meaning → action |
|---|---|
| `error_code: missing_dependency` | Call `get_readiness`; report the `fix` to the user. |
| `status: retry` | Transcription/alignment still running (not a failure). Wait ~10 s, retry. |
| `error_code: stale_revision` / "stale graph revision" | Re-read `graph_revision`, re-apply once. |
| Render job `failed` | `get_render_job {job_id, include_details: true}`; fix the named op, re-render proxy. |
| "unknown operation/query" or unexpected key | Check `open-edit-ops`; never guess parameter names. |
| `lint.errors > 0` after `add_hyperframes_overlay` | Apply each `fixHint`, re-add the template. |

## Reference skills (load one only when the task needs it)

- `open-edit-ops`: every query, operation, generate kind and render option with exact params.
- `open-edit-editing`: cutting craft, effects/transitions catalog, QC checks and fixes.
- `open-edit-graphics`: Diffusion JSX grammar, HyperFrames contract, Remotion migration.
- `open-edit-review`: review notes, style memory, undo/redo/revert.

MCP hosts expose these as resources `open-edit://skills/<name>` and prompts.
