# REVIEW PACK — changes applied in this pass

This folder is an annotated copy of the skills / tools the editing
agent (Pi / Minimax M3) used while attempting the "professional YouTube
edit" brief. The previous revision left review notes inline; this
revision applies the fixes and removes the inline review annotations.

The goal of this pass was a *correct, coherent* skill / tool surface
that an editing agent can actually rely on — fixing correctness bugs,
resolving cross-skill conflicts, and aligning the skills with the real
Open Edit pipeline (EditGraph + IR ops + 4-pillar tools). No new
"weird functions" were added: the LLM path in `narrative_analyzer`
remains a documented stub, and cursor-following zoom remains
explicitly impossible.

## File index

| File | What it is | What changed in this pass |
|---|---|---|
| `edit-planning.md` | Agent skill `edit-planning` | Re-anchored to the real pipeline (EditGraph + IR + 4-pillar tools). Dropped phantom `FootageManifest` / `save_edl` / `RenderSettings` / `qualityFlags` / `musicBrief` / `captionsEnabled`. Replaced the blanket ">2s silence → cut" rule with sense-boundary guidance (cut on sentence/breath boundaries, keep breaths <600ms, no sub-2s fragments). Lifted the dissolve ban — dissolve IS supported by the catalog. Added a section covering the real effect catalog and the free-form escape hatch (`RawMltXmlOp` / `FreeFormCodeOp`) for zoom / denoise / compression / fades. Documented that cursor-following zoom is impossible. |
| `qc-standards.md` | Agent skill `qc-standards` | Replaced phantom tools (`qc_check`, `save_edl`, `generate_captions`, `state.json` / `JobState.stage`, "Ingest/Plan/Enrich/Compose" stages, `xfade`) with the real `trigger_render` → `open_edit render --mode {proxy,final,overlay}` flow. Clarified that silence cuts re-time A/V together via clip `inSec`/`outSec`, so `audio_sync` holds by construction (removed the contradictory "no silenceremove" claim). Added real-world failure modes: asset-reference failures at append, untranscribed assets, stale server code, over-aggressive cut density. |
| `silence_cutter.py` | Internal skill | Added leading (`[0, first.t_start]`) and trailing (`[last.t_end, asset_duration]`) silence detection. Added a policy layer in `propose_cuts`: breath-keep (`keep_breath_ms=600`), tiny-fragment merge (gaps separated by a sub-`min_segment_s` speech fragment are merged into one wider cut), and boundary min-segment protection (leading/trailing cuts that would leave a sub-min fragment are dropped). Defaults tuned to prevent the ~2s-fragment over-cutting observed in the field. Documented that filler-word / semantic removal is out of scope (needs transcript-text analysis). |
| `narrative_analyzer.py` | Internal skill | Replaced fixed 5s-window segmentation with sentence-aligned segmentation (splits at terminal punctuation `.!?` or inter-word pauses ≥350ms). Beat labels are now honestly documented as POSITIONAL heuristics (first → hook, second → turn, third → scope, last → button, else → mechanism), not semantic classifications. `cost` and `tease` are reserved for the future LLM path and not emitted by the rule-based path. Removed the `_analyze_with_llm` private stub; `use_llm=True` now routes to the rule-based path with a clear warning (the LLM path is still NOT implemented — adding it would be a "weird function" outside this pass). Default `use_llm` changed from `True` to `False` to match the wrapper. Added `gap_after_s` field on `NarrativeSegment` so the agent can pick cut boundaries without re-querying the alignment. |
| `pyagent_propose_silence_cuts.py` | Tool wrapper | Fixed the misleading "Whisper not run?" error: the response now includes `"retry": True` and an explicit hint that server-side transcription may still be in progress, with an instruction NOT to fall back to raw ffmpeg. Documented the wrapper as the PREFERRED way to find silence gaps (over hand-rolled `ffmpeg silencedetect`). Exposed `keep_breath_ms` and `min_segment_s` as optional args. Added `asset_hash` validation. |
| `pyagent_analyze_narrative.py` | Tool wrapper | Aligned the `use_llm` default with the skill (`False`). Same `retry: True` fix on no-alignment. Added a schema / example in the docstring so the agent doesn't need a failed call to learn the required params. Documented that `use_llm=True` is currently a no-op. |
| `freeform_and_effects.md` | Reference doc (not a skill) | Converted from review notes into a clean agent-facing reference for the structured effect catalog vs the free-form escape hatch. Includes the "when to escape" table, the explicit list of what the catalog CANNOT express (denoise / compressor / fade / zoom), the cursor-follow impossibility, and the validation-gap dry-run workflow. |
| `tool_surface.md` | Reference doc (not a skill) | Converted from review notes into a clean 4-pillar tool reference. Documents `query_project` sub-queries with required params, `edit_project` mutations + `generate` options, `run_script` escape hatch, `trigger_render` modes. Adds the priority order and a "common mistakes" section capturing the failures the agent actually hit (hand-rolled ffmpeg, guessed asset paths, premature "no transcript", skipped style-profile / pending-notes calls). |
| `REVIEW.md` | This file | Replaced the reviewing-AI instructions with this changelog. |

