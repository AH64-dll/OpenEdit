# Render/QC Polish Pass — Design

**Date:** 2026-07-17
**Status:** approved
**Scope:** close gaps after Phases 3–6 ship, so the working system is
discoverable and the LLM can actually use the tools it has.

## Context

Phases 3, 4, 5, and 6 are all committed (commits `bc510c1`, `4cd0769`,
`563754a`, `0354f2a`). 98 tests pass. But:

- `phase3_pyagent_core/system_prompt.md` still describes the original 12
  edit tools. The LLM has no way to know about the 3 Phase 5 live-mode
  tools or the 6 Phase 6 render/QC tools, so it doesn't use them.
- The Phase 4 chat UI has 4 "quick action" buttons, but all of them just
  send LLM prompts. There's no way for a user to trigger a render or QC
  pass without phrasing it themselves.
- The Phase 6 README explains the render/QC tools, but there's no
  top-level `README.md` describing how the four phases fit together or
  how to actually run the system end-to-end.
- The only end-to-end test today is the Phase 4 WebSocket integration
  test, which uses a fake `pi` binary. Nothing exercises the real
  Phase 3 → Phase 6 path.

This polish pass closes those four gaps. It does not add new
functionality.

## Goals

1. The LLM knows about all 19 wired-up tools and uses Phase 5 live mode
   and Phase 6 render/QC when appropriate.
2. The chat UI exposes 4 quick actions that drive render + QC through
   the LLM.
3. A scripted smoke test exercises the full Phase 3 → Phase 6 pipeline
   without an LLM in the loop, asserting real artifacts.
4. A top-level README explains the system as a whole, lists the 19
   tools, and tells the reader how to run it.

## Non-goals

- No new tools, no new dependencies.
- No image rendering in the chat UI. When the LLM calls
  `pyagent_get_thumbnail`, the result is shown as text (the user opens
  the file in their OS viewer).
- No new WebSocket protocol messages, no new server endpoints.
- No changes to the Phase 4 chat UI's layout, styling, or
  state-panel shape.
- No re-architecture of the LLM/tool split.
- No Phase 7 (D-Bus fork) or Phase 8 (native dock) work. Both remain
  deferred.

## Design

### 1. `phase3_pyagent_core/system_prompt.md`

**Add to "Hard rules" section** (after the existing rules, before
"Available tools"):

> **Phase 5 live mode** — when `PYAGENT_LIVE=1` is set, three tools
> (`pyagent_import_media`, `pyagent_append_clip`,
> `pyagent_apply_effect`) apply via Kdenlive's D-Bus instead of the
> file backend, so the user sees the change without a reload. In a long
> session, prefer them. If a live call fails (Kdenlive not running, D-Bus
> unavailable), the extension falls back to file mode automatically —
> do not preemptively avoid them.
>
> **Phase 6 render + QC** — after any non-trivial edit, verify it. The
> cheap flow is:
> 1. `pyagent_render(mode="proxy", in_sec=X, out_sec=Y)` — render a
>    small range around the change. 640x360, sub-2s for a 4s clip.
> 2. `pyagent_list_black_frames(video)` and
>    `pyagent_list_silence(video)` — deterministic, runs on the
>    rendered video, returns spans.
> 3. `pyagent_get_audio_levels(video)` — numeric RMS + peak dB.
> 4. If anything is flagged, `pyagent_get_thumbnail(video,
>    timestamp_sec)` for a visual check. Output is capped at ≤480px
>    long-edge JPEG, q70, <250KB.
>
> Do not skip step 1 — a QC pass on the source clips tells you nothing
> about your edit; you have to render the *timeline* to see what your
> edit actually produces.

**Add to "Available tools (summary)"** (after the existing list):

