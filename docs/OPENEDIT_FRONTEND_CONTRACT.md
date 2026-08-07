# OpenEdit Front-End Contract (for redesign)
Source: open_edit/serve/static/ (vanilla JS SPA, no framework, no CSS lib)

## Files
- index.html (329 ln): topbar / left panel (assets+edits+notes tabs) / center (preview + chat agent-only) / right panel (renders + style) / timeline panel / modals (cmd-k, new-project, notes, settings, asset-preview) / toast
- style.css (1565 ln): 37 CSS vars in :root (dark only) — bg/accent/semantic/radii/layout/motion/fonts; 134 classes; @media 1023px + 600px; NO light-theme rules (toggle is a no-op today → fix in redesign)
- app.js (1942 ln) + js/{api,assets,chat,dom,state,ws}.js

## JS contract (must keep working)
- ~82 element IDs queried by JS (btn-*, panel-*, timeline-*, modal-*, chat-*, preview-*)
- Theme: documentElement data-theme attr + localStorage 'open-edit-theme'
- Timeline: DOM-built (renderTimeline): track labels col, ruler, playhead, tracks area;
  classes built in JS: track-kind-badge, timeline-clip, timeline-edit-marker, timeline-note-marker
- Server API: /api/projects, /api/projects/{id}, /api/projects/{id}/renders, /api/llm/providers, ws chat

## Redesign strategy
1. Swap :root tokens (colors/fonts/radii/shadows/motion) to chosen design system tokens.css
2. Add real light theme ([data-theme="light"] var overrides)
3. Restyle components via class changes; keep all IDs; update JS-built classes in js/dom.js+app.js in lockstep
4. Verify live at :8000 (serve --review-only, OPEN_EDIT_PROJECTS_ROOT=/home/amr/Videos)
