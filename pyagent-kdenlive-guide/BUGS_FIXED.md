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
