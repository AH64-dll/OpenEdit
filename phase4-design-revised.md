# Phase 4 Design (Revised) — Review Room + Creation Verification

| | |
|---|---|
| **Date** | 2026-07-20 |
| **Status** | Draft v2 (for approval) — merges the original Phase 4 draft with two independent reviews (Claude + Super Z) |
| **Supersedes** | Phase 4 Design (draft v1) |
| **Phase** | 4 of 5 (with conditional Phase 4.5 — see §2) |
| **Estimated effort** | 1.5 weeks for Phase 4 as written; +2–3 weeks if Phase 4.5 is triggered by the §2 verification gate |

---

## 0. Change Log (vs. Phase 4 draft v1)

| Change | Source | Section |
|--------|--------|---------|
| Added §2 verification gate — confirm creation pipeline status against Phases 0–3 before treating it as unbuilt | Both reviews (NEEDS VERIFICATION) | §2 |
| Added T6 — unified `review_notes` store (typed / voice / region / agent sources) | Both reviews | §3.6 |
| Added T7 — `commit_feedback` batch trigger + notification | Both reviews | §3.7 |
| De-scoped T3's slider/form UI to v1.1; kept `correction_note` as free-text | Both reviews | §3.3 |
| Restored `pyagent_add_marker` writing into the unified notes store (source=agent), not a new IR op | Merge resolution | §3.1, §3.6 |
| Added `RenderSnapshotStore` + version switcher to T4 | Both reviews | §3.4 |
| Added per-frame notes + speech-to-text input to T5 | Both reviews | §3.5 |
| Added `creativity_level` run parameter to T1 | Both reviews | §3.1 |
| Replaced fixed rollup-every-10-ops with adaptive trigger (project close + commit_feedback + token budget) | Both reviews | §3.2 |
| Added `prior_state` lightweight pending-notes summary injection (count + 3 most recent), replacing tool-call-only retrieval | Claude review | §3.2, §3.6 |
| Added Phase 4.5 (conditional) — creation skills: silence cutter, narrative analyzer, motion graphics, music, SFX | Both reviews | §4 |
| Added explicit cost/testability decision for motion graphics (templated vs. bespoke) | Claude review | §4.3 |
| Added §6 long-form scaling note for 11-minute videos | Claude review | §6 |
| Deferred: brand profile, multi-project orchestration, export/upload, contrast analysis, tool consolidation audit | Both reviews | §7 |

---

## 1. Scope Correction

**Phase 4 v1 draft built the *review room* half of the product.** Style memory, form editing, history, preview, region marks — all review-pipeline work.

**Phase 4 v1 did not build the *creation* half** — narrative analysis, silence-based cuts, custom motion graphics, music, SFX. The Loop Studio demo video's entire pitch rests on the creation half: *"It writes actual code for every single thing that's being said. So it is super custom."*

**Whether the creation half is genuinely missing or simply out-of-scope for the Phase 4 doc is currently unverified.** Phase 4 references an IR API, a sandbox, a QC gate, and a `phase3_pyagent_core` module from Phases 0–3, but neither review has seen those specs in full. Before treating "the creation pipeline doesn't exist" as settled fact, §2 must be completed.

This revised plan therefore:
- **Ships the review-room improvements regardless of §2's answer** (§3) — these are needed and match the demo closely.
- **Gates the creation-pipeline work on §2's outcome** (§4) — if Phases 0–3 already contain narrative analysis / silence cutting / motion graphics codegen, §4 shrinks to "wire this into Phase 4's prompt/tools." If not, §4 becomes Phase 4.5, a dedicated build phase.

---

## 2. Verification Gate (Step 0 — must run before §4)

Three questions, each requiring direct confirmation against Phase 0–3 source. Each answer determines the scope of §4.

### 2.1 Does any existing skill perform narrative story-beat segmentation?

Look for: a tool or skill that takes a transcribed clip and returns structured segments like `{beat_type, t_start, t_end, text, suggested_visual_concept}` — specifically the seven beat types the demo names (hook, turn, scope, mechanism, cost, tease, button).

- **If yes:** §4.1 is reduced to "wire the existing skill into Phase 4's system prompt and tool table."
- **If no:** §4.1 is a new build item.

### 2.2 Does any existing skill perform word-level transcription + propose silence-based cuts?

Look for: (a) Whisper / faster-whisper integration at asset ingestion producing word-level timestamps, and (b) a tool that consumes those timestamps + Phase 2's silence markers to emit `TrimClipOp` / `RemoveClipOp` batches targeting only inter-word silence.

