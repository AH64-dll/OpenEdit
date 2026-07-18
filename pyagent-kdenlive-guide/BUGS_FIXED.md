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
