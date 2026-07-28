# Handoff Report: Milestone 1 (R1: 30ms Audio Micro-Fades in MLT Emitter)

## 1. Observation

### Codebase Inspection & Line References

1. **`open_edit/render/emitter.py`**:
   - Lines 26-28: `_format_timecode(seconds: float, fps_num: int, fps_den: int) -> str` converts time in seconds to MLT frame index using `str(int(round(seconds * fps_num / fps_den)))`.
   - Lines 31-57: `_emit_filter(parent, effect, fps_num, fps_den)` creates `<filter id="{effect.effect_id}" service="{effect.effect_type}">` and appends child `<property>` elements for params and `<kf frame="..." value="..." interp="...">` elements for keyframes.
   - Lines 157-167: Entry emission loop inside `emit_timeline`:
     ```python
     entry = etree.SubElement(playlist, "entry", attrib={
         "producer": f"producer_{clip.asset_hash}",
         "in": _format_timecode(clip.in_point_sec, fps_num, fps_den),
         "out": _format_timecode(clip.out_point_sec, fps_num, fps_den),
     })
     for effect in clip.effects:
         if effect.effect_type.startswith("transition_"):
             _emit_transition(entry, effect)
         else:
             _emit_filter(entry, effect, fps_num, fps_den)
     ```

2. **`open_edit/ir/catalog/effects/volume.yaml`**:
   - Lines 1-12:
     ```yaml
     name: volume
     mlt_service: volume
     target_kind: [clip, track]
     params:
       gain:
         type: float
         default: 1.0
         range: [0.0, 4.0]
         unit: linear
     keyframe_params: [gain]
     interp: [linear, discrete]
     description: "Audio volume control. gain=1.0 is unity."
     ```

3. **`tests/test_render/test_emitter.py` & `tests/test_emitter.py`**:
   - Existing test suite contains 9 unit tests checking MLT XML emission string outputs.
   - Command run: `pytest tests/test_render/test_emitter.py tests/test_emitter.py`
   - Output: `9 passed in 0.16s`.

---

## 2. Logic Chain

1. **Pop/Click Prevention Needs Boundary Micro-Fades**:
   - *Observation*: Hard cut boundaries in MLT XML clips lack amplitude ramping, producing digital audio clicks/pops at cut points.
   - *Inference*: Automatic injection of a 30ms volume envelope (fade-in $0.0 \to 1.0$, fade-out $1.0 \to 0.0$) on clip boundaries in emitted MLT XML eliminates amplitude step discontinuities.

2. **MLT `volume` Service with Linear Gain Keyframes**:
   - *Observation*: `open_edit/ir/catalog/effects/volume.yaml` defines `mlt_service: volume` with keyframeable parameter `gain` (linear scale, 0.0 to 1.0). `emitter.py:_emit_filter` serializes keyframe points to `<kf frame="..." value="..." interp="linear"/>`.
   - *Inference*: Emitting a `<filter service="volume">` with keyframes `(frame=0, gain=0.0)`, `(frame=N_fade, gain=1.0)`, `(frame=N_clip - N_fade, gain=1.0)`, `(frame=N_clip, gain=0.0)` inside each clip's `<entry>` element provides native, compliant MLT audio micro-fading.

3. **Frame Calculation & FPS Scalability**:
   - *Observation*: `_format_timecode` calculates frame count as `round(sec * fps_num / fps_den)`.
   - *Inference*: For $T_{fade} = 0.03$s, $N_{fade} = \max(1, \text{int}(\text{round}(0.03 \times \frac{fps\_num}{fps\_den})))$. At 30fps this yields 1 frame; at 60fps this yields 2 frames. For clips shorter than $2 \times N_{fade}$ frames, $N_{fade}$ is clamped to $\lfloor N_{clip} / 2 \rfloor$ to prevent keyframe crossover.

4. **Integration without Breaking Existing IR or Tests**:
   - *Observation*: `emit_timeline` constructs MLT XML in memory without mutating the input `Timeline` IR object.
   - *Inference*: Injecting automatic micro-fades during XML emission keeps the IR pipeline clean and immutable. Existing unit tests check for `<entry>` elements and producer attributes, which remain unchanged.

---

## 3. Caveats

1. **Video-Only Clips / Muted Clips**:
   - *Caveat*: In MLT XML, `<entry>` elements generated from video files (which may or may not contain audio streams) also receive the `<filter service="volume">` filter. In MLT, applying a volume gain envelope to a video stream with audio is harmless if video has audio, and ignored if stream is silent.
2. **User-Defined Volume Keyframes**:
   - *Caveat*: If a user explicitly adds a custom volume keyframe animation to a clip, the automatic micro-fade filter is emitted before the user effect. In MLT, filter order processes micro-fade first on raw clip audio.

---

## 4. Conclusion

Injecting automatic 30ms audio micro-fades in `emitter.py` is straightforward, isolated, and fully compatible with the existing MLT XML pipeline:
1. Define `MICRO_FADE_DURATION_SEC = 0.03`.
2. Implement a helper function `_emit_audio_micro_fades(entry, clip_id, clip_dur_sec, fps_num, fps_den)` in `emitter.py`.
3. Invoke `_emit_audio_micro_fades` when creating `<entry>` elements in `emit_timeline`.
4. Add comprehensive unit tests in `tests/test_render/test_emitter.py` validating 30fps, 60fps, short clip clamping, and XML structure.

---

## 5. Verification Method

### 1. Execute Unit Tests
Run the test command:
```bash
pytest tests/test_render/test_emitter.py tests/test_emitter.py
```
Expected result: All tests pass (including new micro-fade unit tests).

### 2. File Inspection
Inspect `/home/ah64/apps/mlt-pipeline/open_edit/open_edit/render/emitter.py`:
- Verify presence of `_emit_audio_micro_fades` helper function.
- Verify keyframe tag structure `<kf frame="..." value="..." interp="linear"/>`.

### 3. Invalidation Conditions
- Any micro-fade keyframe frame index $< 0$ or $> N_{clip}$.
- Keyframe crossover where start fade-out frame index $<$ end fade-in frame index on short clips.
- Failure of existing tests in `tests/test_render/test_emitter.py`.
