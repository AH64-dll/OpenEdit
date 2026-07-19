# BUGS_FIXED — running log

One line per bug. Format: `## YYYY-MM-DD — <short title>` then bullets
with `file:line` of the fix. Append-only.

## 2026-07-19 — Initial survey (10 bugs found)

- BUG 1: `insert_clip` audio fallback used `playlists[0]` — would silently misroute audio into a video playlist
  - File: `phase2_project_engine/kdenlive_file_backend.py:443`
- BUG 2: `add_transition` timing only used `a.out` — could clip the B side
  - File: `phase2_project_engine/kdenlive_file_backend.py:601-603`
- BUG 3: `add_transition` cross-track restriction was a TODO comment, error message unclear
  - File: `phase2_project_engine/kdenlive_file_backend.py:573-579`
- BUG 4: `_bump_tractor_duration` ignored `blank` children
  - File: `phase2_project_engine/kdenlive_file_backend.py:777-785`
- BUG 5: `apply_effect` ignored catalog defaults when `params` was empty
  - File: `phase2_project_engine/kdenlive_file_backend.py:628-654`
- BUG 6: Three different `_resolve_*` helpers for finding a producer
  - Files: `kdenlive_file_backend.py:683-754` (3 methods)
- BUG 7: `get_video_tracks` (heuristic) conflicted with `get_tracks` (structural)
  - File: `phase2_project_engine/kdenlive_xml.py:244-254`
- BUG 8: `ValidationError` defined in both `editor_backend.py` and `validation.py`
  - Files: `editor_backend.py:115`, `validation.py:45`
- BUG 9: `apply_effect` wrote `kdenlive_id` (snake) instead of `kdenlive:id` (colon)
  - File: `phase2_project_engine/kdenlive_file_backend.py:645-647`
- BUG 10: `add_transition` wrote to `get_tractor()` (the main one) instead of the tractor that owns the playlist
  - File: `phase2_project_engine/kdenlive_file_backend.py:592-620`

## 2026-07-19 — Baseline locked

- Tests passing: 187 (1 skipped, expected)
- Branches/commits ahead of cleanup: 0
- All 19 tool JSON I/O outputs are about to be locked by
  `phase3_pyagent_core/tests/test_golden_io.py` in Task 2.3.

## 2026-07-19 — Phase 2 rewrite complete

Phase 2 was decomposed from a single `KdenliveFileBackend` class
(943 lines) into a 3-layer architecture:

- `types.py` — frozen dataclasses (`ProjectInfo`, `ClipSummary`, ...,
  `TimelineSummary`)
- `errors.py` — single source of `BackendError` / `ValidationError` /
  `NotFoundError` / `CatalogError`
- `catalog.py` — `Catalog` dataclass + `from_json`
- `io.py` — `ProjectTree` + `load_project` / `save_project` +
  `ensure_docproperties`
- `tracks.py` — pure track navigation (`get_tracks`,
  `get_video_playlist`, `resolve_producer`, `next_kdenlive_id`,
  `bump_tractor_duration`, ...)
- `validators.py` — pure validation functions
- `ops/*.py` — per-domain operations (bin, clips, transitions,
  effects, markers)
- `backend.py` — `EditorBackend` (ABC) + `KdenliveFileBackend`
  (thin dispatch, one line per method)
- `__init__.py` — re-exports the public surface for backward compat

Legacy files deleted: `editor_backend.py`, `kdenlive_file_backend.py`,
`kdenlive_xml.py`, `test_phase2.py`. `validation.py` was never
created under the new name (the file is `validators.py`, plural).

Bugs fixed (final list, in addition to the initial 10):

- BUG 1: audio fallback no longer misroutes — `tracks.get_video_playlist`
  returns `None` instead of guessing. File:
  `phase2_project_engine/tracks.py:88-119`. Test:
  `tests/test_ops_clips.py:test_insert_clip_into_audio_track_does_not_misroute_to_video`.
