# Milestone 3 Analysis Report: Waveform Cut Inspection Image Generation

**Explorer Agent**: Explorer 2 (`teamwork_preview_explorer_m3_2`)  
**Target Module**: `open_edit/serve/visual_verify.py` & `tests/test_visual_verify_waveform.py`  
**Date**: 2026-07-23  

---

## 1. Executive Summary

This report presents a comprehensive edge-case analysis, testing strategy, and API design for implementing **Waveform Cut Inspection Image Generation** in `open_edit/serve/visual_verify.py` and its corresponding test suite `tests/test_visual_verify_waveform.py`.

The objective of Milestone 3 (R3) is to extend `visual_verify.py` with a public API function `generate_waveform_inspection_image(...)` that executes FFmpeg (`showwavespic` filter combined with `vstack`/`hstack`) to produce dual-panel or single-panel composite images around cut boundaries for visual and audio quality inspection.

---

## 2. Codebase Baseline Observation

1. **`open_edit/serve/visual_verify.py`**:
   - Contains pure/near-pure helper functions: `sample_frames`, `encode_jpeg`, `model_capability`, `build_verification_tool_result`, `build_failure_tool_result`, `build_no_change_tool_result`, `parse_verdict`, `project_state_hash`, `prune_images`, `log_event`.
   - `encode_jpeg` (lines 103–146) invokes `subprocess.run(["ffmpeg", ...], shell=False, check=False, capture_output=True, text=True)`.
   - Error handling in `encode_jpeg` raises `RuntimeError(f"ffmpeg failed: {stderr.strip() or stdout.strip()}")` if `returncode != 0`.

2. **Existing FFmpeg & QC Patterns in `open_edit/qc/`**:
   - `open_edit/qc/silence.py`, `open_edit/qc/black_frames.py`, `open_edit/qc/thumbnail.py` use `shutil.which("ffmpeg")` to check for binary availability before running commands.
   - If missing, they return structured error result objects/dicts containing `error="ffmpeg not on PATH"`.
   - They pass `timeout=30` to `subprocess.run` to prevent hanging processes.

3. **Existing Test Patterns in `tests/test_visual_verify.py`**:
   - `test_visual_verify.py` tests `encode_jpeg` using `unittest.mock.patch("subprocess.run")`.
   - Synthetic 1x1 PNG files are created in pure Python via `_write_minimal_png(path, width, height)` using `struct` and `zlib` without external media dependencies.
   - Tests assert `shell=False` is passed to `subprocess.run` for security compliance.

---

## 3. Comprehensive Corner Case Analysis

### 3.1 Corner Case 1: Audio-Only Inputs (MP3, WAV, AAC, or MP4 without video stream)
- **Problem**: When input media lacks a video stream (`0:v`), any FFmpeg filtergraph referencing `[0:v]` or attempting video extraction will fail with `Stream specifier ':v' in filtergraph matches no streams`.
- **Technical Mechanism**: FFmpeg complex filter graphs like `[0:a]showwavespic=s=1280x360[wv]; [0:v]scale=1280:360[vid]; [wv][vid]vstack` fail during graph initialization if `[0:v]` is invalid.
- **Handling Strategy**:
  1. Probe stream availability (`has_audio`, `has_video`).
  2. When `has_video` is `False` and `has_audio` is `True`, generate a single-panel audio waveform image using `[0:a]showwavespic=s={width}x{height}` (or a dual-panel image with a synthetic dark background panel containing text "Audio-Only Input / No Video Stream").
  3. Return metadata: `{"ok": True, "has_audio": True, "has_video": False, "mode": "waveform_only"}`.

