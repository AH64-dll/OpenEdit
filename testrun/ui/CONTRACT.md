# UI CONTRACT (binding) — Stage 2 workers must preserve ALL of this

## Element IDs (68) — keep ids; renaming requires a lockstep app.js update
 — element IDs app.js/chat.js/ws.js/assets.js/dom.js REQUIRE (must keep ids or update JS in lockstep)
`#project-select` `#btn-new-project` `#btn-refresh-project` `#btn-create-project` `#new-project-name`
`#assets-list` `#dropzone` `#file-input` `#upload-progress`
`#edit-graph-list` `#edit-detail-panel` `#edit-detail-kind` `#edit-detail-status` `#edit-detail-author` `#edit-detail-id` `#edit-detail-payload` `#btn-edit-undo` `#btn-edit-delete`
`#preview-player` `#preview-empty` `#preview-mode-badge`
`#chat-log` `#chat-input` `#btn-send` `#btn-stop` `#btn-topbar-stop` `#chat-status` `#verify-chip` `#cost-badge` (+ inner `.chat-status-text` `.verify-chip-text` `.cost-badge-text`)
`#renders-list` `#btn-refresh-renders` `#btn-render-proxy` `#btn-render-final` `#render-encoder-select` `#renders-degraded-warn` (created on demand)
`#notes-summary` `#btn-show-notes` `#notes-list`
`#timeline-panel`(data-od-id) `#timeline-timecode-label` `#timeline-duration-label` `#btn-copy-timecode` `#btn-add-note-playhead` `#btn-timeline-zoom-in` `#btn-timeline-zoom-out` `#btn-timeline-fit` `#timeline-track-labels` `#timeline-ruler-col` `#timeline-playhead` `#timeline-ruler` `#timeline-tracks-area` `#timeline-empty-msg`
`#conn-status` `#btn-cmd-k` `#cmd-input` `#cmd-list` `#modal-cmd-k` `#btn-toggle-theme` `#btn-settings` `#btn-toggle-left-panel` `#btn-toggle-right-panel` `#btn-left-panel` `#btn-right-panel` `#left-panel` `#right-panel`
`#llm-provider-select` `#llm-model-select` `#llm-tools-warn`
`#modal-new-project`(via `$('#new-project-name')` only + showModal id) `#modal-asset-preview` `#asset-preview-title` `#asset-preview-video` `#modal-notes` `#modal-settings` `#settings-runtimes-list` `#key-anthropic` `#key-openai` `#key-opencode` `#key-antigravity` `#btn-save-settings-keys` `#toast`
(showModal/hideModal use `$('#'+id)` — modal ids `modal-cmd-k`, `modal-new-project`, `modal-asset-preview`, `modal-notes`, `modal-settings` are referenced by name in JS.)


## Classes & attributes (JS-emitted / JS-queried)

- `.modal`, `.modal-backdrop`, `.modal-card(-wide)`, `.hidden` (display:none !important), `[data-modal-close]` (buttons + backdrop).
- `.panel-tabs .tab` + `.tab-content[data-tab="…"]` + `data-tab` values `assets`/`edits`; `.panel-tabs .tab[data-tab="edits"]` clicked by timeline edit markers.
- `.empty-state` (removed by chat.js when first message arrives), `.msg .msg-user .msg-bot .msg-error`, `.tool-card .gear .tool-body .tool-name .tool-input .tool-result(.failed)`, `.spinner`, `.search-results(-placeholder)` grid `.result-card .result-thumb .result-body .result-title .result-meta .license-badge(.attr-required/.permissive) .result-attribution .result-import-btn`, `.render-card`, `.prompt-chip` + `data-prompt` attribute.
- `.timeline-*`: `.timeline-track-row`, `.timeline-clip(.video-clip/.audio-clip)`, `.timeline-overlay-marker`, `.timeline-remotion-marker(.pending)`, `.timeline-edit-marker(.reverted)`, `.timeline-note-marker`, `.timeline-ruler-tick(-line/-label)`, `.timeline-track-label-row`, `.track-kind-badge(.video/.audio)`, `.timeline-empty-state`; `#timeline-ruler-col[data-scrub-bound]` flag.
- Body classes toggled by JS: `review-only-mode`, `panel-left-collapsed`, `panel-right-collapsed`; `has-timeline` (static in HTML); `.open` on `#left-panel`/`#right-panel` (mobile drawers); `agent-only`/`review-only`/`mobile-only` visibility classes driven by CSS + review-mode body class.
- `.chat-status[data-state]`, `.cost-badge[data-source]`, `.verify-chip[data-state]` attributes are set by JS state machines (tests intercept `setAttribute`).
- `data-od-id` attributes (30 in index.html — reference-compatible ids): topbar, logo, btn-new-project, btn-refresh-project, btn-cmd-k, btn-toggle-theme, btn-toggle-left-panel, btn-toggle-right-panel, btn-settings, btn-topbar-stop, btn-left-panel, btn-right-panel, conn-status, layout, panel-left, panel-center, btn-send, panel-right, btn-refresh-renders, btn-render-proxy, btn-render-final, btn-show-notes, timeline-panel, btn-copy-timecode, btn-add-note-playhead, btn-timeline-zoom-in/out/fit, btn-create-project, btn-save-settings-keys. (Used by reference harness/automation — keep them.)

