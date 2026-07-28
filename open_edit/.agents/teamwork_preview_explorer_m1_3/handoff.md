# Handoff Report: Milestone 1 (Explorer 3 - Corner Cases & Test Implementation)

## 1. Observation
- **Target Files Inspected**:
  - `open_edit/render/emitter.py` (183 lines)
  - `open_edit/ir/types.py` (331 lines)
  - `open_edit/ir/apply.py` (845 lines)
  - `tests/test_emitter.py` (21 lines)
  - `tests/test_render/test_emitter.py` (145 lines)
  - `tests/conftest.py` (64 lines)
  - `pyproject.toml` (68 lines)
- **Emitter Structure (`open_edit/render/emitter.py:150-167`)**:
  ```python
  for clip in track.clips:
      ...
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
- **Filter Keyframe Generation (`open_edit/render/emitter.py:50-56`)**:
  ```python
  for param, kfs in effect.keyframes.items():
      for time_sec, value, interp in kfs:
          etree.SubElement(filter_el, "kf", attrib={
              "frame": _format_timecode(time_sec, fps_num, fps_den),
              "value": str(value),
              "interp": interp,
          })
  ```
- **Timecode Formatting (`open_edit/render/emitter.py:26-28`)**:
  ```python
  def _format_timecode(seconds: float, fps_num: int, fps_den: int) -> str:
      return str(int(round(seconds * fps_num / fps_den)))
  ```
- **Existing Emitter Tests (`tests/test_render/test_emitter.py:1-145`)**:
  Contains tests asserting XML formatting (`<?xml`), `<mlt`, `width="1920"`, `<entry`, `producer="producer_abc"`, `<transition`, `<filter`, `service="volume"`, and `<track`.

---

## 2. Logic Chain
1. **Observation**: `emitter.py:157-167` iterates through `track.clips` and builds an `<entry>` element for each clip, appending filters for each item in `clip.effects`.
2. **Observation**: `_format_timecode` converts time in seconds to integer frame numbers via `int(round(seconds * fps_num / fps_den))`.
3. **Logic Step A (Corner Case - Short Clips <60ms)**:
   For a clip shorter than 60ms ($T_{\text{clip}} < 0.060\text{s}$), a 30ms fade-in ($0 \to 0.030\text{s}$) and 30ms fade-out ($T_{\text{clip}}-0.030 \to T_{\text{clip}}$) would overlap or yield $T_{\text{clip}}-0.030 < 0$. Therefore, the fade duration must be capped at $T_{\text{fade}} = \min(0.030,\, T_{\text{clip}} / 2.0)$.
4. **Logic Step B (Frame Collision & Deduplication)**:
   At 30fps, 30ms is 0.9 frames (rounds to 1 frame). For short clips or high/low frame rates, `int(round(...))` can produce identical frame numbers for fade-in end and fade-out start. Filtering adjacent keyframes with duplicate frame indices prevents invalid MLT XML `<kf>` tags.
5. **Logic Step C (Cascading Gain Multiplier for Muted/Custom Gains)**:
   In MLT, filters in an `<entry>` run in series. A dedicated micro-fade filter with gain $0.0 \to 1.0 \to 0.0$ acts as a linear gain multiplier $M(t)$. When combined with a user volume filter $G_{\text{user}}(t)$ (e.g., $G_{\text{user}} = 0.5$ or $G_{\text{user}} = 0.0$ for muted clips), the combined signal is $A(t) \cdot M(t) \cdot G_{\text{user}}(t)$. This guarantees that muted clips stay muted ($0.0 \cdot M(t) = 0.0$) and custom gain clips scale proportionally ($0.5 \cdot M(t)$).
6. **Logic Step D (Configurability & Backward Compatibility)**:
   Adding `enable_audio_micro_fades: bool = True` and `micro_fade_duration_sec: float = 0.030` to `EmitterConfig` ensures micro-fades are enabled by default for rendering while allowing callers/tests to opt out if needed.

---

## 3. Caveats
- Direct execution via `run_command` in this sandbox environment returned terminal connection reset errors; verification was performed via static analysis of code, Pydantic schemas, and MLT XML specifications.
- FFmpeg audio rendering output (actual WAV/MP3 waveform output) was not directly listened to; analysis relies on MLT XML schema specification for the `volume` filter service.

---

## 4. Conclusion
Automatic 30ms audio micro-fades should be implemented in `emitter.py` by emitting a dedicated `<filter id="microfade_{clip.clip_id}" service="volume">` with keyframes `(0, 0.0)`, `(fade_in_frame, 1.0)`, `(fade_out_frame, 1.0)`, `(total_frames, 0.0)` inside each clip's `<entry>`.
Capping fade duration to $\min(0.030, T_{\text{clip}} / 2.0)$ and deduplicating keyframes cleanly handles all corner cases (short clips, 1-frame clips, muted clips, and custom gains) without regression.

---

## 5. Verification Method
1. **Inspection**:
   View `/home/ah64/apps/mlt-pipeline/open_edit/.agents/teamwork_preview_explorer_m1_3/analysis.md` and `emitter.py`.
2. **Pytest Verification Command**:
   Run `pytest tests/test_render/test_emitter.py tests/test_emitter.py` to verify unit tests pass.
3. **Invalidation Conditions**:
   - If keyframes are emitted with negative frame numbers or duplicate frame numbers.
   - If user volume gain (e.g. muted clip) is overridden by hardcoded values instead of cascading.