- **If yes (both a and b):** §4.2 is reduced to "expose the existing tool; add a QC check that no cut splits a word."
- **If partial (a exists, b doesn't):** §4.2 is a smaller build — just the cut-proposal tool, reusing existing alignment.
- **If no:** §4.2 is a full build — ingestion extension + cut-proposal tool.

### 2.3 Does any existing component generate custom motion graphics per utterance?

Look for: a tool that takes a transcript segment + narrative beat + brand profile, calls an LLM to produce a visual concept, generates renderable code (manim / moviepy / headless canvas / WebGL / PNG sequence), runs that code in a sandbox, and emits an `AddClipOp` referencing the resulting video asset at the correct timeline position.

Also confirm: **does Phase 3's sandbox allow this?** The Phase 3 spec §3.7 (as quoted in review) scopes the sandbox to "lightweight per-op work" with `30s CPU + 512MB RAM` and explicitly excludes "full melt renders." If that quote is accurate at the source, motion graphics cannot run in the Phase 3 sandbox as built.

- **If yes (tool exists AND sandbox can run it):** §4.3 is reduced to "verify the bridge works end-to-end; document it."
- **If partial (sandbox is too small but the tool exists):** §4.3 is a sandbox expansion / second-sandbox build (see §4.3.1).
- **If no:** §4.3 is the largest single build item in the entire project — see §4.3.2.

### 2.4 Verification output

Produce a one-page memo answering 2.1 / 2.2 / 2.3 with citations to specific files in Phases 0–3. This memo gates §4 scope. Until it's written, treat §4 as conditional.

---

## 3. Phase 4 Tasks (Revised) — Review Room

These tasks ship regardless of §2's outcome. They match the demo's review-room scenes directly.

### 3.1 T1 — Tool repointing + new tools (revised)

**Repointed (32 existing wrappers):** Bodies in `pyagent-kdenlive-guide/phase3_pyagent_core/tools/*.py` call `open_edit.ir.api.*`. Names + JSON schemas unchanged. `OP_TABLE` in `runtime.py:69-102` updated.

**New tools (5, up from 3 in v1):**

| Tool | Body | Purpose |
|------|------|---------|
| `pyagent_run_python` | `agent.sandbox_bridge.run_free_form()` | Phase 3 bridge — unchanged from v1 |
| `pyagent_get_style_profile` | `style/retrieve.py` slice | Returns the tag-gated style profile slice for the current op context |
| `pyagent_set_pinned_value` | writes to `style_profile.json` pinned block | User-set override; highest precedence (see §3.2) |
| `pyagent_get_pending_notes` | `storage/notes.py` query | Full-detail pull of pending review notes (status=pending) for the current project; agent calls this on demand for detail |
| `pyagent_add_marker` | writes to `storage/notes.py` with `source=agent` | Restored — agent can proactively flag uncertain sections; lives in the same notes store as user notes (see §3.6) |

**Why `pyagent_add_marker` is not a new IR op:** Super Z proposed `AddMarkerOp` as a first-class edit-graph citizen. The Claude review correctly noted the demo never shows the agent flagging anything unprompted — that's an inference about what a *good* agentic editor should do, not a demoed feature. Resolution: markers live in the unified notes store (`source=agent`), not in the edit graph. One place a user checks for "everything flagged on this video," regardless of who flagged it. If a future phase needs markers as edit-graph citizens (e.g. for undo), promote to `AddMarkerOp` then.

**New `creativity_level` run parameter** (`conservative | balanced | full`):
- Set on the agent run config, surfaced in the system prompt as a directive: *"You are running in FULL creativity mode. Generate ambitious custom graphics for each segment."*
- Conservative: small adjustments, mostly cuts, minimal graphics.
- Balanced: some graphics, standard motion design.
- Full: heavy custom graphics, ambitious motion.
- Bias affects LLM prompt-generation step, not tool dispatch.

**System prompt changes:**
- Add the 5 new tools' schemas.
- Add `creativity_level` directive block.
- Add `prior_state` block (built by `style_inject.py` — see §3.2).
- Add lightweight `pending_notes_summary` (count + 3 most recent note texts, ≤150 tokens) so the agent knows feedback exists without a tool call. Full detail via `pyagent_get_pending_notes` on demand.
- Keep "keep results small" rule from v1.

**`extension.ts:343-365`:** register the 5 new tools.

### 3.2 T2 — Style Memory (revised rollup trigger)

Components unchanged from v1, except the rollup trigger.

**`open_edit/style/aggregate.py`** — rule-based rollup per spec §8.6. Weights: `applied_modified=+5`, `reverted=-3`, `applied_unmodified=0`. Examples capped at 4 per category, evict lowest-weight. Confidence = `min(weighted_sum/50, 1.0)`. Trim to ≤5000 tokens if over budget.

**`open_edit/style/retrieve.py`** — tag-gated slice per spec §8.8: `TAG_MAP` matches op type → relevant profile categories → ≤250 token injection. Below confidence 0.2 → omit.

**`open_edit/agent/style_inject.py`** — builds the `prior_state` block for the system prompt at every turn. Now also includes the `pending_notes_summary` (§3.1).

**`~/.open-edit/` bootstrap:** `mkdir -p`, `chmod 600` on `style_profile.json`, last 3 versions kept as `.bak`.

**Rollup trigger (revised — replaces v1's "every 10 ops"):**
- (a) Project close (`Project.close()`).
- (b) `commit_feedback` WS message (§3.7) — user signals "I'm done leaving notes, go."
- (c) Token-budget trigger: when unrolled events would exceed ~2000 tokens (estimated by `len(json.dumps(events)) / 4`), rollup runs.
- No fixed-op-count trigger. The magic-number-10 was arbitrary and didn't scale (30-clip video = 3 rollups; 200-op 11-minute video = 20 rollups).

**Pin precedence** (spec §8.7, enforced in `style_inject.py`):
`pinned > user_override_in_form > profile_default > LLM_default`.

### 3.3 T3 — De-scoped: Effect parameter fine-tuner (v1.1)

**What stays in Phase 4:**
- The free-text `correction_note` field, attached to any edit (not just form-based param edits). This is the qualitative feedback the demo actually shows (*"more 3D," "feels empty," "add a Claude logo here"*).
- The `correction_note` feeds `TasteEventStore` (T2) so freeform critique trains style memory, not just structured parameter diffs.

**What moves to v1.1:**
- The slider/dropdown form UI for `AddEffectOp` / `SetKeyframeOp` params.
- Per-param diff computation.

**Why de-scope:** The product's pitch is *"I never open an editor. I never touch a timeline. I just talk and give it notes."* Sliders and dropdowns for effect parameters reintroduce a direct-manipulation interaction model the product is explicitly positioned against. Freeform notes don't violate that framing; parameter forms arguably do. The demo never shows numeric parameter tweaking.

**If T3 is rebuilt in v1.1:** rename to "Effect parameter fine-tuner" and mark it experimental / power-user, not primary.

### 3.4 T4 — Style panel + edit history + rendered version snapshots (extended)

**Style profile panel (unchanged from v1):**
- Read-only JSON view of `~/.open-edit/style_profile.json`.
- Reset button (`POST /api/style/reset` calls `aggregate.reset()`).
- Pin control (calls `pyagent_set_pinned_value`).

**Edit history list (unchanged from v1):**
- Vertical list of ops from `EditGraphStore.load_all()`.
- Each row: `kind, label, author, timestamp, status` badge.
- Right-click menu: undo, redo (revert→applied), fine-tune (creates a new op with same parent), supersede.

**NEW — Rendered version snapshots:**

The demo's "version history" is at the *rendered output* level — different MP4s the user switches between (v1, v2, v3, v4). T4 v1's op-level history is a different thing; both are needed.

- New `RenderSnapshotStore` in `open_edit/storage/render_snapshots.py`:
  ```
  RenderSnapshot {
    version_id: str
    project_id: str
    edit_graph_hash: str      # SHA-256 of serialized edit graph at render time
    render_path: Path         # ~/.open-edit/projects/<id>/renders/<hash>.mp4
    created_at: str
    notes_summary: str        # one-line summary of what changed vs. previous version
  }
  ```
- Each render emitted by the Phase 2 orchestrator creates a snapshot automatically (hook in the orchestrator's post-render step).
- Version switcher dropdown in the preview player UI (§3.5): user selects v1/v2/v3/v4 → preview player loads that MP4.
- Edit-graph recovery: `edit_graph_hash` points at a snapshot in `edit_graph.db` (or a serialized copy stored alongside the render). Selecting an old version restores the edit graph state for inspection.
- Optional v1.1: diff view between two versions' op graphs.

### 3.5 T5 — HTML5 preview player + region mark + per-frame notes + STT + commit UI (extended)

**HTML5 preview player (unchanged from v1):**
- `<video>` element in `phase4_chat_ui/static/index.html`.
- Loads latest `~/.open-edit/projects/<id>/renders/<hash>.mp4`.
- Scrub-bar overlays: black-frame and silence markers from QC report (`qc/gate.py` output, Phase 2).
- **NEW:** version switcher dropdown (reads from `RenderSnapshotStore`, §3.4).

**Click-and-drag region mark (revised):**
- Creates a region `(x, y, w, h, t_start, t_end)` and writes it to the unified notes store (§3.6) with `source=region`.
- Region marks default to queuing into the batch (status=pending). Keep an explicit "handle this one right now" toggle for the v1 single-shot use case (populates the next prompt immediately, status=processed after send).

**NEW — Per-frame free-text notes:**
- Click on the scrub bar at time `T` → note input appears.
- User types text or uses speech-to-text (below).
- Note stored in `notes` table (§3.6) with `anchor={t_start: T, t_end: T}`.
- Notes sidebar (below) shows all notes chronologically; click → seek to timestamp.

**NEW — Speech-to-text input:**
- Microphone button next to each note input.
- Uses Web Speech API (`SpeechRecognition`) where available (Chrome, Edge, Safari).
- Graceful fallback on browsers without support (Firefox): button hidden, text input still works.
- Transcribed text populates the note field; user can edit before committing.

**NEW — Notes sidebar:**
- Chronological list of all notes (typed / voice / region / agent).
- Each note: anchor (timestamp or region), text, source badge, status badge (pending / processed / dismissed).
- Click a note → video seeks to its anchor.
- Edit / delete / change-status controls per note.
- Updates in real time via `note_list` WS broadcast (§3.6).

**NEW — "Send to Claude" button (commit UI):**
- Button at top of notes sidebar: "Send N notes to Claude."
- On click: sends `commit_feedback` WS message (§3.7). Button disabled until response.
- After agent run completes + new render ready: notification appears, button re-enables, version switcher (§3.4) shows the new version.

### 3.6 T6 — Unified `review_notes` store (NEW)

Single source of truth for "things pointing at the video that need attention." Replaces v1's parallel `mark_region` single-shot + `correction_note` per-param systems with one store.

**`open_edit/storage/notes.py`:**

```python
@dataclass
class ReviewNote:
    note_id: str               # new_id()
    project_id: str
    anchor: NoteAnchor         # timestamp or region — see below
    text: str                  # free-text; may be empty for pure region marks
    source: NoteSource         # "typed" | "voice" | "region" | "agent" | "form_correction"
    status: NoteStatus         # "pending" | "processed" | "dismissed"
    created_at: str            # ISO 8601
    processed_at: str | None
    resulting_op_ids: list[str]   # ops created when this note was acted on

class NoteAnchor(PydtUnion):
    # Discriminated union:
    timestamp: TimestampAnchor   # { t_start: float, t_end: float }
    region: RegionAnchor         # { x, y, w, h, t_start, t_end }
    op: OpAnchor                  # { op_id: str } — points at a specific op
```

**Storage:** SQLite table in `~/.open-edit/projects/<id>/notes.db`. Schema mirrors the dataclass. Indexed on `(project_id, status)` for fast pending-note queries.

**WebSocket messages:**
- `note_add` (client→server): `{anchor, text, source}` → server writes note, broadcasts `note_list`.
- `note_delete` (client→server): `{note_id}` → server marks `status=dismissed` (soft delete; never hard-delete for audit), broadcasts `note_list`.
- `note_update` (client→server): `{note_id, text?, status?}` → server updates, broadcasts `note_list`.
- `note_list` (server→client, broadcast on any change): full list of notes for the current project.

**Backend handlers** in `phase4_chat_ui/ws/handlers.py`:
- `note_add`: parse anchor, write via `NotesStore.append()`, broadcast.
- `note_delete` / `note_update`: as above.
- On `commit_feedback` (§3.7): all `status=pending` notes for the project are marked `status=processed` after the agent run completes; `resulting_op_ids` populated with the new ops.

**`prior_state` injection:**
- `style_inject.py` adds `pending_notes_summary` to every turn's system prompt: count + 3 most recent note texts (≤150 tokens total).
- This is more reliable than tool-call-only retrieval — the agent always knows feedback exists, even if it forgets to call `pyagent_get_pending_notes`.
- Full detail still available via `pyagent_get_pending_notes` tool call when the agent needs it.

**Taste event linkage:**
- Each processed note also writes a `TasteEvent` (T2) with `action=applied_modified` (or `reverted` if dismissed) and the note text as `correction_note`.
- Freeform critique like *"add a Claude logo here"* feeds style memory, not just structured parameter diffs.

### 3.7 T7 — `commit_feedback` batch trigger + notification (NEW)

The "I'm done leaving notes, now go produce v(n+1)" signal. Distinct from individual note writes.

**`commit_feedback` WS message** (client→server):
```json
{ "type": "commit_feedback", "project_id": "<id>" }
```

**Backend handler** in `phase4_chat_ui/ws/handlers.py`:
1. Query all `status=pending` notes for `project_id` from `NotesStore`.
2. Assemble a `pending_feedback` block, ordered by anchor (timestamp first, then region, then op-anchored):
   ```
   pending_feedback:
     - note_1: [00:12.3 - 00:15.0] "feels empty, more creative visual please"
     - note_2: [00:42.0 - 00:48.5, region (120,80,200,150)] "television overlays text, fix layout"
     - note_3: [01:23.0 - 01:25.0] "add Claude logo here"
     - note_4: [op_id=clip_7] "pacing too slow, trim 1s off the front"
   ```
3. Trigger the next agent turn with the `pending_feedback` block injected into the system prompt (alongside `prior_state`).
4. Agent runs, makes edits, calls IR API. Each new op's `parent_id` includes the originating `note_id` (extension to IR op metadata — see §3.8).
5. After agent turn completes: trigger Phase 2 render orchestrator → new MP4 → `RenderSnapshot` created (§3.4).
6. On render completion: mark all `pending` notes as `processed`, populate `resulting_op_ids`. Push notification to client.
7. Trigger T2 rollup (commit_feedback is one of the three rollup triggers per §3.2).

**Notification channel:**
- WS push to the chat UI: `{ "type": "version_ready", "project_id": "<id>", "version_id": "<vid>" }`.
- Client receives → shows toast notification + enables "Send to Claude" button + updates version switcher.
- Multi-project future (§7): per-project notification channel.

### 3.8 IR op metadata extension (small)

To support §3.7 step 4 (track which note originated which op), extend the base `Operation` model:

```python
class Operation(BaseModel):
    edit_id: str
    project_id: str
    parent_id: str
    # ... existing fields ...
    originating_note_id: str | None = None   # NEW — set by sandbox_bridge
```

`sandbox_bridge.run_free_form()` and direct IR API calls accept an optional `originating_note_id` parameter. If set, it's stamped on every op produced by that run. Default `None` (no note origin — e.g. agent-initiated edits without user feedback).

This is a small additive change. Existing fixtures continue to work (`originating_note_id` defaults to `None`).

---

## 4. Phase 4.5 — Creation Skills (CONDITIONAL on §2)

**Only if §2 verification confirms the creation pipeline is genuinely missing.** If any of §2.1 / §2.2 / §2.3 returns "yes, exists," the corresponding §4.x item shrinks to "wire into Phase 4."

### 4.1 Narrative analyzer (if §2.1 = no)

**`open_edit/agent/skills/narrative_analyzer.py`** + new tool `pyagent_analyze_narrative`.

- Input: transcribed raw clip (depends on §4.2 for word-level alignment).
- Output: structured segments:
  ```json
  [
    {"beat_type": "hook",     "t_start": 0.0,  "t_end": 3.2,  "text": "...", "suggested_visual_concept": "..."},
    {"beat_type": "turn",     "t_start": 3.2,  "t_end": 7.5,  "text": "...", "suggested_visual_concept": "..."},
    {"beat_type": "scope",    "t_start": 7.5,  "t_end": 12.1, "text": "...", "suggested_visual_concept": "..."},
    {"beat_type": "mechanism","t_start": 12.1, "t_end": 28.4, "text": "...", "suggested_visual_concept": "..."},
    {"beat_type": "cost",     "t_start": 28.4, "t_end": 33.0, "text": "...", "suggested_visual_concept": "..."},
    {"beat_type": "tease",    "t_start": 33.0, "t_end": 36.8, "text": "...", "suggested_visual_concept": "..."},
    {"beat_type": "button",   "t_start": 36.8, "t_end": 40.0, "text": "...", "suggested_visual_concept": "..."}
  ]
  ```
- Seven beat types are domain-specific to YouTube/marketing scripting (a "Storyloom"-style framework).
- Output feeds: planning step (which cuts to make), motion graphics (§4.3, concept per beat), music (§4.4, mood per beat), SFX (§4.5, placement at beat boundaries).

### 4.2 Silence cutter (if §2.2 = no or partial)

**Ingestion extension (if §2.2a = no):**
- Add Whisper / faster-whisper integration at asset ingestion (Phase 0/1 `AssetStore.ingest()`).
- Output: word-level timestamps stored on the Asset as `alignment: list[{word, t_start, t_end}]`.
- Use `faster-whisper` (CTranslate2-backed) for speed; ~5x faster than openai/whisper at equivalent quality.

**Cut-proposal tool (if §2.2b = no):**
- `open_edit/agent/skills/silence_cutter.py` + new tool `pyagent_propose_silence_cuts`.
- Input: asset alignment + Phase 2 silence markers + configurable threshold (default 400ms inter-word silence).
- Output: batch of `TrimClipOp` / `RemoveClipOp` targeting only silences above threshold.
- QC check (added to `qc/gate.py`): no cut splits a word — verify cut boundaries fall on inter-word gaps in the alignment.

### 4.3 Motion graphics generator (if §2.3 = no) — the "magic" feature

**Decide first (blocks §4.3 implementation):**

> **Templated vs. bespoke — pick one before building.**
>
> The demo promises *"no extra usage costs, only your Claude subscription."* Fully bespoke, from-scratch generated code for every single narrated segment means a concept call + a codegen call + a render pass per segment — 100+ model calls before a single review round on an 11-minute video. That's expensive in usage/rate-limit terms even without a literal dollar cost, and fully free-form generated code per segment is close to impossible to cover with the deterministic golden-IO pytest style the rest of the plan relies on.
>
> Two options:
>
> - **(A) Bespoke per segment.** Maximum creative flexibility. Highest cost (100+ LLM calls for an 11-min video). Hardest to test. Closest to the demo's pitch.
> - **(B) Templated per beat type.** A library of parameterized templates, one per narrative beat type (hook template, mechanism template, cost template, etc.). The LLM picks a template and customizes its parameters (text, colors, animation speed, asset references). Lower cost (1 LLM call per segment for parameter selection). Testable (each template has golden IO). Looks equally custom in the output.
>
> **Recommendation: (B) templated.** It matches the demo's visible output ("US map with dots merging into a computer" looks like a template populated with brand-specific assets, not a from-scratch render). It's testable. It scales. Reserve (A) bespoke for v1.1 power-user override.

**Sandbox fix (if §2.3 confirms Phase 3 sandbox too small):**

Two options (per both reviews):

- **(A) Two sandboxes (preferred).** Keep Phase 3 sandbox as-is for lightweight per-op work (validation, math, batch op generation). Add a new **render sandbox** `open-edit-render-sandbox`: no CPU/mem limit, no seccomp, runs as the user (or in a cgroup with `MemoryMax=4G` and `CPUQuota=300%`), can call melt/ffmpeg/manim freely. Output is a video asset written to the project's assets dir. Agent routes by task type: `pyagent_run_python` → Phase 3 sandbox; `pyagent_generate_visual_for_segment` → render sandbox.
- **(B) Expand Phase 3 sandbox (simpler, riskier).** Raise defaults (`--mem 4096`, `--cpu 600`). Drop seccomp entirely for the render path. Document that the sandbox is no longer a security boundary even for accidental damage on this path.

**(A) matches the Phase 3 trust model (Phase 3 = prevent accidental; v1.1 = security boundary). (B) is faster but conflates two different trust postures. Pick (A).**

**Pipeline:**

`open_edit/agent/skills/motion_graphics.py` + new tool `pyagent_generate_visual_for_segment`.

Three-step pipeline per segment:
1. **Concept step** (LLM call): transcript segment + narrative beat + brand profile (§7.1, deferred but read from a minimal `~/.open-edit/brand_profile.json` if present) → structured visual concept (what to draw, how it animates, what style).
2. **Codegen step** (LLM call if bespoke; parameter selection if templated): concept → renderable code (manim / moviepy / headless canvas / PNG sequence).
3. **Render-and-composite step** (in render sandbox): run generated code → produces video asset at `~/.open-edit/projects/<id>/assets/<hash>.mp4` → emit `AddClipOp` referencing the new asset at the correct timeline position.

**Critical MLT constraint (both reviews flagged):** MLT is a clip/effects/transition compositor, not a general motion-graphics renderer. Generated code must produce a re-importable clip asset (rendered video or PNG sequence) that gets composited into the timeline as a normal clip — not raw MLT XML expected to do the animating itself. If Phase 3's IR API already handles this bridge, the Phase 4.5 docs should say so explicitly.

### 4.4 Music selector (if missing)

- Tagged royalty-free track library (mood: upbeat / dramatic / contemplative / corporate / etc.; BPM; energy level).
- `open_edit/agent/skills/music_selector.py` + new tool `pyagent_select_music`.
- Input: narrative analysis (§4.1) → mood per segment → pick track.
- New IR op type `AddMusicTrackOp` (or extend `AddEffectOp` with `effect_type="music_bed"`).
- Auto-ducking: when narration is active, music volume dips; when narration pauses, music rises. Implemented as keyframes on the music track's gain (`SetKeyframeOp`).

### 4.5 SFX placer (if missing)

- Tagged SFX library (whooshes, impacts, risers, pops, dings, etc., tagged by emotion and use case).
- `open_edit/agent/skills/sfx_placer.py` + new tool `pyagent_place_sfx`.
- Input: narrative analysis (§4.1) + music downbeats (if §4.4 selected) → propose SFX placements at transition points, beat drops, on-screen reveals.
- New IR op type `AddSfxOp` (or extend `AddEffectOp`).

### 4.6 Phase 4.5 "done when" (conditional)

- A user can drop a raw clip, type "go full creativity," and receive a first-pass edit that includes:
  - Silence-based cuts (no words split).
  - At least one custom motion graphic (templated per beat type, brand-styled).
  - At least one music bed (mood-matched, auto-ducked).
  - At least two SFX placements (at narrative beats).
- The first-pass edit is reviewable in the Phase 4 review room (§3) — notes, region marks, version snapshots all work on Phase 4.5 output.
- An 11-minute video completes end-to-end (ingest → first-pass render) in under 30 minutes wall clock on a single Claude subscription, without rate-limit failures. (This is the demo's "faster, cheaper, just better" claim — needs explicit budget sizing per §6.)

---

## 5. Data Flow (v1 demo path — revised)

```
1. User: "fade the last 2 seconds to black" + click-and-drag on the last frame
   → note written to NotesStore (source=region, status=pending)
   → WS broadcasts note_list → sidebar updates

2. User: clicks "Send to Claude" button
   → commit_feedback WS message

3. Backend assembles pending_feedback block (all status=pending notes)
   → triggers next agent turn

4. style_inject.py builds prior_state block:
   - creativity_level directive (default: balanced)
   - tag-gated style profile slice for expected op types
   - pin overrides
   - latest 3 ops
   - pending_notes_summary (count + 3 most recent texts)

5. LLM emits: pyagent_apply_effect(target_kind="clip", target_id="clip_3",
                                    effect_type="fade_to_black", params={...},
                                    originating_note_id="note_7")

6. apply_effect wrapper: calls open_edit.ir.api.add_effect()
   → op appended to edit_graph.db
   → originating_note_id stamped on op

7. Agent turn complete → trigger Phase 2 render orchestrator
   → emit MLT → melt → preview.mp4
   → RenderSnapshot created (version_id=v(n+1))

8. QC gate: 5 checks (black frame, silence markers, etc.)

9. NotesStore: mark all status=pending notes as status=processed
   → populate resulting_op_ids from this run's ops
   → write TasteEvent per note (action=applied_modified, correction_note=text)

10. Rollup trigger (commit_feedback is one of three triggers per §3.2)
    → aggregate.py runs if token budget exceeded

11. WS push: version_ready notification → client
    → toast "v(n+1) ready"
    → version switcher updates
    → "Send to Claude" button re-enables

12. User clicks version switcher → preview player loads v(n+1) MP4
    → user reviews, leaves new notes, repeats from step 1
```

---

## 6. Long-Form Scaling (NEW — both reviews flagged)

The demo claims an 11-minute edit worked "faster, cheaper, and just better." Nothing in v1's error-handling table addresses timeout/perf budgets for anything beyond short-form.

**Concerns for 11-minute videos:**

- **Op count:** 200+ ops likely. Edit-graph serialization, referential validation (Phase 3 §4.3 `_validate_references` is O(n²) after the C6 incremental-validation fix), and timeline derivation all scale with op count.
- **LLM call count:** if §4.3 picks bespoke codegen, 100+ calls for graphics alone. Even templated: ~30 calls (one per segment) + planning + review = ~50 calls. Rate-limit risk.
- **Render time:** Phase 2 melt render of 200+ ops with effects + transitions + music + SFX can take 5–15 minutes on a single CPU. Acceptable for a v1 demo if the user is notified; not acceptable if it blocks the chat UI.
- **Memory:** style_profile.json grows with taste events; cap at 5000 tokens (T2 already does this). Notes DB grows with notes; cap pending notes at ~50 (warn user to commit before adding more).

**Mitigations to add to Phase 4:**
- Render is async (Phase 2 orchestrator already is, presumably — confirm). Chat UI shows progress; user can keep working.
- Long-form stress test in `tests/test_long_form_e2e.py`: 50-segment synthetic video, verify end-to-end completes in <15 minutes wall clock on CI.
- Rate-limit handling: agent retries with exponential backoff on 429s; surfaces "rate limited, retrying in Ns" to user.
- Op-count cliff: document that >500 ops may cause noticeable UI lag in the edit history list; v1.1 should add pagination.

---

## 7. Deferred to v1.1 / Later Phase

| Item | Why deferred | Source |
|------|--------------|--------|
| Brand profile (`colors, fonts, logo_path, lower_third_template, intro/outro_template, watermark`) at `~/.open-edit/brand_profile.json` with first-run wizard | Phase 4.5 motion graphics can read a minimal brand profile if present, but the full wizard is v1.1. The demo's "completely adjustable for exactly your branding" claim is partially met by style memory (T2); full brand assets need their own phase. | Both reviews |
| Multi-project parallel workflow (project switcher, per-project JobLock scope, per-project notification channel, dashboard view) | Real gap but not blocking for v1 demo. The demo shows 5 parallel videos but the v1 demo can ship single-project. | Both reviews |
| Export presets + platform upload (YouTube/TikTok/Instagram presets, YouTube Data API v3 OAuth upload, render queue with progress UI) | "All the way to the actual upload" is a demo claim. Confirm whether this is intentionally scoped to a later phase; if not scoped anywhere, it's a headline claim currently unaccounted for. Not blocking for v1 demo. | Both reviews |
| Contrast analysis (`pyagent_analyze_contrast` — visual/pacing/topic contrast between sections) | One of the demo's six quality pillars; five map to existing/planned work, "contrast" doesn't. Worth a placeholder so it isn't silently dropped. Low priority. | Both reviews |
| Tool consolidation audit (38 → ~15–20 tools; consolidate `pyagent_apply_<effect>` family into one discriminated `pyagent_apply_effect`) | Nice-to-have cleanup, not a blocker. Token overhead per turn is ~5700 tokens for 38 schemas; consolidating to 20 saves ~2800 tokens/turn. | Both reviews |
| T3 slider/form UI for effect parameters (renamed "Effect parameter fine-tuner," marked experimental) | De-scoped from v1 — see §3.3. | Both reviews |
| Diff view between two rendered versions' op graphs | `RenderSnapshotStore` (§3.4) supports switching versions; diff view is v1.1 polish. | Claude review |

---

## 8. Error Handling (revised — extends v1)

| Failure | Behavior |
|---------|----------|
| `pyagent_add_marker` called | Writes to NotesStore with `source=agent`. No IR validation needed (markers aren't ops). Broadcasts `note_list`. |
| Tier 1 op rejected by IR validation | `FreeFormResult.fail("invalid_op", ...)`. Agent sees failure, can retry. |
| Sandbox timeout (Tier 2) | `FreeFormResult.fail("timeout")`. Per Phase 3 §3.3 reason code. |
| `~/.open-edit/` not writable | `run_free_form` returns `FreeFormResult.fail("config_not_writable")`. Agent surfaces to user. |
| `style_profile.json` corrupt | Load fails → `aggregate.bootstrap()` regenerates from scratch. `.bak` rotation (T2) restores last good version if available. |
| Pin weakened (5 overrides on one key) | Warning logged; pin auto-demoted to `user_override` precedence. User notified via chat UI. |
| Free-form code crashes in sandbox | `FreeFormResult.fail("nonzero_exit", stderr)`. `ops.jsonl` unlinked by atomic commit gate (Phase 3 §2.2 step 7). |
| Click-and-drag region mark on a frame without time | Client-side validation: reject region marks before `t_start=0` or after video duration. Show toast "cannot mark region outside video bounds." |
| `commit_feedback` with zero pending notes | Backend returns error: `{ "type": "error", "message": "no pending notes to commit" }`. Button stays enabled. |
| Agent run triggered by `commit_feedback` fails midway | Notes remain `status=pending` (not marked processed). Render not triggered. User notified: "agent run failed, your notes are preserved. Retry?" |
| Render fails after successful agent run | Agent ops are committed to edit graph. Notes marked `status=processed` (the agent did act on them). `RenderSnapshot` not created. User notified: "edits applied but render failed; click retry to re-render." |
| Rate limit (429) during agent run | Exponential backoff (1s, 2s, 4s, 8s, max 60s). After 5 retries: fail. User notified: "rate limited, please retry in N minutes." |
| `RenderSnapshotStore` disk full | Render still succeeds (MP4 written); snapshot metadata write fails. Logged. User can still access the render via filesystem; version switcher won't list it until metadata is repaired. |
| Long-form op count > 500 | Edit history list shows pagination (50 ops/page). Timeline derivation slows; warn user if > 1000 ops. |
| Notes DB grows large (>1000 notes) | Archive processed notes older than 30 days to `notes.db.archive`. Pending notes never archived. |

---

## 9. Testing (revised — extends v1)

### 9.1 Unit tests (pytest `open_edit/tests/test_style/`)

- `test_aggregate.py` — weights, eviction-by-weight, confidence-weighted-not-raw, trim-to-budget, rollup atomicity, bootstrap. **NEW:** adaptive trigger (project close, commit_feedback, token budget — not op count).
- `test_retrieve.py` — tag map, confidence threshold (omit below 0.2), ≤250 token cap.
- `test_style_inject.py` — pin precedence, `prior_state` block shape, **NEW:** `pending_notes_summary` injection (count + 3 most recent, ≤150 tokens).
- `test_taste_events.py` — already exists (4 tests, Phase 3 stub); extend.

### 9.2 Tool repointing tests (pytest `open_edit/tests/test_tools/`)

- Golden IO tests: for each of the 32 repointed wrappers, call with fixture args, assert the IR API was called with the right args, assert edit graph state matches expected.
- Mirror `pyagent-kdenlive-guide/phase3_pyagent_core/tests/test_golden_io.py` patterns.
- **NEW:** test for `pyagent_add_marker` — writes to NotesStore with `source=agent`, broadcasts `note_list`.
- **NEW:** test for `pyagent_get_pending_notes` — returns only `status=pending` notes for the current project.
- **NEW:** test for `creativity_level` parameter — appears in system prompt directive block.

### 9.3 Review notes store tests (pytest `open_edit/tests/test_storage/test_notes.py` — NEW)

- `test_note_add` — write via `NotesStore.append()`, read back, verify fields.
- `test_note_list_pending` — query by `status=pending`, verify ordering (by `created_at`).
- `test_note_delete_soft` — `note_delete` marks `status=dismissed`, doesn't hard-delete.
- `test_note_update_status` — `note_update` transitions `pending → processed`, populates `resulting_op_ids`.
- `test_anchor_discriminated_union` — timestamp / region / op anchors all serialize and deserialize correctly.
- `test_notes_db_archive` — processed notes older than 30 days move to archive table.

### 9.4 Form UI tests (pytest `phase4_chat_ui/test_form_*.py` + JS — REDUCED from v1)

- ~~WebSocket `form_apply` round-trip: server receives, calls IR, writes taste_event, returns `form_state`.~~ (De-scoped — T3 form UI moved to v1.1.)
- `correction_note` empty → event recorded without note. (Kept — `correction_note` is still a field.)
- ~~diff (proposed vs final) → action is `applied_modified`.~~ (De-scoped with T3.)

### 9.5 Preview player tests (pytest `phase4_chat_ui/test_preview_*.py` — EXTENDED)

- Region mark: client sends `note_add` with `source=region` and `anchor=region`, server echoes via `note_list`, sidebar updates.
- QC markers on scrub bar: derived from QC report. (Unchanged from v1.)
- **NEW:** per-frame note: client clicks scrub bar at T, types note, sends `note_add` with `source=typed` and `anchor=timestamp`.
- **NEW:** speech-to-text: mock `SpeechRecognition` API, verify transcribed text populates note field. (Graceful fallback tested separately: hide button when API unavailable.)
- **NEW:** version switcher: client selects v2 from dropdown, server returns v2's `render_path`, preview player loads v2 MP4.
- **NEW:** "Send to Claude" button: click sends `commit_feedback`, button disables, on `version_ready` notification button re-enables.

### 9.6 Commit-feedback tests (pytest `phase4_chat_ui/test_commit_feedback.py` — NEW)

- `test_commit_feedback_assembles_pending_notes` — 3 pending notes (timestamp, region, op-anchored), `commit_feedback` fires, agent turn receives `pending_feedback` block with all 3.
- `test_commit_feedback_zero_notes` — no pending notes → error response, no agent turn triggered.
- `test_commit_feedback_marks_notes_processed` — after agent run completes, all pending notes transition to `processed`, `resulting_op_ids` populated.
- `test_commit_feedback_triggers_rollup` — `commit_feedback` is one of three rollup triggers; verify rollup runs after commit.
- `test_commit_feedback_agent_fails_notes_preserved` — agent run raises; notes remain `status=pending`; user can retry.
- `test_version_ready_notification` — after render completes, WS push `version_ready` received by client.

### 9.7 Aggregate e2e tests (pytest `open_edit/tests/test_style/test_aggregate_e2e.py`)

- 50 taste events with known weights → rollup produces expected profile. (Unchanged from v1.)
- **NEW:** rollup triggered by `commit_feedback` (not op count).
- **NEW:** rollup triggered by token-budget threshold (mock events exceeding 2000 tokens → rollup runs).

### 9.8 Long-form stress test (pytest `tests/test_long_form_e2e.py` — NEW)

- 50-segment synthetic video (5 minutes, 50 narrative beats).
- Full pipeline: ingest → silence cut → narrative analyze → motion graphics (templated) → music → SFX → render → QC.
- Assert end-to-end completes in <15 minutes wall clock on CI.
- Assert no rate-limit failures (mock LLM if needed).
- Assert edit graph <500 ops (sanity check on op count growth).

### 9.9 Phase 4.5 tests (CONDITIONAL — only if §2 triggers Phase 4.5)

- `test_narrative_analyzer.py` — golden IO per beat type.
- `test_silence_cutter.py` — alignment + silence markers → cut proposals; verify no word splits.
- `test_motion_graphics_templated.py` — each template has golden IO; parameter selection produces valid renderable code.
- `test_motion_graphics_render.py` — render sandbox produces non-empty MP4 for a sample template.
- `test_music_selector.py` — narrative mood → track selection; auto-ducking keyframes correct.
- `test_sfx_placer.py` — beat boundaries → SFX placements; sync to music downbeats if music present.

---

## 10. Phase 4 "Done When" (revised — adds items 11–17)

1. The 32 repointed tools all call `open_edit.ir.api.*` and pass golden IO tests.
2. The 5 new tools (was 3 in v1) register and dispatch correctly.
3. ~~The form UI's Apply writes a taste_event with the right action + diff.~~ (De-scoped — T3 form UI moved to v1.1. `correction_note` free-text field still writes taste events; test this instead.)
4. The style profile panel renders; Reset and Pin controls work.
5. The edit history list shows all ops from `EditGraphStore` with undo/redo controls.
6. The HTML5 preview player loads the latest render with QC markers.
7. Click-and-drag on the video frame sends a region mark — **revised:** writes to unified NotesStore with `source=region`, broadcasts `note_list`.
8. `prior_state` is injected into the system prompt on every turn — **revised:** includes `pending_notes_summary`.
9. Rollup runs on **(a) project close, (b) `commit_feedback`, (c) token-budget threshold** — no fixed-op-count trigger.
10. `~/.open-edit/style_profile.json` is `chmod 600`.
11. **NEW:** The unified `review_notes` store handles typed / voice / region / agent sources; sidebar UI shows all notes chronologically with status badges.
12. **NEW:** Speech-to-text input works on supported browsers (Chrome/Edge/Safari); graceful fallback on Firefox.
13. **NEW:** "Send to Claude" button triggers `commit_feedback`; on completion, `version_ready` notification fires and version switcher updates.
14. **NEW:** `RenderSnapshotStore` records each render; version switcher in preview player allows switching between v1/v2/v3/v4.
15. **NEW:** `creativity_level` parameter (`conservative | balanced | full`) appears in system prompt as a directive.
16. **NEW:** `originating_note_id` is stamped on ops produced during a `commit_feedback` run; notes transition to `processed` with `resulting_op_ids` populated.
17. **NEW (conditional on §2):** A user can drop a raw clip, type "go full creativity," and receive a first-pass edit with silence cuts + at least one motion graphic + music + SFX. (Phase 4.5 — only if §2 verification confirms creation pipeline missing.)

All Phase 4 (non-conditional) pytest suites pass with no regressions in Phases 0–3.

---

## 11. Implementation Sequencing

Recommended order, optimized for unblocking demo-able progress:

| Step | Tasks | Why this order |
|------:|-------|----------------|
| 0 | §2 verification gate (one-page memo) | Determines whether §4 / Phase 4.5 is needed. Blocks §4 only — §3 ships regardless. |
| 1 | T6 unified notes store + sidebar UI | Foundation for T5's per-frame notes and T7's commit-feedback. Without this, T5 and T7 have nowhere to write. |
| 2 | T5 preview player + region mark + per-frame notes + STT | User can leave feedback. STT is small (~50 lines JS). |
| 3 | T7 `commit_feedback` + notification | User can trigger agent run from feedback. |
| 4 | T4 `RenderSnapshotStore` + version switcher | User can switch between v1/v2/v3. |
| 5 | T2 style memory (revised rollup trigger) + `prior_state` injection | Style learning kicks in. |
| 6 | T1 tool repointing + 5 new tools + `creativity_level` | Agent has the tools to act on feedback. |
| 7 | (Parallel with 1–6) §4 Phase 4.5 if §2 triggers it | Long pole; start early if needed. |
| 8 | Long-form stress test (§9.8) | Validates 11-minute video claim. |

After Step 6, the review room matches the demo. After Step 7 (if triggered), the creation pipeline matches the demo. After Step 8, the long-form claim is validated.

---

## 12. Open Questions for Approval

Before implementation, confirm:

1. **§2 verification:** who runs it, and by when? It blocks §4 scope but not §3 implementation.
2. **§4.3 templated vs. bespoke:** if §4.3 is triggered, which path? (Recommendation: templated.)
3. **§4.3 sandbox fix:** two sandboxes (A) or expand Phase 3 (B)? (Recommendation: A.)
4. **§7 brand profile:** is the demo's "completely adjustable for exactly your branding" claim met by style memory (T2) alone for v1, or is a minimal brand profile needed? (Recommendation: minimal brand profile in Phase 4.5, full wizard in v1.1.)
5. **§7 export/upload:** is "all the way to the actual upload" intentionally scoped to a later phase? If not, it's a headline claim currently unaccounted for.
6. **§9.8 long-form stress test:** is 15 minutes wall clock for a 5-minute video acceptable, or does the demo's "faster" claim require a tighter budget?
7. **T3 de-scope:** confirm slider/form UI moves to v1.1. (Both reviews recommend yes.)

---

## 13. Bottom Line

**Phase 4 v2 (this plan) ships a review room that matches the demo.** Unified notes store, per-frame notes, speech-to-text, commit-feedback trigger, version snapshots, creativity level, adaptive style-memory rollup. De-scoped the slider UI (wrong UX paradigm for the product's pitch). Seven "done when" criteria added (items 11–17).

**Phase 4.5 (conditional) ships the creation pipeline that matches the demo's pitch.** Five skills: silence cutter, narrative analyzer, motion graphics (templated), music selector, SFX placer. Sandbox fix (two sandboxes preferred). Only triggered if §2 verification confirms the creation pipeline is genuinely missing from Phases 0–3.

**Together, Phase 4 v2 + Phase 4.5 match the Loop Studio demo video end-to-end.** Phase 4 v2 alone ships a polished review room for a video the agent can produce only if Phases 0–3 already contain the creation skills. Run §2 first to know which world you're in.
