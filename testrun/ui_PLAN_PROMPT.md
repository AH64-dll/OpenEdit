# OpenEdit UI Redesign Mission — Structured Prompt (restructured from user brainstorm)

## Objective
Redesign OpenEdit's Review Studio frontend (`open_edit/serve/static/`) so it looks and feels like the reference design in `/home/amr/Downloads/file/openedit-shell-explorer.html` — **inspired by it, not a copy**. Full creative freedom for improvements. The UI must remain **fully functional** (all existing features keep working).

## Hard requirement: the OpenEdit logo
- The logo must read as **"Open"** (OpenEdit wordmark = the new logo mark + "pen Edit" or "pen" + "Edit").
- The **O is a television/monitor screen**: a rounded square (rounded corners/center) that simultaneously looks like the letter O and a screen. **No letter O inside the monitor** — the monitor shape itself IS the O.
- Sizing: the logo mark must be the same size as a capital "O" in the wordmark, so the design matches optically.
- The logo must match the reference design's style (colors, gradients, radius, elevation, glass).

## Phases (as requested by the user)

### Stage 0 — Restructure (this doc). DONE by coordinator.

### Stage 1 — Study & Planning (5 parallel sub-agents)
- 3 study the reference HTML: (a) design language & tokens, (b) layout & components, (c) interactions/motion/typography.
- 2 study the current OpenEdit design: (a) current UI structure & features inventory (index.html/app.js/style.css), (b) gap analysis + merge strategy (what to keep, what to replace, logo design spec).
- Outputs → `testrun/ui/STAGE1_*.md` + a consolidated `testrun/ui/PLAN.md` (coordinator merges).

### Stage 2 — Execution (4 sub-agents: 2 orchestrators × 3 workers each)
- **Orchestrator A — "Style & Design"** (GPT-5.6 Luna, vision): leads 3 DeepSeek v4 Flash workers. Implements the new design system (CSS variables, tokens, layout, components, **logo**) per PLAN.md. Luna reviews rendered screenshots visually (vision).
- **Orchestrator B — "Backend & Functionality"** (GPT-5.6 Luna, vision): leads 3 DeepSeek v4 Flash workers. Connects the new UI to the backend; ensures every existing function works (project select, timeline render, preview streaming, renders list, notes, chat if present); runs the test suite + API smoke tests. Luna verifies visually that the UI works end-to-end.
- Both orchestrators work in parallel; shared files in `testrun/ui/`; no direct child↔child comms.

### Stage 3 — Review & Confidence Loop (3 sub-agents, repeat until 100%)
- 1× GPT-5.6 Luna (vision — looks at rendered pages/screenshots) + 2× DeepSeek v4 Flash (code review + functional test review).
- Review against rubric `testrun/ui/REVIEW_RUBRIC.md`: (A) design fidelity to reference, (B) logo requirement (monitor=O, no inner O, capital-O size), (C) functionality (all features work, tests pass), (D) code quality/regression risk, (E) verdict format.
- Any concern → coordinator fixes (or routes back to Stage 2) → fresh review round. Loop until **VERDICT: 100% PASS**.

## Non-negotiables
- All production edits go through `edit` (targeted string replacement) per repo AGENTS.md.
- The dev server (port 8000, Review Studio) must keep working; final verification includes real browser/API smoke tests.
- Test suite must stay green (`source .venv/bin/activate && python -m pytest tests/ -q --timeout=120 -p no:cacheprovider`).
- Logo: NO literal "O" inside the monitor; the monitor glyph itself is the O.

## Deliverables
1. New `index.html` / `style.css` / `app.js` (as needed) with the redesign + logo
2. `testrun/ui/REPORT.md` — what changed, how each feature maps, verification evidence
3. `testrun/ui/CONFIDENCE.md` — review rounds + final verdict
