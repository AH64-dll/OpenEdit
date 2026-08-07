# Stage 3 Code Review R2 — OpenEdit Review Studio (Redesign)
Reviewer: review-code R2 (DeepSeek V4 Flash) · Round 2 · Date: 2026-08-06
Scope: 4 coordinator fixes since R1 — (1) js/dom.js `fmtTime` epoch-seconds; (2) app.js review-mode settings early-return; (3) app.js render-card class; (4) style.css logo-text 16px + light-theme remap + grid 3-col revert.
Sources: open_edit/serve/static/{app.js,style.css,index.html}, js/dom.js, js/state.js, open_edit/serve/projects.py, open_edit/serve/routers/config.py, open_edit/kernel/render_jobs.py, open_edit/storage/render_snapshots.py, git diff (HEAD ce93e42 → working tree), testrun/ui/CONTRACT.md, testrun/ui/REVIEW_CODE_R1.md.

---
## Summary
| # | Item | Verdict | Confidence |
|---|---|---|---|
| 1 | `node --check` all JS files | **PASS** | 100% |
| 2 | 4 fixes syntactically correct; contract intact (IDs, classes, `__testHooks`, pinned strings) | **PASS** (fix 3 partial — see item 4) | 96% |
| 3 | style.css ordering: `.logo-text` final wins; `[data-theme="light"]` after dark `:root`; no duplicate selectors; grid collapsed 3-col + rails in tracks | **PASS** (2 notes) | 94% |
| 4 | NEW dead code / regressions introduced by the fixes | **FAIL — 1 issue (fix 3 CSS lockstep)** | 95% |

---

