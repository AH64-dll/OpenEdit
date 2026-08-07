# OpenEdit Front-End Redesign via Open Design — PLAN

## Phase 0 — DONE (investigation + connectivity + pipeline smoke test)

### MODE-B READINESS (2026-08-06, proven)
- PATCH /api/projects/74a72af0... (project "Untitled") metadata.linkedDirs =
  ["/home/amr/apps/mlt-pipeline/open_edit"] → Open Design runs can READ the real
  OpenEdit front-end (read-only reference) and WRITE redesigned files into the project.
- Probe run (runId 0004ac7c): opencode agent read open_edit/serve/static, produced
  PROBE.md with findings IDENTICAL to my inventory (vanilla JS ESM, 37 CSS vars,
  82 ids, light theme unimplemented). Write path verified (PROBE.md in project).
- Mode B is fully operational: style choice + prompt → start_run → get_run → files.

### SMOKE TEST (2026-08-06, done)
- Open Design run pipeline verified end-to-end: create_project("redesign-smoke-test")
  → start_run(prompt=...) → get_run → **status: succeeded** in ~2 min (opencode agent)
- Produced a real 11.4KB `index.html` "Nova Studio — Design Shell" (dark studio app:
  topbar/sidebar/main/timeline grid, oklch tokens) at
  /home/amr/Documents/open-design/.od/projects/redesign-smoke-test-63c6/index.html
- API gotchas: get_run uses `runId=` kwarg; get_file uses `path=` (not name).


### Target: OpenEdit front-end (the thing being redesigned)
- Served by `open_edit serve` → Review Studio at open_edit/serve/static/ (live at http://127.0.0.1:8000)
- **Vanilla JS SPA, no framework, no CSS library** — 3 core files:
  - `index.html` (329 lines): topbar (project selector, provider/model, theme toggle, panels), assets panel, renders panel, timeline, chat (agent mode), command palette, settings
  - `style.css` (1565 lines): dark "Professional NLE" theme, **all theming centralized in `:root` CSS custom properties** (`--bg`, `--accent`, `--radius`, `--font-sans`...) → ideal for design-system swaps
  - `app.js` (1942 lines) + `js/{api,assets,chat,dom,state,ws}.js`: UI logic; component contract = element IDs/classes

### Open Design (the design engine) — CONNECTED
- Daemon v0.14.2 running at http://127.0.0.1:7456 (gotcha: needs Node 24 via nvm; system Node 26 breaks better-sqlite3)
- **MCP server connected + installed as Prime Agent skill `opendesign`** (auto-starts the daemon):
  - 18 tools: projects/files (get_file, write_file, create_artifact, search_files...), design runs (start_run, get_run, cancel_run), skills/plugins/agents discovery
  - **152 design-system resources** over MCP: `od://design-systems/<id>/DESIGN.md` (200+ systems: linear-app, arc, shadcn, brutalism, glassmorphism, apple, spotify, ...)
  - 162 skills incl. **redesign-existing-projects** (scan→diagnose→fix, keeps existing stack), frontend-design, design-taste-frontend, taste-skill
  - `start_run` can spawn **opencode** agent for autonomous design work

## Phase 1 — Style selection (AWAITING USER)
1. User picks a design system (or I present curated options with DESIGN.md summaries).
2. I read `od://design-systems/<id>/DESIGN.md` + `tokens.css` + `components.html` via MCP.
3. Optionally create a fresh Open Design project seeded with that design system.

## Phase 2 — Design execution (per user instructions)
Mode A (recommended): I pull design tokens/components from Open Design + its skill guidance,
   then implement in OpenEdit myself — full control, keeps app.js contract.
Mode B: start_run with redesign-existing-projects on an Open Design project linked to the
   OpenEdit front-end dir (native flow; Open Design's agent does the work, I review + integrate).

## Phase 3 — Implementation
1. Swap `:root` tokens in style.css (colors, fonts, radii, shadows, motion) to the chosen system.
2. Restructure index.html markup/components per the design system's component library.
3. Update app.js/dom.js class names in lockstep (or keep IDs, restyle classes).
4. Iterate live against the running server (browser refresh + screenshots).

## Phase 4 — Verification & iteration
- Screenshots at each step for the user; they review and direct refinements.
- Keep functionality intact: all panels, timeline, chat, command palette, theme toggle.

## Open questions for user
1. Which style/design system? (I can summarize the library)
2. Mode A (I implement from Open Design tokens) or Mode B (Open Design's agent implements)?


## REDESIGN v1 SHIPPED (2026-08-06)
- Open Design run 9c343f51 (opencode, ~10.5 min) on project "openedit-redesign"
  (linkedDirs -> /home/amr/apps/mlt-pipeline/open_edit) — skill: none (plain prompt
  with full contract), design system chosen by agent: **linear-app**.
- Deliverables (in .od/projects/openedit-redesign-ea50/): index.html (17KB),
  style.css (45.7KB), DESIGN_NOTES.md.
- INTEGRATED into open_edit/serve/static/ (backup: static.bak.20260806_154241).
- VERIFIED: all 82 ids preserved; 76/77 runtime classes styled (edit-status- is a
  dynamic prefix); 13 [data-theme="light"] rules (REAL light theme — fixes the
  no-op toggle bug); 72 CSS vars; no frameworks; full pytest 1467 passed.
- Screenshots: docs/redesign/redesign_dark.png + redesign_light.png.
- Live: http://127.0.0.1:8000 (serve --review-only, projects root /home/amr/Videos).

### v1 FUNCTIONAL VERIFICATION (playwright + google-chrome headless, live UI)
10/10 checks PASS (docs/redesign/FUNCTIONAL_VERIFICATION.md): page load, project
dropdown, timeline render (1 clip video project), ruler+playhead, panel toggles,
cmd palette, theme toggle -> REAL light theme (bg #f5f6f7), light vars, toast,
body content. Zero JS console errors (only pre-existing favicon 404).
