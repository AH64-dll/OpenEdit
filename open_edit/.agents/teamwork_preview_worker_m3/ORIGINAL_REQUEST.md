## 2026-07-23T13:39:17Z
You are Worker 3 for Milestone 3 (R3: Waveform Cut Inspection Image Generation).
Your working directory is `/home/ah64/apps/mlt-pipeline/open_edit/.agents/teamwork_preview_worker_m3`. Please create this directory if needed and write only metadata files inside it.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Objective:
Extend `open_edit/serve/visual_verify.py` to generate dual-panel waveform + video frame composite images around cut boundaries using FFmpeg `showwavespic` and `vstack`/`hstack`, and write unit tests in `tests/test_visual_verify_waveform.py`.

Requirements:
1. In `open_edit/serve/visual_verify.py`:
   - Implement public function:
     `generate_waveform_inspection_image(input_path: Path, output_path: Path, cut_time_sec: float, window_sec: float = 2.0, layout: str = "vstack", width: int = 1280, height: int = 720, colors: str = "cyan|blue") -> dict`
   - Use `shutil.which("ffmpeg")` to check FFmpeg availability. Return error dict if missing.
   - Calculate window start/end: `start_time = max(0.0, cut_time_sec - window_sec / 2.0)`, `duration = window_sec`.
   - Build a single FFmpeg `-filter_complex` pipeline:
     - Audio pipeline: `showwavespic` to generate audio waveform with requested `colors` and size.
     - Video pipeline: extract/scale video frame around cut boundary.
     - Overlay/Draw cut marker: red line (`drawbox`) in the center of the waveform representing exact cut position `cut_time_sec`.
     - Stack video frame panel and audio waveform panel using `vstack` or `hstack` based on `layout`.
     - Downscale/pad to requested `width` x `height`.
   - Single-stream fallbacks: render placeholder synthetic surface (`color=c=black`) if input is audio-only; handle silent video streams without failing.
   - Execute FFmpeg via `subprocess.run(..., shell=False, timeout=30, capture_output=True, text=True)`.
   - Return status dict `{"status": "ok", "output_path": str(output_path), ...}` or `{"status": "error", "error": "..."}`.
2. In `tests/test_visual_verify_waveform.py`:
   - Implement unit tests covering:
     - Basic composite image generation parameters and FFmpeg command syntax.
     - `vstack` and `hstack` layout parameters.
     - Audio-only and silent-video stream fallbacks.
     - Missing FFmpeg binary (`shutil.which` returns None) and subprocess timeout/error handling.
     - Use `unittest.mock.patch("subprocess.run")` and `shutil.which` for deterministic testing.
   - Run `pytest tests/test_visual_verify_waveform.py` and `pytest tests/test_visual_verify.py`.

Write your changes summary and test output to `/home/ah64/apps/mlt-pipeline/open_edit/.agents/teamwork_preview_worker_m3/changes.md` and `/home/ah64/apps/mlt-pipeline/open_edit/.agents/teamwork_preview_worker_m3/handoff.md`.
When complete, notify the orchestrator via send_message.