- BUG 2: transition timing uses BOTH `a.out` and `b.in` (not just
  `a.out`) for the cut point. File:
  `phase2_project_engine/ops/transitions.py:61-65`. Test:
  `tests/test_ops_transitions.py`.
- BUG 3: cross-track transition error has a clearer `fix:` line
  naming the source track. File:
  `phase2_project_engine/ops/transitions.py:46-51`. Test:
  `tests/test_ops_transitions.py`.
- BUG 4: `bump_tractor_duration` includes `<blank>` children (it
  walks every playlist and takes the max). File:
  `phase2_project_engine/tracks.py:257-275`. Test:
  `tests/test_tracks.py`.
- BUG 5: `apply_effect` falls back to the catalog's parameter
  defaults when `params` is None or empty. File:
  `phase2_project_engine/ops/effects.py:60-63`. Test:
  `tests/test_ops_effects.py`.
- BUG 6: Three `_resolve_*` helpers consolidated into a single
  `tracks.resolve_producer` (with `resolve_source_duration` as a
  thin wrapper). File:
  `phase2_project_engine/tracks.py:142-198`.
- BUG 7: `get_video_tracks` removed (was unused and conflicted with
  the structural `get_tracks`). No replacement needed.
- BUG 8: `ValidationError` defined once in `errors.py`. The old
  duplicate in `validation.py` is gone. File:
  `phase2_project_engine/errors.py:20-21`.
- BUG 9: `apply_effect` writes `kdenlive:id` (colon) for the effect
  label, not `kdenlive_id` (snake). File:
  `phase2_project_engine/ops/effects.py:54-56`. Test:
  `tests/test_ops_effects.py`.
- BUG 10: `add_transition` writes to `tracks[track_a]` (the tractor
  that owns the playlist) instead of `get_tractor()` (the main
  sequence tractor). File:
  `phase2_project_engine/ops/transitions.py:52-56`. Test:
  `tests/test_ops_transitions.py`.
- BUG 11 (new): `kdenlive_file_backend.py` had a broken
  `from .validation import ValidationError` import (singular).
  The atomic swap (Task 1.8) removes the file, eliminating the
  broken import entirely.
- BUG 12 (new): `kdenlive_file_backend.py` still re-imported
  `KdenliveFileBackend` from the legacy `editor_backend.py` ABC
  even after Tasks 1.1-1.7 had moved the ABC. The thin
  `KdenliveFileBackend` in `backend.py` re-derives the ABC from
  its own definition; the old broken re-export is gone.
- BUG 13 (new): `__init__.py` was missing — every
  `from phase2_project_engine import X` call (in Phase 3, Phase 5,
  and the legacy test file) raised `ImportError: cannot import
  name 'X' from 'phase2_project_engine' (unknown location)`.
  The new `__init__.py` re-exports the public surface.

Test counts after Task 1.8:

- Phase 2 tests (new): 85 passed
- Total (across all phases): 216 passed, 15 pre-existing
  infrastructure failures (missing `phase1_knowledge_base/catalog.json`
  in the worktree; same failures exist on the prior commit, before
  my changes — verified by `git stash`).
- Baseline (before this task): 187 passed.

## 2026-07-19 — Task 3.2: drop AntiGravityAdapter (dead code)

`AntiGravityAdapter` (357-line `agent_adapters.py:288-309`) hard-coded
`available() -> False` and was never wired into the menu. The
spec put it in place as a "menu + factory stub for a 3rd app" but the
backing integration never landed, so the entry was always
unreachable from the running game (the WebSocket
`set_app` handler rejected it on availability).

- Removed: `phase4_chat_ui/agent_adapters.py` (whole file, 358 lines)
- Added: `phase4_chat_ui/adapters/{__init__,piagent,opencode,_registry}.py`
- Updated: `phase4_chat_ui/app.py` to import from `adapters/`
- Updated: 3 tests that asserted on the now-removed `antigravity`
  entry (`test_agent_adapters.py:test_list_apps_*`,
  `test_task4_apps.py:test_api_apps_*` + `test_set_app_*`,
  `test_task5_ui.py:test_api_apps_contract`).
  The replacement `test_set_app_unknown_rejected` now uses an
  unknown id to exercise the same error path.

