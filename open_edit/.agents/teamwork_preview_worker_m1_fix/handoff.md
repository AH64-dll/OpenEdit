# Handoff Report — Worker 1 Fix Agent (Milestone 1)

## 1. Observation
- **Files Inspected & Modified**:
  - `open_edit/render/emitter.py`: Lines 16-26 (`EmitterConfig`), 33-76 (`_emit_audio_micro_fade`), 226-234 (`emit_timeline`).
  - `tests/test_render_emitter.py`: Lines 1-182 (updated assertions for short clips, added 1-frame clip test, added `interp="linear"` checks).
- **Tool Commands Executed & Output**:
  - `pytest tests/test_render_emitter.py tests/test_render/test_emitter.py tests/test_emitter.py`
    - Result: `16 passed in 0.10s` (100% clean test passes).
- **Code Observations**:
  1. In `open_edit/render/emitter.py`: `_emit_audio_micro_fade` previously used a last-wins deduplication loop `deduped[-1] = (frame, val)` over raw keyframes `[(frame_0, 0.0), (fade_in_end_frame, 1.0), (fade_out_start_frame, 1.0), (clip_end_frame, 0.0)]`. For a 40ms clip at 30fps (`clip_end_frame == 1`, `fade_in_end_frame == 1`), the `(1, 0.0)` keyframe overwrote `(1, 1.0)`, creating keyframe list `[(0, 0.0), (1, 0.0)]` which completely muted the clip.
  2. In `tests/test_render_emitter.py`: `test_emitter_audio_micro_fades_short_clip_under_60ms` line 94 previously hardcoded `assert kf_data == [("0", "0.0"), ("1", "0.0")]`.
  3. `_emit_audio_micro_fade` keyframe elements omitted the `interp="linear"` attribute required by MLT emitter standards.

---

## 2. Logic Chain
1. **Observation 1**: On short clips (<60ms), frame indices collide because fade duration (capped to `clip_dur / 2.0`) and total clip duration yield identical frame indices when converted to integers at target frame rate (e.g. 40ms at 30fps -> 20ms fade = 0.6 frames -> 1 frame, 40ms clip = 1.2 frames -> 1 frame).
2. Sequentially overwriting colliding frame values with the final `clip_end_frame` value `0.0` caused peak volume `1.0` to be lost, leaving only `0.0` values across all keyframes and muting the audio stream.
3. Resolving frame value collisions by prioritizing peak volume `1.0` during clip playback ensures peak gain `1.0` is preserved. `clip_end_frame` value `0.0` is assigned **only** when `clip_end_frame` strictly exceeds all peak frame indices (`clip_end_frame > max_peak_frame`).
4. For single-frame clips (`clip_end_frame == 0`), assigning `[(0, 1.0)]` guarantees 1-frame clips retain 100% gain instead of being muted at volume 0.0.
5. **Observation 2**: Replacing the flawed test assertion `assert kf_data == [("0", "0.0"), ("1", "0.0")]` with `assert kf_data == [("0", "0.0"), ("1", "1.0")]` and asserting `max(values) == 1.0` ensures the test suite accurately certifies clip audibility.
6. **Observation 3**: Adding `interp="linear"` to emitted `<kf>` attributes fulfills MLT keyframe XML formatting requirements.

---

## 3. Caveats
- No caveats. The fix was directly verified against unit tests and full MLT XML emission structures across 30fps/60fps profiles, 1-frame clips, 40ms clips, 50ms clips, and standard 2-second clips.

---

## 4. Conclusion
The keyframe deduplication and calculation logic in `open_edit/render/emitter.py` (`_emit_audio_micro_fade`) has been fixed:
- Short clips (<60ms) and 1-frame clips maintain peak volume `1.0` and are no longer muted.
- Colliding frame indices resolve cleanly with peak gain priority.
- All emitted `<kf>` elements include `interp="linear"`.
- Test assertions in `tests/test_render_emitter.py` have been updated and expanded to cover 1-frame clips and verify linear interpolation.

---

## 5. Verification Method
1. Run pytest suite:
   ```bash
   pytest tests/test_render_emitter.py tests/test_render/test_emitter.py tests/test_emitter.py
   ```
   Expect: 16 passed, 0 failures.
2. Inspect `open_edit/render/emitter.py` lines 45-77:
   Verify `clip_end_frame == 0` returns `[(0, 1.0)]`, peak volume `1.0` takes priority over `0.0`, `clip_end_frame` sets `0.0` only when `clip_end_frame > max_peak_frame`, and `<kf>` elements include `interp="linear"`.
3. Invalidation condition: If any short clip keyframe sequence resolves to all-zero volume `[("0", "0.0"), ("1", "0.0")]`, or omits `interp="linear"`, verification fails.
