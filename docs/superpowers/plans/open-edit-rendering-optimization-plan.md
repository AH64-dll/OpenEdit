# Open Edit — Rendering Pipeline Investigation & Optimization Master Plan (v3)

> **Status:** Investigation plan only. **Do not implement** until AH64 gives explicit green light.
> **Format peers:** `docs/superpowers/plans/2026-08-01-render-pipeline-fix.md`, `docs/superpowers/plans/2026-07-31-open-edit-restructure.md`
> **Final architecture deliverable (after Phases 0–6):** still named `open-edit-rendering-optimization-plan.md` content under Phase 6, or a sibling `…-architecture-proposal.md` if this file stays as the investigation brief.

**Goal:** Make Open Edit preview feel interactive (Kdenlive/Shotcut-class scrubbing) and make final export substantially faster — based on measured bottlenecks, not guessed micro-optimizations.

**Architecture (current, graph-grounded — to be verified in Phase 0):** Edit Graph → `derive_timeline` → Remotion materialize → MLT emit → melt→ffmpeg frame-server pipe → optional source-repair/QC → MP4. Cache key = edit-graph hash + profile fingerprint.

**Tech Stack:** Python 3.11 pin, MLT/melt, ffmpeg (NVENC already in use), Remotion (Node/Chromium), HyperFrames (HTML overlays), Edit Graph IR, sandboxed `ops.jsonl` for free-form IR mutations.

---

## Orchestrator review (AH64 ask — 2026-08-02)

### Verdict on your v2 draft

**Keep it.** Phase 0 gate, measurement-first Phase 1, Tier 1/2 industry split, Hard Constraints, 5-agent cap, and the human review stop before implementation are exactly right. Do **not** dilute those.

### Critical corrections from graph + product reality

These must be first-class in the investigation — they were under-weighted in the original draft:

1. **“Preview” today is not live playback.**  
   Open Edit `mode=proxy` is a **full-timeline MP4 encode** (lower res / faster tier), then the Review Studio plays that file. Kdenlive/Shotcut “instant” feel comes from an **interactive MLT consumer** + optional **chunked background timeline preview cache**, not from re-encoding the whole sequence after every edit. Treating “make proxy faster” as the only goal will never feel like Premiere/Kdenlive.

2. **Remotion materialization is a primary suspect, not a side note.**  
   Graph path: `render_project()` → `materialize_remotion_compositions()` → Remotion Chromium renders → CAS clips → ffmpeg `filter_complex` overlays in the frame-server pipe. On timeline-test, dozens of overlays meant minutes of Remotion work **before** melt/ffmpeg even started. Phase 0/1 must time Remotion separately from melt/ffmpeg. Agent 2 must own **Remotion + HyperFrames + MLT**, not HyperFrames alone.

3. **A large chunk of “render is slow” is already partially addressed — measure against the new baseline.**  
   The 2026-08-01 render-pipeline-fix (`docs/superpowers/plans/2026-08-01-render-pipeline-fix.md`, memory: landed on main) already shipped:
   - single-pass melt→rawvideo→ffmpeg overlays+encode
   - quality tiers (`fast`/`standard`/`high`/`archival`)
   - cache key = graph hash + profile fingerprint
   - optional `hwaccel=cuda` on producers + NVENC encode  
   Phase 0 must start from **this** code, not from a pre-fix mental model. Remaining pain is likely: **full-timeline invalidation**, **Remotion per-overlay cost**, **post-render QC/source-repair**, and **no interactive scrub path**.

4. **Sandbox Hard Constraint needs a precise split.**  
   - **IR / free-form edits** (`run_script`): Rust/seccomp/bwrap + `ops.jsonl` — Hard Constraint as written.  
   - **Render jobs** (`open_edit.cli render`, melt/ffmpeg/Remotion): typically **host GPU processes outside that sandbox**.  
   Phase 0 must document which stages run where. Proposals that require GPU inside the free-form sandbox vs. only in the render worker are different risk classes — do not conflate them.

5. **Industry target must be stated as three systems, not one “faster render”.**  
   From Tier-1 sources (Kdenlive docs; Shotcut FAQ/releases):
   | System | What it does | Open Edit today |
   |---|---|---|
   | **Source proxies** | Low-res stand-ins for heavy camera media | Partial (proxy *mode* is output profile, not per-asset proxy clips) |
   | **Timeline preview cache** | Background chunked bake of effect-heavy zones for smooth playback | **Missing** — closest is whole-file `proxy` MP4 |
   | **Final export** | Full-quality one-shot (or multi-pass) deliverable | Present (`mode=final`) but slow under Remotion load |

