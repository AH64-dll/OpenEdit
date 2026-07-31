# Style memory

Capture and reuse the user's editing preferences so later turns need less
re-explanation. Prefer tools over inventing style.

## When to load

- At the start of an editing session (with the MCP playbook).
- Whenever the user states taste: pacing, transitions, aspect ratio, music,
  captions, color, silence policy, export format.

## Read before planning

1. Call `query_project` with `query=get_style_profile` and an `op_type`
   matching the work ahead (e.g. `AddClip`, `AddTransition`, `AddEffect`).
2. Honor `<pinned>` and high-confidence categories in the returned slice.
3. The serve agent also injects a `<prior_state>` block; treat pins and
   corrections as hard preferences.

## Capture confirmed hints

When the user clearly states a preference (or confirms your paraphrase):

```text
edit_project
  operation=capture_style_hint
  params={
    "category": "pacing" | "transitions" | "fades" | "color" | "audio" |
                "text_captions" | "visual_treatment" | "export" | "corrections" | "other",
    "hint": "short preference text",
    "key": "optional.dot.path",   # if set, also pins this key
    "value": "optional pin value",
    "confirmed": true             # must be true to persist
  }
```

Rules:

- **Confirm before persist.** If the preference is ambiguous, ask once;
  only call with `confirmed=true` after yes / an unambiguous statement.
- Use `set_pinned_value` for hard overrides (`aspect_ratio`, durations).
- Use `capture_style_hint` for free-text memories and corrections.
- Do **not** silently learn every chat phrase.

## Reuse later

- Re-read `get_style_profile` before generate modes (visual / music / sfx).
- Prefer stock search that matches pinned mood/aspect before generating.
- Mention applied style briefly ("using your 9:16 pin") so the user can correct.

## Do not

- Invent a style profile when none exists.
- Overwrite pins without an explicit new preference.
- Dump the full profile into every reply — keep user-facing text short.
