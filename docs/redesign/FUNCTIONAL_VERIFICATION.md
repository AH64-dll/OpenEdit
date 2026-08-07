# Redesign v1 — Functional Verification (playwright + chrome, live at :8000)

| check | result |
|---|---|
| page loads (title) | PASS |
| project dropdown populates (API /api/projects 200) | PASS |
| timeline renders clips (video project: 1 clip, 2 label rows) | PASS |
| timeline ruler + playhead present | PASS |
| left panel toggle (open 260px / collapse display:none) | PASS |
| command palette opens (⌘K) | PASS |
| theme toggle flips data-theme + REAL light bg (rgb(245,246,247)) | PASS |
| light theme vars applied (--bg=#f7f8f8) | PASS |
| toast fires | PASS |
| body content present | PASS |
| JS console errors | NONE (only pre-existing favicon 404) |

Notes: review-only mode auto-collapses the left panel at startup (by design);
panel toggles use body.panel-left-collapsed + grid reflow.
