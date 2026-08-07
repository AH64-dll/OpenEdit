# Summary of Changes

## 1. `open_edit/render/emitter.py`
- Updated `EmitterConfig` to include:
  - `enable_audio_micro_fades: bool = True`
  - `micro_fade_duration_sec: float = 0.030`
- Implemented `_emit_audio_micro_fade` helper:
  - Calculates 30ms audio micro-fade duration (capped to `clip_dur / 2.0` for clips shorter than 60ms).
  - Computes frame indices: relative frame 0 (value 0.0) -> `fade_in_end_frame` (value 1.0) -> `fade_out_start_frame` (value 1.0) -> `clip_end_frame` (value 0.0).
  - Deduplicates adjacent keyframes when frame indices collide (e.g., short or 1-frame clips).
  - Emits `<filter id="microfade_{clip_id}" service="volume">` XML tags with `<kf frame="..." value="..." />` keyframe points inside `<entry>`.
- Updated `emit_timeline`:
  - When `config.enable_audio_micro_fades` is `True`, automatically invokes `_emit_audio_micro_fade` for each clip entry in the MLT XML playlist.

## 2. `tests/test_render_emitter.py`
- Created unit tests verifying automatic 30ms audio micro-fades:
  - `test_emitter_audio_micro_fades_regular_clip`: Verifies 4 keyframe points at 30fps for a 2.0s clip (frames 0, 1, 59, 60).
  - `test_emitter_audio_micro_fades_at_60fps`: Verifies keyframe scaling at 60fps for a 2.0s clip (frames 0, 2, 118, 120).
  - `test_emitter_audio_micro_fades_short_clip_under_60ms`: Verifies capping duration to `clip_dur / 2.0` (20ms for 40ms clip) and keyframe deduplication at 30fps.
  - `test_emitter_audio_micro_fades_50ms_clip_at_60fps`: Verifies 25ms fade capping and keyframe deduplication at 60fps.
  - `test_emitter_audio_micro_fades_opt_out`: Verifies setting `enable_audio_micro_fades=False` omits micro-fade XML tags.
  - `test_emitter_audio_micro_fades_coexist_with_user_effects`: Verifies coexistence with user-defined clip effects.

## 3. Verification Commands Run & Outputs

### Command:
`pytest tests/test_render_emitter.py tests/test_render/test_emitter.py tests/test_emitter.py`

### Output:
```
...............                                                          [100%]
15 passed in 0.11s
```
