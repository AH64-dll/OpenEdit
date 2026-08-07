# Milestone 3 Analysis Report: Dual-Panel Waveform Cut Inspection Image Generation

**Explorer Agent**: Explorer 1 (`teamwork_preview_explorer_m3_1`)  
**Target Modules**: `open_edit/serve/visual_verify.py`, `open_edit/serve/agent.py`, `tests/`  
**Date**: 2026-07-23  

---

## 1. Executive Summary

This report provides a detailed architecture analysis and step-by-step implementation design for **Milestone 3 (R3: Waveform Cut Inspection Image Generation)**.

The primary objective is to extend `open_edit/serve/visual_verify.py` with a public API function `generate_waveform_inspection_image(...)` that uses FFmpeg's `showwavespic` filter combined with `vstack`/`hstack` layout filters to produce high-quality dual-panel (or single-panel fallback) composite inspection images around cut boundaries. These images allow visual and acoustic verification of clip boundaries, micro-fades, and frame transitions.

---

## 2. Codebase Baseline & Function Inventory

### 2.1 Inventory of `open_edit/serve/visual_verify.py`

`visual_verify.py` currently contains pure and near-pure helper functions used by the v1.5 post-render visual verification system:

1. **`sample_frames(duration_s: float, override_count: int | None = None) -> list[float]`** (lines 70–97):
   - Calculates clamped, deduped frame timestamps across 4 duration tiers:
     - $D \le 1.0\text{s} \implies 1\text{ frame at } 0.5 \times D$
     - $D \le 30.0\text{s} \implies 3\text{ frames at } [0.2, 0.5, 0.8] \times D$
     - $D \le 120.0\text{s} \implies 4\text{ frames at } [0.15, 0.4, 0.65, 0.9] \times D$
     - $D > 120.0\text{s} \implies 5\text{ frames at } [0.1, 0.3, 0.5, 0.7, 0.9] \times D$
   - Timestamps are clamped to $[0.05\text{s}, D - 0.05\text{s}]$, deduped with a minimum gap threshold of $0.1\text{s}$, and rounded to 4 decimal places.

2. **`encode_jpeg(input_path: Path, output_path: Path, max_edge_px: int, jpeg_quality: int, max_bytes: int | None = None) -> int`** (lines 103–146):
   - Invokes FFmpeg via `subprocess.run(["ffmpeg", "-y", "-i", str(input_path), "-vf", vf, "-frames:v", "1", "-q:v", str(jpeg_quality), "-metadata:s:v", " ", str(output_path)], shell=False, check=False, capture_output=True, text=True)`.
   - Scale string: `vf = f"scale={long_edge}:-2"`.
   - If `max_bytes` is provided and output exceeds it, halves `long_edge` and retries once (min 64px). Returns output byte count.
   - Raises `RuntimeError(f"ffmpeg failed: {stderr.strip() or stdout.strip()}")` if returncode != 0.

3. **`model_capability(model_id: str, models_store_path: Path | None = None) -> dict[str, Any]`** (lines 160–190):
   - Reads `~/.pi/agent/models-store.json` to determine image capability (`supports_images`, `input_modalities`, `max_image_count`). Defaults to `supports_images: True` for default `minimax-m3`.

4. **`build_verification_tool_result`, `build_failure_tool_result`, `build_no_change_tool_result`** (lines 231–285):
   - Structured JSON builders for tool execution responses returned to the LLM agent loop.

5. **`parse_verdict(text: str) -> dict[str, Any]`** (lines 290–309):
   - Regular expression `re.compile(r"^\s*verification\s*:\s*(pass|fail|uncertain)\b", re.IGNORECASE | re.MULTILINE)` parses explicit LLM verification lines.

6. **`project_state_hash`, `prune_images`, `log_event`** (lines 315–450):
   - Utilities for state hashing (no-change guard), context history pruning, and structured observability logging.

### 2.2 Usage in `open_edit/serve/agent.py`

In `agent.py` (lines 550–615), the post-render verification loop invokes `visual_verify.sample_frames` to sample frame timestamps, probes duration via `_probe_duration`, and calls `visual_verify.encode_jpeg` asynchronously via `asyncio.to_thread` for each frame timestamp.

