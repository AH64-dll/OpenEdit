# Phase 3 — PyAgent Core (the actual agent)

## Context (recap)

Everything up to here has been deterministic. This phase is the one
non-deterministic piece — same role your `prompts/edl_writer.md` plays for
`mlt-pipeline`, except this is a live conversational loop instead of a single
batch prompt. Depends on Phase 1 (catalog) and Phase 2 (`EditorBackend`).

## Goal

A Python process that: takes a chat message, decides which of Phase 2's
operations (exposed as tools) to call, calls them, reports back in plain
language, and keeps going across turns while the project state accumulates.

## Model routing — reuse what you already have, don't rebuild it

You already run OpenClaw (Gemini Flash primary, local Qwen3:8b fallback via
Ollama) and separately drive `opencode` for coding tasks. Don't hardcode
PyAgent to a single provider — make the model a config value from the start,
for two independent reasons: first, whichever model plans *edits* doesn't
need to be the same one your coding agent uses to *build* PyAgent; second,
tool-calling reliability varies enough between models that you'll want to
swap and compare once this is running. If OpenClaw already has a clean
provider-swap abstraction, reuse it here instead of writing a second one.

## The loop

1. Build the system prompt: a short fixed description of what PyAgent is and
   its ground rules (below), plus a *filtered* slice of Phase 1's catalog
   relevant to the conversation so far (not the whole catalog every turn —
   see Phase 1's token-budget note).
2. Feed in: the running chat history, plus **current project state** from
   `get_timeline_summary()`/`get_project_info()` — call these fresh each
   turn rather than trusting the model's memory of a state that may have
   changed. LLM APIs are stateless between calls; don't let PyAgent quietly
   assume otherwise.
3. Let the model respond with either plain text or a tool call mapped onto
   Phase 2's operation API.
4. On a tool call: run it through Phase 2's `Validate` step first. If it
   fails, feed the `fix:`-hinted error back to the model and let it retry —
   cap retries (3, matching `edl_writer.md`'s own limit) and surface a clear
   failure to the user rather than looping forever.
5. On success: summarize what changed in plain language back to the user.

## Ground rules to put in the system prompt

Adapt these directly from `prompts/edl_writer.md`'s own hard prohibitions,
which already encode good judgment for this exact problem:

- Never touch the project file through any means except the operation API —
  no shelling out to `ffmpeg`/`melt` directly, no hand-editing XML.
- Every `effect_id`/transition type must come from Phase 1's catalog; if the
  user asks for something not in it, say so rather than inventing a
  plausible-sounding parameter name.
- State assumptions plainly when a request is ambiguous ("added a 1-second
  crossfade — say if you wanted something longer") rather than silently
  guessing and moving on.

## Propose-then-apply — the safety/UX pattern

This mirrors the EDL-approval-gate idea from your Pi extension design: for
anything beyond a trivial single-clip tweak, PyAgent should describe the
planned change in plain language (and, once Phase 2 exposes it, a
diff-style summary — "moves clip 3 from 00:12 to 00:18, adds a 1s dissolve
before it") **before** calling the operation that commits it, and wait for
confirmation. Make this a toggle (`auto_approve: bool` in config) rather than
hardcoded either way — good for fast iteration once you trust it, good for
safety while you don't.

## Explicit non-goals for this phase

- No UI yet — build and test this against a plain terminal loop first
  (`input()`/`print()` is genuinely fine for this phase's own testing). Phase
  4 wraps a real interface around the same core.
- Don't wire up Phase 6's render/QC tools yet unless trivial to stub — keep
  this phase's scope to editing operations.
- Don't build the D-Bus backend here — if Phase 7 happens, it's a second
  `EditorBackend` implementation slotted in later, not something this phase
  needs to anticipate beyond respecting the interface boundary.

## Acceptance criteria

- [ ] A terminal session where you type "add these two clips to the timeline
      with a crossfade between them" and PyAgent correctly calls
      `import_media` → `append_clip` (×2) → `add_transition`, in that order,
      confirming with you before applying if `auto_approve` is off.
- [ ] A deliberately invalid request (e.g. "trim this clip to 50 seconds" on
      a 10-second clip) triggers the `fix:`-hint retry path and either
      self-corrects or clearly reports failure — doesn't silently do the
      wrong thing.
- [ ] Calling `get_timeline_summary()` fresh every turn is verifiable in the
      code (not cached from an earlier turn).
- [ ] Model provider is a config value, not a hardcoded string.

## Handoff to Phase 4

Phase 4 needs: a way to send PyAgent a message and stream back its response
plus the pending-confirmation state (if `auto_approve` is off) — design this
phase's public interface as a small function/class Phase 4 can call into
directly (in-process) or wrap with a thin HTTP layer (out-of-process) without
having to change this phase's internals either way.