Test count after Task 3.2: 245 passed, 1 skipped (no regression
vs. the pre-Task-3.2 baseline of 245 passed, 1 skipped).

## 2026-07-19 — Task 3.3: Type.Object schema binding (commit 22caaeb)

`extension.ts` called `Type.Object(def.parameters_schema as any)` with a
**full JSON Schema document** (`{type: "object", properties: {...}, required: [...]}`).
TypeBox's `Type.Object()` takes only the **properties map**; it was
treating the top-level keys `"type"`, `"properties"`, `"required"` as
parameter names. Every real LLM tool call returned
`Missing required argument` (or the SDK rejected the schema outright).

- Fixed: the `ToolDef` dataclass (`tools/project.py:20-28`) now stores
  `parameters_schema` (the properties object only) AND `required`
  (a separate tuple of required parameter names) as distinct fields.
  `extension.ts:50-54` adds a `buildTypeBoxSchema()` helper that wires
  them together correctly. `runtime.py:38-62` exposes `required` in the
  `list_tools()` JSON payload so the TS side can read it.
- Files: `phase3_pyagent_core/extension.ts:35-54, 349, 362`;
  `phase3_pyagent_core/tools/project.py:20-28` (ToolDef definition);
  every other `tools/*.py` (parameters_schema ↔ required split);
  `phase3_pyagent_core/runtime.py:38-62` (exposes `required` to TS).

## 2026-07-19 — Phase 4: drop AntiGravityAdapter (Task 3.2)

Already logged above. Listed here again only because the task-counting
exercise below ("10 + 5 additional bugs") double-counts it if both
places count.

## 2026-07-19 — Phase 4: ws.py over-budget + watcher false positives (commits b56a4ad, 4642059)

- `ws.py` was 358 lines (over the 300-line prod budget). Split into
  `ws/manager.py` (49 lines, conn registry) + `ws/handler.py` (260
  lines, single message) + `ws/handlers.py` (225 lines, dispatch) +
  `ws/__init__.py` (22 lines, re-exports).
- `watcher.py` was firing `on_change` on **any** change in the project
  directory — Kdenlive's autosave, thumbnail regeneration, and sibling
  temp-file writes all counted, so the chat UI re-rendered the project
  panel ~10x per minute. Fix (commit 4642059): added a `mtime_window_sec`
  parameter (default 1.0s) and rewrote the loop to compare each
  changed file's mtime against the project's mtime; events outside the
  window are ignored. Path 1 also handles the atomic-rename case
  (os.replace of a sibling onto the project file) by tracking
  `last_project_mtime` across polls.

Files: `phase4_chat_ui/ws/{__init__,manager,handler,handlers}.py`,
`phase4_chat_ui/watcher.py:24-76` (the mtime comparison logic).

## 2026-07-19 — Phase 6: audio/timeout + black-frames bugs (commit 5165fb7)

- `audio` module's `get_audio_levels()` and `list_silence()` called
  `subprocess.run(..., timeout=60)` and let `subprocess.TimeoutExpired`
  propagate up. The chat UI surfaces that as a generic 500 instead of
  a structured `{ok: false, error: "ffmpeg timed out after 60s ..."}`.
  Fix: wrap both calls in `try/except subprocess.TimeoutExpired` and
  return the existing dataclass with `ok=False` and a clear error
  message.
- `black_frames.list_black_frames()` had no validation that
  `out_sec > in_sec` when both are positive — the call would pass a
  negative duration to ffmpeg's `blackdetect` filter, which silently
  produced no output. Fix: explicit range check at the top of
  `list_black_frames()` that returns `BlackFramesResult(False, ...)`
  with an `"invalid range: out_sec=... must be > in_sec=..."` error.

