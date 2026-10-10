---
name: open-edit-ops
description: >-
  Exact parameters for every Open Edit MCP query, edit operation, generate kind,
  render option and run_script IR method. Load when you need a parameter name,
  a return shape, object tracking, studio changes or a run_script recipe.
---

# Open Edit operations reference

Shapes: `query_project {query, params}`, `edit_project {operation, params}` or
`edit_project {generate, generate_params}`, `run_script {code, timeout_sec}`,
`trigger_render {mode, ...}`, `get_render_job {job_id, include_details}`,
`cancel_render_job {job_id}`. Use only the keys listed (graphics, studio and
tracking operations reject others); `project_id` is injected.

## Queries (`query_project`)

| query | params | returns |
|---|---|---|
| `get_readiness` | `detail?` | capabilities, `needs_setup[{name,fix,found}]` |
| `list_assets` | `offset?`, `limit?` (50, max 500), `detail?`, `include_derivatives?` | `hash`, `filename`, `duration_s`; `next_offset` |
| `get_transcript_packed` | `asset_hash`, `offset?`, `limit?` (500 words, max 2000), `pause_threshold_sec?` | phrase-packed words with silence markers |
| `get_silence_gaps` | `asset_hash`, `threshold_ms?`, `keep_breath_ms?`, `min_segment_s?`, `include_fillers?` | silence + filler spans |
| `get_timeline_view` | `asset_hash` or `path`, `start_sec`, `end_sec`, `n_frames?`, `width?` | PNG path (filmstrip+waveform+words) |
| `analyze_narrative` | `asset_hash` | rule-based segments with `gap_after_s` (heuristic) |
| `search_assets` | `query`, `kind?`, `role?`, `license?`, `limit?` | stock results to `import_asset` |
| `get_pending_notes` | `summary_only?` | review notes (see `open-edit-review`) |
| `get_style_profile` | `op_type`: `AddClip`, `TrimClip`, `MoveClip`, `RemoveClip`, `AddTransition`, `AddEffect`, `SetKeyframe`, `SetAudioGain`, `NormalizeAudio`, `GroupEdits`, `RawMltXml`, `FreeFormCode` | style slice |
| `get_editing_context` | `selected_ids?`, `annotation_ids?`, `document_id?`, `region?`, `playhead_sec?`, `section?`, `offset?`, `limit?` (20), `include_timeline?`, `include_source?` | targeted context; `include_timeline` adds a compact track/clip index |
| `get_studio` | `kind?`, `object_id?`, `include_source?` | full studio objects (fetch before replacing one) |
| `get_history` | `limit?` (20, max 100) | `graph_revision`, next `undo`/`redo`, recent actions |
| `get_graphics_view` | `clip_id?`, `include_source?` | Diffusion graphics source/revision/`worker_ready` |
| `get_authoring_view` | `include_source?` | Diffusion media JSX view |
| `get_tracking_job` | `job_id` | tracking status + compact motion summary |

## Edit operations (`edit_project operation=…`)

| operation | params |
|---|---|
| `ingest_local` | `paths` (absolute), `transcribe?` |
| `import_asset` | `result_id` or `source_url`, `provider`, `license`, `attribution`, `source_page_url` (from `search_assets`) |
| `add_clip` | `asset_hash`, `track_id`, `position_sec`, `in_point_sec`, `out_point_sec` (required), `track_kind?` (`video`/`audio`) |
| `trim_clip` | `clip_id`, `in_point_sec?`, `out_point_sec?` |
| `remove_clip` | `clip_id` |
| `replace_clip_source` | `clip_id`, `new_asset_hash` |
| `change_clip_speed` | `clip_id`, `rate` |
| `set_audio_gain` | `clip_id`, `gain` (linear, 0 = mute) or `gain_db` |
| `apply_silence_gaps` | `clip_id`, `gaps[{t_start,t_end}]`, `padding_ms?`, `snap_to_words?`, `snap_tolerance_ms?` |
| `auto_color_grade` | `preset?` (`auto`, `subtle`, `neutral_punch`, `warm_cinematic`, `none`), `clip_ids?`, `params?` (`contrast`/`gamma`/`saturation` overrides) |
| `add_marker` | `t_start`, `t_end?`, `text` |
| `set_pinned_value` / `capture_style_hint` | see `open-edit-review` |
| `add_hyperframes_overlay` | `template_path` (inside project), `position_sec`, `duration_sec`, `variables?` (JSON); returns `lint` |
| `apply_generated_ops` | `ops`: IR op dicts returned by `generate` |
| `apply_graphics_edits` | `expected_revision`, `document_id`, `edits`, `request_id?`, `label?` |
| `apply_studio_changes` | `expected_revision`, `changes[{kind,object_id,data}]`, `ops?`, `request_id?`, `label?` |
| `commit_graphics` | `job_id`, `expected_revision`, `clip_id?`, `track_id?`, `position_sec?` |
| `rewrite_graphics_source` | `source`, `edits`, `expected_revision` (draft only, no graph change) |
| `apply_authoring_edit` | `expected_revision`, `source` or `edits` |
| `retime_asset` | `asset_hash`, `source_in?`, `source_out?`, `playback_rate?` or `segments[{source_in,source_out,rate}]`, `fps?` |
| `undo` / `redo` | `expected_revision` |
| `revert_request` | `request_id`, `expected_revision`, `preview?` |
| `start_tracking` | `expected_revision`, `clip_id`, `region`, `direction?` (`forward`/`backward`/`both`), `target_mode?` (`foreground`/`region`), `start_sec?`, `end_sec?`, `object_id?`, `request_id?` |
| `apply_tracking_job` | `expected_revision`, `job_id`, `request_id?` |
| `cancel_tracking` | `job_id` |
| `edit_object_track` | `expected_revision`, `object_id`, `edits`, `request_id?`, `label?` |