### 3.2 Corner Case 2: Video-Only Inputs (Silent video clips without audio track)
- **Problem**: When input media lacks an audio stream (`0:a`), `showwavespic` cannot run and fails with `Stream specifier ':a' in filtergraph matches no streams`.
- **Technical Mechanism**: `showwavespic` filter requires audio PCM/compressed stream input.
- **Handling Strategy**:
  1. Detect `has_audio=False` and `has_video=True`.
  2. Options:
     - **Option A (Filter Fallback)**: Use FFmpeg filter `anullsrc=channel_layout=stereo:sample_rate=44100` as a synthetic silent audio input to feed `showwavespic`, generating a flat horizontal center line waveform alongside the video frame.
     - **Option B (Frame-Only Fallback)**: Extract the frame alone without waveform, returning `{"ok": True, "has_audio": False, "has_video": True, "mode": "frame_only"}`.
  3. Recommendation: Option A (or B with clear metadata) ensures callers always receive a structured composite image without uncaught FFmpeg runtime errors.

### 3.3 Corner Case 3: Short Clip Windows & Boundary Timestamps
- **Problem**:
  - `cut_time_s` may be near the start (`cut_time_s < window_s / 2`) or end of file (`cut_time_s > duration - window_s / 2`).
  - Total file duration $D$ may be smaller than requested `window_s` (e.g., $D = 0.5\text{s}$, `window_s` = $2.0\text{s}$).
- **Technical Mechanism**: Passing negative `-ss` values or zero/negative durations `-t` causes FFmpeg seeking errors or zero-byte output.
- **Handling Strategy**:
  1. Calculate `half_w = window_s / 2.0`.
  2. Compute `start_t = max(0.0, cut_time_s - half_w)`.
  3. If file duration $D$ is probed: `end_t = min(D, cut_time_s + half_w)` and `window_duration = max(0.05, end_t - start_t)`.
  4. If $D$ is unknown: set `-ss start_t` and `-t window_s`.
  5. Minimum window duration clamp: Ensure `window_duration >= 0.05` seconds.

### 3.4 Corner Case 4: Missing FFmpeg Binary
- **Problem**: Host environment lacks `ffmpeg` executable on system PATH (`shutil.which("ffmpeg") is None`).
- **Handling Strategy**:
  1. Check `ffmpeg_bin = ffmpeg_path or shutil.which("ffmpeg")` before spawning subprocess.
  2. If `ffmpeg_bin` is `None`, return `{"ok": False, "output_path": str(output_path), "error": "ffmpeg binary not found on PATH"}` matching `open_edit/qc/` conventions.
  3. Do NOT allow `FileNotFoundError` to propagate unhandled.

### 3.5 Corner Case 5: Error Handling & Subprocess Failures
- **Problem**: Subprocess non-zero exit codes, command timeouts, 0-byte output files, corrupt input files.
- **Handling Strategy**:
  1. Wrap `subprocess.run` with `timeout=timeout_s`. Catch `subprocess.TimeoutExpired` and return `{"ok": False, "error": f"FFmpeg execution timed out after {timeout_s}s"}`.
  2. Validate `proc.returncode == 0` AND `output_path.exists()` AND `output_path.stat().st_size > 0`.
  3. If verification fails, parse last non-empty line of `proc.stderr` and return `{"ok": False, "error": f"FFmpeg failed: {stderr_line}"}`.

---

## 4. API Function Signatures for `visual_verify.py`

### Primary Function Signature
```python
def generate_waveform_inspection_image(
    input_path: str | Path,
    output_path: str | Path,
    cut_time_s: float,
    window_s: float = 2.0,
    width: int = 1280,
    height: int = 720,
    layout: str = "vstack",
    ffmpeg_path: str | Path | None = None,
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    """Generate a composite image combining audio waveform visualization
    (via FFmpeg showwavespic) and video frame(s) around a cut timestamp.

    Parameters
    ----------
    input_path : str | Path
        Path to input media file (video or audio).
    output_path : str | Path
        Target output file path (JPEG or PNG).
    cut_time_s : float
        Cut boundary timestamp in seconds.
    window_s : float, default 2.0
        Inspection time window in seconds around cut_time_s.
    width : int, default 1280
        Total output image width in pixels.
    height : int, default 720
        Total output image height in pixels.
    layout : str, default "vstack"
        Layout arrangement: "vstack" (vertical stack) or "hstack" (horizontal stack).
    ffmpeg_path : str | Path | None, optional
        Custom path to ffmpeg executable. Resolved via shutil.which if None.
    timeout_s : float, default 30.0
        Subprocess execution timeout in seconds.

    Returns
    -------
    dict[str, Any]
        Structured dictionary:
        {
            "ok": bool,
            "output_path": str,
            "file_bytes": int,
            "cut_time_s": float,
            "window_start_s": float,
            "window_duration_s": float,
            "has_audio": bool,
            "has_video": bool,
            "layout": str,
            "error": str | None,
        }
    """
```