---

## 3. Architecture Design: Dual-Panel Waveform Composite Image Generation

### 3.1 Concept & Layout Strategy

When inspecting a cut boundary at timestamp `cut_time_s` over a window `window_s` (default 2.0s):
- **Window Start**: $\text{start\_t} = \max(0.0, \text{cut\_time\_s} - \frac{\text{window\_s}}{2.0})$
- **Window Duration**: $\text{dur\_t} = \text{window\_s}$ (clamped to available media duration $D$)
- **Waveform Panel**: Generated via FFmpeg `showwavespic` filter over the audio interval $[\text{start\_t}, \text{start\_t} + \text{dur\_t}]$.
- **Video Frame Panel**: Extracted from the video stream at `cut_time_s`.
- **Cut Marker Line**: A vertical red line (`color=red@0.8`, width 2px) drawn on the waveform panel at the precise horizontal position corresponding to `cut_time_s`:
  $$X_{\text{marker}} = \text{round}\left(W_{\text{wave}} \times \frac{\text{cut\_time\_s} - \text{start\_t}}{\text{dur\_t}}\right)$$
  When the cut is in the center of the window, $X_{\text{marker}} = \frac{W_{\text{wave}}}{2}$.

### 3.2 Composite Layout Modes

1. **`vstack` (Vertical Stack — Default)**:
   - Total Dimensions: $W \times H$ (e.g. $1280 \times 720$).
   - Top Panel (Video Frame): $W \times H_v$, where $H_v = \lfloor H / 2 \rfloor$ (e.g. $1280 \times 360$).
   - Bottom Panel (Waveform): $W \times H_w$, where $H_w = H - H_v$ (e.g. $1280 \times 360$).

2. **`hstack` (Horizontal Stack)**:
   - Total Dimensions: $W \times H$ (e.g. $1280 \times 720$).
   - Left Panel (Video Frame): $W_v \times H$, where $W_v = \lfloor W / 2 \rfloor$ (e.g. $640 \times 720$).
   - Right Panel (Waveform): $W_w \times H$, where $W_w = W - W_v$ (e.g. $640 \times 720$).

---

## 4. FFmpeg Command Structures & Filtergraphs

### 4.1 Standard Case: Video + Audio (`has_video=True`, `has_audio=True`)

#### Vertical Stack (`vstack`) Command Structure:
```bash
ffmpeg -y -ss {start_t} -t {dur_t} -i {input_path} \
  -filter_complex \
    "[0:a]showwavespic=s={W}x{H_w}:colors=cyan[wv_raw]; \
     [wv_raw]drawbox=x={x_marker}:y=0:w=2:h=h:color=red@0.8:t=fill[wv]; \
     [0:v]scale={W}:{H_v}:force_original_aspect_ratio=decrease,pad={W}:{H_v}:(ow-iw)/2:(oh-ih)/2:color=black[vid]; \
     [vid][wv]vstack[out]" \
  -map "[out]" -frames:v 1 -q:v {q_scale} {output_path}
```

#### Horizontal Stack (`hstack`) Command Structure:
```bash
ffmpeg -y -ss {start_t} -t {dur_t} -i {input_path} \
  -filter_complex \
    "[0:a]showwavespic=s={W_w}x{H}:colors=cyan[wv_raw]; \
     [wv_raw]drawbox=x={x_marker}:y=0:w=2:h=h:color=red@0.8:t=fill[wv]; \
     [0:v]scale={W_v}:{H}:force_original_aspect_ratio=decrease,pad={W_v}:{H}:(ow-iw)/2:(oh-ih)/2:color=black[vid]; \
     [vid][wv]hstack[out]" \
  -map "[out]" -frames:v 1 -q:v {q_scale} {output_path}
```

### 4.2 Single-Stream Fallback Handling

1. **Silent Video (`has_video=True`, `has_audio=False`)**:
   - Synthetic silence via `anullsrc=channel_layout=stereo:sample_rate=44100` generates a flat horizontal baseline waveform:
   ```bash
   anullsrc=channel_layout=stereo:sample_rate=44100:d={dur_t}[silence]; \
   [silence]showwavespic=s={W_w}x{H_w}:colors=gray[wv_raw]; ...
   ```