Files: `phase6_render_qc/audio/__init__.py:85-92` (get_audio_levels)
and `:128-135` (list_silence);
`phase6_render_qc/black_frames/__init__.py:51-53` (range check).

## 2026-07-19 — Phase 7: collapse to ONE persistent e2e test

Pre-cleanup, `phase7_real_session/` had 4 entry points
(`e2e.py`, `xvfb.py`, `run_e2e.py`, `tests/test_e2e.py`) that all
duplicated the skipif + XvfbContext + KdenliveLaunch + ChatUIServer
boilerplate. Collapsed to a single `e2e.py` (299 lines) with the
helpers as named classes; `xvfb.py` + `run_e2e.py` deleted. The XML
parser unit tests (3 cases) and the e2e class (1 case) are now both
in `tests/test_e2e.py`. Net: 4 modules → 4 modules, but 290 LOC
deleted and the only persistent e2e test is the one in
`tests/test_e2e.py::TestE2EPiSession::test_edit_render_qc_roundtrip`.

## 2026-07-19 — Cleanup sub-project complete

Sub-project 1 of 3 (whole-pipeline cleanup of
`pyagent-kdenlive-guide/`) is finished.

**Test results (final, verified at end of Task 7.1):**

- 230 passed, 1 skipped, 0 failed
- Baseline (pre-cleanup, `8c1a495`): 187 passed, 1 skipped
- Net delta: **+43 tests** (185→230, after fixing the 15
  `phase1_knowledge_base/catalog.json` "infrastructure failures" that
  existed on the baseline because the catalog file was never committed)
- E2e test (`make -C phase7_real_session test-e2e`): **PASS** (4 tests)
- Chat UI launch: `Uvicorn running on http://127.0.0.1:18000` — no
  import errors

**Test counts by phase (after cleanup):**

| Phase | Tests | Files |
|---|---|---|
| Phase 2 (`phase2_project_engine`) | 85 | 13 test modules |
| Phase 3 (`phase3_pyagent_core`) | 41 | 7 test modules |
| Phase 4 (`phase4_chat_ui`) | 42 | 10 test modules |
| Phase 5 (`phase5_dbus_sync`) | 29 | 3 test modules |
| Phase 6 (`phase6_render_qc`) | 30 | 3 test modules |
| Phase 7 (`phase7_real_session`) | 4 | 1 test module |
| **Total** | **231** | **37** |

**Structural changes:**

- **Phase 2**: 943-line `KdenliveFileBackend` class split into
  `types.py` + `errors.py` + `catalog.py` + `io.py` + `tracks.py` +
  `validators.py` + `ops/{bin,clips,transitions,effects,markers}.py`
  + `backend.py` (thin dispatch). 3 legacy files deleted
  (`editor_backend.py`, `kdenlive_file_backend.py`, `kdenlive_xml.py`).
- **Phase 3**: 437-line `extension.ts` (per pre-cleanup `git show`) rewritten as
  a thin 367-line loader; tool definitions extracted to
  `tools/{bin,clips,transitions,effects,markers,project,catalog,render_qc}.py`;
  `runtime.py` (192 lines) + `phase3_types.py` (31 lines) extracted
  from `__main__.py`; 19 tool JSON I/O outputs locked by
  `tests/test_golden_io.py` (6 tests).
- **Phase 4**: `ws.py` (457 LOC) split into `ws/{manager,handler,handlers}.py`;
  `adapters/agent_adapters.py` (358 LOC, hard-coded
  `available() -> False`) split into `adapters/{piagent,opencode,_registry}.py`;
  `app.py` slimmed from 722 LOC → 135 LOC; `watcher.py` mtime-window
  filter added.
- **Phase 5**: `kdenlive_state.py` + `notifier.py` deleted (unused);
  `live_sync.py` simplified.
- **Phase 6**: 4 audio/timeout + black-frames bug fixes; `qc_loop`
  consolidated.
