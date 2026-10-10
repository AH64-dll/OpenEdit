---
name: open-edit-review
description: >-
  Act on Open Edit review notes placed in the Review Studio, capture and reuse
  the user's style preferences, and undo, redo or revert edits safely. Load when
  the user mentions notes, feedback at a timecode, preferences, or undo.
---

# Review notes, style memory, history

## Review notes

Notes are the human → agent channel; the Review Studio (`open_edit serve`)
writes them. Read with `query_project {query: get_pending_notes, params: {}}`
(`summary_only: true` for a short list).

Each note has `text`, `anchor.t_start` / `anchor.t_end` (timeline seconds),
`anchor.track_kind` (`video`, `audio` or `any`) and optional `anchor.track_id`.
`track_kind` is a hint about where the reviewer looked: prefer audio ops for
audio notes about sound, but fix picture or audio, whichever the text asks for.

1. Read pending notes before guessing what the user meant.
2. For each note, make the smallest edit at its time range that satisfies the text.
3. Re-render (`proxy`, or `preview-chunks` for the range) so the reviewer can verify.
4. Don't invent, dismiss or edit notes; users delete obsolete ones in the UI.

## Style memory

- Before planning, read `get_style_profile {op_type}` with a PascalCase type:
  `AddClip`, `TrimClip`, `MoveClip`, `RemoveClip`, `AddTransition`, `AddEffect`,
  `SetKeyframe`, `SetAudioGain`, `NormalizeAudio`, `GroupEdits`, `RawMltXml`,
  `FreeFormCode`. Honor pinned values and high-confidence categories.
- When the user clearly states (or confirms) a preference:
  `edit_project {operation: capture_style_hint, params: {category, hint, key?,
  value?, confirmed: true}}`. Categories: `pacing`, `transitions`, `fades`,
  `color`, `audio`, `text_captions`, `visual_treatment`, `export`,
  `corrections`, `other`. Ask once if it's ambiguous; never persist unconfirmed hints.
- Hard overrides (aspect ratio, target duration): `set_pinned_value {key, value}`.
- Mention applied preferences briefly ("using your 9:16 pin"). Don't invent a
  profile or overwrite pins without a new explicit preference.

## Undo, redo, revert

- `get_history {limit?}` returns `graph_revision` and the next `undo`/`redo` action.
- `edit_project {operation: undo|redo, params: {expected_revision}}` reverses one
  complete action. A new edit clears the redo branch.
- `revert_request {request_id, expected_revision, preview: true}` previews
  undoing everything one request did while keeping unrelated later work; run
  again without `preview` to apply. It reports conflicts instead of overwriting.
- Writes that accept `request_id` (`apply_studio_changes`, `apply_graphics_edits`,
  tracking operations) should share one per user request, so it reverts as a unit.
