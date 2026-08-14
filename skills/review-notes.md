---
name: review-notes
description: >-
  Place, edit, delete, and act on Open Edit timeline review notes from the
  Review Studio UI or MCP. Use when the user asks the agent to fix something
  at a timecode, including audio-targeted notes.
---

# Review notes

Review notes are the human → agent feedback channel. The UI writes them;
MCP agents read them with `query_project` / `get_pending_notes` and apply
fixes with `edit_project` / `run_script`.

## Do not explore source

Use tools. Notes live in the project `notes.db` and are already exposed.

## Read pending notes

```json
{ "query": "get_pending_notes", "params": {} }
```

Each note includes:

- `text` — what the reviewer wants changed
- `anchor.t_start` / `anchor.t_end` — timeline seconds
- `anchor.track_kind` — `video` | `audio` | `any`
- `anchor.track_id` — optional concrete track id

`track_kind` is a hint about where the reviewer was looking. You may still
change **either** audio or picture from the same note when the text asks for
it. Prefer audio ops when `track_kind=audio` and the note is about sound.

## UI capabilities (Review Studio)

- **Add note** at playhead (`Note`)
- **Add audio note** at playhead (`Audio note`) or double-click an audio track
- **Edit** / **Delete** notes from the Notes modal
- Notes appear as timeline markers (audio notes are green)

## Agent workflow

1. `get_pending_notes`
2. For each note: seek mentally to `t_start`, apply the smallest edit that
   satisfies the text
3. Prefer structured `edit_project` ops; use `run_script` only when needed
4. Re-render proxy / preview-chunks so the Review Studio can verify
5. Do not invent notes; only act on pending ones unless the user says otherwise

## Editing / deleting notes

Harnesses and the Review UI may PATCH / DELETE
`/api/projects/{id}/notes/{note_id}`. Agents normally **act** on notes rather
than editing them. If a note is wrong or obsolete, the user deletes it in the
UI; do not silently dismiss pending notes.
