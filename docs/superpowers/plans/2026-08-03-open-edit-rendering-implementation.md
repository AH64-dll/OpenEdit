# Open Edit Rendering Implementation — Master Index

> **For agentic workers:** Do not start `open_edit/` code until AH64 approves this index **and** the relevant track plan. Execute with `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans`, one track at a time per the order below.
>
> **Status:** **M0–M3 COMPLETE**; **smoke done / PR pending `gh auth`** on `feat/render-m0-m1-remotion-engine` (2026-08-03). Acceptances: [M0/M1](../specs/2026-08-03-m0-m1-acceptance.md) · [M2](../specs/2026-08-03-m2-acceptance.md) · [M3](../specs/2026-08-03-m3-acceptance.md) (manual MCP/host smoke recorded). Preview chunks still gated (`OPEN_EDIT_PREVIEW_CHUNKS=1`). Review Studio UI Tasks 11–13 skipped (MCP-first). M4 live MLT still deferred.
> **Date:** 2026-08-03
> **Orchestra:** Grok (orchestrator) + GPT Luna 5.6 planning tracks
> **Architecture:** [2026-08-02-open-edit-rendering-architecture.md](../specs/2026-08-02-open-edit-rendering-architecture.md)
> **Session compact:** [2026-08-03-session-compact.md](../specs/2026-08-03-session-compact.md)

**Goal:** Ship the approved rendering rebuild as three independently testable tracks optimized for the **MCP server** product, without breaking melt→ffmpeg final/proxy artifacts or the free-form sandbox host-worker split.

**Architecture:** Keep melt→ffmpeg for final + whole-file `mode=proxy` review artifacts. Turn Remotion into an in-pipeline frame engine (materialize remains default until frame-pull proves parity). Add per-asset source proxies with explicit emission profiles. Add `preview-chunks` as a host render job primarily for agent/MCP consumers (fast dirty-range artifacts + job status). Defer live MLT consumer to M4. Review Studio HTML5 is optional packaging of the same artifacts — never a reason to slow or complicate the MCP path.

**Tech Stack:** Python ≥3.11, Pydantic v2, pytest, melt rawvideo pipe, ffmpeg, Remotion 4.0.278 + Chromium on host worker, MCP tools (`trigger_render` / `get_render_job` / …), SQLite job service. FastAPI Review Studio is secondary.

## Product priority (AH64 2026-08-03)

**Open Edit’s primary product is the MCP server.** Agents drive edits and renders through MCP; that path must be correct, fast, and simple.

| Priority | Surface | Rule |
|---|---|---|
| **P0** | MCP tools + host render worker + CLI used by those tools | Optimize here. Acceptance gates measured here. |
| **P1** | Durable job status / artifact paths returned to agents | Must stay reliable; agents need `job_id`, paths, stage timings |
| **P2** | Review Studio / “use alone” browser UI | Keep only while it shares the MCP/job contracts with **zero** extra cost on the hot path |
| **Delete / demote** | Standalone-only config, UI copy, dual codepaths, or caches that exist only for local browser use | If they slow MCP, fork behavior, or cause bugs — **remove** rather than maintain |

Implications for this wave:

- **M0/M1 (Remotion):** MCP-critical. Dirty/parallel/cache-before-materialize/frame-engine are the main win for `trigger_render`.
- **M2 (source proxies + QC):** MCP-critical for disk and warm-hit latency; QC skip must show up in MCP job payloads.
- **M3 (chunks):** Ship the **job + manifest + artifact API** first (enqueue/poll via MCP/`trigger_render`). Review Studio playlist/MSE tasks (M3 Tasks 11–13) are **optional** — cut them if they add dual playback logic or regress MCP. Agents can open returned chunk/proxy paths externally.
- Do **not** add serve-only feature flags that change render semantics when MCP is the caller.
- Do **not** keep a “solo mode” profile that disables MCP-oriented caches or forces full-timeline re-encode “for the UI.”

## Global Constraints

- No product code until AH64 green-lights execution of this index.
- Host-worker only for melt/ffmpeg/Remotion/GPU; free-form IR stays bwrap/ops.jsonl.
- Preserve `f=rawvideo` pipe contract.
- `mode=proxy` ≠ source proxy ≠ preview-chunks — three product systems (named in MCP docs first).
- Final export always uses canonical originals, never `Asset.proxy_hash`.
- Every new cache: byte cap + eviction + wipe path.
- Remotion long-term model is same-pass/on-demand frame pull, not bake-then-stitch.
- **MCP-first:** when a design choice helps Review Studio but hurts MCP latency/correctness, choose MCP. Prefer deletion of solo-only complexity over dual maintenance.

---

## Execution mode (AH64 2026-08-03)

**Parallel wave execution** (not serial one-task-at-a-time). Grok merges/reviews each wave before the next. Subagents = GPT Luna 5.6. Exclusive file ownership per lane — no two agents edit the same file in one wave.

### M2 waves

| Wave | Parallel lanes | Owns (exclusive) |
|---|---|---|
| **M2-A** | Task 1 alone | `source_proxy.py`, `Asset`/`AssetStore` proxy_hash metadata + CAS generate |
| **M2-B** | Task 2 ‖ Task 3 ‖ Task 5-core | **T2:** `asset_proxy_jobs` + asset status/API · **T3:** emission profiles + final-original guard · **T5-core:** `storage/cache_policy.py` (+ tests) without orchestrator |
| **M2-C** | Task 4 ‖ Task 6 | **T4:** duration-budgeted QC extending M1 `qc/policy.py` · **T6:** repair/final polish |
| **M2-D** | Task 7 → Task 8 | MCP/docs + integration gate / M3 handoff |

---

### M0/M1 waves

