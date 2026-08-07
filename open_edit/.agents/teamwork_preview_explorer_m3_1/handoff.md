# Handoff Report: Milestone 3 (R3: Waveform Cut Inspection Image Generation)

**Explorer Agent**: Explorer 1 (`teamwork_preview_explorer_m3_1`)  
**Target Module**: `open_edit/serve/visual_verify.py` & `tests/test_visual_verify_waveform.py`  
**Date**: 2026-07-23  

---

## 1. Observation

1. **`open_edit/serve/visual_verify.py`**:
   - `sample_frames` (lines 70–97) samples timestamps based on video duration tiers $[1.0, 30.0, 120.0, \infty]$. Clamps to $[0.05, D - 0.05]$ and dedupes $>0.1\text{s}$.
   - `encode_jpeg` (lines 103–146) extracts single frame via `subprocess.run(["ffmpeg", "-y", "-i", str(input_path), "-vf", vf, "-frames:v", "1", "-q:v", str(int(jpeg_quality)), "-metadata:s:v", " ", str(output_path)], shell=False, check=False, capture_output=True, text=True)`.
   - `encode_jpeg` downscales long edge using `vf = f"scale={long_edge}:-2"`, with two-pass fallback if `max_bytes` is exceeded.
   - Additional helper functions: `model_capability`, `build_verification_tool_result`, `build_failure_tool_result`, `build_no_change_tool_result`, `parse_verdict`, `project_state_hash`, `prune_images`, `log_event`.

2. **`open_edit/serve/agent.py`**:
   - Lines 550–615: Post-render verification calls `visual_verify.sample_frames` and `visual_verify.encode_jpeg` via `asyncio.to_thread`.

3. **Existing Tests in `tests/test_visual_verify.py`**:
   - Line 77: Uses `unittest.mock.patch("subprocess.run")` to test FFmpeg parameter construction without requiring external media files.
   - Line 65: Uses Python `struct` and `zlib` to write minimal 1x1 PNG files on the fly.
   - Line 103: Verifies `shell=False` parameter is passed to `subprocess.run`.

4. **Quality Control & Subprocess Patterns in `open_edit/qc/`**:
   - Uses `shutil.which("ffmpeg")` to verify binary presence upfront, returning `error="ffmpeg not on PATH"` if missing.
   - Passes `timeout=30` to `subprocess.run` to prevent process hangs.

---

## 2. Logic Chain

1. **Observation 1 & 2** show that `visual_verify.py` is the central module for visual media extraction and tool result formatting in Open Edit, but currently lacks functions for audio waveform visual verification around cut boundaries.
2. **Observation 1 & 4** establish that FFmpeg is invoked via `subprocess.run` with explicit argument lists (`shell=False`), timeout limits, and upfront `shutil.which("ffmpeg")` validation.
3. **Observation 3** shows that existing unit tests in `tests/test_visual_verify.py` test FFmpeg wrappers deterministically via `unittest.mock.patch("subprocess.run")` and synthetic file generation without external test assets.
4. Synthesizing these observations leads to the proposed design for `generate_waveform_inspection_image(...)`:
   - It should be added directly to `open_edit/serve/visual_verify.py`.
   - It must build a single FFmpeg `-filter_complex` pipeline using `showwavespic`, `drawbox` (red cut marker line), `scale`/`pad`, and `vstack`/`hstack`.
   - Single-stream edge cases (audio-only or silent video) must be handled gracefully using `color` (synthetic video panel) or `anullsrc` (synthetic silence) rather than crashing.
   - Unit tests must be placed in `tests/test_visual_verify_waveform.py`, using `unittest.mock` to verify command construction, layout geometry, stream fallbacks, and error scenarios.

---

## 3. Caveats

1. **Host FFmpeg Binary**: Host system execution depends on `ffmpeg` being installed on system PATH. Unit tests handle missing binary gracefully via mocking and conditional skips (`@pytest.mark.skipif`).
2. **Read-Only Scope**: Explorer 1 operates strictly in read-only investigation mode. No implementation changes to `visual_verify.py` or new test files were made by this agent.
3. **Filter Complex Variants**: Standard FFmpeg builds support `showwavespic`, `drawbox`, `vstack`, `hstack`, `anullsrc`, and `color`. No rare third-party plugins or non-standard filters are required.

---

## 4. Conclusion

The architecture for Milestone 3 (R3: Waveform Cut Inspection Image Generation) is fully mapped:
1. Extend `open_edit/serve/visual_verify.py` with `generate_waveform_inspection_image(...)`.
2. Use single-command `filter_complex` FFmpeg pipelines with `showwavespic`, `drawbox` cut markers, `scale`/`pad`, and `vstack`/`hstack` layout filters.
3. Implement robust single-stream fallbacks (`anullsrc` for silent video, `color` surface for audio-only).
4. Implement comprehensive unit tests in `tests/test_visual_verify_waveform.py`.

---

## 5. Verification Method

1. **Files to Inspect**:
   - `open_edit/serve/visual_verify.py`
   - `/home/ah64/apps/mlt-pipeline/open_edit/.agents/teamwork_preview_explorer_m3_1/analysis.md`
   - `/home/ah64/apps/mlt-pipeline/open_edit/.agents/teamwork_preview_explorer_m3_1/handoff.md`

2. **Test Commands for Implementation Verification**:
   - `pytest tests/test_visual_verify.py`
   - `pytest tests/test_visual_verify_waveform.py`
   - `pytest tests/test_serve_agent_visual_verify.py`

3. **Invalidation Conditions**:
   - Subprocess calls using `shell=True` (violates security guideline).
   - Temporary intermediate image files written to disk during composite image generation (violates single-command pipeline requirement).
   - Unhandled exceptions when media input lacks audio or video streams.