## What was deliberately NOT done

To stay inside the "no weird functions, no hallucination" guardrail:

- The LLM path in `narrative_analyzer.analyze(use_llm=True)` was NOT
  implemented. It remains a documented stub that warns and falls back
  to the rule-based path. Implementing it would require a real LLM
  call and a prompt + parser, which is a new feature, not a fix.
- Cursor-following zoom was NOT added. The `Asset` model has no
  pointer-track telemetry, so it would be fiction. The skills now
  explicitly say so and offer keyframed affine zoom instead.
- No new first-class catalog effects (`afftdn.yaml`, `acompressor.yaml`,
  `afade.yaml`) were added. The skills now point the agent at
  `RawMltXmlOp` for these, which is the existing escape hatch.
- The free-form validation gap (ops bypass the reference check) was
  documented + a dry-run workflow was added, but no new validation
  layer was inserted. Adding one would change sandbox_bridge behavior
  beyond the scope of this pass.

## How to verify

From the `open_edit/` package:

```
.venv/bin/python -m pytest tests/ -q
```

For agent-facing behavior, exercise `query_project` / `edit_project` /
`run_script` against a project under `OPEN_EDIT_PROJECTS_ROOT` with
`OPEN_EDIT_SANDBOX_BACKEND=dev` (the dev backend runs free-form
unsandboxed).

## Resolution log (implemented)

The following fixes were implemented and installed over the originals:

- **`silence_cutter.py`** (`open_edit/agent/skills/`): now detects leading &
  trailing silence and merges gaps separated by speech shorter than
  `min_segment_s`. Added regression tests (leading/trailing/merge). Full
  suite: 976 passed.
- **`pyagent_propose_silence_cuts.py`** (`open_edit/agent/tools/`): "no
  alignment" error now suggests retrying (background transcription may still
  be running) instead of implying Whisper is missing; passes `min_segment_s`.
- **`pyagent_analyze_narrative.py`** (`open_edit/agent/tools/`): same improved
  "no alignment" error; docstring states the LLM path is a stub.
- **`narrative_analyzer.py`** (`open_edit/agent/skills/`): docstring/module
  note now honestly states the LLM path is unimplemented and beat types are
  positional heuristics.
- **`edit-planning.md`** (installed to
  `/home/ah64/Documents/video editing/pi-video-editor/skills/`): added
  legacy-status warning, corrected the dissolve ban (dissolve IS supported),
  and reframed ">2s silence" as a *candidate* cut on sense boundaries.
- **`qc-standards.md`** (installed to
  `/home/ah64/Documents/video editing/pi-video-editor/skills/`): added
  legacy-status warning; corrected the `audio_sync` note (silence cuts re-time
  A/V together via clip in/out).

**NOT yet implemented** (still suggested only): first-class catalog effects for
denoise (`afftdn`) / compression (`acompressor`) / fades (`afade`). These remain
achievable only via `RawMltXmlOp`/`FreeFormCodeOp`. `freeform_and_effects.md`
and `tool_surface.md` are review docs with no original to replace; they remain
here as reference.