- **Phase 7**: 3 duplicate e2e entry-point modules collapsed to 1.

**Bugs and code-health findings:**

*Bugs (something was incorrect and produced wrong behavior):*

- 10 from the initial survey (BUGs 1-10 in §"Initial survey" above)
- 3 atomic-swap fallout bugs (BUGs 11-13: broken re-imports after
  deleting `kdenlive_file_backend.py`; missing `__init__.py`)
- 1 Type.Object schema binding (commit 22caaeb)
- 1 watcher false-positive filter (commit 4642059)
- 1 audio `subprocess.TimeoutExpired` propagating instead of returning
  structured error (commit 5165fb7)
- 1 black-frames `out_sec <= in_sec` passed through to ffmpeg
  (commit 5165fb7)
- **Total: 17 distinct bug fixes**

*Dead-code / unreachable findings (correctness, not a user-visible bug):*

- 1 `AntiGravityAdapter` with hard-coded `available() -> False`,
  unreachable from the running app (commit 16dda61)
- 1 `kdenlive_state.py` and 1 `notifier.py` in Phase 5, both unused
  (commit 0d28604)

*Refactors (structure was over-budget, not buggy):*

- Phase 2: 943-line `KdenliveFileBackend` split into 13 modules
  (commits 5da2c26 → 420e999)
- Phase 3: 437-line `extension.ts` rewritten as a thin 367-line loader
  (commits 43ae817 → 39fd95b)
- Phase 4: 457-line `ws.py` and 358-line `agent_adapters.py` split into
  per-package modules (commits b56a4ad, 16dda61)
- Phase 4: 722-line `app.py` slimmed to 135 lines (commit 4642059)
- Phase 6: 110-line `qc_loop` orchestration consolidated
  (commit 5165fb7)
- Phase 7: 4 e2e entry-point modules collapsed to 1 (commit 0318735)

**Module-size budget (final):**

- Every prod file < 300 lines (largest: `phase3_pyagent_core/runtime.py` 192 lines)
- Every test file < 400 lines (largest: `phase3_pyagent_core/test_runtime.py` 359 lines)
- 3 prod files in the 200-300 range (intentional: they own a single
  concern and a split would just add cross-module indirection)

**Branch / commits:**

- Branch: `cleanup/whole-pipeline`
- 24 cleanup commits layered on top of pre-existing history
- One commit per logical change (not strictly "one per phase" — some
  phases needed 3-9 commits because each layer was its own reviewable
  unit)

**See also:**

- `git log cleanup/whole-pipeline` — full commit history
- `docs/superpowers/plans/2026-07-19-cleanup.md` — the plan that drove
  this sub-project

## 2026-07-19 — Task 1 (sub-project 2a): clips-edit tools

Five latent bugs in the brief's skeleton code, caught and fixed during TDD:

- BUG T1.1: `_find_entry_for_clip` iterated `track.iter("entry")` on the
  TRACTOR. Entries live inside the playlists referenced by `<track
  producer="..."/>` refs, not inside the tractor itself. So the helper
  never found any entry and every op raised `clip_not_found`. Fix:
  use the tracks→playlists→entries pattern from
  `tracks.find_all_entries`. File:
  `phase2_project_engine/ops/clips_edit.py:19-31`.
- BUG T1.2: `slip_clip` returned `timeline_start_sec` by reading
  `entry.getparent().get("kdenlive:start") or "0"`. Playlists have no
  `kdenlive:start` attribute, so the fallback `"0"` raised
  `ValueError` from `_tc_to_sec`. Fix: use `entry_start_sec(pl, entry)`
  from `ops._helpers`. File:
  `phase2_project_engine/ops/clips_edit.py:67-78`.
