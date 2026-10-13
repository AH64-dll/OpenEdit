# Open Edit

Choose the edits; Open Edit handles media processing, timing and project storage.
The server is pinned to one project and needs no provider API key.

Six composable tools:

- `query_project`: state, media and capability help.
- `edit_project`: direct edits or atomic batches.
- `run_script`: trusted Python for complex IR edits.
- `trigger_render`: range previews and final export.
- `get_render_job`: status and optional diagnostics.
- `cancel_render_job`: stop obsolete work.

Inspect only the information the task needs. `get_editing_context` gives selected
clips, timed marks, a selected video region and the graph revision.
`list_assets` gives compact media metadata. `inspect_media` returns a timestamped
contact sheet and range transcript; narrow the source range to investigate an
event, use more frames for detail, or set frames=0 for text only. Visual samples
are cached by source identity. Uniform samples are not scene boundary detection.

Use `query_project` with query=`describe`, params={name:"trim_clip"} to fetch
operation parameters. Omit name for available capabilities; name="ir" lists the
Python editing API. Specialized help loads only when requested.

Edit directly, or use operation=`apply_studio_changes` with expected_revision,
changes, ops and label to commit related edits as one undoable action. On a stale
revision, inspect the changed state before retrying. Undo/Redo operate on actions;
media remains available for reopening and recovery.

`trigger_render` with mode=`preview-chunks` and ranges=[{start_sec,end_sec}] checks
only relevant dirty timeline ranges. Unchanged chunks stay cached.
Mode=`proxy` is a whole-file preview. Video and audio artifacts are independent;
playback uses sequential chunks and keeps the checked same-range fallback while updating. Mode=`final`
exports original media at full quality. Poll the returned job_id and verify the
completed result before reporting an export. The application handles rendering;
there is no mandatory full proxy render between edits.

Editable titles, shapes and animation use the graphics worker. Advanced HTML
and legacy Remotion engines are optional compatibility paths. Existing graphs
remain replayable. Keep scene timing and audio synchronization inside the engine.

Optional specialized queries (transcription, silence_cuts suggestions, object
tracking, stock media, style preferences) are available through capability help.
Use whichever improves the requested edit; no fixed editing sequence is required.
