# §2 Verification Memo — Phases 0-3 Creation Pipeline Audit

**Date:** 2026-07-20
**Auditor:** Phase 4 design review
**Status:** GATE OPENED — all three creation-pipeline items are **missing** from Phases 0-3
**Result:** **Phase 4.5 is in scope.** All five creation skills (§4.1-§4.5) must be built.

---

## §2.1 — Narrative story-beat segmentation

**Question:** Does any existing skill take a transcribed clip and return structured `{beat_type, t_start, t_end, text, suggested_visual_concept}` segments, with the seven beat types (hook, turn, scope, mechanism, cost, tease, button)?

**Answer: NO.**

**Evidence:**

| Search | Files matched |
|---|---|
| `beat_type` literal in any source file | 0 (matches only in `pygments` lexer test fixtures) |
| `narrative` keyword in any source file | 0 in `open_edit/` and `pyagent-kdenlive-guide/` source |
| `story_beat` keyword in any source file | 0 |
| `suggested_visual_concept` field anywhere | 0 |
| `hook/turn/scope/mechanism` enum values | 0 |

**No IR op type** in `open_edit/open_edit/ir/types.py` (lines 26-189, 12 op types) accepts a beat_type. No tool in `pyagent-kdenlive-guide/phase3_pyagent_core/tools/*.py` (38 tools) processes transcripts into beats. The LLM (any OpenCodeGo model) has no way to produce or consume narrative beat structure today.

**§4.1 implication:** Full build required — `open_edit/agent/skills/narrative_analyzer.py` + new tool `pyagent_analyze_narrative`. Depends on §4.2 for word-level alignment input.

---

## §2.2a — Word-level transcription at asset ingestion

**Question:** Does any ingestion path produce word-level timestamps (Whisper / faster-whisper / equivalent)?

**Answer: NO.**

**Evidence:**

| Search | Files matched |
|---|---|
| `whisper` keyword in any source file | 0 in `open_edit/` and `pyagent-kdenlive-guide/` (matches only in venv site-packages) |
| `faster.whisper` keyword | 0 |
| `ctranslate2` keyword | 0 |
| `alignment` field on `Asset` model | 0 |
| `Asset.alignment` attribute | 0 — `Asset` has only `asset_hash, original_path, stored_path, type, duration_sec, fps, width, height, codec, has_audio` (`open_edit/open_edit/storage/assets.py:90-150`) |
| `AssetStore.ingest()` calls anything other than `ffprobe` | 0 — only `_probe_media(str(src))` is called (`open_edit/open_edit/storage/assets.py:107-115`) |

**Current state:** `AssetStore.ingest()` (`open_edit/open_edit/storage/assets.py:90-120`) does only:
1. SHA-256 hash → CAS copy
2. `_probe_media()` → ffprobe metadata (duration, fps, codec, has_audio)

No transcription. No word-level alignment. No segment boundaries.

**Pyproject deps** (`open_edit/pyproject.toml:6-9`): `pydantic>=2.0, pyyaml>=6.0, lxml>=5.0`. Dev deps: `pytest>=7.0, pytest-cov>=4.0`. No `faster-whisper` or any ASR dependency.

**§4.2 implication (a):** Full build required — Whisper integration added to `AssetStore.ingest()`. New optional dependency `faster-whisper`. Add `Asset.alignment: list[WordAlignment]` field with additive Pydantic schema.

---

## §2.2b — Silence-based cut proposal tool

**Question:** Does any tool consume alignment + silence markers and emit `TrimClipOp` / `RemoveClipOp` batches targeting inter-word silence?

**Answer: NO.**

**Evidence:**

| Search | Files matched |
|---|---|
| `silence_cutter`, `silence_cutter.py` | 0 |
| `propose_cuts` or `propose.cuts` | 0 |
| `inter_word_silence` | 0 |
| `cut_proposal` | 0 |
| Tool that emits `TrimClipOp` from silence analysis | 0 |

The `qc/silence.py` module (`open_edit/open_edit/qc/silence.py`) does detect silence via `ffmpeg -af silencedetect`, but it only produces **QC markers** (visible on the preview scrub bar) — it does not propose or emit edit ops.

**§4.2 implication (b):** Full build required — `open_edit/agent/skills/silence_cutter.py` + new tool `pyagent_propose_silence_cuts`. Depends on §2.2a for alignment input. New QC check: no cut splits a word (added to `qc/gate.py`).

---

## §2.3 — Custom motion graphics generator per utterance

**Question:** Does any tool take a transcript segment + narrative beat + brand profile, call an LLM to produce a visual concept, generate renderable code, run it in a sandbox, and emit an `AddClipOp` referencing the resulting video asset at the correct timeline position?

**Answer: NO.**