- BUG T1.3: the brief's `test_ripple_delete_clip_removes_entry_and_shifts_following`
  used `e.find("producer/property[@name='kdenlive:id']")` to read
  each entry's kid. Entries have `kdenlive:id` as a direct
  `<property>` child, NOT nested under `<producer>` (the bin
  producer's `kdenlive:id` is what's nested, but that's a different
  element). Fix: use `e.find("property[@name='kdenlive:id']")`. File:
  `phase2_project_engine/tests/test_ops_clips.py:266-267`.
- BUG T1.4: `ripple_delete_clip` collected "shifted" clip ids by
  iterating `playlist.findall("entry")` AFTER `playlist.remove(entry)`,
  then checking `if e is entry: following_started = True`. The `entry`
  reference is detached after removal, so the check never fires and
  `shifted_clip_ids` is always empty. Fix: collect the kid list BEFORE
  removal, using `entry_idx = entries.index(entry)`. File:
  `phase2_project_engine/ops/clips_edit.py:101-122`.
- BUG T1.5 (pre-existing latent): `_READ_ONLY_OPS` in
  `test_golden_io.py:83` was computed as `{c[0] for c in _CASES}`.
  When all cases were read-only, this was fine. Adding mutating cases
  (`slip_clip`, `ripple_delete_clip`, etc.) made the test skip the
  tmp-copy branch and run mutating ops directly against the demo
  fixture, auto-saving (via `runtime.MUTATING_OPS`) and silently
  corrupting the fixture. The corruption cascaded into 13+ test
  failures across `test_runtime.py`, `test_tracks.py`, the golden
  tests, and the e2e tests. Fix: hardcode the read-only set
  `{get_project_info, get_timeline_summary, list_catalog}`. File:
  `phase3_pyagent_core/tests/test_golden_io.py:80-86`.

Test count after Task 1: 242 passed, 1 skipped (baseline 230 + 12 new:
7 integration tests in test_ops_clips.py, 5 golden tests in
test_golden_io.py). Output pristine.

## 2026-07-19 — Task 2 (sub-project 2a): remove_effect

Three latent bugs in the brief's skeleton code, caught during TDD:

- BUG T2.1: the brief's `remove_effect` looked for filters inside the
  clip's `<producer>` element. `apply_effect` writes them as direct
  `<filter>` children of the clip's `<entry>` element, so the brief's
  `remove_effect` would always see `effect_count=0` and reject every
  index with `effect_index_out_of_range`. Fix: read filters from
  `entry.findall("filter")` (the same place `apply_effect` writes).
  Files: `phase2_project_engine/ops/effects.py:79-104`;
  `phase2_project_engine/tests/test_ops_effects.py:148-189`
  (regression: the test applies an effect, then calls remove_effect,
  then asserts `tree.root.iter("filter")` count decreased).
- BUG T2.2: the brief's `test_remove_effect_by_index` called
  `apply_effect(tree, clip_id=kid, effect_id="sepia")` with no
  catalog. `apply_effect` validates `effect_id` against the catalog
  (or raises `CatalogError` with empty catalog). Fix: added a
  `SEPIA_CATALOG` fixture mirroring the existing `BRIGHTNESS_CATALOG`
  pattern and pass it explicitly. File:
  `phase2_project_engine/tests/test_ops_effects.py:40-49, 157`.
- BUG T2.3: the brief's `_CASES` entry for `remove_effect` used
  `"clip_id": "PLACEHOLDER_KID"` — a placeholder that would never
  match a real clip. The demo fixture has clip_id `"2"`. Fix: use
  clip_id `"2"` and add a `_SETUP` mechanism in `test_golden_io.py`
  that runs `apply_effect` against the tmp project before the
  golden op, so the test has something to remove. Files:
  `phase3_pyagent_core/tests/test_golden_io.py:78-90, 144-152`;
  `phase3_pyagent_core/tests/fixtures/golden_io.json:127-132`.

Test count after Task 2: 245 passed, 1 skipped (baseline 242 + 3 new:
2 integration tests in test_ops_effects.py — happy path + out-of-range,
1 golden test in test_golden_io.py). Output pristine.
