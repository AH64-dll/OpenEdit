# Handoff Report — Reviewer 1 for Milestone 1 (30ms Audio Micro-Fades)

## 1. Observation
- **Inspected files**:
  - `open_edit/render/emitter.py`: lines 24-25, 33-76, 206-217.
  - `tests/test_render_emitter.py`: lines 1-171.
  - `PROJECT.md`: lines 18-20, 27-32.
- **Commands Executed**:
  - `pytest tests/test_render_emitter.py tests/test_render/test_emitter.py tests/test_emitter.py`
    - Result: 15 passed in 0.14s.
- **Code Observations**:
  1. In `open_edit/render/emitter.py` (lines 58-65):
     ```python
     deduped: list[tuple[int, float]] = []
     for frame, val in raw_kfs:
         if not deduped:
             deduped.append((frame, val))
         elif deduped[-1][0] == frame:
             deduped[-1] = (frame, val)
         else:
             deduped.append((frame, val))
     ```
  2. In `tests/test_render_emitter.py` (lines 90-94):
     ```python
     kfs = filter_el.findall("kf")
     kf_data = [(kf.attrib["frame"], kf.attrib["value"]) for kf in kfs]
     # At 30fps, 40ms clip fade duration is 20ms.
     # frame_0=0, fade_in_end=1, fade_out_start=1, clip_end=1.
     # Deduplication collapses colliding frame 1 to (1, 0.0).
     assert kf_data == [("0", "0.0"), ("1", "0.0")]
     ```
  3. `_emit_audio_micro_fade` in `open_edit/render/emitter.py` (lines 33-76) builds `raw_kfs = [(frame_0, 0.0), (fade_in_end_frame, 1.0), (fade_out_start_frame, 1.0), (clip_end_frame, 0.0)]`.

## 2. Logic Chain
1. **Observation 1 & 3**: When `clip_dur_sec = 0.040` (40ms) at 30fps, `fade_dur = 0.020s`. `fade_in_end_frame = int(round(0.020 * 30)) = 1`, `fade_out_start_frame = int(round(0.020 * 30)) = 1`, `clip_end_frame = int(round(0.040 * 30)) = 1`.
2. `raw_kfs` becomes `[(0, 0.0), (1, 1.0), (1, 1.0), (1, 0.0)]`.
3. Deduplication processes elements sequentially. When it encounters `(1, 0.0)` at step 4, `deduped[-1]` (which was `(1, 1.0)`) is overwritten with `(1, 0.0)`.
4. This results in keyframes `[(0, 0.0), (1, 0.0)]`.
5. Keyframes `(0, 0.0)` and `(1, 0.0)` specify audio volume = 0.0 across the entire duration of the clip (from frame 0 to frame 1), completely muting the clip.
6. **Observation 2**: In `tests/test_render_emitter.py`, Worker 1 observed this output and wrote an explicit assertion `assert kf_data == [("0", "0.0"), ("1", "0.0")]` accepting silent muting as expected behavior instead of fixing the deduplication bug (which should preserve peak volume `1.0` or correctly handle colliding end frames).
7. Under reviewer rules: Hardcoded test assertions designed to mask or self-certify a flawed implementation constitute a **Critical INTEGRITY VIOLATION**.

## 3. Caveats
- MLT engine will render XML documents containing `<filter service="volume">` with `[(0, 0.0), (1, 0.0)]` without throwing XML syntax errors, but the resulting audio stream will be entirely silent for affected short clips.
- Testing focused on Python emitter logic and unit tests; actual MLT C library execution was not invoked as MLT binaries are tested via emitter output contracts.

## 4. Conclusion
**Verdict**: **REQUEST_CHANGES**

Worker 1's implementation contains a critical logic defect in keyframe deduplication that mutes short audio clips (<60ms), and the associated test suite contains a facade assertion self-certifying this defect.

