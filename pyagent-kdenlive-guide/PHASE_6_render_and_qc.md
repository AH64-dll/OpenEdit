# Phase 6 — Render & QC

## Context (recap)

Everything so far edits the project file; nothing so far produces watchable
video or checks that an edit actually looks right. This phase closes that
gap using the same token-efficiency principle the findings doc borrowed from
D-Ogi's design doc (§4): PyAgent itself should never handle full-resolution
frames, full audio waveforms, or GUI screenshots. It gets small,
text-and-thumbnail-sized signals; a human gets the real video. Depends on
Phase 2 (`EditorBackend`, for reading the current timeline state to render)
and reuses your existing `mlt-pipeline` render wrapper as its starting point
rather than writing a new one from scratch.

## Goal

Give PyAgent two things it currently can't do: turn the current project into
actual video (proxy or final), and sanity-check its own edits well enough to
catch obvious mistakes (a transition that didn't land, a clip that's silent
when it shouldn't be, a title that's off-screen) without a human having to
open Kdenlive every time.

## Render modes

Two modes, one underlying `render()` operation, exposed to PyAgent as a tool
the same way Phase 2's edit operations are:

- **`render(mode="proxy")`** — low-resolution, fast-encode pass (reuse the
  same `melt`/`ffmpeg` invocation pattern `mlt-pipeline` already uses for
  its own preview output, just pointed at the `.kdenlive` file's MLT
  structure instead of a bare `.mlt`). This is the `render --dry-run` output
  Phase 4 already promises the user: something to open in a normal video
  player to actually watch what changed, without waiting for a
  full-quality encode.
- **`render(mode="final")`** — full project settings (resolution, fps,
  codec) taken from the `.kdenlive` file's own `<profile>` element, not
  re-specified by PyAgent. This is the one that takes real time; PyAgent
  should say so before kicking one off, not launch it silently mid-
  conversation.

Both modes call `melt` directly, matching the "you're doing exactly what
Kdenlive's own renderer does, just without the detour through
`kdenlive_render`" observation from the findings doc (§1). Range-limited
renders (a specific clip or time window rather than the whole timeline)
should be supported from the start — most QC questions are about one recent
change, not the whole project, and re-rendering everything every time is
wasteful.

## QC tools — text and thumbnails only, never full frames

These are the "does this look right" tools PyAgent actually calls after a
render, modeled directly on the Must/Should-have QC items from D-Ogi's
MoSCoW list in the findings doc (§4):

- **`get_thumbnail(timestamp)`** — a single capped frame, ≤480px on the long
  edge, JPEG quality ~70. Enough for PyAgent to confirm "yes, there's a
  title card here" or "yes, this is a dissolve, not a hard cut" — not
  enough to burn tokens on, and not something a human needs either since
  they have the real proxy render for that.
- **`get_qc_crop(timestamp, region)`** — a small 1:1 pixel crop of a
  specific region at a specific time (e.g. "the lower-third where the title
  text sits"), for questions a downscaled thumbnail can't answer, like
  whether text is actually legible or a logo is where it should be.
- **`get_audio_levels(range)`** — numeric RMS/peak values (or a short
  waveform-as-list) over a time range, not a spectrogram image. Enough to
  answer "is this clip silent when it shouldn't be" or "did that crossfade
  duck the audio correctly" without any image at all.
- **`list_black_frames(range)` / `list_silence(range)`** — cheap, fully
  deterministic checks (frame-average luma near zero; audio RMS near zero)
  that don't need the LLM to look at anything — flag candidate problem spots
  first, and only pull a thumbnail or audio sample for the ones actually
  flagged. This keeps the common case (nothing's wrong) nearly free.

## The conversational QC loop

After an applied edit (or on request), PyAgent's flow should be: render a
ranged proxy around the change → run the deterministic checks first → only
pull a thumbnail/crop/audio sample for anything the deterministic checks
flagged or the user specifically asked about → report back in plain
language ("the crossfade between clips 2 and 3 completes cleanly around
00:13, no black frames, audio doesn't dip"). This mirrors Phase 3's
propose-then-apply pattern: cheap deterministic signal first, expensive/rich
signal only when something actually needs it.

## Explicit non-goals for this phase

- No continuous/streaming preview into the chat UI — Phase 4 already ruled
  this out; Phase 6 doesn't reopen it.
- No computer-vision content recognition ("does this clip contain a dog") —
  explicitly a Won't-have in D-Ogi's own MoSCoW list, and outside what a
  text-and-thumbnail-budget agent needs anyway.
- No broadcast-grade QC (waveform/vectorscope, loudness-standard
  compliance) — this is a sanity check for an indie project, not a delivery
  QC pass.
- Don't build a general video-analysis library — every tool above should be
  the smallest thing that answers one specific question PyAgent needs to
  ask.

## Acceptance criteria

- [ ] `render(mode="proxy")` on a project with at least one transition
      produces a file that opens and plays correctly in a normal video
      player, in well under the time a full-quality render would take.
- [ ] `render(mode="final")` uses the project's own profile settings
      (confirm resolution/fps in the output match the `.kdenlive` file's
      `<profile>`, not a hardcoded default).
- [ ] `list_black_frames`/`list_silence` correctly flag a
      deliberately-introduced problem (e.g. a clip with an accidental
      1-second gap) in a test project, and correctly report nothing on a
      known-good project.
- [ ] `get_thumbnail` and `get_qc_crop` both respect the size/quality caps
      above — verify actual output file size, don't just trust the encode
      settings.
- [ ] A full turn — "check that the last edit looks right" — results in a
      ranged render, deterministic checks, and a plain-language summary,
      without PyAgent requesting a full-resolution frame or the whole
      project re-rendered.

## Handoff to Phase 7

None directly — Phase 7 (the D-Bus fork track) is independent of rendering
and can proceed in parallel. If Phase 7 is adopted, this phase's render/QC
tools stay backend-agnostic either way, since they operate on rendered
output files, not on live editor state.