Studio change kinds: `document` `{source,clip_id,track_id,duration_sec,fps,label}`,
`caption` `{text,start_sec,end_sec,style,enabled,locked}`, `style` `{label,caption_style}`;
`data: null` deletes. Use one `request_id` for all writes of one user request.

Object tracking: boxes are normalized 0–1 in the original source image; times
are original-source seconds; analysis covers at most 300 s. `edit_object_track`
edits: `{action:"properties",values:{label,enabled,locked}}`,
`{action:"set_frame",frame:{time_sec,x,y,width,height,valid}}`,
`{action:"remove_frame",time_sec}`, `{action:"add_effect",effect:{effect_id,kind}}`
(kinds `highlight`, `label`, `cover`, `blur`, `pixelate`),
`{action:"update_effect",effect_id,values}`, `{action:"remove_effect",effect_id}`.
Lost samples disable effects until corrected or retracked.

## Generate (`edit_project generate=…`)

Returns suggested ops; commit with `apply_generated_ops` (or `apply_silence_gaps`).

| generate | generate_params |
|---|---|
| `silence_cuts` | `asset_hash`, `threshold_ms?`, `keep_breath_ms?` (600), `min_segment_s?` (2.0), `compress?` |
| `music` | `asset_hash`, `library_path?` |
| `sfx` | `asset_hash`, `library_path?`, `music_downbeats?` |
| `visual` | `asset_hash`, `template`, `beat_type?`, `params?` |
| `remotion`, `init_remotion`, `write_remotion` | legacy migration only; do not create new ones |

## Render (`trigger_render`)

| field | values |
|---|---|
| `mode` | `proxy` (640x360 whole-file review MP4), `final` (canonical originals), `preview-chunks` (range cache), `graphics` (Diffusion JSX → CAS, no graph change), `overlay` (legacy) |
| `wait` | default `false` → returns `job_id`; poll `get_render_job` |
| `expected_revision` | refuse to render a newer/older graph than you reviewed |
| `encoder` | `gpu` (default; probes NVENC/QSV/AMF, falls back to libx264) or `cpu` |
| `quality` | `fast`, `standard`, `high`, `archival` |
| `codec` | `h264`, `hevc`, `av1` |
| `crf` (0–51), `vb` (`10M`), `preset`, `scale` (`1280x720`), `profile` | encoder overrides; omit unless asked |
| `ranges`, `media`, `priority` | preview-chunks only: `[{start_sec,end_sec}]`, `video`/`audio`/`both`, `interactive`/`background` |
| `graphics` | graphics only: `{source, duration_sec, fps}` plus `expected_revision` |

`preview-chunks` results are a manifest of sequential self-contained MP4
chunks, not one file: green = current, yellow = an exact same-range older
artifact plays while it re-bakes, red = nothing usable. Video and audio planes
are independent. The job result's `qc_report` has `passed` and `complete`;
`complete=false` means checks were skipped or timed out, so it is not proof.
`diagnostics.profile.encoder_vcodec` is the codec actually used.

## run_script

Python builds ops through a preloaded `ir` object; the version header is
injected. The script cannot read project state and its prints are not
returned; fetch IDs first. Result: `ops_appended`, `ops_summary`, `graph_revision`.

```python
ir.move_clip("<clip_id>", "<track_id>", 12.0)        # clip_id, new_track_id, new_position_sec
left, right = ir.split_clip("<clip_id>", 30.0)       # returns both new clip IDs
ir.add_transition("<clip_a_id>", "<clip_b_id>", "dissolve", 0.5)
ir.add_effect("clip", "<clip_id>", "audio_fade_out", {"duration": 1.0})
```

`ir` methods (one per IR op kind): `add_clip`, `trim_clip`, `move_clip`,
`remove_clip`, `split_clip`, `slip_clip`, `ripple_delete_clip`,
`duplicate_clip`, `replace_clip_source`, `change_clip_speed`,
`set_clip_speed_ramp`, `set_clip_properties`, `set_track_properties`,
`remove_track`, `add_transition`, `remove_transition`,
`set_transition_property`, `add_effect`, `remove_effect`, `set_effect_param`,
`control_effect`, `set_keyframe`, `remove_keyframe`, `set_audio_gain`,
`normalize_audio`, `group_edits`, `ungroup_edits`, `add_html_overlay`,
`remove_html_overlay`, `raw_mlt_xml`, `free_form_code`. Captions, graphics
sources and object tracks change through `apply_studio_changes` and the
tracking operations, not `run_script`.
