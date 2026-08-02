# Session Compact — Open Edit Render (2026-08-03)

> Durable handoff for new turns / agents. Prefer this + brain-memory over re-reading the full chat.

## Status

| Item | State |
|---|---|
| Harden Asset Pipeline | **Done** — commit `94a9fde` on GitHub `origin/main` |
| Render investigation Phases 0–6 | **Done** |
| Architecture proposal | **Approved for implementation planning** (AH64 2026-08-03) |
| Implementation plans (3 tracks + master index) | **Written — waiting AH64 execute approval** |
| Implementation code (preview/Remotion engine) | **Not started** |

## Architecture verdict (verified vs Phase 0/1)

| Claim | Verified? |
|---|---|
| Preview today = full-timeline MP4, not live scrub | **Yes** (Phase 0) |
| Remotion ~50–60% of overlay-heavy proxy wall (~8 s/comp serial) | **Yes** (Phase 1 B/C) |
| Keep melt→ffmpeg for final / whole-file proxy artifact | **Yes** — pipe still needed; Remotion is the editing tax |
| Add chunked timeline preview for HTML5 scrub | **Yes** — Tier-1 Kdenlive pattern; only path to “instant” feel |
| Hard Constraints broken: none (host worker) | **Yes** |
| Remotion as external bake-then-OpenEdit is wrong UX | **Yes** — AH64: Remotion must be **in-pipeline engine** (same-pass / on-demand), not a separate program relay |

**Plan health:** coherent, measurement-backed, constraints-clean. Gap to close in planning: elevate **Remotion frame-engine integration** (same-pass pull) alongside dirty rematerialize — not only “faster file bake.”

## Key paths

| Doc | Path |
|---|---|
| Master investigation plan | `docs/superpowers/plans/open-edit-rendering-optimization-plan.md` |
| Architecture (Phase 6) | `docs/superpowers/specs/2026-08-02-open-edit-rendering-architecture.md` |
| Ground truth / Phase 1 / Remotion / industry / sandbox | `docs/superpowers/specs/2026-08-02-render-*.md` |
| Migration phases | Architecture §10 — M0…M5 |

## Migration order (approved direction)

1. **M0** — naming + instrumentation (non-breaking)  
2. **M1** — Remotion dirty/parallel/cache/QC + **in-pipeline engine design toward same-pass**  
3. **M2** — per-asset source proxies  
4. **M3** — chunked preview + HTML5 scrub  
5. **M4** — live MLT only if M3 insufficient  
6. **M5** — final export polish  

## Product priority (AH64)

**Open Edit = MCP server first.** Optimize `query_project` / `edit_project` / `trigger_render` / `get_render_job`. Review Studio / solo browser use is secondary; solo-only configs that slow or fork the MCP path are candidates for deletion. M3 ships MCP chunk jobs first; Review Studio playlist UI is optional.

## Orchestra

- **Orchestrator:** Grok (this session)  
- **Planning subagents:** GPT Luna 5.6 (`gpt-5.6-luna-max`) — all three tracks complete  

## Implementation plans

| Doc | Role |
|---|---|
| [Master index](../plans/2026-08-03-open-edit-rendering-implementation.md) | Order, shared-file rules, AH64 gate |
| [Remotion M0/M1](../plans/2026-08-03-remotion-in-pipeline-engine.md) | 10 tasks — dirty/parallel + frame engine |
| [Source proxies / QC M2](../plans/2026-08-03-source-proxies-and-qc-policy.md) | 8 tasks |
| [Chunked preview M3](../plans/2026-08-03-chunked-timeline-preview.md) | 16 tasks |

**Next:** AH64 approves master index (recommend execute M0/M1 first).

## Explicitly out of this compact

- Uncommitted asset-indexer / visual-effects-library / graphify caches (left unstaged)  
- timeline-test creative editing (separate from render rebuild)  
