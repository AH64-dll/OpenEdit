# Analysis Report: Automatic 30ms Audio Micro-Fades in MLT Emitter (Milestone 1 / R1)

## Executive Summary
This report presents a thorough, read-only architectural investigation of `open_edit/render/emitter.py` and its corresponding test suite in `tests/test_render/test_emitter.py`. The objective is to design a clean, robust, and automatic 30ms audio micro-fade injection mechanism (fade-in at clip start, fade-out at clip end) on clip boundaries when emitting MLT XML to eliminate audio clicks and pops.

---

## 1. MLT XML Emission Architecture in `emitter.py`

### 1.1 Core Flow & Primary Functions
The entry point for emitting MLT XML is `emit_timeline(timeline: Timeline, config: Optional[EmitterConfig] = None, asset_paths: Optional[dict[str, str]] = None) -> str` (`emitter.py:79-182`).

```
Timeline (IR) ──> EmitterConfig (FPS, profile) ──> lxml etree ──> XML String
```

1. **Profile & Time Code Formatting**:
   - `config.profile` sets `frame_rate_num` (default 30) and `frame_rate_den` (default 1).
   - Time to frame calculation is performed by `_format_timecode(seconds: float, fps_num: int, fps_den: int) -> str` (`emitter.py:26-28`):
     $$\text{frame\_count} = \text{int}\left(\text{round}\left(seconds \times \frac{fps\_num}{fps\_den}\right)\right)$$

2. **Root MLT Document Hierarchy**:
   - `<mlt LC_NUMERIC="C" version="7.22.0">` (`emitter.py:104-110`)
   - `<profile width="..." height="..." frame_rate_num="..." frame_rate_den="..." ...>` (`emitter.py:112-123`)
   - Producer definitions: `<producer id="producer_{asset_hash}" resource="...">` (`emitter.py:130-135`)
   - Main tractor: `<tractor id="tractor0" out="...">` containing `<multitrack>` (`emitter.py:137-142`).

3. **Track & Clip Entry Generation**:
   - For each track in `timeline.tracks`:
     - Creates `<playlist id="playlist_{track.track_id}">` (`emitter.py:145-147`).
     - For each clip in `track.clips`:
       - Emits `<blank length="...">` if `clip.position_sec > current_pos` (`emitter.py:151-155`).
       - Emits clip entry (`emitter.py:157-161`):
         ```xml
         <entry producer="producer_{asset_hash}" in="{in_frames}" out="{out_frames}" />
         ```
       - Emits clip effects:
         - Transitions via `_emit_transition(entry, effect)` (`emitter.py:164`).
         - Regular filters via `_emit_filter(entry, effect, fps_num, fps_den)` (`emitter.py:166`).
       - Advances position counter: `current_pos = clip.position_sec + clip_dur`.
     - Track-level effects are attached directly to the `<playlist>` (`emitter.py:169-173`).
     - Playlist is linked to tractor multitrack: `<track producer="playlist_{track.track_id}">` (`emitter.py:175-177`).

---

## 2. Filter Representation & Attachment in `open_edit`

### 2.1 Filter Emission (`_emit_filter`)
`_emit_filter(parent, effect, fps_num, fps_den)` (`emitter.py:31-57`) converts an `Effect` model into an MLT `<filter>` element:

```xml
<filter id="{effect_id}" service="{effect_type}">
  <property name="key">value</property>
  <kf frame="0" value="0.0" interp="linear"/>
  ...
</filter>
```

- When `parent` is a clip's `<entry>`, the `<filter>` applies exclusively to that clip entry.
- Keyframe offsets (`kf/@frame`) are 0-indexed relative to the start of the `<entry>`.

### 2.2 OpenEdit IR Catalog Spec for `volume`
In `/home/ah64/apps/mlt-pipeline/open_edit/open_edit/ir/catalog/effects/volume.yaml`:
- `name`: `volume`
- `mlt_service`: `volume`
- `params`: `gain` (linear scale, default 1.0, 0.0 = silence, 1.0 = unity)
- `keyframe_params`: `[gain]`

MLT's `volume` filter service with keyframes is the official, catalog-backed mechanism in `open_edit` for audio gain envelope control.

---

## 3. Detailed Architecture for 30ms Audio Micro-Fades

### 3.1 Objective & Rationale
When cuts occur between audio/video clips, instantaneous gain transitions create high-frequency digital clicks/pops. Injecting automatic 30ms (0.03s) volume fade-in keyframes at clip entry start and fade-out keyframes at clip entry end smooths amplitude transitions below human psychoacoustic pop perception.

### 3.2 Frame Count & Keyframe Calculation

Let $T_{fade} = 0.03$ seconds (30ms).
Given frame rate $FPS = \frac{fps\_num}{fps\_den}$:
$$N_{fade\_raw} = \text{int}\left(\text{round}\left(0.03 \times FPS\right)\right)$$
$$N_{fade} = \max(1, N_{fade\_raw})$$

#### Frame Rate Reference Values:
- **30 fps**: $0.03 \times 30 = 0.9 \implies 1$ frame (33.3ms fade)
- **60 fps**: $0.03 \times 60 = 1.8 \implies 2$ frames (33.3ms fade)
- **25 fps**: $0.03 \times 25 = 0.75 \implies 1$ frame (40.0ms fade)
- **24 fps**: $0.03 \times 24 = 0.72 \implies 1$ frame (41.7ms fade)

Let total clip frames $N_{clip} = \text{int}\left(\text{round}\left((out\_point\_sec - in\_point\_sec) \times FPS\right)\right)$.