### Internal Helper Signatures
```python
def _probe_media_streams(
    input_path: Path,
    ffmpeg_path: str | Path | None = None,
) -> tuple[bool, bool, float]:
    """Return (has_audio, has_video, duration_s) for media file at input_path."""
    ...

def _build_waveform_filtergraph(
    has_audio: bool,
    has_video: bool,
    width: int,
    height: int,
    layout: str = "vstack",
) -> str:
    """Construct FFmpeg filter_complex string based on available streams and layout."""
    ...
```

---

## 5. Unit Test Strategy for `tests/test_visual_verify_waveform.py`

### 5.1 Principles
- Pure mock-based unit tests using `pytest` and `unittest.mock`.
- Synthetic file helpers written in pure Python (no FFmpeg binary required for standard unit test runs).
- Optional end-to-end integration test skipped automatically if FFmpeg is missing.

### 5.2 Test Fixtures & Utilities
1. **`_write_minimal_wav(path: Path, duration_s: float = 1.0)`**:
   - Generates a valid 44-byte WAV header + PCM silence in pure Python using `struct.pack`.
2. **`_write_minimal_png(path: Path, width: int = 1280, height: int = 720)`**:
   - Generates a valid PNG file in pure Python using `struct` and `zlib` (reused pattern from `test_visual_verify.py`).

### 5.3 Planned Test Suite Test Cases
| Test Function | Target Scenario | Verification Assertion |
|---|---|---|
| `test_waveform_vstack_success` | Video + audio input with `layout="vstack"` | Assert `subprocess.run` called with `shell=False`, filter contains `showwavespic` and `vstack`, return dict `ok=True`. |
| `test_waveform_hstack_success` | Video + audio input with `layout="hstack"` | Assert filter contains `hstack`, return dict `ok=True`. |
| `test_waveform_audio_only` | Audio file without video stream | Assert `has_video=False`, filter graph handles missing video, return dict `ok=True`. |
| `test_waveform_video_only` | Silent video file without audio stream | Assert `has_audio=False`, `anullsrc` or frame fallback used, return dict `ok=True`. |
| `test_waveform_edge_timestamp_start` | `cut_time_s=0.2` with `window_s=2.0` | Assert `window_start_s` clamped to `0.0`, `-ss 0.0` passed to FFmpeg. |
| `test_waveform_missing_ffmpeg` | `shutil.which("ffmpeg")` returns `None` | Assert returns `{"ok": False, "error": "ffmpeg binary not found on PATH"}` without exception. |
| `test_waveform_ffmpeg_nonzero_exit` | `subprocess.run` returns `returncode=1` | Assert returns `{"ok": False, "error": ...}` containing stderr text. |
| `test_waveform_timeout` | `subprocess.run` raises `TimeoutExpired` | Assert returns `{"ok": False, "error": ...}` containing timeout details. |
| `test_waveform_integration_real_ffmpeg` | End-to-end run against synthetic WAV | Decorate with `@pytest.mark.skipif(shutil.which("ffmpeg") is None, ...)` to verify real execution when available. |

---

## 6. Summary of Architectural Recommendations

1. Implement `generate_waveform_inspection_image` in `open_edit/serve/visual_verify.py` as a non-blocking pure wrapper around FFmpeg.
2. Probe streams or gracefully handle single-stream inputs (audio-only, video-only) to avoid unhandled filtergraph crashes.
3. Use `shutil.which("ffmpeg")` for upfront binary checking, aligning with `open_edit/qc/` standards.
4. Implement `tests/test_visual_verify_waveform.py` with mock-based execution to keep pytest suite ultra-fast and reliable across environments.
