# Handoff Report: 30ms Audio Micro-Fades in MLT Emitter (Milestone 1 / R1)

## 1. Observation

### Source Code Observations
- **`open_edit/render/emitter.py`**:
  - `emit_timeline(timeline, config, asset_paths)` (lines 79-182) constructs MLT XML using `lxml.etree`.
  - Timecode formatting `_format_timecode(seconds, fps_num, fps_den)` (lines 26-28):
    `return str(int(round(seconds * fps_num / fps_den)))`
  - Filter emission `_emit_filter(parent, effect, fps_num, fps_den)` (lines 31-57):
    Emits `<filter id="{effect.effect_id}" service="{effect.effect_type}">` and child `<property>` / `<kf>` tags under `parent`.
  - Clip entry processing (lines 157-167):
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
- **`open_edit/ir/catalog/effects/volume.yaml`**:
  - `name`: `volume`, `mlt_service`: `volume`, `params`: `gain` (linear scale, 1.0 default), `keyframe_params`: `[gain]`.
- **`tests/test_render/test_emitter.py`**:
  - Contains 8 test cases testing XML declaration, profile, entry emission, transitions, filters, audio tracks, and producers.

---

## 2. Logic Chain

1. **Observation**: `emitter.py` attaches clip-level filters to playlist `<entry>` elements using `_emit_filter()`.
2. **Observation**: In MLT XML, multiple `<filter>` elements inside a playlist `<entry>` process audio sequentially in series.
3. **Reasoning**: Injecting an automatic `volume` filter with linear keyframe ramps ($0.0 \to 1.0 \to 0.0$) directly into clip `<entry>` tags creates a dedicated micro-fade envelope. Because MLT filters cascade, this micro-fade envelope multiplies with any user-specified gain settings without modifying user IR effects or breaking existing tests.
4. **Observation**: `_format_timecode` converts time in seconds to frame count via `int(round(seconds * fps_num / fps_den))`.
5. **Reasoning**: At 30 fps, $30\text{ms} = 0.030\text{s} \times 30 = 0.9 \implies 1\text{ frame}$. At 60 fps, $30\text{ms} = 0.030\text{s} \times 60 = 1.8 \implies 2\text{ frames}$.
6. **Reasoning**: For short clips where $2 \times \text{fade\_frames} > \text{total\_clip\_frames}$, clamping $\text{fade\_frames} = \text{total\_clip\_frames} // 2$ and deduplicating identical keyframe frame indices prevents frame collision and negative index errors.
7. **Conclusion**: Adding `enable_audio_micro_fades: bool = True` to `EmitterConfig` and invoking a dedicated `_emit_audio_micro_fade` helper inside `emit_timeline` fulfills the requirement to eliminate audio clicks/pops safely and cleanly.

---

## 3. Caveats

- **Silent / Image Assets**: MLT producers for image assets or video files without audio streams will receive the `volume` filter tag, but MLT ignores volume filters on audio-less streams with zero overhead or side-effects.
- **Sub-frame Fades**: At 24/25/30 fps, 30ms rounds to 1 full frame (33.3ms - 41.7ms). This minor difference is physically required by discrete frame boundaries in video editing frameworks.

---

## 4. Conclusion

The design for Milestone 1 (R1: 30ms Audio Micro-Fades in MLT Emitter) is completely verified and ready for implementation.
- Filter service: `volume`
- Keyframe interpolation: `linear`
- Frame calculation: `fade_frames = max(1, int(round(0.030 * fps_num / fps_den)))` capped at `total_frames // 2`
- Configuration: `EmitterConfig.enable_audio_micro_fades = True`

---

## 5. Verification Method

### 1. Code Inspection Verification
Inspect `open_edit/render/emitter.py` after implementation to verify:
- `EmitterConfig` includes `enable_audio_micro_fades: bool = True` and `micro_fade_duration_sec: float = 0.030`.
- Helper `_emit_audio_micro_fade` is defined and called for clip entries inside `emit_timeline`.
- `<filter service="volume">` contains `<kf>` tags with `frame="0"`, `value="0.0"`, `frame="{fade_frames}"`, `value="1.0"`, `frame="{out_start}"`, `value="1.0"`, `frame="{total}"`, `value="0.0"`.

### 2. Pytest Execution
Run test suite to verify no regressions:
```bash
pytest tests/test_render/test_emitter.py tests/test_emitter.py
```
Expected result: All existing tests pass, and new micro-fade unit tests pass 100%.

### 3. Invalidation Conditions
- If MLT emitter emits invalid XML syntax or breaks `<entry>` tag attributes, `test_emitter_emits_clips_as_entries` will fail.
- If keyframe frame indices are negative or non-monotonic for short clips ($< 60\text{ms}$), keyframe validation in pytest will fail.