6. **Disk / cache budget is a hard product constraint.**  
   timeline-test regularly sits at ~95% disk; Remotion `out/final` ProRes intermediates and render_cache can eat GBs. Any caching strategy must include eviction, size caps, and “keep source CAS + newest deliverable” rules.

### Industry notes (for Phase 2 — already triaged)

**Tier 1 (usable as evidence):**

- **Kdenlive timeline preview:** background chunked preview (historically ~25–100 frame chunks), red→green progress bar, invalidate only touched zones; audio independent of video preview; proxy clips ≠ timeline preview ([Kdenlive manual — Timeline Preview Rendering](https://docs.kdenlive.org/en/tips_and_tricks/tips_and_tricks/timeline_preview_rendering.html), [Proxy Settings](https://docs.kdenlive.org/en/project_and_asset_management/project_settings/proxy_settings.html); architecture uses MLT — [dev-docs/architecture.md](https://github.com/KDE/kdenlive/blob/master/dev-docs/architecture.md)).
- **Shotcut:** preview scaling + proxy editing; hardware decode for preview with caveats; Shotcut FAQ explicitly warns that full zero-copy GPU pipelines are hard and often not worth it if frames bounce CPU↔GPU ([Shotcut FAQ](https://www.shotcut.org/FAQ/); hw decode in v26.1 release notes).

**Tier 2 (context only — label unverified):**

- **Premiere “Mercury Playback Engine” / background rendering** and **Resolve Smart/User Render Cache** are reported to pre-bake heavy segments for realtime scrubbing — do **not** drive architecture alone; use only as UX targets (“scrub stays realtime after idle cache fills”).

### Suggested success metrics (fill exact numbers in Phase 1)

| Metric | Stretch target (subject to Phase 1 baselines) |
|---|---|
| Scrub / seek on cached preview | Realtime or better; no full re-encode |
| Edit one overlay → visible change in Review Studio | Prefer **seconds on dirty region**, not full-timeline re-encode |
| Proxy of 10 min @ 640×360 with N Remotion overlays | Measure baseline first; target ≥2× faster wall clock vs Phase 1 baseline |
| Final of ~27 min @ 1080p with ~50 overlays | Measure baseline (timeline-test ~2 GB / long wall clock); target large reduction via Remotion reuse + skip redundant QC |
| Remotion materialize | Cache hit = near-instant; miss = only dirty compositions |

### Amendments applied in this v3

- Remotion elevated into Phase 0 checklist + Agent 2 scope.
- Explicit **interactive preview vs proxy MP4 vs final** product split.
- Sandbox vs render-worker clarification in Hard Constraints.
- Reference prior render-pipeline-fix as baseline.
- Disk/cache budget constraint.
- Target metrics table.
- Agent 2 renamed; Agent 1 owns Remotion timing in Phase 1 instrumentation.
- Stop gate unchanged: **no Phase 7 / no implementation without AH64 green light.**

---

## What changed from v2 → v3

- Incorporated Orchestrator review above (Remotion, interactive preview gap, prior pipeline fix, sandbox split, disk).
- Expanded Phase 0 checklist with Remotion path and “is proxy a live consumer?” confirmation.
- Expanded Phase 1 fixed test project to include Remotion-heavy case matching real usage.
- Agent roles remapped to include Remotion.
- Added success-metrics and three-system industry framing.

*(v2 changes from original draft remain: Phase 0 gate, instrumented Phase 1, 5-agent cap, Tier 1/2 research, Hard Constraints, merged orchestration, acceptance + human review gate.)*

---

## Objective

The current rendering path is too slow for practical editing: every meaningful change tends toward a **full timeline re-render** to MP4; Remotion overlays multiply cost; final export of long cuts is painful. The goal is an architecture that approaches Kdenlive/Shotcut-class responsiveness: **interactive scrubbing**, **smart invalidation**, **chunked/background preview**, and **reasonable export times** — not a bag of unmeasured micro-optimizations.

---

## Hard Constraints

Every recommendation must fit these, or explicitly say **“this requires breaking X”** with justification.

- **Python 3.11 strict pin** (project policy; Phase 0 must confirm runtime vs pin).
- **Free-form IR execution** happens inside the Rust/seccomp/bubblewrap sandbox; IPC across that boundary is file-based (`ops.jsonl`). Proposals that need shared memory, sockets, or shared GPU contexts **across that sandbox boundary** must say so explicitly.
- **Render workers** (melt/ffmpeg/Remotion) may already run **outside** the free-form sandbox with host GPU — Phase 0 must confirm. GPU/native proposals must state whether they touch sandbox, render worker, or both.
- **IR is Edit Graph → Python emission** (`derive_timeline` / `emit_timeline`). Changes to emission or a new evaluation layer must be described precisely.
- **Compositing stack:** MLT + ffmpeg frame-server pipe; Remotion for React graphics; HyperFrames for HTML overlays. Known historical issues (alpha, `filter_complex`, orchestrator gaps) must be re-checked in Phase 0 before blaming “architecture.”
- **Disk budget:** caching/strategies must include eviction and size caps; do not assume unbounded Remotion ProRes / render_cache growth.
- **Do not regress** the 2026-08-01 frame-server correctness fixes (e.g. `f=rawvideo` pipe contract) without an explicit migration plan.

---

## Phase 0 — Ground Truth (mandatory, blocks everything else)

Before any agent writes a finding:

1. Read the actual render path end to end and list every file touched, in order. Expected spine (confirm/refute via graph + code):
   - `EditGraphStore` / `derive_timeline` / `derive_or_load_timeline`
   - `materialize_remotion_compositions` → `open_edit/render/remotion/*`
   - `emit_timeline` / `timeline_for_melt` / `build_render_plan`
   - `build_pipe_commands` / `run_pipe` (melt → ffmpeg)
   - `repair_render_output` / QC (if still on the critical path)
   - `RenderCache` / `render_cache_key` / snapshot stores
2. Confirm or refute, with **file/line** references:
   - GPU path today: NVENC? `hwaccel=cuda`? Remotion CPU vs GPU? Entirely CPU?
   - Is preview a **cheaper separate path**, the **same pipeline at lower resolution**, or something else?
   - Is there any **interactive MLT SDL/OpenGL consumer** for Review Studio, or only **file playback of rendered MP4**?
   - Remotion: per-composition cache keys, when rematerialize is forced, alpha/ProRes cost.
   - Are v1.4 preview-failure / v1.6 alpha / `filter_complex` / missing-orchestrator items still open?
   - Which stages run **inside** the free-form sandbox vs **host render worker**?
3. Deliverable: **ground-truth doc ≤ 2 pages** — what’s true, what’s unknown, what’s in-scope vs N/A.  
   Save as: `docs/superpowers/specs/2026-08-02-render-ground-truth.md` (suggested).

**Nothing in Phase 1+ may cite a claim not backed by Phase 0 or measured in Phase 1.**

---

## Phase 1 — Instrumented Investigation

Candidate areas: timeline evaluation, Remotion materialize, frame generation, effects, compositing, decoding, threading, asset loading, disk, cache hits/misses, ffmpeg `filter_complex`, scheduling, source-repair/QC.

**Every claim needs a measurement.**

### Fixed test projects (use all three; keep identical across the investigation)

| Fixture | Purpose |
|---|---|
| **A — Baseline** | ~60s 1080p, 1 clip, 0 overlays |
| **B — Light Remotion** | ~60s, 3 FocusPopup-style overlays |
| **C — Heavy Remotion** | ~10 min, ≥20 Remotion overlays (timeline-test–like) |

### Measurements required

- End-to-end wall clock for `proxy` and `final` on A/B/C.
- Stage breakdown: IR/timeline derive, Remotion materialize (per comp + total), melt, ffmpeg encode, source-repair, QC.
- Tools: cProfile/py-spy; Remotion timing logs; `ffmpeg -benchmark` / `-progress`; cache hit rate from `RenderCache` / Remotion materialize cache.
- Report numbers like: “Remotion materialize 180s of 240s proxy on fixture C.”

Only then name bottlenecks — each cites a measurement.

---

## Phase 2 — Industry Research (source-quality tiered)

**Tier 1 — evidence:** Kdenlive, Shotcut, Olive, OpenShot, Blender VSE, Natron. Claims → source/docs/commits.

**Tier 2 — context only:** Premiere, Resolve, FCP, Lightworks. Label **“reported by [source], unverified.”** Never sole justification.

Focus: interactive playback, timeline preview chunks, smart cache, proxy media, GPU/hwaccel limits, dirty-region invalidation, background render, async jobs.

Prioritize extracting **patterns Open Edit can copy without leaving MLT**:

1. Chunked timeline preview cache with zone invalidation (Kdenlive).
2. Preview scaling + source proxies (Shotcut).
3. Separate audio path from video preview re-bake (Kdenlive).

---

## Phase 3 — Evaluate the Current Renderer

Decide: keep / heavily modify / partially replace / fully replace — each option must cite Phase 0/1 and Hard Constraints.

Likely decision axes (hypothesis only — not findings until measured):

- Keep melt→ffmpeg frame-server for **final**.
- Add or replace **preview** with interactive consumer + chunked cache.
- Attack Remotion cost (reuse, lower proxy codec, dirty-only materialize, prewarm).

---

## Phase 4 — Explore Alternative Technologies

Candidates (FFmpeg/libav, GPU libs, Vulkan/OpenGL graphs, hw decode/encode, zero-copy, frame caches, timeline frameworks) — each recommendation must state:

1. Runs in sandbox, render worker, or both?
2. Integration cost given Python 3.11 + existing MLT/ffmpeg/Remotion investment?
3. Drop-in vs Edit Graph IR change?

**Bias:** prefer extending MLT+ffmpeg+Remotion over a greenfield GPU compositor unless Phase 1 proves the pipe itself is the ceiling.

---

## Phase 5 — Optimization Opportunities

Each opportunity must:

- Cite the Phase 1 measurement it addresses.
- Give a before/after estimate grounded in that measurement.
- State cache/disk impact.

Candidate list (not prioritized until measured): incremental/dirty-frame rendering, Remotion materialize reuse, chunked timeline preview, proxy source media, background preview jobs, skip/async QC for proxy, GPU effects, parallel Remotion, job system, memory pools, zero-copy (with Shotcut-style skepticism).

---

## Phase 6 — Architecture Proposal

Produce a 14-part proposal (original 12 +):

13. **Acceptance criteria** per migration phase (checkbox handoff format).
14. **Hard Constraints this proposal breaks** (explicit list + why), or “none.”

Also include:

- Product split: interactive preview / proxy review artifact / final export.
- Migration strategy that does not break Review Studio mid-flight.
- Disk/cache policy.

**Not self-approved.** Hand to AH64. **No Phase 7 / no implementation** until green light.

Suggested save path for the proposal body: keep updating this file’s “Phase 6 output” section, or add  
`docs/superpowers/specs/2026-08-02-open-edit-rendering-architecture.md`.

---

## Multi-Agent Orchestration & Workflow

Cap at **5** agents:

1. **Pipeline Profiler** — Phase 0 + Phase 1 (code path + instrumentation + numbers). Owns Remotion wall-clock in the stage breakdown.
2. **Compositing / Remotion / HyperFrames Specialist** — MLT, Remotion materialize, alpha, `filter_complex`, overlay pipe. Owns known open bugs + Remotion cache behavior.
3. **Open-Source Renderer Researcher** — Phase 2 Tier 1 + Phase 4.
4. **Sandbox & IR Integration Reviewer** — Hard Constraints on every proposal (sandbox vs render worker, `ops.jsonl`, Python pin, Edit Graph).
5. **Synthesis / Documentation Agent** — Phase 6 deliverable; flags contradictions.

### Workflow

1. Orchestrator assigns the 5 roles. No extra agents without a stated gap.
2. **Agent 1 completes Phase 0 before anyone else does substantive work** (blocking).
3. Agents 2–4 run in parallel after ground-truth exists.
4. Agent 5 consolidates → Phase 6 doc.
5. Orchestrator presents to AH64 → **STOP**.

---

## Constraints (investigation conduct)

- Correctness of investigation over speed of investigation.
- Do not preserve architecture if Phase 0/1 evidence says otherwise.
- Reuse mature open-source components when beneficial, subject to Hard Constraints.
- Justify architecture with Phase 0 facts or Phase 1 measurements — not generic industry lore.
- Optimize for long-term maintainability, not only a single benchmark spike.
- Prefer patterns proven in **MLT-based editors** (Kdenlive/Shotcut) before Tier-2 closed-source mimicry.

---

## Execution gate

| Step | Owner | Status |
|---|---|---|
| Save / review this master plan | Orchestrator | **Done (this file)** |
| Green light to run Phase 0 | AH64 | **Granted (Phases 0–6 investigation ran 2026-08-02)** |
| Phases 0–6 investigation | 5 agents as above | **Done** — see Phase 6 output below |
| Implementation | — | **Forbidden until AH64 approves Phase 6 architecture** |

---

## Phase 6 output (Synthesis)

**Architecture proposal:** [`docs/superpowers/specs/2026-08-02-open-edit-rendering-architecture.md`](../specs/2026-08-02-open-edit-rendering-architecture.md)

**WAITING AH64 APPROVAL — no implementation.**

Do not start Phase 7 / do not change `open_edit/` until AH64 green-lights that architecture doc.

---

## References (seed for agents — not Phase 0 substitutes)

- `docs/superpowers/plans/2026-08-01-render-pipeline-fix.md` — frame-server + quality tiers + cache key.
- Graph nodes: `render_project()`, `materialize_remotion_compositions()`, `build_pipe_commands()`, `run_pipe()`, `RenderCache`, `EditGraphStore`.
- Kdenlive timeline preview + proxy docs (Tier 1).
- Shotcut FAQ / v26.1 hw decode notes (Tier 1).
- Resolve/Premiere cache articles (Tier 2 — unverified).
- Phase 0–6 specs: `docs/superpowers/specs/2026-08-02-render-*.md` + `2026-08-02-open-edit-rendering-architecture.md`.
