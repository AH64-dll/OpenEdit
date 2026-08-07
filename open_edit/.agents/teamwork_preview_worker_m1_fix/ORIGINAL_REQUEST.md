## 2026-07-23T10:38:00Z
You are Worker 1 Fix Agent for Milestone 1 (R1: 30ms Audio Micro-Fades in MLT Emitter).
Your working directory is `/home/ah64/apps/mlt-pipeline/open_edit/.agents/teamwork_preview_worker_m1_fix`. Please create this directory if needed and write only metadata files inside it.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Context & Reviewer Feedback:
Reviewer 1 flagged a CRITICAL issue in the keyframe deduplication logic in `open_edit/render/emitter.py`:
On short clips (<60ms, e.g. 40ms at 30fps), colliding frame indices caused `(clip_end_frame, 0.0)` to overwrite `(1, 1.0)`, resulting in `[(0, 0.0), (1, 0.0)]` which completely MUTED short clips! And `tests/test_render_emitter.py:94` hardcoded `assert kf_data == [("0", "0.0"), ("1", "0.0")]`, certifying a muted clip as correct.

Fix Requirements:
1. In `open_edit/render/emitter.py`:
   - Fix `_emit_audio_micro_fade` keyframe calculation and deduplication logic:
     - Peak volume (`1.0`) MUST NOT be overwritten by `0.0` at intermediate/peak frames on short clips.
     - For short clips or 1-frame clips: ensure the clip is NOT muted. If a clip is 1 frame long (`clip_end_frame == 0`), do not mute it or set value to `1.0`.
     - When frame indices collide, resolve values cleanly: at frame 0 (start), 0.0 (if total frames > 1); at fade peak frames, 1.0; at clip end frame, 0.0 (only if frame > start and frame > fade peak). If fade peak collides with clip end frame, preserve peak 1.0 or non-zero audible volume so short clips remain audible.
     - Add `interp="linear"` attribute to every emitted `<kf>` element: `<kf frame="..." value="..." interp="linear"/>`.
2. In `tests/test_render_emitter.py`:
   - Fix `test_emitter_audio_micro_fades_short_clip_under_60ms` and all micro-fade test assertions. Assert that short clips remain AUDIBLE (peak gain 1.0 present, keyframes show valid non-zero volume curve, NOT `[("0", "0.0"), ("1", "0.0")]`).
   - Add tests for 1-frame clips and short clips.
3. Run tests:
   `pytest tests/test_render_emitter.py tests/test_render/test_emitter.py tests/test_emitter.py`
   Confirm 100% clean test passes.

Write your changes and test outputs to `/home/ah64/apps/mlt-pipeline/open_edit/.agents/teamwork_preview_worker_m1_fix/changes.md` and `/home/ah64/apps/mlt-pipeline/open_edit/.agents/teamwork_preview_worker_m1_fix/handoff.md`.
When complete, notify the orchestrator via send_message.