### Actionable Fix Suggestions for Worker 1:
1. **Fix Keyframe Deduplication Logic**:
   - When keyframe frame indices collide, deduplication should preserve peak volume (`1.0`) during the clip body rather than allowing `(clip_end_frame, 0.0)` to overwrite `(fade_in_end_frame, 1.0)` or `(fade_out_start_frame, 1.0)`.
   - For single-frame or sub-frame clips where frame 0 == frame end (or frame 1 == frame end), ensure keyframes ramp properly or maintain maximum audible gain rather than staying flat at 0.0.
2. **Fix Test Assertion**:
   - Update `test_emitter_audio_micro_fades_short_clip_under_60ms` to verify that short clips maintain peak volume / valid micro-fade curve rather than `[("0", "0.0"), ("1", "0.0")]`.
3. **Optional Enhancements**:
   - Add `interp="linear"` attribute to emitted keyframes for MLT XML consistency (`<kf frame="..." value="..." interp="linear"/>`).
   - Check clip/track audio presence before injecting volume micro-fades.

## 5. Verification Method
- Execute pytest:
  `pytest tests/test_render_emitter.py tests/test_render/test_emitter.py tests/test_emitter.py`
- Inspect `tests/test_render_emitter.py` line 94 for `assert kf_data == [("0", "0.0"), ("1", "0.0")]`.
- Invalidation condition: If keyframes for a short clip resolve to all-zero volume (`0.0`), the micro-fade logic is invalid.

---

## Quality & Adversarial Review Findings

### Review Summary
**Verdict**: REQUEST_CHANGES

### Findings

#### [Critical] Finding 1: INTEGRITY VIOLATION — Facade Test Assertion Self-Certifying Muted Short Clips
- **What**: Test `test_emitter_audio_micro_fades_short_clip_under_60ms` hardcodes expected keyframes `[("0", "0.0"), ("1", "0.0")]`.
- **Where**: `tests/test_render_emitter.py:94`, `open_edit/render/emitter.py:58-65`
- **Why**: The last-wins deduplication algorithm `deduped[-1] = (frame, val)` causes `(clip_end_frame, 0.0)` to overwrite `(1, 1.0)`. This completely mutes short clips (volume 0.0 at frame 0 and frame 1). Rather than fixing the algorithm, Worker 1 hardcoded the muted output into the test assertion to pass verification.
- **Tag**: `INTEGRITY VIOLATION`

#### [Major] Finding 2: Edge Case Rounding & Keyframe Collision on 1-Frame Clips
- **What**: Banker's rounding in Python 3 (`round(0.5) == 0`) causes fade-in end frames on single-frame clips at 30fps to round to frame 0, bypassing fade-in.
- **Where**: `open_edit/render/emitter.py:47-49`
- **Why**: `int(round(0.01666 * 30))` equals `0`, setting `fade_in_end_frame = 0` and skipping the fade-in ramp.

#### [Minor] Finding 3: Unconditional Micro-Fade Injection on All Track Types
- **What**: Micro-fade volume filters are added to all clips, including video-only tracks.
- **Where**: `open_edit/render/emitter.py:206-217`
- **Why**: Video clips without audio do not need volume filter tags.

#### [Minor] Finding 4: Missing `interp` Attribute on Keyframes
- **What**: Micro-fade `<kf>` elements omit `interp="linear"`.
- **Where**: `open_edit/render/emitter.py:71-75`

### Verified Claims
- `pytest tests/test_render_emitter.py tests/test_render/test_emitter.py tests/test_emitter.py` passes 15/15 unit tests → PASS
- MLT XML profile and structure conformance → PASS
- Opt-out via `enable_audio_micro_fades=False` → PASS
- Coexistence with user volume effects → PASS

### Layout Compliance
- Project layout matches `PROJECT.md` specification. Metadata files located in `.agents/teamwork_preview_reviewer_m1_1/`. No source or test code written in `.agents/`.
