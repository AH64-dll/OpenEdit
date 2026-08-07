# Handoff Report: Waveform Cut Inspection Edge Case Analysis & Unit Test Strategy (Milestone 3 / R3)

**Agent**: Explorer 2 (`teamwork_preview_explorer_m3_2`)  
**Target Files**: `open_edit/serve/visual_verify.py` & `tests/test_visual_verify_waveform.py`  
**Date**: 2026-07-23  

---

## 1. Observation

1. **`open_edit/serve/visual_verify.py`**:
   - `encode_jpeg` (lines 103–146) executes FFmpeg via `subprocess.run`:
     ```python
     proc = subprocess.run(
         [
             "ffmpeg", "-y", "-i", str(input_path),
             "-vf", vf,
             "-frames:v", "1",
             "-q:v", str(int(jpeg_quality)),
             "-metadata:s:v", " ",
             str(output_path),
         ],
         capture_output=True, text=True, check=False,
         shell=False,
     )
     ```
   - Standard error handling in `encode_jpeg` checks `if rc != 0:` and raises `RuntimeError(f"ffmpeg failed: {stderr.strip() or stdout.strip()}")`.
   - `PROJECT.md` contract specifies:
     - Line 25: `generate_waveform_inspection_image`: Takes cut timestamp / clip info, runs FFmpeg `showwavespic` and stacks waveform with video frame output.
     - Target unit test file: `tests/test_visual_verify_waveform.py`.

2. **`open_edit/qc/` FFmpeg Binary & Error Patterns**:
   - In `open_edit/qc/silence.py` (lines 42–52), `open_edit/qc/black_frames.py` (lines 51–56), and `open_edit/qc/thumbnail.py` (lines 70–76):
     ```python
     ffmpeg = shutil.which("ffmpeg")
     if ffmpeg is None:
         return ThumbnailResult(
             ok=False, ..., error="ffmpeg not on PATH",
         )
     ```
   - Timeout limit is enforced on `subprocess.run` (e.g. `timeout=30`).

3. **`tests/test_visual_verify.py` Test Patterns**:
   - Subprocess call is mocked using `unittest.mock.patch("subprocess.run")` and `_write_minimal_png(path)` (lines 65–75) creates minimal 1x1 PNG fixtures in pure Python using `struct` and `zlib`.
   - `test_subprocess_uses_argv_list_not_shell` (lines 103–113) asserts `shell=False` was passed to `subprocess.run`.

---

## 2. Logic Chain

1. **Observation 1 & 2** show that FFmpeg execution in `open_edit` uses `subprocess.run` with `shell=False`, binary discovery via `shutil.which("ffmpeg")`, and timeout limits.
2. **Observation 1** indicates that `generate_waveform_inspection_image` must execute an FFmpeg filtergraph combining `showwavespic` and `vstack`/`hstack`.
3. **Corner Case Analysis**:
   - **Audio-only input**: FFmpeg fails if `[0:v]` is referenced without a video stream. **Step 1**: Probe or check stream availability (`has_audio`, `has_video`). **Step 2**: Render waveform-only panel when `has_video` is `False`.
   - **Video-only input**: `showwavespic` fails if `[0:a]` is missing. **Step 1**: Use `anullsrc` silent audio filter fallback or render video frame panel only.
   - **Short clip windows & boundary timestamps**: Setting `start_t = max(0.0, cut_time_s - window_s / 2.0)` and clamping duration prevents negative `-ss` or zero-length `-t` seek errors.
   - **Missing FFmpeg binary**: Performing `shutil.which("ffmpeg")` upfront and returning `{"ok": False, "error": "ffmpeg binary not found on PATH"}` avoids raw unhandled `FileNotFoundError` exceptions.
   - **Error Handling**: Catching `subprocess.TimeoutExpired` and checking `returncode == 0` ensures graceful failure responses `{"ok": False, "error": ...}`.
4. **Observation 3** shows that unit tests in `tests/test_visual_verify_waveform.py` should mock `subprocess.run` and `shutil.which` while asserting command arguments (`shell=False`, filter strings, timestamp parameters). Synthetic test audio files can be generated in pure Python (`_write_minimal_wav`).

---

## 3. Caveats

- **FFmpeg Filter Complex Syntax**: Specific filter parameters for `showwavespic` (e.g. `showwavespic=s=1280x360:colors=0x00FF00`) and layout stacking (`vstack` vs `hstack`) depend on Explorer 1's detailed FFmpeg command investigation.
- **FFprobe Availability**: Probing streams via `ffprobe` assumes `ffprobe` is available alongside `ffmpeg`, or stream presence can be checked by analyzing FFmpeg fallback behavior / stderr output during execution.
- No caveats regarding Python standard library features (`subprocess`, `shutil`, `struct`, `unittest.mock`).

---

## 4. Conclusion

1. **API Signature**: Expose `generate_waveform_inspection_image(input_path, output_path, cut_time_s, window_s=2.0, width=1280, height=720, layout="vstack", ffmpeg_path=None, timeout_s=30.0) -> dict[str, Any]` in `open_edit/serve/visual_verify.py`.
2. **Corner Case Protections**: Implement stream detection (`has_audio`, `has_video`), `start_t` clamping to `>= 0.0`, `anullsrc` audio fallback for silent video, `shutil.which("ffmpeg")` binary check, and subprocess timeout handling.
3. **Unit Test Strategy**: Implement `tests/test_visual_verify_waveform.py` using `unittest.mock.patch("subprocess.run")`, verifying command line flags, filter strings, return dict structures, and error paths without requiring real FFmpeg binary installation on test runner environments.

---

## 5. Verification Method

1. **Detailed Analysis Inspection**:
   - Inspect `/home/ah64/apps/mlt-pipeline/open_edit/.agents/teamwork_preview_explorer_m3_2/analysis.md` for full technical breakdown and code signatures.
2. **Unit Test Execution (Post-Implementation)**:
   - Command: `pytest tests/test_visual_verify_waveform.py`
   - Invalidation conditions: Any test failure, unhandled `FileNotFoundError` when FFmpeg is missing, or failure to pass `shell=False` in subprocess execution.