| Wave | Parallel lanes | Owns (exclusive) | After |
|---|---|---|---|
| **0** | Task 1 alone | `diagnostics.py` + contract tests | foundation |
| **A** | Task 2 ‖ Task 3-core ‖ Task 8 | **T2:** orchestrator timing + MCP.md + melt_runner/jobs passthrough · **T3-core:** `remotion/dirty.py` + unit tests only (no orchestrator/materialize yet) · **T8:** `frame_engine.py` + `remotion_frame_server.mjs` + scaffold/packages + protocol tests | Task 1 merged |
| **B** | Task 3-wire→4→5 (one lane) ‖ Task 6-cache ‖ Task 7 | **Hot path:** materialize + orchestrator dirty/parallel/cache-before · **T6-cache:** `cache.py` eviction/LRU tests · **T7:** `qc/policy.py` + render_jobs/cli QC skip + repair early-out | Wave A reviewed |
| **C** | Task 6-alpha leftovers (if any) → Task 9 ‖ then Task 10 | Feeder gate + verification matrix | Wave B reviewed |

Review gate after each wave: I read diffs, run focused pytest, fix conflicts, then dispatch the next wave. Review Studio UI edits in Task 2 are **optional/skip** under MCP-first (MCP.md + diagnostics only).

---

## Track plans (Luna)

| Phase | Track | Plan | Tasks | Author |
|---|---|---|---:|---|
| **M0 + M1** | Remotion dirty/parallel/cache + in-pipeline frame engine | [2026-08-03-remotion-in-pipeline-engine.md](2026-08-03-remotion-in-pipeline-engine.md) | 10 | [Remotion M1](2cf080b4-0f4c-49bb-83f8-5db30b0c1add) |
| **M2 + QC/disk + M5 polish** | Source proxies, emission profiles, QC budgets, eviction | [2026-08-03-source-proxies-and-qc-policy.md](2026-08-03-source-proxies-and-qc-policy.md) | 8 | [Proxies/QC](a13e2e66-defd-44fb-a078-945cd2971b5e) |
| **M3** | Chunked preview job + MCP artifacts (Review Studio optional) | [2026-08-03-chunked-timeline-preview.md](2026-08-03-chunked-timeline-preview.md) | 16 | [Chunked preview](aed87675-9cba-407b-9d41-497f08466146) |

**Out of this wave:** M4 live MLT SDL/OpenGL consumer (only if M3 scrub UX fails).

---

## Execution order

```text
1. Approve this index + start M0/M1 Remotion plan (Tasks 1→10)
2. After M1 Tasks 5–7 land (cache-before-materialize + QC skip hooks):
     begin M2 Tasks 1–3 (source-proxy CAS + job + emission) in parallel if capacity,
     else fully sequential after M1 Task 10
3. M2 Tasks 4–6 (QC policy, eviction, repair) — require M1 cache/QC surfaces
4. M3 starts only after:
     - M1 Task 8+ (frame-engine seam proven; feeder may still be gated)
     - M2 Tasks 1–3 + 5 (emission profile + cache policy contracts)
5. M3 Tasks 1→10 + 14→16 (job/API/docs/gates) first; Tasks 11–13 (Review Studio HTML5) only if they share contracts with zero MCP cost — else skip/delete
```

### Shared-file merge rule

If two tracks touch the same file, **port into the later branch — never restore the earlier version**:

| Hot files | First owner | Second owner |
|---|---|---|
| `open_edit/render/cache.py` | M1 | M2 eviction / access metadata |
| `open_edit/render/orchestrator.py` | M1 | M2 emission + M3 range path |
| `open_edit/render/materialize.py` | M1 | M2 hooks only |
| `open_edit/kernel/render_jobs.py` | M1 QC hooks | M2 QC policy + M3 `preview-chunks` kind |
| `open_edit/qc/policy.py` | M1 skip-on-hit (may create) | M2 expands budgets/blackdetect |
| `docs/MCP.md`, Review Studio copy | M0 vocabulary | M2/M3 extend, do not rename |

**QC ownership:** M1 introduces skip-on-verified-proxy-cache-hit. M2 owns duration-budgeted detectors + final blackdetect timeout. Do not duplicate QC modules — extend `qc/policy.py`.

**Remotion ownership:** M1 owns dirty/parallel/materialize + frame_engine. M3 consumes the frame-engine seam; it must not invent a second Remotion bake path.

---

## Acceptance gates (from architecture)

| ID | Gate | Track |
|---|---|---|
| A1 | Three product systems named; proxy ≠ source proxy ≠ chunks | M0 |
| A2 | Deliverable cache hit skips Remotion materialize | M1 |
| A3 | Parallel Remotion reduces Fixture C Remotion stage vs 93.7 s | M1 |
| A4 | Remotion disk eviction under cap | M1/M2 |
| A5 | Proxy QC skip/async policy; final QC retained | M1/M2 |
| A6 | Source proxies for preview emit; final originals | M2 |
| A7 | Dirty-zone chunk scrub without full timeline MP4 | M3 |
| A8 | Audio-only edits do not invalidate video chunks | M3 |
| A9 | Free-form sandbox unchanged | all |
| A10 | `f=rawvideo` pipe preserved | all |

---

## First commit after approval

Start at Remotion plan **Task 1** (M0 diagnostics + vocabulary). Do not begin M3 scaffolding before the M1 frame-engine handoff exists.

---

## AH64 decision

MCP-first priority is locked into this index.

Approve one of:

1. **Execute M0/M1 only** (recommended first wave — highest MCP `trigger_render` win)
2. **Execute full M0→M3 sequence** under this index (M3 UI tasks optional per product priority)
3. **Request changes** to a track plan (cite section)

Until then: **no `open_edit/` product code.**