> - `pyagent_render` — render the project (or a range) to MP4.
>   `mode="proxy"` (default) is fast; `mode="final"` uses the project
>   profile and is slow.
> - `pyagent_get_thumbnail` — extract a single capped JPEG frame.
> - `pyagent_get_qc_crop` — extract a cropped frame for legibility
>   checks.
> - `pyagent_list_black_frames` — deterministic black-frame check.
> - `pyagent_list_silence` — deterministic silence check.
> - `pyagent_get_audio_levels` — numeric RMS + peak dB.

**No other changes to the file** — the catalog slice mechanism and
template injection stay exactly as they are.

### 2. Phase 4 chat UI — 4 quick actions

**File:** `phase4_chat_ui/static/app.js`

**Change:** extend the `QUICK_ACTIONS` array at the bottom of the file
(currently 4 entries, lines 199–204) to 8 entries by appending 4 new
ones:

| Label | Prompt |
|---|---|
| "Render proxy" | `"Render a 640x360 proxy of the current project to /tmp/pyagent_proxy.mp4 and report the file size, duration, and elapsed render time."` |
| "Render final" | `"Render the project at full quality to /tmp/pyagent_final.mp4 using the project's own profile. This is slow — confirm the user is okay with it before proceeding."` |
| "Check QC" | `"Run the cheap deterministic QC checks (black frames, silence, audio levels) on /tmp/pyagent_proxy.mp4 over the full timeline and report any flags. If anything is flagged, pull a thumbnail for the affected timestamp and include it in the report."` |
| "Get thumbnail" | `"Pick a representative timestamp around the middle of the timeline and extract a thumbnail to /tmp/pyagent_thumb.jpg so the user can see what the project looks like right now."` |

**No other changes** to the chat UI. The 4 original quick actions stay
where they are. The new buttons are appended after them in the same
horizontal row (the existing CSS already handles wrapping).

The "Render final" prompt contains a self-check ("confirm the user is
okay with it before proceeding") because the LLM's existing rules
require a confirm step for slow or expensive operations. The LLM will
present a plan card; the user approves via the existing approve/reject
flow. This reuses the existing plan mechanism instead of inventing a
new "expensive op" UI.

### 3. End-to-end test — scripted pipeline smoke

**File:** `phase6_render_qc/test_e2e_pipeline.py` (new)

**What it does**, in order, all real (no mocks):

1. Copy the demo fixture (`phase3_pyagent_core/tests/fixtures/demo.kdenlive`)
   to a tempdir.
2. Use `phase3_pyagent_core.run_op` to:
   - `import_media` with the demo's existing source clip (idempotent
     check — verify the existing producer).
   - `append_clip` to add a second instance of the clip on track 0
     (extending the timeline by ~4s).
   - `add_transition` between the two clips (1s crossfade).
   - `save_project` to flush to disk.
3. Use `phase6_render_qc.render` to render a proxy of the result to a
   tempdir. Assert:
   - `rr.ok` is True.
   - Output file exists.
   - `ffprobe` shows `width=640 height=360 duration≈8s`.
4. Use `phase6_render_qc.list_black_frames` on the proxy. Assert result
   is well-formed (ok=True, spans is a list — content is implementation-
   defined).
5. Use `phase6_render_qc.list_silence` and
   `phase6_render_qc.get_audio_levels` similarly. Assert each returns
   the documented shape.
6. Use `phase6_render_qc.get_thumbnail` at `t=4.0s` (the transition
   midpoint). Assert: file exists, JPEG magic bytes, file_bytes <
   250_000, max(width, height) ≤ 480.

**Skip conditions** (in addition to existing skipif for melt/ffmpeg):

- Skip if the demo fixture is missing.

**Expected runtime:** <15 seconds on a developer machine.

**This is not a unit test** — it requires melt, ffmpeg, ffprobe, and
the demo fixture to all be present. It will be run by
`make test` in `phase6_render_qc/` along with the other Phase 6 tests.