**Evidence:**

| Search | Files matched |
|---|---|
| `manim` import | 0 |
| `motionpy` or `moviepy` import | 0 |
| `motion_graphics` or `motion.graphics` keyword | 0 |
| `generate_visual` or `visual.concept` | 0 |
| `pyagent_generate_visual*` tool | 0 |
| Any tool that produces an `AddClipOp` referencing a new asset | 0 (all `AddClipOp` tools reference pre-ingested assets) |

**The 12 IR op types** (`open_edit/open_edit/ir/types.py`) include `AddClipOp` but the only way to populate it is via `AssetStore.get(asset_hash)` — a pre-existing asset. No code path creates a new asset programmatically (no "render and ingest" loop).

**Sandbox capability check (sub-claim in revised plan §2.3):**

The revised design's §2.3 quotes "Phase 3 spec §3.7 scopes the sandbox to 'lightweight per-op work' with 30s CPU + 512MB RAM." This is the **default**, not the hard cap.

Actual Phase 3 implementation (`open_edit/open_edit/agent/sandbox_bridge.py`):
- `MAX_FREEFORM_TIMEOUT_SEC = 300` (5 min default, user can request)
- `MAX_FREEFORM_MEM_MB = 4096` (4 GB default, user can request)
- `FreeFormCodeOp` accepts `timeout_sec: int = 30, mem_mb: int = 512` per-op
- Phase 3 sandbox **can** do heavier work if explicitly requested

**However**, the design's §4.3.1 conclusion (two sandboxes) is still correct because:
1. Default 30s/512MB is too small for manim / moviepy / ffmpeg-with-complex-filtergraph work.
2. Motion graphics wants `--dev /dev/dri` for GPU (not in Phase 3 sandbox).
3. Trust posture differs: Phase 3 = prevent accidental; motion graphics render = user explicitly requests heavy compute + filesystem writes outside workdir.
4. Melt renders are explicitly excluded from the Phase 3 sandbox (the orchestrator calls melt as a normal subprocess, not via the sandbox).

**§4.3 implication:** Full build required — `open_edit/agent/skills/motion_graphics.py` + new tool `pyagent_generate_visual_for_segment`. Plus a new **render sandbox** Rust binary (`open-edit-render-sandbox`): no CPU/mem limit, no seccomp, runs as user, can call melt/ffmpeg/manim. Output is a new video asset at `~/.open-edit/projects/<id>/assets/<hash>.mp4`, then emitted as `AddClipOp`.

**Templated vs. bespoke decision (per §4.3.1):** Recommend **templated per beat type**:
- Bespoke = 100+ LLM calls for 11-min video, untestable.
- Templated = 1 LLM call per segment for parameter selection, each template has golden IO, looks equally custom in output.
- Bespoke available as v1.1 power-user override.

**Sandbox decision (per §4.3.1):** Recommend **two sandboxes (A)**:
- Phase 3 sandbox stays as-is for lightweight per-op work.
- New `open-edit-render-sandbox` (Rust, no seccomp, no CPU/mem limit, cgroup MemoryMax=4G + CPUQuota=300%, `--dev /dev/dri` available with `--with-hwaccel` flag).
- Agent routes by task type: `pyagent_run_python` → Phase 3; `pyagent_generate_visual_for_segment` → render sandbox.

---

## §2.4 — Verification result summary

| § | Question | Answer | §4 work required |
|---|---|---|---|
| 2.1 | Narrative story-beat segmentation? | NO | Full build (§4.1) |
| 2.2a | Word-level transcription at ingestion? | NO | Full build (§4.2a — Whisper integration) |
| 2.2b | Silence-based cut proposal tool? | NO | Full build (§4.2b — silence_cutter tool) |
| 2.3 | Custom motion graphics generator? | NO | Full build (§4.3 — templated + render sandbox) |

**GATE OUTCOME:** **Phase 4.5 is fully in scope.** All five §4.x skills must be built.

**Phase 4.5 estimated effort:** 3-4 weeks additional (vs. 1.5 weeks for Phase 4 v2 review room alone). Critical path: §2.2a (Whisper) → §4.2 (silence cutter) → §4.1 (narrative) → §4.3 (motion graphics, longest pole) → §4.4-§4.5 (music, SFX, parallel).

**Music + SFX check (§4.4 / §4.5):** No existing music selector, no SFX placer, no `AddMusicTrackOp` or `AddSfxOp` in IR (`open_edit/open_edit/ir/types.py` has 12 op types, neither of those two). Both new op types + new tools required.

**Brand profile check (§7.1):** No `~/.open-edit/brand_profile.json`, no first-run wizard. v1.1 defer is correct; Phase 4.5 motion graphics can read a minimal brand profile if present (else use defaults).
