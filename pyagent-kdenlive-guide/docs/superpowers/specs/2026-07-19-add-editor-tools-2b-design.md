# PyAgent for Kdenlive — Sub-project 2b: Advanced editor tools

**Sub-project 2b of 3.** Sub-project 1 (cleanup) shipped; sub-project
2a (core tools: 10 high-frequency edits) shipped; this sub-project
adds 9 advanced tools (effect-param edit, keyframes, transition
edit, track effects, variable-rate speed). Sub-project 3 (end-to-end
AI + real-Kdenlive verification) is future.

## Problem

After 2a, pyagent exposes 29 editor tools. The user identified
the next layer of operations the AI cannot do without resorting
to "delete and re-insert" workarounds that lose precision and
state:

- Change the value of an existing effect parameter (e.g. raise
  the opacity of a vignette from 0.5 to 0.8) — the only path
  today is `remove_effect` followed by `apply_effect` with new
  params, which loses the effect's position in the stack and
  any per-effect keyframes the user added in the GUI.
- Add or edit keyframes on a keyframable parameter (e.g. ramp
  opacity from 0 to 1 across the first 2 seconds of a clip) —
  currently impossible; keyframes can only be set by hand in
  the Kdenlive UI.
- Edit a transition's timing (e.g. shorten a crossfade from
  1.0s to 0.5s) or change a transition's kind-specific param
  (e.g. a wipe's geometry) — currently impossible.
- Add a track-level effect (e.g. a compressor on the master
  audio track) — currently impossible.
- Add a keyframed speed ramp (e.g. 0–1s at 1×, 1–3s ramping
  to 4×, 3–4s back to 1×) — `change_clip_speed` from 2a is
  constant-rate only.

Sub-project 2b closes these gaps. The remaining items from the
2a spec's deferred list (undo/redo infrastructure, compound
clips, color scopes) are deferred to 2c — see "Non-goals" below.

## Goals

- 9 new tools that follow the existing per-domain pattern
  (ToolDef in `tools/*.py`, op function in `ops/*.py`,
  OP_TABLE entry, golden-file fixture, behavior test).
- Real Kdenlive file-format fidelity: keyframe animation
  strings, track-level filters, and the `timeremap` link all
  round-trip through a real Kdenlive open+save (Layer 3 test,
  when Kdenlive harness is extended).
- A small but necessary catalog update: every effect parameter
  in `phase1_knowledge_base/catalog.json` gains a `keyframes`
  boolean, populated by reading `param type="keyframe"`,
  `param type="animated"`, and 7 other animation-string
  keyframable `type=` values from the source XML (plus
  `param type="simplekeyframe"` for the 5 mlt_geometry
  params). This is required so `set_effect_param` can
  refuse to clobber keyframed data without warning, and
  so `set_keyframe` can reject calls on non-keyframable
  params.
- All 9 tools' JSON I/O locked by golden-file tests.
- All 9 tools' behavior verified by per-domain integration tests.
- 14 new error codes, all with at least one test case.
- All prod files stay <300 lines; all test files stay <400 lines.

## Non-goals (this sub-project)

- **Undo / redo of pyagent operations.** Kdenlive's own
  `QUndoStack` is in-memory only (no persistence — see
  `src/doc/docundostack.cpp`); pyagent could build its own
  snapshot-based undo, but that's a backend infrastructure
  change that touches every mutating op, not a single tool.
  Deferred to 2c.
- **Color scopes / vectorscope / waveform / histogram.**
  Kdenlive's scope widgets are pure runtime (no file
  representation exists). A `get_clip_color_stats`-style
  tool (render-frame-and-compute) would be a different
  category (read-only analytics) and is deferred to 2c.
- **Compound clips.** Reachable in the file format (nested
  `<tractor>` as a bin entry with `kdenlive:control_uuid`
  + `kdenlive:producer_type` + `kdenlive:clip_type` per
  `src/mltcontroller/clipcontroller.cpp:386-402`), but the
  integrity invariants (bin clip ID resolution, inner
  sequenceproperties coherence) make this a multi-week
  project. Deferred to 2c.
- **Subtitle / composition group targets.** Could be added
  to `group_clips` (2a) by allowing leaves with
  `leaf: "composition"`, but no concrete user need yet.
  Deferred.
- **Curve-ease params (`a`..`u`, `A`..`D`).** The 7 most
  common types are exposed (`linear`, `discrete`, `smooth`,
  `hold`, plus 4 ease-in / 4 ease-out variants). Adding the
  full `typeMap` from `keyframemodel.cpp:22-53` would add
  ~20 more `invalid_type` test cases for marginal AI value.

## The 3-sub-project plan (recap)

| # | Sub-project | Scope | Status |
|---|---|---|---|
| 1 | Cleanup | 7-phase rewrite + bug fixes | SHIPPED (commit `1693e5d`) |
| 2a | Core tools | 10 high-frequency edits (slip, ripple, speed-constant, split, replace, remove_effect, remove_transition, group, ungroup, list_groups) | SHIPPED (commits `5f2ef5f`–`7f71457` on main) |
| 2b | Advanced tools | **THIS SPEC**: 9 tools (effect-param edit, keyframes, transition edit, track effects, variable-rate speed) | NOT STARTED |
| 2c | Tier-3 deferred | undo/redo infra, compound clips, color stats, multi-clip ops, effect param-at-keyframe, more curve types | FUTURE |
| 3 | E2E verification | Real-Kdenlive + real-AI end-to-end; performance + UX polish | FUTURE |

## Architecture (this sub-project)

### Module layout

