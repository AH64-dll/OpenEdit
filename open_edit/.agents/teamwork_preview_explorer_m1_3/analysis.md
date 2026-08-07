# Deep-Dive Technical Analysis: 30ms Audio Micro-Fades in MLT Emitter

## Executive Summary
This analysis investigates the technical details, corner cases, test infrastructure, and regression risks involved in automatically injecting 30ms audio micro-fades into the MLT XML emitter (`open_edit/render/emitter.py`).

Audio micro-fades (30ms linear gain ramp-in at clip start and 30ms linear gain ramp-out at clip end) prevent audible audio pops and clicks at clip boundaries. This investigation establishes the exact corner case handling rules, mathematical composition with user gains, pytest structure, and concrete implementation recommendations.

---

## 1. Corner Cases for 30ms Audio Micro-Fades

### A. Clips Shorter than 60ms (< 60ms, down to 1 frame / 0s)
- **Problem**: Standard 30ms fade-in + 30ms fade-out requires 60ms total duration. For clips with duration $T_{\text{clip}} < 0.060\text{s}$ (e.g. 40ms, 20ms, or a 1-frame clip at 30fps = 33.3ms), fixed 30ms fade windows overlap in time, creating negative fade-out start times ($T_{\text{clip}} - 0.030 < 0$) or invalid keyframe order.
- **Mathematical Resolution**:
  - Max fade duration for any clip: $T_{\text{fade\_max}} = \frac{T_{\text{clip}}}{2.0}$.
  - Actual fade duration: $T_{\text{fade}} = \min(0.030,\, \frac{T_{\text{clip}}}{2.0})$.
  - Fade-in window: $[0,\, T_{\text{fade}}]$.
  - Fade-out window: $[T_{\text{clip}} - T_{\text{fade}},\, T_{\text{clip}}]$.
