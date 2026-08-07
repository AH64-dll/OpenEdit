# OpenEdit Review Studio — Redesign PLAN (consolidated from Stage 1)

## Design language (from reference, inspired-not-copied)
- "Apple calm × Codex glass × NLE density": dark graphite studio, ONE accent = Apple blue #0071e3 (CTAs/play/active/playhead only), semantic colors success #16a34a / warn #eab308 / danger #dc2626 as 16–40% alpha tints w/ pastel text.
- Glass surfaces: backdrop-filter blur 10–18px, translucent white hairlines 14–22% alpha instead of solid borders, oklab color-mix, ambient radial accent glow.
- Typography: SF Pro Display/Text/Mono stacks (fallback Inter/JetBrains Mono — current Google Fonts link), display for logo/titles -0.015em tracking, uppercase 11px/600/0.06em micro-labels, mono 9–13px tabular-nums for all timecodes/meta.
- Motion: 150ms fast / 220ms base cubic-bezier(.28,0,.22,1); :active scale .97; hover = white 4–14% background lift; selection = accent 12–16% wash + 40% accent border; :focus-visible 4px accent halo; prefers-reduced-motion kill switch; one keyframe softPulse.
- Radii 8/12/18/980(pill); elevation 0 24px 64px black 45% + 1px light ring; spacing 4–48px.
- Layout: 48px glass topbar; workspace grid 240px|1fr|260px + bottom timeline panel; list-item component (thumb+name/sub+meta/status-pill) reused across assets/edits/renders/notes; clip color language v=blue/a=green/ov=amber; custom transport controls (⏮▶⏭ + timecode) around the <video>; agent dock compact under preview (status pill, bubbles, prompt chips, textarea+Send).
- Responsive: rail folds to strip at 1100px, workspace stacks at 900px.

## What stays (features — must ALL keep working)
project select/create/refresh; provider+model selects; tools-warn; ⌘K; theme toggle; panel toggles; settings modal (runtimes + BYOK); stop; WS dot; assets tab w/ dropzone+upload+progress+preview modal; edit-graph list w/ undo/delete + detail panel; renders list + proxy/final render + encoder select + job polling + degraded warn; notes (playhead add + summary); agent chat (WS text/tool_start/tool_result/done/cost_update/verify; status/verify/cost pills; prompt chips; reconnect); preview <video> HTTP-Range streaming (render + asset endpoints); timeline (DOM: ruler ticks+labels, clips, overlay/remotion/edit/note markers, playhead scrub, zoom in/out/fit, timecode copy, empty state); cmd-K palette; toast; review-only vs agent mode (server-side class on <body>).

## The CONTRACT (must never break — see CONTRACT.md)
- 68 element IDs (listed in STAGE1_CUR_INVENTORY.md §5.1)
- JS-emitted classes (.timeline-*, .msg .msg-user/.msg-bot/.msg-error, .tool-card .gear .tool-*, .render-card, .prompt-chip, .search-results .result-*, .empty-state, .spinner, .panel-tabs .tab, .modal*, .hidden, [data-modal-close], [data-tab], .status-pill-ish equivalents created by chat.js, etc.)
- 3 inline CSS var names in app.js: --green, --text-dim, --border (keep these names; can add new vars)
- window.OpenEdit.__testHooks; test-pinned strings 'Review artifact · 640×360' and 'Source media'
- data-od-id attributes used by tests/serve

## Logo (mission-critical)
- Mark = MONITOR/SQUIRCLE that IS the letter O (no inner O glyph anywhere; no literal 'O' text inside).
- Optical size = capital O of the wordmark (mark height ≈ 0.728 × wordmark font-size; ~22–24px).
- Recommended: CSS squircle-screen: rounded-rect (border-radius ~38%), gradient screen surface (accent blue → darker), bezel hairline, subtle screen glow, optional tiny stand. Pure CSS/SVG, inline in index.html (no external asset).
- Wordmark: "open" + "Edit" (display font, -0.015em tracking); the mark replaces the O position (open▮Edit).

## Implementation order (Stage 2, two orchestrators in parallel)
A (style): 1) tokens+base in style.css (rewrite ~95% wholesale) 2) components+layout 3) safe markup edits in index.html + logo. B (backend): 1) required app.js patch (theme icon + any hooks for new chrome) 2) feature verification against live server 3) automated screenshots + pytest suite.
Parallel coordination: A owns index.html/style.css; B owns app.js/js/* (B may NOT edit style.css/index.html except the agreed one-line theme-icon patch — or coordinate via CONTRACT.md updates). A's markup edits MUST preserve the 68 IDs + classes + modal ids. B verifies continuously against :8000.