```
phase2_project_engine/
  _keyframes.py             # NEW: parse/serialize animation strings,
                           # is_keyframable_param(catalog, effect_id, param_name)
  ops/
    effects.py              # EXTEND: +get_effect_param, +set_effect_param
                           # (was 107 lines; target ~165)
    keyframes.py            # NEW: list_keyframes, set_keyframe, remove_keyframe
                           # (~150 lines)
    transitions.py          # EXTEND: +set_transition_property
                           # (was 152 lines; target ~230)
    clips_edit.py           # EXTEND: +set_clip_speed_ramp
                           # (was 228 lines; target ~275)
    track_effects.py        # NEW: add_effect_to_track, list_track_effects
                           # (~120 lines)
  backend.py                # EXTEND: 9 new methods on KdenliveBackend
                           # 333 lines; risk: pushes over 300-line cap.
                           # Mitigation: Task 0 will split into
                           # backend.py (interface) + backend_dispatch.py
                           # (concrete class), same pattern as 2a's
                           # clips.py → clips_edit.py split.
  tests/
    test_ops_effects.py     # EXTEND: +2 test functions
    test_ops_keyframes.py   # NEW: 3 test functions (+ 2-3 edge cases)
    test_ops_transitions.py # EXTEND: +1 test function
    test_ops_track_effects.py # NEW: 2 test functions
    test_ops_clips_edit.py  # EXTEND: +1 test function for set_clip_speed_ramp

phase3_pyagent_core/
  runtime.py                # EXTEND: +9 OP_TABLE entries, +7 MUTATING_OPS
  tools/
    effects.py              # EXTEND: +2 ToolDefs
    keyframes.py            # NEW: 3 ToolDefs
    transitions.py          # EXTEND: +1 ToolDef
    clips_edit.py           # EXTEND: +1 ToolDef
    track_effects.py        # NEW: 2 ToolDefs
  tests/
    fixtures/golden_io.json # EXTEND: +9 entries
    test_golden_io.py       # EXTEND: +9 parametrized cases

phase1_knowledge_base/
  catalog.json              # REBUILD: add keyframes: bool per parameter
  build_catalog.py          # EXTEND: read param type= in
                           # ANIMATION_STRING_KEYFRAME_TYPES or
                           # SIMPLEKEYFRAME_TYPES → keyframes: true or
                           # keyframes: "simplekeyframe"

phase7_real_session/
  tests/test_e2e.py         # EXTEND: +1 interop test (skipped in CI
                           # without Kdenlive; the kdenlive 26.04 CLI
                           # has no headless open+save mode and
                           # melt drops kdenlive:* properties, so
                           # activation is blocked on the Xvfb+Kdenlive
                           # harness extension documented in BUGS_FIXED T4.5)
```

### Why this layout

- **Per-domain file per concern**, same as 2a. The keyframe
  helper is the only new shared module, and it lives at
  `_keyframes.py` (underscore prefix) to mark it as private to
  the engine — not part of the public ops API.