## 1. Syntax gates — PASS
`node --check` on **all 7 JS files**: `app.js`, `js/api.js`, `js/assets.js`, `js/chat.js`, `js/dom.js`, `js/state.js`, `js/ws.js` — **7/7 OK, exit 0, no output**. (R1's 7-file set unchanged; the 4 fixes only touch app.js + js/dom.js + style.css.)

Frontend contract suites re-run (same 8 files as R1): `test_serve_chat_status`, `test_serve_search_assets`, `test_serve_cost_badge`, `test_serve_send_reconnect`, `test_serve_loading_state`, `test_serve_module_structure`, `test_serve_asset_stream`, `test_review_ui` → **44 passed, 0 failed, exit 0** (14.4 s).

## 2. The 4 fixes — syntax + contract

### Fix 1 — js/dom.js `fmtTime` epoch-seconds: PASS
```js
let value = iso;
if (typeof value === 'number' || /^\d{9,10}(\.\d+)?$/.test(String(value).trim())) {
  value = Number(value) * 1000;
}
const d = new Date(value);
if (Number.isNaN(d.getTime())) return String(iso);
return d.toLocaleString();
```
- Syntax OK (`node --check`). Logic matches the **actual backend timestamp sources**, verified in Python:
  - `job.updated_at` — `float` epoch seconds (kernel/render_jobs.py:36) → serialized as number.
  - `st.st_mtime` — float epoch seconds (serve/projects.py:555, 573).
  - notes `timestamp = float(anchor.get("t_start"))` — epoch seconds (serve/projects.py:263, 270).
  - `snap.created_at` — ISO 8601 **string** (storage/render_snapshots.py:28) → falls through the regex (contains `-`/`T`) to `new Date(iso)`. ✓
- All four formats handled; 9–10-digit numeric strings (defensive) covered by the regex; NaN guard replaces the pre-fix `"Invalid Date"` leak with the raw value. Epoch-millis numbers are never produced by this backend, so the unconditional `number → ×1000` is safe today.
- Callers unchanged (`fmtTime(r.timestamp)` in renderRendersList, `fmtTime(n.timestamp)` in renderNotesList); no contract IDs/classes/strings touched. No test pins fmtTime output format.

### Fix 2 — app.js review-mode settings early-return: PASS
```js
showModal('modal-settings');
if (document.body.classList.contains('review-only-mode')) {
  if (rList) { rList.innerHTML = ''; rList.appendChild(el('div', { class: 'note-item muted small' }, [...note...])); }
  return;
}
```
- Placed **after** `showModal` (modal opens), **before** the two fetches — no `/api/runtimes` / `/api/settings/keys` request is made in review mode.
- Premise verified server-side: both endpoints call `_require_agent_mode()` → 404 in review-only mode (serve/routers/config.py:43–45, 138–144, 147–152) — the fix removes two guaranteed 404 fetches and the resulting "Failed to load settings" toast.
- The guard actually fires: `review-only-mode` is added to `<body>` at boot from `/api/ui-config` (app.js:1384–1388).
- The note uses contract classes (`.note-item .muted .small`); `#settings-runtimes-list`, `#key-anthropic/openai/opencode/antigravity`, `#btn-save-settings-keys` all still present in index.html modal markup. Save-button behavior in review mode (PUT → 404 toast) is unchanged from pre-fix.

### Fix 3 — app.js render-card class: PASS (JS side) — FAIL (CSS lockstep, see item 4)
- `renderRendersList` now emits `class: \`render-card render-status-${status}\`` (app.js:455). HEAD baseline emitted `render-item` (git show HEAD:app.js); contract lists `.render-card` as a JS-emitted class → JS now matches contract.
- All 7 JS files: **0 occurrences of `render-item`**, `render-card` in app.js (list) + chat.js (chat tool card). No test pins either class in the renders list.

### Fix 4 — style.css (logo-text, light remap, grid): PASS (see item 3)

### Contract sweep (unchanged by fixes, re-verified)
- **IDs**: all 81 contract IDs present in index.html (`missing = []`); 0 true duplicate `id` attrs (93 unique; the 25 apparent `×2` hits are regex artifacts — `data-od-id="…"` contains the substring `id="…"`). `data-od-id`: exactly **30 unique**, matches CONTRACT list.
- **`__testHooks`**: 12 hooks intact (normalizeAssets, normalizeEdits, normalizeTimeline, normalizeRenders, normalizeNotes, summarizeOpPayload, openAssetPreview, createChatStatus, createCostBadge, appendSearchResults, sendChatMessage, handleSend).
- **Pinned strings**: `"Review artifact · 640×360"` ×2 in app.js (renderRendersList modeLabel + loadRenderInPreview badge) ✓; `"Source media"` ×1 ✓; `"Proxy 720p"`/`"540p"` absent ✓; `id="cost-badge"` present ✓.
- Classes/state machines (`.chat-status[data-state]`, `.cost-badge[data-source]`, `.verify-chip[data-state]`, body classes) untouched.

## 3. style.css structural checks

### 3a. `.logo-text` final rule wins — PASS
- Legacy rule: line 198–205 `.logo-text { … font-size: 13.5px; … }`.
- Studio rule: line 2367–2375 `.logo-text { … font-size: 16px; … }` with comment documenting the optical-size contract.
- Same specificity (0,1,0), studio block later (2367 > 198) → **16px wins**. Wordmark/mark ratio = 16/22 = **0.727 ∈ [0.72, 0.75]** ✓. (This is a real fix: pre-fix, the span fell back to the legacy 13.5px → 13.5/22 = 0.614, off-spec.)
- Note: ≤560px media query (line 2950) scales `.logo` to 14px but not `.logo-text` (stays 16px; mark 20px → ratio 0.8) — cosmetic, desktop-topbar spec unaffected.

### 3b. `[data-theme="light"]` ordering — PASS
Source order: legacy light block **line 85–118** (remapped to linear light neutrals: `--bg:#f5f5f7`, `--text:#1d1d1f`, `--border:rgba(0,0,0,.12)`, `--accent:#0071e3`, `--green:#16a34a`, `--yellow:#b45309`; **zero CRT green/amber values remain**) → … → dark studio `:root` **line 2171–2200** → **`[data-theme="light"]` studio overrides line 2202–2216** (AFTER the dark :root → wins for `--studio-*`: bg #f5f5f7, elev #fff/#e8e8ed/#d2d2d7, ink #1d1d1f, line rgba(0,0,0,.12/.2), accent #0071e3) → legacy dark `:root` 2219–2271 → `--oe-*` alias `:root` 2275–2300 (resolves studio vars first).
- The visible UI is driven by `--oe-*`/`--studio-*` (studio layer redefines every major component: `.btn`×19, `.modal*`×7, `.topbar*`×18, `.panel*`×27, `.layout`×9, `.project-select`×6 — verified by rule scan after line 2164), so light mode now resolves light via the 2202 block.
- The two root-level `[data-theme="light"]` blocks (85, 2202) set **disjoint variable sets (overlap = ∅)** → no cascade conflict between them.
- Note (pre-existing, values improved): legacy vars set at line 85 are still overridden by the later dark `:root` at 2219 for legacy-var consumers (equal specificity, later wins) — but no visible studio component uses legacy color vars directly (only the token blocks themselves and font aliases). Studio light theme works; legacy-var leftovers stay dark. Design-level nit for reviewer A, not a contract break.

### 3c. No duplicate selectors introduced — PASS (1 note)
- New/changed rules from the fixes: studio `.logo-text` (2371, extends the pre-existing studio logo block), `[data-theme="light"]` root (2202), `.layout` collapsed variants (2563–2565), rails-in-tracks block (2985–2990). None is a duplicate of an existing rule *with overlapping properties*; the 2202 block duplicates the 85 selector string but has zero property overlap (see 3b).
- Pre-existing legacy/studio selector pairing (`.logo` ×3, `.logo-text` ×2, `.layout` ×3 incl. media queries) is the redesign's intentional compat pattern, unchanged by the fixes.

### 3d. Grid collapsed rules consistent (3-col + hidden rails kept in tracks) — PASS
- Desktop: `.layout { grid-template-columns: 240px minmax(0,1fr) 260px }` (2533).
- Collapsed (2563–2565): `0 minmax(0,1fr) 260px` / `240px minmax(0,1fr) 0` / `0 minmax(0,1fr) 0` — **3 tracks always, zero-width rails stay in tracks**.
- ≤1100px (2917–2919): `200px minmax(0,1fr) 220px` + matching 0-track collapsed variants.
- ≤900px (2936, 2941–2944): single column `minmax(0,1fr) !important` stack; rails re-shown (`display:flex; visibility:visible`).
- ≥901px (2985–2990, end-of-file): collapsed rails `display:flex !important; visibility:hidden` — kept in their 0-width tracks so auto-placement never moves the center preview (comment documents intent). Consistent with rubric D's 0/1fr/260 review-only geometry.
- Dead legacy 2-col collapsed rules (1684–1688: `1fr var(--sidebar-w)` etc.) are overridden by the later same-specificity studio rules — pre-existing (R1), not introduced by the fixes.

## 4. NEW dead code / regressions — FAIL (1 issue)

### Issue A (NEW from fix 3): CSS list-item selectors not renamed with the JS class
`renderRendersList` now emits `.render-card`, but the stylesheet's renders-*list* styling still targets `.render-item` — **22 rules now dead**:
- Studio layer (the rules that actually styled the list): 2619 `.asset-card,.edit-card,.render-item,.note-item` (base card: width:100%, grid, padding 8px 9px, bg surface-2 22%, radius 12), 2633 hover, 2634 active, 2662 `.render-item { grid-template-columns: 34px minmax(0,1fr); cursor: pointer; }`.
- Legacy layer: 938–982 (12 rules) + duplicated legacy blocks 1823–1831 and 2044–2053 (6 rules).

Consequences for the renders list (JS emits only `render-card`):
- Items now fall into the **chat tool-card rules** `.tool-card, .render-card` (2796): `width: min(90%, 680px)`, `font-size: 10px`, no `cursor: pointer`, no hover/active feedback; and `.render-card` (2803) adds the success-green text tint (largely masked by child rules, but present).
- `.render-status-running/.render-status-failed` border colors (2663–2664) are overridden by the later `border:` shorthand at 2796 → status border tinting dead.
- Click handler still binds (functional), but the rail's card affordance (pointer cursor, hover, press, full-width) is gone. `.render-thumb` stays hidden — same as pre-fix (rule covers both classes, 1822–1827).

This is a **styling/UX regression introduced by fix 3** and **new dead code** (`.render-item` selectors). The contract itself is not broken (`.render-card` is a contract class and is still styled — for the chat context), but the fix is only half-applied.

**Recommended fix:** in the studio layer, replace `.render-item` with `.render-card` at 2619, 2633, 2634, 2662 (or scope `.renders-list .render-card`), and delete/supersede the legacy `.render-item` blocks (938–982, 1823–1831, 2044–2053); keep `.render-status-*` (class-agnostic). Re-verify: renders list cards full-width, pointer cursor, hover/active, status borders, no green tint, no dead `.render-item` selectors.

### Non-issues checked (fixes 1/2/4 introduce nothing else)
- Fix 1: no dead code; error path improved (raw value instead of "Invalid Date").
- Fix 2: early-return leaves modal fully wired; no dangling fetches/timers; no new dead code (the normal path is still reachable in agent mode).
- Fix 4: no new dead selectors (the 2202 block is live in light mode for the studio layer; the 2985–2990 block is live ≥901px). Legacy light block values were remapped but the block remains inert for legacy vars (pre-existing override by 2219) — values now harmless.
- Pre-existing R1 notes unchanged: duplicated legacy CRT logo blocks, legacy 2-col collapsed rules, `.conn-label` styling.

## Verdict
- Items 1, 2, 3: **PASS**.
- Item 4: **FAIL** — fix 3's CSS half is missing (`.render-item` → `.render-card` in 4 studio selectors + 18 legacy/dead rules), causing a renders-list styling regression. Contract, syntax, pinned strings, `__testHooks`, IDs, and all 44 frontend tests still green.
- Overall: **CONDITIONAL PASS** — unblocked for contract/syntax, **blocker for visual polish**: update the 4 studio `.render-item` selectors to `.render-card` and remove dead legacy `.render-item` rules, then re-verify renders rail rendering (screenshot).
- Confidence: **95/100** (all findings are source-verified; runtime pixel rendering of the renders rail is outside this review and belongs to reviewers D/F).