**No real LLM test** — that would require network, an API key, and
flaky model output. A real pi session will be run manually by the
developer (or by a CI job in a future iteration) and its results
documented in `docs/phase6-e2e-results.md`. That manual run is
out of scope for this design.

### 4. Top-level README

**File:** `pyagent-kdenlive-guide/README.md` (new)

**Sections** (in this order, ~150 lines total):

1. **One-paragraph summary** — what the project is, that it's a
   `.kdenlive`-editing AI assistant built on the `pi` agent harness,
   and the 4 working phases.
2. **Architecture diagram** — ASCII box-and-arrow showing
   LLM → pi extension → Phase 3 backend → `.kdenlive` file
   (file mode) and Phase 5 D-Bus bridge (live mode, opt-in via
   `PYAGENT_LIVE=1`). Phase 4 chat UI on the left as a WebSocket
   front-end to the same extension. Phase 6 render/QC as a
   downstream consumer of the project file.
3. **Quickstart** — exact commands to:
   - `pip install -e` all 5 working packages
     (phase1, phase2, phase3, phase4, phase5, phase6).
   - Set `PYAGENT_PROJECT=/path/to/project.kdenlive`.
   - (Optional) Set `PYAGENT_LIVE=1` for live-mode D-Bus.
   - Run `python -m phase4_chat_ui` (or document the actual entry
     point — confirm during implementation; if there's no top-level
     entry, document each phase's separately).
   - Open `http://localhost:<port>`.
4. **Tool reference** — a single table of all 19 tools, columns:
   name, phase, one-line description, live-mode-eligible. Highlight
   the 3 live-capable tools.
5. **Testing** — one line per phase's test command.
6. **Limitations** — file-mode edits require reload unless
   `PYAGENT_LIVE=1`; QC is sanity-check only; no broadcast-grade QC;
   no native dock.
7. **Stretch (deferred)** — Phase 7 (D-Bus fork) skipped because
   upstream Kdenlive already exposes the methods we need (Phase 5's
   spike confirmed); Phase 8 (native dock) deferred until the system
   is in real use.

**No content is copied verbatim from per-phase READMEs** — the top
README is the single entry point. Per-phase READMEs stay detailed;
the top README links to them where appropriate.

## Files touched

| File | Action | Approx lines |
|---|---|---|
| `phase3_pyagent_core/system_prompt.md` | edit (insert 2 paragraphs, 6 tool entries) | +20 |
| `phase4_chat_ui/static/app.js` | edit (extend `QUICK_ACTIONS` array) | +6 |
| `phase6_render_qc/test_e2e_pipeline.py` | new | +90 |
| `pyagent-kdenlive-guide/README.md` | new | +150 |

## Acceptance

- [ ] `system_prompt.md` contains the new Phase 5 / Phase 6 paragraphs
      and tool list.
- [ ] Chat UI shows 8 quick-action buttons; clicking the 4 new ones
      sends the right prompt and the LLM (with a real model) calls the
      expected Phase 6 tool.
- [ ] `python3 -m unittest discover -s phase6_render_qc -p "test_*.py"`
      runs the new e2e test plus the existing 23, all pass in <20s
      total.
- [ ] `pyagent-kdenlive-guide/README.md` exists and the quickstart
      commands run end-to-end on a clean checkout.
- [ ] All existing tests still pass: 98 + 1 new e2e = 99 total.
- [ ] Single commit `[polish][docs+ui] wire render/QC into LLM prompt,
      add quick actions, e2e test, top-level README` (or two if the
      README is large enough to deserve its own commit).

## Out of scope (explicit)

- Image rendering in the chat UI transcript.
- A real-LLM e2e test (network + model flake; manual-only).
- Phase 7 (D-Bus fork) and Phase 8 (native dock).
- New WebSocket protocol messages, new server endpoints, new tools.
- Re-architecture of the LLM/tool split.
- Per-phase README updates (the existing ones are already detailed;
  only the top-level README is missing).