- **Track effects get their own file** (`track_effects.py`)
  rather than extending `effects.py` because the filter
  lives on a different service (the track's `<tractor>` vs
  the clip's `<entry>`); putting both in one file would
  conflate the two domains and require cross-domain
  parameter validation logic. Splitting them keeps the
  per-domain boundary clean.
- **`backend.py` split is the only architectural risk.**
  333 lines + 9 new methods (~80 lines) = ~413 lines,
  well over the 300-line cap. Task 0 will determine the
  right split: most likely `backend.py` (ABC + 7
  trivial-pass methods) + `backend_dispatch.py`
  (the `KdenliveBackend` class with the substantive
  method bodies). The exact split is decided in Task 0,
  not in this spec.

## The 9 tool schemas

All tools follow the 2a convention: kwargs are snake_case,
returns are JSON-serializable dicts, runtime ids (clip_id,
effect_index, etc.) are positional or kwarg-based as
documented per tool.

### 1. `pyagent_get_effect_param` — read a single param

```python
def get_effect_param(
    tree: ProjectTree,
    clip_id: str,
    effect_index: int,
    param_name: str,
    *,
    catalog: Sequence[Mapping] | None = None,
) -> dict:
    """Return the current value of `param_name` on effect `effect_index` of `clip_id`.

    For non-keyframable params, returns the static value as a string.
    For keyframable params, returns both the raw animation string and
    a parsed list of {frame, value, type} entries.
    """
```

**Args:** `clip_id` (str), `effect_index` (int, 0-based),
`param_name` (str, exact match against the effect's catalog
parameter list).

**Returns:**

```json
{
  "clip_id": "clip_1",
  "effect_index": 0,
  "effect_id": "vignette",
  "param_name": "opacity",
  "value": "0.5",            // static value, or raw animation string
  "is_keyframable": false,   // true if catalog says so
  "keyframes": null          // or [{frame, value, type}, ...]
}
```

**Errors:** `clip_not_found`, `effect_index_out_of_range`,
`param_not_found`.

**Why not just expose the raw property?** Two reasons:
(1) the AI shouldn't have to know that the value is wrapped
in an animation string for keyframable params — this tool
abstracts that; (2) parsing the animation string is the
host's job, not the AI's, and we want to avoid the AI
mishandling the curve-type characters.

### 2. `pyagent_set_effect_param` — set a static value

```python
def set_effect_param(
    tree: ProjectTree,
    clip_id: str,
    effect_index: int,
    param_name: str,
    value: str,
    *,
    catalog: Sequence[Mapping] | None = None,
) -> dict:
    """Set `param_name` on effect `effect_index` of `clip_id` to a static `value`.

    WARNING: if the param is keyframable and currently has keyframes,
    this REPLACES the entire animation string with the static value.
    The response includes `previous_value` and `is_keyframable` so the
    caller can detect the case and decide to use set_keyframe instead.
    """
```

**Args:** `clip_id`, `effect_index`, `param_name`, `value` (str,
coerced to the catalog parameter's `type` if specified).

**Returns:**

```json
{
  "clip_id": "clip_1",
  "effect_index": 0,
  "param_name": "opacity",
  "previous_value": "0=1.0; 50=0.5; 100=1.0",
  "new_value": "0.8",
  "is_keyframable": true
}
```

**Errors:** `clip_not_found`, `effect_index_out_of_range`,
`param_not_found`, `value_type_mismatch` (if the catalog
declares a `type` and the value can't be coerced to it).

**Tool description (the prompt the LLM sees) explicitly
warns about the keyframe clobbering case.** A `confirm: bool`
arg is rejected for 2b to keep the API minimal; the warning
in the description is the v1 mitigation. (A `confirm` arg
is a candidate for 2c.)

### 3. `pyagent_list_keyframes` — read-only

```python
def list_keyframes(
    tree: ProjectTree,
    clip_id: str,
    effect_index: int,
    param_name: str,
) -> dict:
    """Return the keyframes on a keyframable param.

    Empty list if the param is not keyframable, or has no keyframes.
    `type` is one of: linear (`), discrete (|), smooth (~), hold (!),
    or the 8 ease-in/ease-out variants (a, b, c, d, A, B, C, D).
    Empty string if MLT didn't store a type (defaults to linear).

    For `simplekeyframe` params (5 in the 26.04 catalog, all in
    `rotation_keyframable.xml`), returns an empty list — the on-disk
    format is mlt_geometry, not animation-string, and pyagent 2b
    does not yet parse that format. The response includes a
    `format: "simplekeyframe"` field in this case so the caller
    can detect the situation.
    """
```

**Args:** `clip_id`, `effect_index`, `param_name`.

**Returns:**

```json
{
  "clip_id": "clip_1",
  "effect_index": 0,
  "param_name": "opacity",
  "format": "animated",
  "keyframes": [
    {"frame": 0, "value": "1.0", "type": ""},
    {"frame": 25, "value": "0.5", "type": "~"},
    {"frame": 50, "value": "1.0", "type": ""}
  ]
}
```

`format` is one of: `"animated"`, `"keyframe"`,
`"animatedrect"`, `"animatedfakerect"`, `"animatedfakepoint"`,
`"curve"`, `"bezier_spline"`, `"geometry"`, `"roto-spline"`
(all parsed as animation strings; `keyframes` is populated),
or `"simplekeyframe"` (mlt_geometry format; `keyframes` is
always `[]`). For non-keyframable params, `format` is `""`
and `keyframes` is `[]`.

**Errors:** `clip_not_found`, `effect_index_out_of_range`,
`param_not_found`. (No error for "not keyframable" — returns
empty list instead, matching the read-only semantics.)

### 4. `pyagent_set_keyframe` — add or update one keyframe

```python
def set_keyframe(
    tree: ProjectTree,
    clip_id: str,
    effect_index: int,
    param_name: str,
    frame: int,
    value: str,
    type: str = "linear",
) -> dict:
    """Add a new keyframe at `frame`, or update the value/type of an existing one.

    `frame` is 0-based, relative to the clip's in-point (matches Kdenlive UI).
    If a keyframe already exists at `frame`, its value and type are replaced.
    Otherwise the keyframe is inserted at the correct sorted position in
    the animation string. Other existing keyframes are preserved.
    """
```

**Args:** `clip_id`, `effect_index`, `param_name`, `frame`
(int, must satisfy `0 <= frame < clip_duration_frames`),
`value` (str), `type` (str; one of the 15 allowed values
above; default `"linear"`).

**Returns:**

```json
{
  "clip_id": "clip_1",
  "effect_index": 0,
  "param_name": "opacity",
  "frame": 25,
  "value": "0.7",
  "type": "linear",
  "action": "added"
}
```

(`action: "updated"` if a keyframe at that frame already
existed.)

**Errors:** `clip_not_found`, `effect_index_out_of_range`,
`param_not_found`, `param_not_keyframable`,
`simplekeyframe_format_unsupported` (the 5 simplekeyframe
params cannot be written by 2b's keyframe tools; full
mlt_geometry support is deferred to 2c), `frame_out_of_range`,
`invalid_type`.

### 5. `pyagent_remove_keyframe` — remove one keyframe

```python
def remove_keyframe(
    tree: ProjectTree,
    clip_id: str,
    effect_index: int,
    param_name: str,
    frame: int,
) -> dict:
    """Remove the keyframe at `frame`. No error if no keyframe exists there.

    If after removal the animation string is empty, the property is set
    to an empty string (which Kdenlive treats as "no animation").
    """
```

**Args:** `clip_id`, `effect_index`, `param_name`, `frame`.

**Returns:**

```json
{
  "clip_id": "clip_1",
  "effect_index": 0,
  "param_name": "opacity",
  "frame": 25,
  "removed": true
}
```

(`removed: false` if no keyframe at that frame — not an
error, just a no-op signal.)

**Errors:** `clip_not_found`, `effect_index_out_of_range`,
`param_not_found`, `param_not_keyframable`,
`simplekeyframe_format_unsupported`, `frame_out_of_range`.

### 6. `pyagent_set_transition_property` — edit any one transition prop

```python
def set_transition_property(
    tree: ProjectTree,
    transition_id: str,
    prop_name: str,
    value: str,
) -> dict:
    """Set any one property on a transition service.

    Reserved names (`mlt_service`, `id`, `_childid`, properties starting
    with `_`) are rejected. All other prop names are accepted; integer
    coercion is applied for `in`/`out`/`a_track`/`b_track`.
    """
```

**Args:** `transition_id` (str), `prop_name` (str), `value` (str).

**Returns:**

```json
{
  "transition_id": "transition_1",
  "prop_name": "in",
  "previous_value": "00:00:00.500",
  "new_value": "00:00:00.250"
}
```

**Errors:** `transition_not_found`, `prop_not_allowed`,
`value_type_mismatch` (if `prop_name` is a known integer
field and the value doesn't parse as an integer or timecode).

**Why one tool instead of two (timing + params)?** Timing
is 4 fields (`in`, `out`, `a_track`, `b_track`); transition
params are 5-20 fields depending on transition kind. A
single tool with a `prop_name` whitelist avoids the AI
needing to know which kind of property it's editing. The
reserved-name check prevents the AI from breaking the
transition by renaming `mlt_service` or `id`.

### 7. `pyagent_add_effect_to_track` — add effect to a track

```python
def add_effect_to_track(
    tree: ProjectTree,
    track_index: int,
    effect_id: str,
    params: Mapping[str, object] | None = None,
    *,
    catalog: Sequence[Mapping] | None = None,
) -> dict:
    """Add a Kdenlive effect to a track (not a clip).

    The effect is added as a <filter> child of the track's <tractor>.
    Same parameter semantics as `apply_effect`: if `params` is None or empty,
    the catalog's parameter defaults are used.

    Video effects cannot be added to audio tracks and vice versa
    (Kdenlive's own constraint; see effectstackmodel.cpp:1201-1214).
    """
```

**Args:** `track_index` (int), `effect_id` (str), `params`
(Mapping, optional).

**Returns:**

```json
{
  "track_index": 2,
  "effect_index": 1,
  "effect_id": "volume"
}
```

**Errors:** `track_index_out_of_range`, `effect_id_unknown`
(catalog miss), `effect_id_must_be_video` /
`effect_id_must_be_audio` (track type mismatch).

### 8. `pyagent_list_track_effects` — read-only

```python
def list_track_effects(
    tree: ProjectTree,
    track_index: int,
) -> dict:
    """Return the effect stack of `track_index`."""
```

**Args:** `track_index`.

**Returns:**

```json
{
  "track_index": 2,
  "effects": [
    {
      "index": 0,
      "effect_id": "avfilter.compressor",
      "enabled": true,
      "params": {"av.threshold": "0.5", "av.ratio": "4"}
    }
  ]
}
```

**Errors:** `track_index_out_of_range`.

### 9. `pyagent_set_clip_speed_ramp` — keyframed speed (timeremap)

```python
def set_clip_speed_ramp(
    tree: ProjectTree,
    clip_id: str,
    keyframes: Sequence[Mapping[str, int | float]],
) -> dict:
    """Add or replace a keyframed speed ramp on a clip.

    Uses an <link mlt_service="timeremap"> element on the clip's
    producer chain. Replaces the entire existing ramp; the AI
    is expected to read get_timeline_summary or list_keyframes
    first if it wants to preserve existing keyframes.

    `keyframes` is a list of {"time_ms": int, "rate": float} entries,
    sorted ascending by time. The first keyframe must be at time_ms=0
    and rate=1.0 (Kdenlive's own invariant; the LHS of the time_map
    is normalized to start at 0).

    See clipmodel.cpp:494-509 (read path) and 556-567 (write path).
    """
```

**Args:** `clip_id` (str), `keyframes` (Sequence of
`{"time_ms": int, "rate": float}`, must be non-empty,
sorted ascending, first must be at `time_ms=0` and
`rate=1.0`, all rates in `(0.0, 10.0]`, all `time_ms` in
`[0, clip_duration_ms]`).

**Returns:**

```json
{
  "clip_id": "clip_1",
  "keyframes_added": 3,
  "time_map": "00:00:00:00=0.000;00:00:01:00=0.500;00:00:04:00=1.000;",
  "min_rate": 0.5,
  "max_rate": 1.0
}
```

**Errors:** `clip_not_found`, `keyframes_empty`,
`time_out_of_range`, `rate_out_of_range` (0.1..10.0 per
the 2a convention), `time_monotonic_violation`,
`first_keyframe_must_be_zero` (new error code).

**Note on MLT HACK:** The Kdenlive write path uses
`frames_to_time(j.key() + offset, mlt_time_clock)` with
`offset=1` on the last keyframe (`clipmodel.cpp:556-567`).
pyagent will reproduce this exactly: the serialized
`time_map` has a `;` after the last keyframe's value and
no trailing frame number, matching Kdenlive's own output.

## Storage of group data: real Kdenlive format

### Keyframe animation strings (effect params)

Stored as the **value** of a `<property name="param_name">`
inside a `<filter>`. Kdenlive's effect XMLs declare keyframable
parameters with one of **two** `type=` attribute values, and the
two use **different on-disk serialization formats**:

| Catalog `type=` | Count in 26.04 | On-disk format | pyagent 2b support |
|---|---|---|---|
| `keyframe` | 12 | Animation string (this section) | **Full**: read, write, keyframe ops |
| `animated` | 685 | Animation string (this section) | **Full**: read, write, keyframe ops |
| `animatedrect` | 15 | Animation string (this section) | **Full**: read, write, keyframe ops |
| `animatedfakerect` | 2 | Animation string (this section) | **Full**: read, write, keyframe ops |
| `animatedfakepoint` | 1 | Animation string (this section) | **Full**: read, write, keyframe ops |
| `curve` | 2 | Animation string (this section) | **Full**: read, write, keyframe ops |
| `bezier_spline` | 1 | Animation string (this section) | **Full**: read, write, keyframe ops |
| `geometry` | 1 | Animation string (this section) | **Full**: read, write, keyframe ops |
| `roto-spline` | 1 | Animation string (this section) | **Full**: read, write, keyframe ops |
| `simplekeyframe` | 5 | mlt_geometry string (different format) | **Read-only**: tagged in catalog, listed, but `set_keyframe`/`remove_keyframe` raise `simplekeyframe_format_unsupported` |

(The original 2a spec had `type="keyframable"` — that value does
**not** appear in any of Kdenlive 26.04's 368 effect XMLs. The
correct values are the ten listed above. The catalog rebuild in
Task 0.3 checks for membership in the animation-string set; this
captures 720 of 725 keyframable params. The remaining 5
(simplekeyframe) are tagged in the catalog but route to the
"read-only" branch.)

The animation-string format:

```
{first_frame_int}={value}[{type_char}]; {frame_int}={value}[{type_char}]; ...
```

- `first_frame_int` is the frame at which the keyframe
  applies. The leading "header" form is what MLT uses to
  record the clip's filter-in frame; pyagent writes `0`
  (matching the 2a pattern of "always start from 0").
- `value` is the parameter's value as a string. For
  `double` types this is a decimal; for `integer` it's an
  int; for `bool` it's `0`/`1`; for `string` it's the
  literal text.
- `type_char` is optional. Allowed values (per
  `keyframemodel.cpp:22-53`'s `typeMap`):
  - `` ` `` linear
  - `|` discrete
  - `!` hold
  - `~` smooth
  - `a`..`u` (22 chars) ease curves, subtype "in"
  - `A`..`D` (4 chars) ease curves, subtype "out"

  pyagent 2b accepts a documented subset: linear, discrete,
  hold, smooth, and the 8 most common ease variants
  (`a`, `b`, `c`, `d`, `A`, `B`, `C`, `D`). The full
  alphabet is documented as "all 26 ease variants exist
  but are not yet exposed by pyagent" in the tool
  description.

Example (a fade-in over the first second at 25fps):

```xml
<filter mlt_service="fade_from_black">
  <property name="kdenlive:id">fade_from_black</property>
  <property name="level">0=0; 0~=0; 24=1</property>
  <property name="alpha">0=0; 24=1</property>
</filter>
```

### Track-level filters

Same XML structure as clip-level filters, but nested under
the track's `<tractor>` (the `Mlt::Tractor` per `trackmodel.cpp:52-54`):

```xml
<tractor id="track_tractor_2">
  <property name="kdenlive:track_name">Video 1</property>
  <multitrack>...</multitrack>
  <filter mlt_service="avfilter.compressor">
    <property name="kdenlive:id">avfilter.compressor</property>
    <property name="av.threshold">0.5</property>
    <property name="av.ratio">4</property>
  </filter>
</tractor>
```

### Time-remap (variable-rate speed)

A `<link mlt_service="timeremap">` element appended to the
clip's producer chain. The `time_map` is an animation
string of timecode→rate pairs, with the last keyframe
followed by a trailing `;`:

```xml
<producer id="clip_1_producer">
  <property name="resource">/path/to/source.mp4</property>
  <property name="in">00:00:00.000</property>
  <property name="out">00:00:04.000</property>
  <!-- ... other producer properties ... -->
  <link mlt_service="timeremap">
    <property name="time_map">00:00:00:00=0.000;00:00:01:00=0.500;00:00:04:00=1.000;</property>
    <property name="pitch">1</property>
    <property name="image_mode">nearest</property>
  </link>
</producer>
```

`time_map` timecode format: `HH:MM:SS:FF` (frame-precise
timecode, matching Kdenlive's output). Conversion from
milliseconds uses the existing `io._sec_to_tc(sec)` helper,
rounded to the nearest frame at the project's fps.

`pitch` is 1 (default; preserve audio pitch) or 0
(chipmunk effect). pyagent always writes 1 for now.

`image_mode` is `"nearest"` (default) or `"blend"`.
pyagent always writes `"nearest"`.

### Catalog update: `keyframes: bool` per parameter

The existing `catalog.json` has no `keyframes` field on any
of the 368 effects. `set_effect_param`, `set_keyframe`,
and `remove_keyframe` all need to know if a param is
keyframable. The `build_catalog.py` script already parses
each effect's source XML (`/usr/share/kdenlive/effects/*.xml`);
the addition is to read the `type` attribute on each
`<parameter>` element and write `"keyframes": true` to the
JSON if the value is in the animation-string keyframable
set, or `"keyframes": "simplekeyframe"` if it's the
mlt_geometry-based one.

**Concrete addition to `build_catalog.py`:**

```python
ANIMATION_STRING_KEYFRAME_TYPES = frozenset({
    "keyframe", "animated", "animatedrect", "animatedfakerect",
    "animatedfakepoint", "curve", "bezier_spline", "geometry",
    "roto-spline",
})
SIMPLEKEYFRAME_TYPES = frozenset({"simplekeyframe"})

# In the parameter-parsing loop, after extracting `type`:
t = param.attrib.get("type")
if t in ANIMATION_STRING_KEYFRAME_TYPES:
    out_param["keyframes"] = True
elif t in SIMPLEKEYFRAME_TYPES:
    out_param["keyframes"] = "simplekeyframe"
```

This is a ~10-line change. The catalog is rebuilt once
before Task 2 (keyframes) starts; the test suite
subsequently treats the `keyframes` field as required.

**Sanity check (Task 0.5):** after the rebuild, the
expected count is **720 params tagged `True` + 5 params
tagged `"simplekeyframe"`** across 368 effects. If the
count is wildly off (e.g. < 100 `True`), the catalog
rebuild is broken and Task 0.3 must be re-done.

## Error model

### Re-use existing codes from 2a

| Code | Type | Source tool |
|---|---|---|
| `clip_not_found` | `NotFoundError` | all 9 tools |
| `transition_not_found` | `NotFoundError` | `set_transition_property` |
| `effect_index_out_of_range` | `NotFoundError` | tools 1, 2, 3, 4, 5 |
| `rate_out_of_range` | `ValidationError` | `set_clip_speed_ramp` |

### New codes for 2b (14 total)

| Code | Type | Source tool | When |
|---|---|---|---|
| `param_not_found` | `NotFoundError` | 1, 2, 3, 4, 5 | effect param name doesn't exist in the catalog entry for this effect |
| `param_not_keyframable` | `ValidationError` | 4, 5 | `set_keyframe` / `remove_keyframe` called on a non-keyframable param (catalog says `keyframes: false`) |
| `simplekeyframe_format_unsupported` | `ValidationError` | 4, 5 | `set_keyframe` / `remove_keyframe` called on a `simplekeyframe` param (catalog says `keyframes: "simplekeyframe"`); mlt_geometry support is deferred to 2c |
| `frame_out_of_range` | `ValidationError` | 4, 5 | `frame < 0` or `frame >= clip_duration_frames` |
| `invalid_type` | `ValidationError` | 4 | `type` arg to `set_keyframe` is not in the allowed subset (15 values) |
| `value_type_mismatch` | `ValidationError` | 2, 6 | `set_effect_param` value can't be coerced to the catalog's `type`; or `set_transition_property` value can't be coerced to int for `in`/`out`/`a_track`/`b_track` |
| `prop_not_allowed` | `ValidationError` | 6 | `set_transition_property` prop name is reserved (`mlt_service`, `id`, `_childid`, or starts with `_`) |
| `track_index_out_of_range` | `NotFoundError` | 7, 8 | `track_index < 0` or beyond `len(get_tracks(tree))` |
| `effect_id_must_be_video` | `ValidationError` | 7 | `add_effect_to_track` with a video effect on an audio track |
| `effect_id_must_be_audio` | `ValidationError` | 7 | `add_effect_to_track` with an audio effect on a video track |
| `time_out_of_range` | `ValidationError` | 9 | `time_ms < 0` or `time_ms > clip_duration_ms` in `set_clip_speed_ramp` |
| `time_monotonic_violation` | `ValidationError` | 9 | `keyframes` not sorted ascending by time, or duplicate times |
| `keyframes_empty` | `ValidationError` | 9 | `set_clip_speed_ramp` called with empty list |
| `first_keyframe_must_be_zero` | `ValidationError` | 9 | first keyframe's `time_ms != 0` or `rate != 1.0` |

(14 codes listed above; the goal section's "14 new error codes" is correct.)

Re-use existing `BackendError`, `ValidationError`,
`NotFoundError` classes per the 2a pattern. Every error
carries a `fix:` line in its message (e.g.
`fix: call list_keyframes to see valid keyframes`).

## Testing approach: 3 layers

### Layer 1: golden-file (per-tool I/O)

Each of the 9 new tools gets one parametrized entry in
`phase3_pyagent_core/tests/fixtures/golden_io.json` and
one corresponding case in
`phase3_pyagent_core/tests/test_golden_io.py`. The
existing `_SETUP` mechanism (added in 2a Task 2) is reused
where a tool needs a precondition (e.g. an effect with
keyframes already set). No new `_SETUP` mechanism is
needed for 2b.

**Count:** +9 entries (10 → 19 total).

### Layer 2: per-domain integration tests

Each of the 9 new tools gets a behavior test in
`phase2_project_engine/tests/test_ops_<domain>.py`. The
tests follow the 2a pattern: build a small project, call
the op, assert the XML state, assert the return shape,
and test at least one error case per tool.

Additional edge-case tests (3-5 total):

- `set_keyframe` with an invalid `type` arg → `invalid_type`
- `set_keyframe` on a non-keyframable param → `param_not_keyframable`
- `set_keyframe` on a `simplekeyframe` param → `simplekeyframe_format_unsupported`
- `set_clip_speed_ramp` with non-monotonic keyframes → `time_monotonic_violation`
- `add_effect_to_track` with an audio effect on a video track → `effect_id_must_be_audio`
- `set_transition_property` with reserved name → `prop_not_allowed`

**Count:** +9 to +12 test functions (across 5 test files).

### Layer 3: real-Kdenlive interop test

One new interop test in
`phase7_real_session/tests/test_e2e.py`:

```python
@skipif_kdenlive_missing
def test_2b_round_trip_through_real_kdenlive():
    # Build a project with a keyframed effect, a track effect,
    # and a time-remapped clip. Open in real Kdenlive, save,
    # re-load, and verify all three features survive.
    ...
```

The test is **always skipped** until the Xvfb+Kdenlive
harness extension documented in BUGS_FIXED T4.5 is
implemented (kdenlive 26.04 CLI has no headless open+save
mode, and `melt` drops `kdenlive:*` properties). Code is
in place; activation is gated.

**Count:** +1 new skipped test. Post-2a has 2 skipped
(1 baseline e2e + 1 new interop skip from 2a). Post-2b
will have 3 skipped (2 existing + 1 new).

## Test count budget

Verified baseline (re-ran `pytest -q` against
`main@7f71457`): **260 passed + 2 skipped + 1 warning**.
Breakdown (by file, not by layer — see "Why this is by
file, not by layer" below):

| Test file | Count | What it covers |
|---|---|---|
| `phase3_pyagent_core/tests/test_golden_io.py` | 16 (parametrized) | Layer 1: 19 existing tools × ~1 case each |
| `phase2_project_engine/tests/test_ops_*.py` | 107 | Layer 2: behavior tests for all 19 existing tools |
| `phase3_pyagent_core/test_*.py` (no `tests/`) | 27 | Layer 1+2 mixed (extension, runtime, integration) |
| `phase4_chat_ui/test_*.py` | 51 | Phase 4 UI tests (unchanged by 2b) |
| `phase5_dbus_sync/test_*.py` | 29 | Phase 5 dbus tests (unchanged by 2b) |
| `phase6_render_qc/test_*.py` | 34 | Phase 6 render tests (unchanged by 2b) |
| `phase7_real_session/tests/test_e2e.py` | 5 (2 skipped) | Layer 3: real-Kdenlive interop |
| **Total collected** | **262** | 260 passed + 2 skipped |

After 2b:

| Source | Net | Rationale |
|---|---|---|
| Layer 1: `test_golden_io.py` | **+9** | 1 new parametrized case per new tool (9 tools, some shared test functions) |
| Layer 2: per-domain integration | **+10 to +13** | 1 behavior test per new tool (9) + 2-4 edge-case tests (invalid_type, param_not_keyframable, simplekeyframe_format_unsupported, time_monotonic_violation, effect_id_must_be_audio, prop_not_allowed) |
| Layer 3: real-Kdenlive interop | **+1 (skipped)** | 1 new test in `test_e2e.py` (always skipped until Kdenlive harness extended) |
| **Total passing** | 260 + 9 + 10..13 = **279..282** | |
| **Total skipped** | 2 + 1 = **3** | |

Target: **280 passed + 3 skipped** (conservative
midpoint). The 2 existing skips remain; the 1 new skip
is the L3 interop test.

**Why this is by file, not by layer:** the 2a spec's
test-count table split by layer but conflated the
"Layer 2: 260" baseline number with the actual total,
masking a ~19-test gap. The breakdown above is the
authoritative source for the 260 + 2 baseline; every
test in the repo that does not change in 2b is
accounted for.

**2a spec discrepancy (corrected here):** the 2a spec
predicted "252 passed + 1 skipped" but the actual
post-2a count is 260 + 2. The 8-test positive gap
and 1-skip positive gap are both real — the 2a
implementation caught more latent bugs (each fixed
with a regression test) and added 1 more L3 skip
than the spec budgeted for. This is documented here
so 2b's budget is grounded in the actual post-2a
state, not the spec's (slightly optimistic)
prediction.

## Commit plan

| # | Commit | Branch (on top of `main`) | Files touched | Tools added |
|---|---|---|---|---|
| 1 | `[effects] add get/set_effect_param` | `add-editor-tools-2b` | `ops/effects.py` (+2), `tools/effects.py` (+2 ToolDefs), `runtime.py` (+2 OP_TABLE, +2 MUTATING_OPS), `tests/test_ops_effects.py` (+2), `golden_io.json` (+2) | 2 |
| 2 | `[keyframes] add list/set/remove_keyframe` | (same) | `ops/keyframes.py` (new, ~150 lines), `tools/keyframes.py` (new, ~70 lines), `runtime.py` (+3 OP_TABLE, +2 MUTATING_OPS; `list_keyframes` is read-only), `tests/test_ops_keyframes.py` (new, ~250 lines incl. 3 edge cases), `golden_io.json` (+3) | 3 |
| 3 | `[transitions] add set_transition_property` | (same) | `ops/transitions.py` (+1), `tools/transitions.py` (+1 ToolDef), `runtime.py` (+1 OP_TABLE, +1 MUTATING_OPS), `tests/test_ops_transitions.py` (+1), `golden_io.json` (+1) | 1 |
| 4 | `[track-effects + variable-speed] add add/list_track_effects + set_clip_speed_ramp` | (same) | `ops/track_effects.py` (new, ~120 lines), `tools/track_effects.py` (new, ~70 lines), `ops/clips_edit.py` (+1), `tools/clips_edit.py` (+1 ToolDef), `runtime.py` (+3 OP_TABLE, +2 MUTATING_OPS; `list_track_effects` is read-only), `tests/test_ops_track_effects.py` (new, ~180 lines), `tests/test_ops_clips_edit.py` (+1), `golden_io.json` (+3) | 3 |

**Pre-work (Task 0):**

- 0.1: Branch + worktree at `/home/ah64/apps/mlt-pipeline-2b`, branch `add-editor-tools-2b` off `main@7f71457`. Baseline: 260 passed + 2 skipped; `list_tools()` = 29.
- 0.2: `backend.py` split decision. If 333 + 80 > 300 after Task 1's first commit shows the bloat, split into `backend.py` (interface, ~150 lines) + `backend_dispatch.py` (concrete, ~250 lines). The split happens in Task 0.2; Task 1 then adds the new methods against the split structure.
- 0.3: Catalog update. Edit `build_catalog.py` (3-line change), rebuild `catalog.json`. Verify the new `keyframes` field is present on all 368 effects.
- 0.4: `_keyframes.py` new helper module. Pure functions: `parse_animation_string(s: str) -> list[Keyframe]`, `serialize_keyframes(ks: list[Keyframe]) -> str`, `is_keyframable_param(catalog, effect_id, param_name) -> bool`, `coerce_param_value(catalog, effect_id, param_name, value: str) -> str`. Unit tests in `phase2_project_engine/tests/test_keyframes.py` (~150 lines).
- 0.5: Pre-merge review of catalog change. Pi-1 (or the user) signs off that the catalog update is correct (count of keyframable params matches Kdenlive's UI count for at least 5 known effects).

## Migration / rollback

- All 4 commits land on `add-editor-tools-2b` and merge
  into `main`. If a commit introduces a regression, the
  standard revert path applies: `git revert <sha>` per
  commit. Because each commit is independently testable,
  partial-rollback is possible (e.g. ship commits 1-3 and
  defer 4).
- The 29 existing tools' I/O is unchanged. The agent
  harness does not need to relearn anything.
- The 9 new golden-file fixtures do not conflict with
  existing entries; the existing 19 entries remain
  byte-identical.
- The catalog update is a one-shot JSON file change.
  If it needs to be reverted, `git checkout main --
  phase1_knowledge_base/catalog.json` restores the
  pre-2b catalog (without `keyframes` fields).
- If the Kdenlive format for any of {keyframes,
  timeremap, track effects} diverges from this spec in
  a future Kdenlive version, the relevant commit is the
  only one that needs rework (the L3 interop test will
  fail and surface the drift).

## Definition of done

- [ ] Branch `add-editor-tools-2b` exists with 4 commits
      on top of `main@7f71457`.
- [ ] All 9 new tools appear in `runtime.list_tools()`
      output (29 + 9 = 38).
- [ ] `extension.ts` requires no changes (auto-discovery
      via `list_tools()` confirmed at extension.ts:62-65).
- [ ] All 9 new tools have a parametrized golden-file
      case in `phase3_pyagent_core/tests/fixtures/golden_io.json`.
- [ ] All 9 new tools have a behavior test in
      `phase2_project_engine/tests/test_ops_<domain>.py`.
- [ ] Catalog updated with `keyframes: bool` per
      parameter; `build_catalog.py` reads the field from
      `param type="keyframable"`.
- [ ] All 14 new error codes have at least one test case.
- [ ] All 9 new tools' return shapes match §"The 9 tool
      schemas" above.
- [ ] All 9 new tools' error codes match §"Error model".
- [ ] Track effects use real Kdenlive format: filters
      nested under the track's `<tractor>` with
      `kdenlive:id` (colon) per BUG 9 fix.
- [ ] Variable-rate speed uses real Kdenlive format:
      `<link mlt_service="timeremap">` with `time_map`
      (timecode-based animation string), `pitch=1`,
      `image_mode="nearest"`.
- [ ] The L3 interop test is in place (skipped in CI
      without Kdenlive; activation gated on the
      Xvfb+Kdenlive harness extension).
- [ ] Every new prod file is <300 lines; every new test
      file is <400 lines.
- [ ] No existing tool's JSON I/O has changed (the 29
      existing tools' golden fixtures pass unchanged).
- [ ] `BUGS_FIXED.md` is updated with any bugs found
      during 2b.
- [ ] The plan doc
      (`docs/superpowers/plans/2026-07-19-add-editor-tools-2b.md`)
      exists.
- [ ] All ~280 tests pass (279-282 pass + 3 skip in CI
      without Kdenlive).

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `mlt_service="timeremap"` link is order-sensitive inside the producer chain; wrong placement breaks the clip | Medium | High | The link goes as the LAST element in the producer's child chain, matching Kdenlive's own output (per `clipmodel.cpp:556-567`). A unit test reads back the `time_map` and asserts the structure. The L3 interop test (when activated) is the final check. |
| Curve-type chars (`a..u`, `A..D`) are case-sensitive and many; easy to write a wrong char | Medium | Low | Whitelist exactly the 15 known values (linear, discrete, smooth, hold, 8 ease variants); reject unknown with `invalid_type`. The set is documented in the tool description and a code comment. |
| `set_effect_param` clobbers a keyframed value with a static one — silent data loss | Medium | High | Response includes `is_keyframable` and `previous_value`; tool description explicitly warns the LLM. A `confirm: bool` arg is a candidate for 2c but rejected for 2b to keep the API minimal. |
| Kdenlive's effect XMLs use `type="keyframe"` and `type="simplekeyframe"` for keyframable params; the previous spec's `type="keyframable"` does not exist in any of the 368 effect XMLs. The new spec tags 10 distinct `type=` values as keyframable (see §"Keyframe animation strings" above). | Done | High | The catalog rebuild checks for membership in `ANIMATION_STRING_KEYFRAME_TYPES` (9 values) or `SIMPLEKEYFRAME_TYPES` (1 value), not an exact string match. Task 0.5 sanity check verifies the count matches expectations (~720 animation-string + 5 simplekeyframe). If the count is wildly off, the rebuild is broken. |
| Track effects' filter order matters (Kdenlive processes top-to-bottom); adding to a track that's also a member of a multitrack might conflict | Low | Medium | Insert at end of track's existing filter list (matches Kdenlive's "newest at bottom" convention). Document the ordering invariant in the tool description. |
| `set_transition_property` with `a_track` / `b_track` could orphan a transition if the new track index is invalid | Low | High | Validate the track index is in range; reject with `value_type_mismatch` if the value can't be coerced to int, or `track_index_out_of_range` (re-used) if the int is out of range. |
| `set_clip_speed_ramp` time_map is timecode-based; ms→timecode conversion needs `io._sec_to_tc` which rounds to 3 decimals (ms-precise) but the timeremap uses frame-precise timecode | Low | Low | Use a new helper `_sec_to_tc_frames(sec, fps)` for the timeremap path. The existing `_sec_to_tc` stays for ms-precise contexts. |
| `backend.py` 300-line cap risk | Medium | Low | Task 0.2 splits it. The split is decided before Task 1 starts, not as part of any commit. |
| The catalog update changes `catalog.json` for all 368 effects; this is a 70KB+ file and the diff is huge | Low | Low | The diff is mostly "+1 boolean field per parameter". Review with `git diff --stat`; the actual change is small per-line. |
| `extension.ts` may not pick up the new tools if `list_tools()` ordering changes (the TS uses `Object.keys()` which is insertion-ordered for string keys) | Very low | Low | The 9 new tools are added in 4 separate commits; the ordering is determined by import order in `tools/__init__.py`, which is alphabetical. The TS extension does not depend on the order. |

## Open questions

None. All design decisions captured.
