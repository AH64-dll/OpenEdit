## 2026-07-23T13:34:40Z
<USER_REQUEST>
You are Worker 1 for Milestone 1 (R1: Automatic 30ms Audio Micro-Fades in MLT Emitter).
Your working directory is `/home/ah64/apps/mlt-pipeline/open_edit/.agents/teamwork_preview_worker_m1`. Please create this directory if needed and write only metadata files inside it.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Objective:
Implement 30ms automatic audio micro-fades in MLT Emitter (`open_edit/render/emitter.py`) and write comprehensive unit tests in `tests/test_render_emitter.py`.

Requirements:
1. In `open_edit/render/emitter.py`:
   - Modify clip XML emission (`emit_timeline`) to inject a 30ms audio micro-fade-in and fade-out filter (`<filter service="volume">` or volume keyframes) on clip boundaries.
   - Fade duration: 30ms (0.030 seconds). For clips shorter than 60ms, cap fade duration to `clip_duration / 2.0`.
   - Keyframe points: relative frame 0 (value 0.0) -> fade_in_end frame (value 1.0) -> fade_out_start frame (value 1.0) -> clip_end frame (value 0.0).
   - Deduplicate adjacent keyframes if frame indices collide (e.g. 1-frame or very short clips).
   - Respect configuration options in `EmitterConfig` if present (`enable_audio_micro_fades: bool = True`).
2. In `tests/test_render_emitter.py` (and existing tests):
   - Add unit tests verifying 30ms micro-fade filter tag generation in MLT XML output for regular clips, short clips (<60ms), and opt-out config.
   - Run `pytest tests/test_render_emitter.py` and `pytest tests/test_render/test_emitter.py` to confirm clean test passes.

Write your changes summary and verification output into `/home/ah64/apps/mlt-pipeline/open_edit/.agents/teamwork_preview_worker_m1/changes.md` and `/home/ah64/apps/mlt-pipeline/open_edit/.agents/teamwork_preview_worker_m1/handoff.md`. Include exact build/test commands run and outputs.
When complete, notify the orchestrator via send_message.
</USER_REQUEST>