- **Frame-Level Resolution & Deduplication**:
  - At $30\text{ fps}$, $0.030\text{s} = 0.9\text{ frames} \rightarrow 1\text{ frame}$.
  - Total clip frames: $F_{\text{end}} = \text{round}(T_{\text{clip}} \times \text{fps})$.
  - Fade-in frame count: $F_{\text{in}} = \min(\text{round}(0.030 \times \text{fps}),\, F_{\text{end}} // 2)$.
  - Fade-out frame start: $F_{\text{out}} = F_{\text{end}} - F_{\text{in}}$.
  - **Keyframe collapse rule**: If discrete frame rounding produces identical frame indices (e.g. $F_{\text{in}} == F_{\text{out}}$ for a 2-frame clip, or $F_{\text{in}} == F_{\text{start}}$ for a 1-frame clip), adjacent keyframes on the same frame must be collapsed to prevent duplicate/ambiguous MLT `<kf>` tags.
- **Zero or Non-Positive Duration**: If $T_{\text{clip}} \le 0.0\text{s}$ or $F_{\text{end}} \le 0$, micro-fade emission must be skipped entirely.

### B. Audio-Only vs. Video+Audio vs. Silent/Image Clips
- **MLT Track & Producer Behavior**: MLT XML producers output combined audio and video streams by default. In `emitter.py`, `emit_timeline(timeline)` receives a `Timeline` object containing `Track` and `Clip` instances, but not the full `Project` (and thus lacks `Asset.has_audio`).
- **Impact on Video Clips**: Adding a `volume` filter to a video+audio clip or audio clip in an MLT `<entry>` safely applies audio gain fading. For silent clips or image clips (e.g. `.png`/`.jpg`), MLT audio filters are harmless no-ops because MLT simply ignores volume filters on producers with no audio stream.
- **Scope**: Micro-fades can be applied universally to all clip `<entry>` tags across both video and audio tracks, ensuring seamless cuts regardless of track type.

### C. Muted Clips & Custom Gain Settings (Cascading Multiplier Analysis)
- **Cascading Filter Property**: In MLT XML, multiple `<filter>` elements on a single playlist `<entry>` execute sequentially in series (cascading signal path).
- **Mathematical Composition**:
  Let $A(t)$ be the input audio waveform, $M(t) \in [0.0, 1.0]$ be the automatic micro-fade gain multiplier (fading $0 \to 1 \to 0$), and $G_{\text{user}}(t)$ be the user's custom gain filter (e.g. gain = 0.5, or gain = 0.0 for muted clips, or keyframed gain).
  $$A_{\text{out}}(t) = A(t) \cdot M(t) \cdot G_{\text{user}}(t)$$
  - **Muted Clips ($G_{\text{user}} = 0.0$)**: $A_{\text{out}}(t) = A(t) \cdot M(t) \cdot 0.0 = 0.0$. The clip remains 100% muted throughout its entire duration.
  - **Custom Gain ($G_{\text{user}} = 0.5$)**: $A_{\text{out}}(t) = A(t) \cdot 0.5 \cdot M(t)$. Fades smoothly from $0.0 \to 0.5$ over 30ms, holds at $0.5$, then fades from $0.5 \to 0.0$ over the last 30ms.
  - **Keyframed User Volume**: $M(t)$ attenuates the audio to zero at exact cut boundaries without altering relative keyframe shapes in between.
- **Key Takeaway**: Emitting micro-fade as a separate, dedicated `volume` filter with $0.0 \to 1.0 \to 0.0$ gain keyframes ensures automatic composition with all existing and future user gain settings.

---

## 2. Pytest Environment, Test Structure & Helper Dependencies

### A. Test Execution & Location
- Test runners: `pytest` executed from project root (`/home/ah64/apps/mlt-pipeline/open_edit`).
- Relevant test files:
  - `tests/test_render/test_emitter.py`: Core MLT XML emitter test suite (145 lines, 8 test cases covering XML declarations, profile, entries, transitions, filters, audio tracks, producers).
  - `tests/test_emitter.py`: Secondary emitter test file (21 lines testing clip positioning and blank entries).
- Pytest configuration in `pyproject.toml`:
  ```toml
  [tool.pytest.ini_options]
  testpaths = ["tests"]
  pythonpath = ["."]
  addopts = "-ra -q"
  ```

### B. Helper Structures & Dependencies
- `tests/conftest.py`: Configures `sys.path` to root and provides fixtures (`tmp_notes_db`, `tmp_project_with_assets`).
- Helper functions in `test_render/test_emitter.py`:
  - `_asset(asset_hash="abc", duration_sec=2.0) -> Asset`: Creates mock `Asset` objects.
  - Operations used for test building: `AddClipOp`, `AddEffectOp`, `AddTransitionOp`, `apply_operation`.
  - XML verification via string assertions (`assert "<entry" in xml`, `assert 'in="0"' in xml`) or `lxml.etree.fromstring()`.

---

## 3. Edge Cases & Potential Regression Risks in `emitter.py`

| Risk | Description | Prevention / Mitigation |
|---|---|---|
| **Filter ID Collision** | Micro-fade filter ID colliding with user effect ID | Use a dedicated, deterministic ID prefix, e.g. `f"microfade_{clip.clip_id}"`. |
| **Existing Test Invalidation** | Tests matching string `<filter` or checking exact filter count might break if micro-fades are added unconditionally | Ensure micro-fade filter uses `service="volume"` and check existing assertions. Add opt-out flag in `EmitterConfig` if needed. |
| **Frame Index Collision** | Short clips (< 60ms) or low FPS (12fps) producing identical frame indices for keyframes | Implement strict keyframe deduplication: `f0 < f1 <= f2 < f3`. |
| **Non-Positive Clip Duration** | Clips with `in_point_sec >= out_point_sec` causing `clip_dur <= 0` | Guard: `if clip_dur <= 0.0: return` (skip micro-fade emission). |
| **Configurability** | Hardcoded behavior preventing disabling micro-fades for raw MLT exports | Add `enable_audio_micro_fades: bool = True` and `micro_fade_duration_sec: float = 0.030` to `EmitterConfig`. |

---

## 4. Exact Implementation Recommendations

### A. EmitterConfig Extension (`open_edit/render/emitter.py`)
```python
class EmitterConfig(BaseModel):
    profile: dict = Field(default_factory=lambda: {
        "width": 1920, "height": 1080,
        "frame_rate_num": 30, "frame_rate_den": 1,
    })
    project_meta: dict = Field(default_factory=dict)
    enable_audio_micro_fades: bool = True
    micro_fade_duration_sec: float = 0.030
```

### B. Micro-Fade Emission Helper
```python
def _emit_audio_micro_fade(
    entry: etree._Element,
    clip: Clip,
    fps_num: int,
    fps_den: int,
    fade_duration_sec: float = 0.030,
) -> None:
    clip_dur = clip.out_point_sec - clip.in_point_sec
    if clip_dur <= 0.0:
        return

    actual_fade_dur = min(fade_duration_sec, clip_dur / 2.0)
    fps = fps_num / fps_den
    total_frames = int(round(clip_dur * fps))
    if total_frames <= 0:
        return

    fade_in_frames = min(int(round(actual_fade_dur * fps)), total_frames // 2)
    fade_out_start_frame = total_frames - fade_in_frames

    filter_el = etree.SubElement(entry, "filter", attrib={
        "id": f"microfade_{clip.clip_id}",
        "service": "volume",
    })

    keyframes = []
    keyframes.append((0, "0.0"))
    if fade_in_frames > 0:
        keyframes.append((fade_in_frames, "1.0"))
    if fade_out_start_frame > fade_in_frames:
        keyframes.append((fade_out_start_frame, "1.0"))
    if fade_out_start_frame < total_frames:
        keyframes.append((total_frames, "0.0"))

    # Collapse duplicate frame entries if any
    seen_frames = set()
    for frame_num, val in keyframes:
        if frame_num not in seen_frames:
            seen_frames.add(frame_num)
            etree.SubElement(filter_el, "kf", attrib={
                "frame": str(frame_num),
                "value": val,
                "interp": "linear",
            })
```

### C. Integration in `emit_timeline`
```python
if config.enable_audio_micro_fades:
    _emit_audio_micro_fade(entry, clip, fps_num, fps_den, config.micro_fade_duration_sec)
```

---

## 5. Recommended Unit Tests (`tests/test_render/test_emitter.py`)

1. `test_emitter_injects_30ms_audio_micro_fades()`: Verify 2.0s clip produces `<filter id="microfade_..." service="volume">` with keyframes at 0 (0.0), 1 (1.0), 59 (1.0), 60 (0.0).
2. `test_emitter_micro_fade_short_clip_under_60ms()`: Test 40ms clip (1.2 frames @ 30fps) caps fade duration to 20ms and avoids frame collision.
3. `test_emitter_micro_fade_custom_gain_coexistence()`: Verify both user `volume` filter (gain=0.5) and automatic `microfade` filter are present in `<entry>`.
4. `test_emitter_micro_fade_disabled_via_config()`: Set `enable_audio_micro_fades=False` and verify no `microfade_` filter is emitted.