#### Edge Case Guards (Short Clips):
- If $N_{clip} \le 1$: Skip fade (insufficient frames to fade).
- If $N_{fade} > \lfloor N_{clip} / 2 \rfloor$: Clamp $N_{fade} = \lfloor N_{clip} / 2 \rfloor$.

#### Keyframe Envelope Points (linear interpolation):
1. **Fade-In**:
   - `frame="0"`, `value="0.0"` (silence at start)
   - `frame="{N_fade}"`, `value="1.0"` (full gain after 30ms)
2. **Fade-Out**:
   - `frame="{N_clip - N_fade}"`, `value="1.0"` (start fade-out 30ms before clip end)
   - `frame="{N_clip}"`, `value="0.0"` (silence at clip end)

*(Note: If $N_{clip} - N_{fade} == N_{fade}$, e.g. a 2-frame clip with 1-frame fade-in and 1-frame fade-out, keyframe 1 at 1.0 is shared between fade-in and fade-out, creating a peak envelope: frame 0 = 0.0, frame 1 = 1.0, frame 2 = 0.0).*

### 3.3 Target XML Output Example
For a 2.0 second clip at 30 fps ($N_{clip} = 60$, $N_{fade} = 1$):

```xml
<entry producer="producer_abc" in="0" out="60">
  <filter id="autofade_c1" service="volume">
    <kf frame="0" value="0.0" interp="linear"/>
    <kf frame="1" value="1.0" interp="linear"/>
    <kf frame="59" value="1.0" interp="linear"/>
    <kf frame="60" value="0.0" interp="linear"/>
  </filter>
  <!-- User effects emitted after autofade filter -->
</entry>
```

---

## 4. Proposed Code Patch for `emitter.py`

### Injection Helper Function
```python
MICRO_FADE_DURATION_SEC = 0.03


def _emit_audio_micro_fades(
    entry: etree._Element,
    clip_id: str,
    clip_dur_sec: float,
    fps_num: int,
    fps_den: int,
) -> None:
    """Inject automatic 30ms audio micro-fade filter into a clip entry."""
    total_frames = int(round(clip_dur_sec * fps_num / fps_den))
    if total_frames <= 1:
        return

    fade_frames = max(1, int(round(MICRO_FADE_DURATION_SEC * fps_num / fps_den)))
    fade_frames = min(fade_frames, total_frames // 2)
    if fade_frames <= 0:
        return

    filter_el = etree.SubElement(entry, "filter", attrib={
        "id": f"autofade_{clip_id}",
        "service": "volume",
    })

    # Fade-in
    etree.SubElement(filter_el, "kf", attrib={"frame": "0", "value": "0.0", "interp": "linear"})
    etree.SubElement(filter_el, "kf", attrib={"frame": str(fade_frames), "value": "1.0", "interp": "linear"})

    # Fade-out
    fade_out_start = total_frames - fade_frames
    if fade_out_start > fade_frames:
        etree.SubElement(filter_el, "kf", attrib={"frame": str(fade_out_start), "value": "1.0", "interp": "linear"})
    etree.SubElement(filter_el, "kf", attrib={"frame": str(total_frames), "value": "0.0", "interp": "linear"})
```

### Integration inside `emit_timeline` (`emitter.py:157-167`):
```python
            entry = etree.SubElement(playlist, "entry", attrib={
                "producer": f"producer_{clip.asset_hash}",
                "in": _format_timecode(clip.in_point_sec, fps_num, fps_den),
                "out": _format_timecode(clip.out_point_sec, fps_num, fps_den),
            })
            _emit_audio_micro_fades(entry, clip.clip_id, clip_dur, fps_num, fps_den)
            for effect in clip.effects:
                if effect.effect_type.startswith("transition_"):
                    _emit_transition(entry, effect)
                else:
                    _emit_filter(entry, effect, fps_num, fps_den)
```

---

## 5. Existing Tests & Unit Test Strategy

### 5.1 Existing Tests (`tests/test_render/test_emitter.py`)
Current test suite has 8 tests in `tests/test_render/test_emitter.py` and 1 test in `tests/test_emitter.py`.
All existing tests assert substring or element presence (e.g. `assert "<entry" in xml`, `assert 'producer="producer_abc"' in xml`). Adding `<filter service="volume">` inside clip entries preserves all existing assertions.

### 5.2 Required New Unit Tests for Micro-Fades
The worker agent should add dedicated test cases to `tests/test_render/test_emitter.py`:

1. `test_emitter_injects_30ms_audio_micro_fades_at_30fps()`:
   - Construct timeline with a 2.0s clip.
   - Emit MLT XML at 30 fps.
   - Parse XML via `etree.fromstring`.
   - Assert clip `<entry>` contains `<filter service="volume">`.
   - Assert keyframes: `frame 0 = 0.0`, `frame 1 = 1.0`, `frame 59 = 1.0`, `frame 60 = 0.0`.

2. `test_emitter_micro_fades_60fps_scale()`:
   - Emit timeline at 60 fps (`frame_rate_num: 60`).
   - Verify `fade_frames = 2` ($0.03 \times 60 = 1.8 \implies 2$).
   - Assert keyframe `frame 2 = 1.0` and `frame 118 = 1.0` for a 2.0s clip (120 frames total).

3. `test_emitter_micro_fades_short_clip_clamping()`:
   - Create a 0.04s clip (1 frame at 30fps).
   - Verify no invalid negative or out-of-bound keyframe ranges are generated.

4. `test_emitter_micro_fades_coexist_with_user_effects()`:
   - Add clip with explicit `brightness` effect.
   - Verify emitted entry contains both `autofade` filter and `brightness` filter.
