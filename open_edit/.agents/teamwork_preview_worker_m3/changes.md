# Changes Summary — Milestone 3 (R3: Waveform Cut Inspection Image Generation)

## Files Modified / Created

### 1. `open_edit/serve/visual_verify.py`
- Added `import shutil`.
- Implemented stream probe helper `_probe_streams(input_path: Path) -> tuple[bool, bool]` to detect video and audio stream presence via `ffprobe` or `ffmpeg -i`.
- Implemented public function:
  ```python
  def generate_waveform_inspection_image(
      input_path: Path,
      output_path: Path,
      cut_time_sec: float,
      window_sec: float = 2.0,
      layout: str = "vstack",
      width: int = 1280,
      height: int = 720,
      colors: str = "cyan|blue",
  ) -> dict
  ```
  Key features:
  - Uses `shutil.which("ffmpeg")` to check FFmpeg availability, returning `{"status": "error", "error": "FFmpeg binary not found"}` if missing.
  - Calculates window bounds: `start_time = max(0.0, cut_time_sec - window_sec / 2.0)` and `duration = window_sec`.
  - Calculates relative cut position and computes pixel offset `marker_x` on the waveform panel.
  - Constructs a single FFmpeg `-filter_complex` pipeline:
    - Audio waveform via `showwavespic` with custom `colors` and dimensions.
    - Red line marker overlay (`drawbox=x=marker_x:y=0:w=2:h=ih:color=red:t=fill`) at the exact cut position.
    - Video frame extraction scaled to target panel size.
    - Single-stream fallbacks: synthetic black panel (`color=c=black`) for audio-only streams; synthetic silent audio generator (`anullsrc`) for silent video streams.
    - Stacking via `vstack` or `hstack` depending on `layout` parameter.
  - Executes FFmpeg via `subprocess.run(..., shell=False, timeout=30, capture_output=True, text=True)`.
  - Returns status dict `{"status": "ok", "output_path": str(output_path), ...}` or `{"status": "error", "error": "..."}`.

### 2. `tests/test_visual_verify_waveform.py` (New File)
- Implemented unit tests covering:
  - `test_missing_ffmpeg_binary`: Verifies handling when `shutil.which("ffmpeg")` returns `None`.
  - `test_basic_vstack_composite_command_syntax`: Validates `-filter_complex` string, window timing (`-ss`, `-t`), `vstack` filter, and cut line position.
  - `test_hstack_layout_parameters`: Validates `hstack` filter layout and panel width division.
  - `test_audio_only_stream_fallback`: Validates fallback to synthetic black video panel when video stream is missing.
  - `test_silent_video_stream_fallback`: Validates fallback to `anullsrc` silent audio when audio stream is missing.
  - `test_subprocess_timeout_handling`: Validates timeout handling when FFmpeg execution exceeds timeout.
  - `test_subprocess_error_handling`: Validates non-zero returncode and error message extraction.
  - `test_cut_time_near_zero_clamping`: Validates start_time clamping to `0.0` when `cut_time_sec` is near 0.
  - `test_real_ffmpeg_waveform_generation`: Integration test generating actual media via FFmpeg and verifying dual-panel composite image creation on disk.

## Test Verification Output

```
pytest tests/test_visual_verify_waveform.py
.........                                                                [100%]
9 passed in 0.35s

pytest tests/test_visual_verify.py
............................                                             [100%]
28 passed in 0.31s
```