2. **Audio-Only File (`has_video=False`, `has_audio=True`)**:
   - Synthetic dark placeholder panel via `color=c=black:s={W}x{H_v}` with text label "Audio-Only Input":
   ```bash
   color=c=black:s={W}x{H_v}[vid_bg]; \
   [vid_bg]drawtext=text='Audio-Only Input / No Video Stream':x=(w-text_w)/2:y=(h-text_h)/2:fontcolor=white:fontsize=24[vid]; ...
   ```

---

## 5. Temporary File Management Strategy

### 5.1 Single-Command Pipeline (Recommended)
By using FFmpeg's `-filter_complex`, the video scaling, waveform generation, cut marker drawing, and panel stacking occur in RAM inside a single FFmpeg process.
- **Intermediate Files**: None (0 temporary files).
- **Disk I/O**: Only the final target image file is written to disk.
- **Process Overhead**: Single `subprocess.run` invocation.

### 5.2 Error Cleanliness
If FFmpeg fails or encounters an error during output creation, any incomplete file at `output_path` is cleaned up (`if output_path.exists() and proc.returncode != 0: output_path.unlink(missing_ok=True)`).

---

## 6. Target API Specification for `visual_verify.py`

```python
def generate_waveform_inspection_image(
    input_path: str | Path,
    output_path: str | Path,
    cut_time_s: float,
    window_s: float = 2.0,
    width: int = 1280,
    height: int = 720,
    layout: str = "vstack",
    jpeg_quality: int = 90,
    ffmpeg_path: str | Path | None = None,
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    """Generate a dual-panel waveform + video frame composite image around a cut boundary.

    Parameters
    ----------
    input_path : str | Path
        Path to source media file (video or audio).
    output_path : str | Path
        Path where generated JPEG/PNG image will be saved.
    cut_time_s : float
        Cut boundary timestamp in seconds.
    window_s : float, default 2.0
        Inspection window duration in seconds around cut_time_s.
    width : int, default 1280
        Total output composite image width in pixels.
    height : int, default 720
        Total output composite image height in pixels.
    layout : str, default "vstack"
        Panel layout mode: "vstack" (video top, waveform bottom) or "hstack" (video left, waveform right).
    jpeg_quality : int, default 90
        JPEG quality parameter (1-100 scale).
    ffmpeg_path : str | Path | None, optional
        Custom path to ffmpeg binary (defaults to shutil.which("ffmpeg")).
    timeout_s : float, default 30.0
        Process execution timeout in seconds.

    Returns
    -------
    dict[str, Any]
        Structured result payload:
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

---

## 7. Step-by-Step Implementation Strategy for Worker

1. **Step 1: Stream Probing Helper**:
   Implement internal `_probe_media_streams(input_path: Path, ffmpeg_path: Path | None)` returning `(has_audio: bool, has_video: bool, duration_s: float)`.
2. **Step 2: Filtergraph Builder**:
   Implement internal `_build_waveform_filtergraph(...)` constructing complex filter string based on stream flags, layout mode, dimensions, and marker offset.
3. **Step 3: Core Generator Function**:
   Implement `generate_waveform_inspection_image(...)` in `open_edit/serve/visual_verify.py`:
   - Validate binary availability (`shutil.which("ffmpeg")`).
   - Calculate window start/end timestamps and cut line $X$ position.
   - Spawn FFmpeg with `subprocess.run(..., shell=False, timeout=timeout_s)`.
   - Validate output file creation and byte size.
4. **Step 4: Unit Test Suite**:
   Create `tests/test_visual_verify_waveform.py` with mock-based unit tests for `vstack`, `hstack`, audio-only, video-only, boundary cut timestamps, missing FFmpeg, non-zero returncodes, and command timeouts.

---

## 8. Summary of Verification Plan

- Run unit tests: `pytest tests/test_visual_verify_waveform.py`
- Run regression suite: `pytest tests/test_visual_verify.py tests/test_serve_agent_visual_verify.py`
- Verify layout compliance: Ensure `generate_waveform_inspection_image` is in `open_edit/serve/visual_verify.py` and unit tests in `tests/test_visual_verify_waveform.py`.
