# PyAgent for Kdenlive — Sub-project 2b: Advanced Editor Tools Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 9 advanced editor tools to pyagent: effect-param edit (2), keyframes (3), transition edit (1), track effects (2), variable-rate speed (1). 4 commits + 5 pre-work sub-tasks. ~280 collected tests post-merge. Catalog gains a `keyframes` field on 725 params (720 animation-string + 5 simplekeyframe).

**Architecture:** Per-domain ops functions in `phase2_project_engine/ops/<domain>.py`, ToolDef dataclasses in `phase3_pyagent_core/tools/<domain>.py`, OP_TABLE + MUTATING_OPS entries in `runtime.py`, golden-file fixtures in `phase3_pyagent_core/tests/fixtures/golden_io.json`, per-tool behavior tests in `phase2_project_engine/tests/test_ops_<domain>.py`, and one real-Kdenlive interop test in `phase7_real_session/tests/test_e2e.py`. The new `_keyframes.py` private helper centralizes animation-string parse/serialize logic. The catalog is rebuilt once in Task 0.3 with the new `keyframes` field. `backend.py` (333 lines pre-2b) is split in Task 0.2 if needed to keep under the 300-line cap. The TypeScript extension auto-discovers tools via `runtime.list_tools()` — no TS changes required.

**Tech Stack:** Python 3.11+, lxml, pytest; existing `phase2_project_engine` and `phase3_pyagent_core` modules. No new dependencies. No TypeScript changes. No Godot patterns.

## Global Constraints

These are the spec's project-wide rules. Every task's requirements implicitly include this section.

- **Python 3.11+** only; keep `from __future__ import annotations` imports.
- **Three error classes** (existing): `BackendError`, `ValidationError`, `NotFoundError` — defined in `phase2_project_engine/errors.py`. **No new error classes.**
- **All errors** raised to the LLM carry a `fix:` hint line (use `validation_error()` for `ValidationError`).
- **File naming**: snake_case, no spaces, no CamelCase.
- **Module size budget**: every production file <300 lines; every test file <400 lines. Split if a file needs to grow.
- **Tool I/O**: each of the 9 new tools' JSON output is locked by a golden-file test. Any drift fails the build.
- **14 new error codes** for 2b, all with at least one test case:
  `param_not_found`, `param_not_keyframable`, `simplekeyframe_format_unsupported`, `frame_out_of_range`, `invalid_type`, `value_type_mismatch`, `prop_not_allowed`, `track_index_out_of_range`, `effect_id_must_be_video`, `effect_id_must_be_audio`, `time_out_of_range`, `time_monotonic_violation`, `keyframes_empty`, `first_keyframe_must_be_zero`.
- **Auto-save after any mutating op**: runtime adds the 7 mutating tools to `MUTATING_OPS`; `list_keyframes` and `list_track_effects` are read-only.
- **Bug policy**: every bug found during 2b implementation MUST be fixed with a regression test before that task's commit lands. Log to `BUGS_FIXED.md` (one line per bug, with `file:line`).
- **Commit format**: `[<system>] add <short summary>`. Use `[effects]`, `[keyframes]`, `[transitions]`, `[track-effects]`, `[setup]` as the system prefix.
- **Working tree state**: at every commit boundary, `PYTHONPATH=. pytest -q` is green. Never commit red.
- **No behavior change** for the 29 existing tools' I/O.
- **TypeScript extension**: NO changes required. `extension.ts:62-65` calls `runtime.list_tools()` at load time and iterates the result. New tools are auto-exposed.
- **Kdenlive file format**: must match real Kdenlive 26.04. The format details are in the spec at `docs/superpowers/specs/2026-07-19-add-editor-tools-2b-design.md` §"Storage of group data: real Kdenlive format".
- **Keyframe attribute names**: Kdenlive's effect XMLs declare keyframable params with `type="keyframe"`, `type="animated"`, and 7 other animation-string values (10 in total) OR `type="simplekeyframe"` for mlt_geometry. There is NO `type="keyframable"` — that string does not appear in any of Kdenlive 26.04's 368 effect XMLs.
- **simplekeyframe params** (5 in the catalog, all in `rotation_keyframable.xml`) are tagged in the catalog as `keyframes: "simplekeyframe"`; `set_keyframe`/`remove_keyframe` on them raise `simplekeyframe_format_unsupported`.

## File Structure (post-2b)

```
pyagent-kdenlive-guide/
  phase2_project_engine/
    _keyframes.py             # NEW: parse/serialize animation strings,
                             # is_keyframable_param(catalog, effect_id, param_name),
                             # coerce_param_value, _sec_to_tc_frames
                             # (~150 lines)
    ops/
      bin.py                  (unchanged)
      clips.py                (unchanged: 5 placement ops)
      clips_edit.py           # EXTENDED: +set_clip_speed_ramp
                             # (was 228 lines; target ~278)
      effects.py              # EXTENDED: +get_effect_param, +set_effect_param
                             # (was 107 lines; target ~170)
      transitions.py          # EXTENDED: +set_transition_property
                             # (was 152 lines; target ~230)
      keyframes.py            # NEW: list_keyframes, set_keyframe, remove_keyframe
                             # (~150 lines)
      track_effects.py        # NEW: add_effect_to_track, list_track_effects
                             # (~130 lines)
      markers.py              (unchanged)
      groups.py               (unchanged)
      _helpers.py             (unchanged)
      __init__.py             # EXTENDED: +keyframes, +track_effects exports
    backend.py                # MAYBE-SPLIT in Task 0.2 (333 lines now;
                             # 9 new methods add ~72 lines → ~405).
                             # If split, becomes:
                             #   backend.py          (interface, ~150 lines)
                             #   backend_dispatch.py (KdenliveBackend, ~250 lines)
    tests/
      test_keyframes.py       # NEW: tests for _keyframes.py (~150 lines)
      test_ops_effects.py     # EXTENDED: +2 test functions
      test_ops_keyframes.py   # NEW: 3 test functions + 3 edge cases (~280 lines)
      test_ops_transitions.py # EXTENDED: +1 test function
      test_ops_track_effects.py # NEW: 2 test functions + 1 edge case (~180 lines)
      test_ops_clips_edit.py  # EXTENDED: +1 test function for set_clip_speed_ramp

phase3_pyagent_core/
  runtime.py                  # EXTENDED: +9 OP_TABLE entries, +7 MUTATING_OPS
  tools/
    effects.py                # EXTENDED: +2 ToolDefs
    keyframes.py              # NEW: 3 ToolDefs (~80 lines)
    transitions.py            # EXTENDED: +1 ToolDef
    track_effects.py          # NEW: 2 ToolDefs (~70 lines)
    clips_edit.py             # EXTENDED: +1 ToolDef
  tests/
    fixtures/golden_io.json   # EXTENDED: +9 entries
    test_golden_io.py         # EXTENDED: +9 parametrized cases (no new _SETUP)

phase1_knowledge_base/
  catalog.json                # REBUILT in Task 0.3 (gains keyframes: bool)
  build_catalog.py            # EXTENDED in Task 0.3 (~10 lines added)

phase7_real_session/
  tests/test_e2e.py           # EXTENDED: +1 interop test (skipped without Kdenlive)
```

## Source-of-truth references

Read these before each task as needed (NOT before reading the task itself):

- **Spec:** `pyagent-kdenlive-guide/docs/superpowers/specs/2026-07-19-add-editor-tools-2b-design.md` — the design doc this plan implements.
- **Existing 2a plan:** `pyagent-kdenlive-guide/docs/superpowers/plans/2026-07-19-add-editor-tools-2a.md` — the template for this plan; same commit pattern, same TDD cadence.
- **Kdenlive 26.04 source:**
  - `src/assets/keyframes/model/keyframemodel.cpp:22-53` (curve-type `typeMap`): the 26 valid curve characters.
  - `src/timeline2/model/clipmodel.cpp:494-509, 556-567` (timeremap read/write): how `time_map` is serialized and the HACK `+offset=1` on the last keyframe.
  - `src/timeline2/model/trackmodel.cpp:42-54, 1653-1658` (track effects): track effects are filters on the track's `<tractor>`.
  - `src/effects/effectstack/model/effectstackmodel.cpp:386-419, 1490-1620` (effect import/persistence): how effect filters are stored, and the `kdenlive:id` (colon) vs `kdenlive_id` (snake) convention.
  - `src/timeline2/model/groupsmodel.cpp:720-770` (groups JSON serialization): the `kdenlive:sequenceproperties.groups` format and the `Leaf` resolution.
- **Existing pyagent code (the patterns to follow):**
  - `phase2_project_engine/ops/clips_edit.py` (the 2a clips-edit ops): the cleanest example of a per-domain ops module. Mirror its error-handling style.
  - `phase2_project_engine/ops/effects.py` (`apply_effect` and `remove_effect`): how effect filters are written; the `kdenlive:id` (colon) BUG 9 fix.
  - `phase2_project_engine/ops/transitions.py` (`add_transition`): how transitions are inserted; the BUG 2 (a.out / b.in) and BUG 10 (track tractor vs main tractor) fixes.
  - `phase3_pyagent_core/tools/clips_edit.py`: the ToolDef pattern (InputSchema with kwargs, response shape, error codes).
  - `phase2_project_engine/tests/test_ops_clips.py`: the per-domain test style (build a project, call the op, assert the XML state).

---

## Task 0: Pre-work

This task is **not** a single commit. It's 5 sub-tasks, each independently testable. Sub-tasks 0.1, 0.2, 0.3, 0.4 land in 4 separate commits; 0.5 is a sanity check that runs after 0.3 and 0.4. Sub-tasks 0.1-0.4 can be done in any order; 0.5 must run last.

### Task 0.1: Set up branch + worktree + verify baseline

**Files:**
- Create: `/home/ah64/apps/mlt-pipeline-2b/` (worktree, NOT in this repo's tracked files)
- Branch: `add-editor-tools-2b` off `main@7f71457`

**Interfaces:**
- Consumes: existing `main@7f71457` with 260 passed + 2 skipped.
- Produces: a new worktree with `add-editor-tools-2b` branch, 260 passed + 2 skipped baseline.

- [ ] **Step 1: Create the worktree**

```bash
cd /home/ah64/apps/mlt-pipeline
git worktree add -b add-editor-tools-2b /home/ah64/apps/mlt-pipeline-2b main
```

Expected: `Preparing worktree (new branch 'add-editor-tools-2b')` then `HEAD is now at 7f71457`.

- [ ] **Step 2: Verify the baseline**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. timeout 180 pytest -q --no-header 2>&1 | tail -3
```

Expected: `260 passed, 2 skipped, 1 warning in ~90s`.

- [ ] **Step 3: Verify `list_tools()` count**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
PYTHONPATH=. python3 -c "from phase3_pyagent_core.runtime import list_tools; print(len(list_tools()))"
```

Expected: `29`.

- [ ] **Step 4: No commit needed for 0.1**

Sub-task 0.1 is just setup. No commit. Move to 0.2.

### Task 0.2: Decide on `backend.py` split (may be a no-op)

**Files:**
- Possibly split: `phase2_project_engine/backend.py` (333 lines)
- Possibly create: `phase2_project_engine/backend_dispatch.py` (the concrete `KdenliveBackend` class, ~250 lines)
- Possibly modify: `phase2_project_engine/backend.py` (becomes the interface, ~150 lines)
- Modify: `phase2_project_engine/tests/test_backend.py` (if split happens, update imports)

**Decision criteria:** The current `backend.py` is 333 lines. The 9 new methods will add ~72 lines (estimated). The 2a spec's cap is 300 lines, so post-2b will be ~405 — over the cap. The split is recommended but NOT mandatory. If the file is split, both halves stay under 300 lines (interface ~150, dispatch ~250). If NOT split, the 300-line cap will be violated.

- [ ] **Step 1: Decide**

If the implementer judges that the 9 new methods can fit in 333 + 72 = 405 lines while keeping the file readable and <300 lines is impossible without splitting, then split. The split is:

- `backend.py`: the `Backend` ABC + docstrings + small shared helpers, ~150 lines.
- `backend_dispatch.py`: the `KdenliveBackend` concrete class with all the methods, ~250 lines.

If the implementer judges the split is worth it, proceed to Step 2. If not, skip to Step 4.

- [ ] **Step 2: Perform the split (if Step 1 says yes)**

Create `phase2_project_engine/backend_dispatch.py` with the `KdenliveBackend` class. Trim `backend.py` to just the ABC.

The split should preserve the public API: `from phase2_project_engine import KdenliveFileBackend` and `from phase2_project_engine.backend import KdenliveBackend` (or similar) should both work. The existing `KdenliveFileBackend` (a class) at the package level should be a re-export of `KdenliveBackend` from one of the two new files.

Check the existing public re-exports:

```bash
cd /home/ah64/apps/mlt-pipeline-2b
grep -nE "KdenliveFileBackend|KdenliveBackend" pyagent-kdenlive-guide/phase2_project_engine/__init__.py
```

Use the result to decide which file owns the public class.

- [ ] **Step 3: Run tests to verify the split (if Step 1 said yes)**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. timeout 180 pytest -q --no-header 2>&1 | tail -3
```

Expected: `260 passed, 2 skipped, 1 warning` (no regression).

- [ ] **Step 4: Commit the split (if Step 1 said yes)**

```bash
cd /home/ah64/apps/mlt-pipeline-2b
git add pyagent-kdenlive-guide/phase2_project_engine/backend.py pyagent-kdenlive-guide/phase2_project_engine/backend_dispatch.py pyagent-kdenlive-guide/phase2_project_engine/tests/test_backend.py
git commit -m "[setup] split backend.py to keep <300 lines (Task 0.2)"
```

If Step 1 said no, skip this entire step and add a note to the Task 5 final review that `backend.py` is 405 lines post-2b and accept the cap violation as a 2c cleanup item.

- [ ] **Step 5: No-op if Step 1 said no**

If `backend.py` is NOT being split, no commit in Task 0.2. Move to 0.3.

### Task 0.3: Catalog update — add `keyframes` field per parameter

**Files:**
- Modify: `phase1_knowledge_base/build_catalog.py` (add the `ANIMATION_STRING_KEYFRAME_TYPES` and `SIMPLEKEYFRAME_TYPES` constants, and the ~5-line logic that reads `param.attrib.get("type")` and writes `keyframes: true` or `keyframes: "simplekeyframe"` to the JSON)
- Rebuild: `phase1_knowledge_base/catalog.json`

**Interfaces:**
- Consumes: Kdenlive 26.04's effect XMLs at `/usr/share/kdenlive/effects/*.xml` (368 files, each with `<parameter>` elements in the `https://www.kdenlive.org` namespace).
- Produces: a `catalog.json` where every effect's `parameters` list has a `keyframes` field on keyframable params (720 expected as `true`, 5 expected as `"simplekeyframe"`).

- [ ] **Step 1: Read the current `build_catalog.py` to find the parameter-parsing loop**

```bash
cd /home/ah64/apps/mlt-pipeline-2b
grep -n "parameters" pyagent-kdenlive-guide/phase1_knowledge_base/build_catalog.py | head -10
```

Expected output: a list of lines where `parameters` appears, including the loop that builds `out_param` from each `<parameter>` XML element.

- [ ] **Step 2: Add the keyframe-type constants and the parameter-tagging logic**

Locate the parameter-parsing loop in `build_catalog.py` and add this code (adapt to the file's existing style — the actual placement depends on where `out_param` is built):

```python
# Keyframe type classification. See Kdenlive 26.04's effect XMLs.
# type="keyframable" does NOT exist; the real values are below.
ANIMATION_STRING_KEYFRAME_TYPES = frozenset({
    "keyframe",            # modern: animation string
    "animated",            # most common (685 params)
    "animatedrect",        # rectangle with keyframes
    "animatedfakerect",    # internal use
    "animatedfakepoint",   # internal use
    "curve",               # curve-typed param
    "bezier_spline",       # bezier-spline param
    "geometry",            # geometry param
    "roto-spline",         # rotoscoping spline
})
SIMPLEKEYFRAME_TYPES = frozenset({"simplekeyframe"})

# In the parameter-parsing loop, after extracting `type`:
param_type = param.attrib.get("type")
if param_type in ANIMATION_STRING_KEYFRAME_TYPES:
    out_param["keyframes"] = True
elif param_type in SIMPLEKEYFRAME_TYPES:
    out_param["keyframes"] = "simplekeyframe"
```

Note: the XML uses the namespace `https://www.kdenlive.org`. If the parser doesn't already use a namespace-aware API, you may need to adjust the parameter extraction. Check the existing code first.

- [ ] **Step 3: Rebuild the catalog**

```bash
cd /home/ah64/apps/mlt-pipeline-2b
PYTHONPATH=. python3 pyagent-kdenlive-guide/phase1_knowledge_base/build_catalog.py
```

Expected: a message that the catalog was rebuilt (e.g., `Wrote catalog.json with 368 effects` or similar). If the script writes to a different path, check the output.

- [ ] **Step 4: Verify the keyframe field is present on the expected count**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
python3 << 'PYEOF'
import json
cat = json.load(open("phase1_knowledge_base/catalog.json"))
effs = cat.get("effects", [])
true_count = 0
simple_count = 0
for e in effs:
    for p in e.get("parameters", []):
        if p.get("keyframes") is True:
            true_count += 1
        elif p.get("keyframes") == "simplekeyframe":
            simple_count += 1
print(f"keyframes: true count: {true_count} (expected ~720)")
print(f"keyframes: simplekeyframe count: {simple_count} (expected 5)")
assert 700 <= true_count <= 740, f"true count off: {true_count}"
assert simple_count == 5, f"simplekeyframe count off: {simple_count}"
print("OK")
PYEOF
```

Expected: `OK`. If the count is wildly off, the build_catalog.py change is broken — debug before committing.

- [ ] **Step 5: Commit the catalog rebuild**

```bash
cd /home/ah64/apps/mlt-pipeline-2b
git add pyagent-kdenlive-guide/phase1_knowledge_base/catalog.json pyagent-kdenlive-guide/phase1_knowledge_base/build_catalog.py
git commit -m "[setup] add keyframes field to catalog (Task 0.3, ~720 true + 5 simplekeyframe)"
```

### Task 0.4: New `_keyframes.py` helper module

**Files:**
- Create: `phase2_project_engine/_keyframes.py` (~150 lines)
- Create: `phase2_project_engine/tests/test_keyframes.py` (~150 lines)

**Interfaces:**
- Consumes: animation strings (e.g., `"0=1.0; 25~0.5; 50=0.0"`) and a catalog for `is_keyframable_param`.
- Produces: parsed `list[Keyframe]` and serialized `str`; `bool` for `is_keyframable_param`; coerced `str` for `coerce_param_value`.

- [ ] **Step 1: Write the failing test**

Create `phase2_project_engine/tests/test_keyframes.py`:

```python
"""Tests for phase2_project_engine._keyframes — animation string parse/serialize."""
from __future__ import annotations

import pytest

from phase2_project_engine._keyframes import (
    Keyframe,
    parse_animation_string,
    serialize_keyframes,
    is_keyframable_param,
    coerce_param_value,
    CURVE_LINEAR,
    CURVE_DISCRETE,
    CURVE_HOLD,
    CURVE_SMOOTH,
)


def test_parse_empty_string():
    assert parse_animation_string("") == []


def test_parse_simple_no_curve():
    kfs = parse_animation_string("0=1.0; 25=0.5; 50=0.0")
    assert kfs == [
        Keyframe(frame=0, value="1.0", type=""),
        Keyframe(frame=25, value="0.5", type=""),
        Keyframe(frame=50, value="0.0", type=""),
    ]


def test_parse_with_curve_chars():
    kfs = parse_animation_string("0=1.0; 25~0.5; 50|0.0; 75!1.0")
    assert [k.type for k in kfs] == ["", CURVE_SMOOTH, CURVE_DISCRETE, CURVE_HOLD]


def test_serialize_round_trip():
    kfs = [Keyframe(frame=0, value="1.0", type=""),
           Keyframe(frame=25, value="0.5", type=CURVE_SMOOTH)]
    s = serialize_keyframes(kfs)
    assert s == "0=1.0; 25~0.5"
    # Round-trip back
    assert parse_animation_string(s) == kfs


def test_serialize_empty():
    assert serialize_keyframes([]) == ""


def test_is_keyframable_param_true():
    cat = [
        {"kdenlive_id": "vignette", "parameters": [
            {"name": "opacity", "type": "animated", "keyframes": True},
        ]}
    ]
    assert is_keyframable_param(cat, "vignette", "opacity") is True


def test_is_keyframable_param_simplekeyframe():
    cat = [
        {"kdenlive_id": "rotation_keyframable", "parameters": [
            {"name": "transition.rotate_x", "type": "simplekeyframe",
             "keyframes": "simplekeyframe"},
        ]}
    ]
    assert is_keyframable_param(cat, "rotation_keyframable", "transition.rotate_x") == "simplekeyframe"


def test_is_keyframable_param_false():
    cat = [
        {"kdenlive_id": "sepia", "parameters": [
            {"name": "level", "type": "constant"},  # no keyframes field
        ]}
    ]
    assert is_keyframable_param(cat, "sepia", "level") is False


def test_is_keyframable_param_unknown_effect():
    cat = []
    assert is_keyframable_param(cat, "unknown", "x") is False


def test_coerce_param_value_constant_passthrough():
    # Constant type accepts any string value.
    assert coerce_param_value("constant", "0.5") == "0.5"


def test_coerce_param_value_double_validates():
    # Double type must be a valid float.
    assert coerce_param_value("double", "0.5") == "0.5"
    with pytest.raises(ValueError):
        coerce_param_value("double", "not a number")


def test_coerce_param_value_integer():
    assert coerce_param_value("integer", "42") == "42"
    with pytest.raises(ValueError):
        coerce_param_value("integer", "42.5")
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. pytest phase2_project_engine/tests/test_keyframes.py -v 2>&1 | tail -10
```

Expected: `ModuleNotFoundError: No module named 'phase2_project_engine._keyframes'`.

- [ ] **Step 3: Implement `_keyframes.py`**

Create `phase2_project_engine/_keyframes.py`:

```python
"""Parse/serialize Kdenlive animation strings + catalog helpers.

Imported by ops/*.py; not part of the public API.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


# Curve-type characters per Kdenlive 26.04's keyframemodel.cpp:22-53.
CURVE_LINEAR = "`"
CURVE_DISCRETE = "|"
CURVE_HOLD = "!"
CURVE_SMOOTH = "~"
# pyagent 2b exposes 15 curve types: 4 listed above + 8 most-common ease
# variants. The full 26-char alphabet (a..u, A..D) is documented but not
# yet exposed.
_ALLOWED_CURVE_CHARS: frozenset[str] = frozenset({
    CURVE_LINEAR, CURVE_DISCRETE, CURVE_HOLD, CURVE_SMOOTH,
    "a", "b", "c", "d", "A", "B", "C", "D",
})


@dataclass(frozen=True)
class Keyframe:
    frame: int
    value: str
    type: str  # empty, or one of the curve chars above


def parse_animation_string(s: str) -> list[Keyframe]:
    """Parse a Kdenlive animation string into a list of Keyframes.

    Format: "{frame}={value}[{type_char}]; {frame}={value}[{type_char}]; ..."
    Empty string returns [].
    """
    if not s:
        return []
    out: list[Keyframe] = []
    for raw_entry in s.split(";"):
        entry = raw_entry.strip()
        if not entry:
            continue
        if "=" not in entry:
            continue
        frame_str, value_with_type = entry.split("=", 1)
        # Optional curve char is the first char of value_with_type
        # if it's in the allowed set. Otherwise the type is "" (linear)
        # and the value is the full value_with_type.
        type_char = ""
        value = value_with_type
        if value_with_type and value_with_type[0] in _ALLOWED_CURVE_CHARS:
            # Check: is the rest of the value parseable as a value?
            # Heuristic: if removing the first char leaves a string
            # that doesn't start with a digit, -, +, or ., it's the value.
            # For now: assume first char is curve if it's in the set.
            type_char = value_with_type[0]
            value = value_with_type[1:]
        out.append(Keyframe(frame=int(frame_str.strip()),
                            value=value.strip(),
                            type=type_char))
    return out


def serialize_keyframes(kfs: Sequence[Keyframe]) -> str:
    """Serialize a list of Keyframes back into a Kdenlive animation string."""
    parts: list[str] = []
    for k in kfs:
        if k.type:
            parts.append(f"{k.frame}={k.type}{k.value}")
        else:
            parts.append(f"{k.frame}={k.value}")
    return "; ".join(parts)


def is_keyframable_param(
    catalog: Sequence[dict],
    effect_id: str,
    param_name: str,
) -> bool | str:
    """Return True if the param is animation-string keyframable, "simplekeyframe"
    if it's mlt_geometry, or False otherwise.

    Reads the `keyframes` field set by build_catalog.py in Task 0.3.
    """
    for entry in catalog:
        if entry.get("kdenlive_id") != effect_id:
            continue
        for p in entry.get("parameters", []):
            if p.get("name") == param_name:
                kf = p.get("keyframes", False)
                if kf is True:
                    return True
                if kf == "simplekeyframe":
                    return "simplekeyframe"
                return False
    return False


def coerce_param_value(param_type: str, value: str) -> str:
    """Coerce `value` to the format expected by `param_type`.

    Returns the string-form of the coerced value. Raises ValueError if the
    value can't be coerced.
    """
    if param_type in ("constant", "string", "url", "fixed", "list", "color",
                       "fixedcolor", "position", "bezier_spline", "geometry",
                       "roto-spline", "curve", "filterjob", "keywords",
                       "listdependency", "fontfamily", "urllist", "switch",
                       "multiswitch", "hidden", "rect", "animatedrect",
                       "animatedfakerect", "animatedfakepoint", "animated"):
        return str(value)
    if param_type in ("double", "float"):
        return str(float(value))
    if param_type in ("integer", "int"):
        return str(int(value))
    if param_type == "bool":
        return "1" if str(value).lower() in ("1", "true", "yes", "on") else "0"
    # Unknown type — pass through.
    return str(value)
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. pytest phase2_project_engine/tests/test_keyframes.py -v 2>&1 | tail -20
```

Expected: all 12 tests pass.

- [ ] **Step 5: Commit**

```bash
cd /home/ah64/apps/mlt-pipeline-2b
git add pyagent-kdenlive-guide/phase2_project_engine/_keyframes.py pyagent-kdenlive-guide/phase2_project_engine/tests/test_keyframes.py
git commit -m "[setup] add _keyframes.py helper module (parse/serialize, ~12 tests)"
```

### Task 0.5: Sanity check the catalog + helper integration

**Files:** none (read-only verification)

- [ ] **Step 1: Verify the new helper works with the rebuilt catalog**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
PYTHONPATH=. python3 << 'PYEOF'
import json
from phase2_project_engine._keyframes import is_keyframable_param

cat = json.load(open("phase1_knowledge_base/catalog.json"))
effs = cat["effects"]

# Pick 5 known keyframable effects
samples = [
    ("vignette", "opacity"),
    ("blur", "blur"),
    ("fade_from_black", "level"),
    ("chroma", "variance"),
    ("mask_start_shape", "filter.mix"),
]
for eid, pname in samples:
    result = is_keyframable_param(effs, eid, pname)
    print(f"  {eid}.{pname}: {result}")
    assert result is True, f"Expected True for {eid}.{pname}, got {result}"

# Pick 1 known simplekeyframe
result = is_keyframable_param(effs, "rotation_keyframable", "transition.rotate_x")
print(f"  rotation_keyframable.transition.rotate_x: {result}")
assert result == "simplekeyframe", f"Expected 'simplekeyframe', got {result}"

# Pick 1 known non-keyframable
result = is_keyframable_param(effs, "sepia", "sepia")  # sepia is a tag, not param
print(f"  sepia.sepia: {result}")
# Sepia may not have any keyframable params; just check it doesn't crash.
print("OK")
PYEOF
```

Expected: `OK`. If any sample returns False unexpectedly, debug the catalog rebuild.

- [ ] **Step 2: Run the full test suite to confirm no regression**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. timeout 180 pytest -q --no-header 2>&1 | tail -3
```

Expected: `260 passed, 2 skipped, 1 warning` (unchanged from 0.1 baseline; the 12 new test_keyframes.py tests are part of the 260).

- [ ] **Step 3: No commit for 0.5**

Task 0.5 is verification only. The catalog update landed in 0.3's commit, the helper landed in 0.4's commit. No new commit.

---


## Task 1: Commit 1 — effects (2 tools: `get_effect_param`, `set_effect_param`)

### Task 1.1: Write the failing test for `get_effect_param`

**Files:**
- Modify: `phase2_project_engine/tests/test_ops_effects.py` (append 3 new test functions)

- [ ] **Step 1: Append the test functions**

```python
def test_get_effect_param_static():
    """Reading a non-keyframable param returns its value and is_keyframable=False."""
    from phase2_project_engine.ops.effects import apply_effect, get_effect_param
    tree = make_minimal_tree()
    _import_source(tree, "fake.mp4")
    _insert_clip(tree, "fake.mp4", "fake_id")
    apply_effect(tree, "2", "brightness", params={"level": "0.5"},
                 catalog=BRIGHTNESS_CATALOG)
    result = get_effect_param(tree, "2", 0, "level", catalog=BRIGHTNESS_CATALOG)
    assert result == {
        "clip_id": "2",
        "effect_index": 0,
        "effect_id": "brightness",
        "param_name": "level",
        "value": "0.5",
        "is_keyframable": True,
        "format": "animated",
        "keyframes": None,
    }


def test_get_effect_param_clip_not_found():
    from phase2_project_engine.errors import NotFoundError
    from phase2_project_engine.ops.effects import get_effect_param
    tree = make_minimal_tree()
    with pytest.raises(NotFoundError, match="clip_not_found"):
        get_effect_param(tree, "nonexistent", 0, "x", catalog=BRIGHTNESS_CATALOG)


def test_get_effect_param_param_not_found():
    from phase2_project_engine.errors import NotFoundError
    from phase2_project_engine.ops.effects import apply_effect, get_effect_param
    tree = make_minimal_tree()
    _import_source(tree, "fake.mp4")
    _insert_clip(tree, "fake.mp4", "fake_id")
    apply_effect(tree, "2", "brightness", catalog=BRIGHTNESS_CATALOG)
    with pytest.raises(NotFoundError, match="param_not_found"):
        get_effect_param(tree, "2", 0, "nonexistent_param", catalog=BRIGHTNESS_CATALOG)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. pytest phase2_project_engine/tests/test_ops_effects.py::test_get_effect_param_static phase2_project_engine/tests/test_ops_effects.py::test_get_effect_param_clip_not_found phase2_project_engine/tests/test_ops_effects.py::test_get_effect_param_param_not_found -v 2>&1 | tail -10
```

Expected: 3 failures with `AttributeError: module 'phase2_project_engine.ops.effects' has no attribute 'get_effect_param'`.

### Task 1.2: Implement `get_effect_param`

**Files:**
- Modify: `phase2_project_engine/ops/effects.py` (append `get_effect_param`)

- [ ] **Step 1: Append the op function**

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

    For keyframable params, also returns the parsed list of keyframes and
    the on-disk format ("animated", "keyframe", "simplekeyframe", etc.).
    """
    from .clips_edit import _find_entry_for_clip
    from .._keyframes import is_keyframable_param, parse_animation_string

    if catalog is None:
        catalog = []
    track, entry, _ti = _find_entry_for_clip(tree, clip_id)
    filters = list(entry.findall("filter"))
    if effect_index < 0 or effect_index >= len(filters):
        raise NotFoundError(
            f"effect_index_out_of_range: effect_index={effect_index}, "
            f"effect_count={len(filters)}\n"
            f"fix: call get_timeline_summary to see valid indices"
        )
    filt = filters[effect_index]
    # Resolve effect_id from the kdenlive:id (colon) property
    effect_id = ""
    for prop in filt.findall("property"):
        if prop.get("name") == "kdenlive:id" and prop.text:
            effect_id = prop.text
            break
    # Find the requested param's value
    value = None
    for prop in filt.findall("property"):
        if prop.get("name") == param_name:
            value = prop.text or ""
            break
    if value is None:
        raise NotFoundError(
            f"param_not_found: effect '{effect_id}' (index {effect_index}) on "
            f"clip '{clip_id}' has no parameter named '{param_name}'\n"
            f"fix: call list_catalog to see valid parameter names for {effect_id}"
        )
    kf_status = is_keyframable_param(catalog, effect_id, param_name)
    is_kf = kf_status is True
    is_simplekf = kf_status == "simplekeyframe"
    if is_kf:
        kfs = parse_animation_string(value)
        keyframes = [{"frame": k.frame, "value": k.value, "type": k.type}
                     for k in kfs]
    elif is_simplekf:
        keyframes = []  # mlt_geometry not yet supported
    else:
        keyframes = None
    # Format string for the response
    fmt = ""
    if is_kf:
        # Look up the exact type= from catalog to report
        for entry_cat in catalog:
            if entry_cat.get("kdenlive_id") == effect_id:
                for p in entry_cat.get("parameters", []):
                    if p.get("name") == param_name:
                        fmt = p.get("type", "")
                        break
                break
    return {
        "clip_id": clip_id,
        "effect_index": effect_index,
        "effect_id": effect_id,
        "param_name": param_name,
        "value": value,
        "is_keyframable": is_kf,
        "format": fmt,
        "keyframes": keyframes,
    }
```

- [ ] **Step 2: Run the test to verify it passes**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. pytest phase2_project_engine/tests/test_ops_effects.py::test_get_effect_param_static phase2_project_engine/tests/test_ops_effects.py::test_get_effect_param_clip_not_found phase2_project_engine/tests/test_ops_effects.py::test_get_effect_param_param_not_found -v 2>&1 | tail -10
```

Expected: 3 passes.

### Task 1.3: Write the failing test for `set_effect_param`

**Files:**
- Modify: `phase2_project_engine/tests/test_ops_effects.py` (append 3 more test functions)

- [ ] **Step 1: Append the test functions**

```python
def test_set_effect_param_static():
    """Setting a non-keyframable param overwrites the value."""
    from phase2_project_engine.ops.effects import apply_effect, set_effect_param
    tree = make_minimal_tree()
    _import_source(tree, "fake.mp4")
    _insert_clip(tree, "fake.mp4", "fake_id")
    apply_effect(tree, "2", "brightness", params={"level": "0.5"},
                 catalog=BRIGHTNESS_CATALOG)
    result = set_effect_param(tree, "2", 0, "level", "0.8",
                              catalog=BRIGHTNESS_CATALOG)
    assert result["previous_value"] == "0.5"
    assert result["new_value"] == "0.8"
    assert result["is_keyframable"] is True


def test_set_effect_param_clobbers_keyframes_returns_warning_info():
    """If the param has keyframes, set_effect_param replaces the entire
    animation string. The response surfaces is_keyframable=True so the
    caller can detect and decide."""
    from phase2_project_engine.ops.effects import apply_effect, set_effect_param
    tree = make_minimal_tree()
    _import_source(tree, "fake.mp4")
    _insert_clip(tree, "fake.mp4", "fake_id")
    apply_effect(tree, "2", "brightness",
                 params={"level": "0=1.0; 25=0.5; 50=0.0"},
                 catalog=BRIGHTNESS_CATALOG)
    result = set_effect_param(tree, "2", 0, "level", "0.7",
                              catalog=BRIGHTNESS_CATALOG)
    assert result["previous_value"] == "0=1.0; 25=0.5; 50=0.0"
    assert result["new_value"] == "0.7"
    assert result["is_keyframable"] is True


def test_set_effect_param_value_type_mismatch():
    """If the value can't be coerced to the catalog's type, raise
    ValidationError with value_type_mismatch."""
    from phase2_project_engine.ops.effects import apply_effect, set_effect_param
    from phase2_project_engine.errors import ValidationError
    DOUBLE_CATALOG = [
        {"kdenlive_id": "dbl", "mlt_service": "dbl", "name": "Dbl",
         "parameters": [{"name": "x", "type": "double", "default": "1"}]}
    ]
    tree = make_minimal_tree()
    _import_source(tree, "fake.mp4")
    _insert_clip(tree, "fake.mp4", "fake_id")
    apply_effect(tree, "2", "dbl", catalog=DOUBLE_CATALOG)
    with pytest.raises(ValidationError, match="value_type_mismatch"):
        set_effect_param(tree, "2", 0, "x", "not a number", catalog=DOUBLE_CATALOG)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. pytest phase2_project_engine/tests/test_ops_effects.py::test_set_effect_param_static phase2_project_engine/tests/test_ops_effects.py::test_set_effect_param_clobbers_keyframes_returns_warning_info phase2_project_engine/tests/test_ops_effects.py::test_set_effect_param_value_type_mismatch -v 2>&1 | tail -5
```

Expected: 3 failures with `AttributeError: module ... has no attribute 'set_effect_param'`.

### Task 1.4: Implement `set_effect_param`

**Files:**
- Modify: `phase2_project_engine/ops/effects.py` (append `set_effect_param`)

- [ ] **Step 1: Append the op function**

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

    WARNING: if the param is keyframable, this REPLACES the entire
    animation string with the static value. The response includes
    `is_keyframable` and `previous_value` so the caller can detect
    the case and decide to use set_keyframe instead.
    """
    from .clips_edit import _find_entry_for_clip
    from .._keyframes import is_keyframable_param, coerce_param_value
    from ..validators import _find_catalog_entry

    if catalog is None:
        catalog = []
    track, entry, _ti = _find_entry_for_clip(tree, clip_id)
    filters = list(entry.findall("filter"))
    if effect_index < 0 or effect_index >= len(filters):
        raise NotFoundError(
            f"effect_index_out_of_range: effect_index={effect_index}, "
            f"effect_count={len(filters)}\n"
            f"fix: call get_timeline_summary to see valid indices"
        )
    filt = filters[effect_index]
    effect_id = ""
    for prop in filt.findall("property"):
        if prop.get("name") == "kdenlive:id" and prop.text:
            effect_id = prop.text
            break
    # Find current value
    current_value = None
    for prop in filt.findall("property"):
        if prop.get("name") == param_name:
            current_value = prop.text or ""
            break
    if current_value is None:
        raise NotFoundError(
            f"param_not_found: effect '{effect_id}' (index {effect_index}) on "
            f"clip '{clip_id}' has no parameter named '{param_name}'\n"
            f"fix: call list_catalog to see valid parameter names for {effect_id}"
        )
    # Coerce the new value to the catalog's type (if specified)
    cat_entry = _find_catalog_entry(catalog, effect_id)
    cat_param = None
    if cat_entry:
        for p in cat_entry.get("parameters", []):
            if p.get("name") == param_name:
                cat_param = p
                break
    if cat_param is not None:
        param_type = cat_param.get("type", "constant")
        try:
            coerced = coerce_param_value(param_type, value)
        except ValueError as e:
            raise validation_error(
                f"value_type_mismatch: cannot coerce {value!r} to "
                f"param type {param_type!r} for {effect_id}.{param_name}: {e}\n"
                f"fix: pass a value that parses as {param_type}",
            )
    else:
        coerced = str(value)
    # Find or create the property element and update its text
    found_prop = None
    for prop in filt.findall("property"):
        if prop.get("name") == param_name:
            found_prop = prop
            break
    if found_prop is not None:
        found_prop.text = coerced
    else:
        p = etree.SubElement(filt, "property")
        p.set("name", param_name)
        p.text = coerced
    kf_status = is_keyframable_param(catalog, effect_id, param_name)
    return {
        "clip_id": clip_id,
        "effect_index": effect_index,
        "param_name": param_name,
        "previous_value": current_value,
        "new_value": coerced,
        "is_keyframable": kf_status is True,
    }
```

- [ ] **Step 2: Run the test to verify it passes**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. pytest phase2_project_engine/tests/test_ops_effects.py::test_set_effect_param_static phase2_project_engine/tests/test_ops_effects.py::test_set_effect_param_clobbers_keyframes_returns_warning_info phase2_project_engine/tests/test_ops_effects.py::test_set_effect_param_value_type_mismatch -v 2>&1 | tail -5
```

Expected: 3 passes.

- [ ] **Step 3: Run the full effects test file to confirm no regression**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
PYTHONPATH=. pytest phase2_project_engine/tests/test_ops_effects.py -v 2>&1 | tail -15
```

Expected: all existing tests + 6 new tests pass (8 + 6 = 14 total in the file).

### Task 1.5: Update `__init__.py`, `runtime.py`, and add ToolDefs

**Files:**
- Modify: `phase2_project_engine/ops/__init__.py` (+2 exports)
- Modify: `phase3_pyagent_core/runtime.py` (+2 OP_TABLE entries, +2 MUTATING_OPS entries)
- Modify: `phase3_pyagent_core/tools/effects.py` (+2 ToolDefs)

- [ ] **Step 1: Update `ops/__init__.py`**

Add the two new exports. The current file ends with the export list; add to the list and to the imports:

```python
from .effects import apply_effect, get_effect_param, remove_effect, set_effect_param
# ...
    "apply_effect",
    "get_effect_param",
    "remove_effect",
    "set_effect_param",
```

- [ ] **Step 2: Update `runtime.py`**

Add 2 entries to `OP_TABLE` and 2 to `MUTATING_OPS`:

```python
# In OP_TABLE:
    "get_effect_param": "get_effect_param",
    "set_effect_param": "set_effect_param",
# In MUTATING_OPS (add to the existing frozenset):
        "set_effect_param", "get_effect_param",
```

- [ ] **Step 3: Update `tools/effects.py`**

Add 2 ToolDefs. Look at the existing `tools/effects.py` to see the pattern (it should have `APPLY_EFFECT` and `REMOVE_EFFECT`). Add 2 more:

```python
GET_EFFECT_PARAM = ToolDef(
    name="pyagent_get_effect_param",
    label="Get effect param",
    description=(
        "Read the current value of an effect parameter on a clip. "
        "For keyframable params, also returns the parsed keyframes list. "
        "WARNING: this does NOT validate that the clip's effect stack "
        "matches the catalog; the returned 'effect_id' is read from the "
        "kdenlive:id property in the file. To change a param's value, "
        "use set_effect_param."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "clip_id": {"type": "string", "description": "Target clip id"},
            "effect_index": {"type": "integer", "description": "0-based effect index in the clip's filter list"},
            "param_name": {"type": "string", "description": "Parameter name (e.g. 'opacity', 'level')"},
        },
        "required": ["clip_id", "effect_index", "param_name"],
        "additionalProperties": False,
    },
    handler="get_effect_param",
    domain="effects",
    mutating=False,
)

SET_EFFECT_PARAM = ToolDef(
    name="pyagent_set_effect_param",
    label="Set effect param",
    description=(
        "Set an effect parameter to a static value. "
        "WARNING: if the param is keyframable, this REPLACES the entire "
        "animation string. The response includes 'is_keyframable' and "
        "'previous_value' so the caller can detect the case and use "
        "set_keyframe instead. For non-keyframable params, the value is "
        "coerced to the catalog's type."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "clip_id": {"type": "string"},
            "effect_index": {"type": "integer"},
            "param_name": {"type": "string"},
            "value": {"type": "string", "description": "New value (as string; coerced to type)"},
        },
        "required": ["clip_id", "effect_index", "param_name", "value"],
        "additionalProperties": False,
    },
    handler="set_effect_param",
    domain="effects",
    mutating=True,
)
```

Add to the file's `all_tools()` list (or whatever the existing export pattern is — match the file's structure).

- [ ] **Step 4: Verify `list_tools()` returns 31**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
PYTHONPATH=. python3 -c "from phase3_pyagent_core.runtime import list_tools; print(len(list_tools()))"
```

Expected: `31` (29 existing + 2 new).

### Task 1.6: Add golden-file entries for the 2 new tools

**Files:**
- Modify: `phase3_pyagent_core/tests/fixtures/golden_io.json` (+2 entries)
- Modify: `phase3_pyagent_core/tests/test_golden_io.py` (+2 parametrized cases)

- [ ] **Step 1: Read the existing golden_io.json structure**

```bash
cd /home/ah64/apps/mlt-pipeline-2b
head -50 pyagent-kdenlive-guide/phase3_pyagent_core/tests/fixtures/golden_io.json
```

The structure is likely an array of objects with `op`, `args`, `expect_keys` (or similar). Match the existing pattern.

- [ ] **Step 2: Add 2 entries**

Append to the array (or whatever the structure is):

```json
{
  "op": "get_effect_param",
  "args": {"clip_id": "2", "effect_index": 0, "param_name": "level"},
  "setup": ("apply_effect", {"clip_id": "2", "effect_id": "brightness", "params": {"level": "0.5"}}),
  "expect_keys": ["clip_id", "effect_index", "effect_id", "param_name", "value", "is_keyframable", "format", "keyframes"]
},
{
  "op": "set_effect_param",
  "args": {"clip_id": "2", "effect_index": 0, "param_name": "level", "value": "0.8"},
  "setup": ("apply_effect", {"clip_id": "2", "effect_id": "brightness", "params": {"level": "0.5"}}),
  "expect_keys": ["clip_id", "effect_index", "param_name", "previous_value", "new_value", "is_keyframable"]
}
```

(Adjust the structure to match what the existing entries look like. The exact field names — `expect_keys` vs `expected_response_keys` vs `must_contain` — depend on the file's convention. Read 2-3 existing entries to confirm.)

- [ ] **Step 3: Run the golden-file tests**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. pytest phase3_pyagent_core/tests/test_golden_io.py -v 2>&1 | tail -10
```

Expected: 2 new tests pass + all existing tests pass (16 → 18 total in this file).

### Task 1.7: Run the full test suite + commit Task 1

- [ ] **Step 1: Run the full test suite**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. timeout 180 pytest -q --no-header 2>&1 | tail -3
```

Expected: 270-272 passed (260 + 12 _keyframes + 6 effects + 2 new golden = 280; minor variance OK), 2 skipped, 1 warning.

- [ ] **Step 2: Update `BUGS_FIXED.md` if any bugs were found**

If any bugs were found during Task 1, append a one-line entry per bug:

```bash
cd /home/ah64/apps/mlt-pipeline-2b
echo "| 2026-07-19 | 2b | <short description> | <file:line> |" >> pyagent-kdenlive-guide/BUGS_FIXED.md
```

(Only if bugs were found. Most tasks don't have any.)

- [ ] **Step 3: Commit Task 1**

```bash
cd /home/ah64/apps/mlt-pipeline-2b
git add pyagent-kdenlive-guide/phase2_project_engine/ops/effects.py \
        pyagent-kdenlive-guide/phase2_project_engine/ops/__init__.py \
        pyagent-kdenlive-guide/phase2_project_engine/tests/test_ops_effects.py \
        pyagent-kdenlive-guide/phase3_pyagent_core/runtime.py \
        pyagent-kdenlive-guide/phase3_pyagent_core/tools/effects.py \
        pyagent-kdenlive-guide/phase3_pyagent_core/tests/fixtures/golden_io.json \
        pyagent-kdenlive-guide/phase3_pyagent_core/tests/test_golden_io.py \
        pyagent-kdenlive-guide/BUGS_FIXED.md
git commit -m "[effects] add get_effect_param, set_effect_param"
```

---

## Task 2: Commit 2 — keyframes (3 tools: `list_keyframes`, `set_keyframe`, `remove_keyframe`)

### Task 2.1: Write the failing test for `list_keyframes`

**Files:**
- Create: `phase2_project_engine/tests/test_ops_keyframes.py` (~280 lines, will be filled incrementally)

- [ ] **Step 1: Create the test file with imports and 2 tests**

```python
"""Tests for phase2_project_engine.ops.keyframes — list/set/remove keyframe."""
from __future__ import annotations

import pytest

from phase2_project_engine.errors import NotFoundError, ValidationError
from phase2_project_engine.tests.ops_fixtures import (
    make_minimal_tree,
)


def _import_source(tree, source):
    from phase2_project_engine.ops.bin import import_media
    return import_media(tree, [str(source)])[0]


def _insert_clip(tree, source, src_id):
    from phase2_project_engine.ops.clips import insert_clip
    return insert_clip(
        tree, track_index=0, position_sec=0.0, source_id=src_id,
        source_in_sec=0.0, source_out_sec=5.0,
    )


BRIGHTNESS_CATALOG = [
    {
        "kdenlive_id": "brightness",
        "mlt_service": "brightness",
        "name": "Intensity",
        "parameters": [
            {"name": "level", "type": "animated", "default": "1",
             "keyframes": True},
        ],
    }
]


def test_list_keyframes_with_animation_string():
    from phase2_project_engine.ops.effects import apply_effect
    from phase2_project_engine.ops.keyframes import list_keyframes
    tree = make_minimal_tree()
    _import_source(tree, "fake.mp4")
    _insert_clip(tree, "fake.mp4", "fake_id")
    apply_effect(tree, "2", "brightness",
                 params={"level": "0=1.0; 25~0.5; 50=0.0"},
                 catalog=BRIGHTNESS_CATALOG)
    result = list_keyframes(tree, "2", 0, "level")
    assert result["format"] == "animated"
    assert result["keyframes"] == [
        {"frame": 0, "value": "1.0", "type": ""},
        {"frame": 25, "value": "0.5", "type": "~"},
        {"frame": 50, "value": "0.0", "type": ""},
    ]


def test_list_keyframes_empty():
    """Non-keyframable params return empty list and format=''."""
    from phase2_project_engine.ops.effects import apply_effect
    from phase2_project_engine.ops.keyframes import list_keyframes
    tree = make_minimal_tree()
    _import_source(tree, "fake.mp4")
    _insert_clip(tree, "fake.mp4", "fake_id")
    apply_effect(tree, "2", "brightness", params={"level": "0.5"},
                 catalog=BRIGHTNESS_CATALOG)
    result = list_keyframes(tree, "2", 0, "level")
    assert result["format"] == ""
    assert result["keyframes"] == []
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. pytest phase2_project_engine/tests/test_ops_keyframes.py -v 2>&1 | tail -5
```

Expected: 2 failures with `ModuleNotFoundError: No module named 'phase2_project_engine.ops.keyframes'`.

### Task 2.2: Implement `list_keyframes`

**Files:**
- Create: `phase2_project_engine/ops/keyframes.py` (~50 lines for `list_keyframes`)

- [ ] **Step 1: Create the file with `list_keyframes`**

```python
"""Keyframe operations: list_keyframes, set_keyframe, remove_keyframe."""
from __future__ import annotations

from lxml import etree

from ..errors import NotFoundError, ValidationError, validation_error
from ..io import ProjectTree
from .._keyframes import (
    parse_animation_string,
    serialize_keyframes,
    is_keyframable_param,
)


def list_keyframes(
    tree: ProjectTree,
    clip_id: str,
    effect_index: int,
    param_name: str,
) -> dict:
    """Return the keyframes on a keyframable param.

    For non-keyframable params, returns an empty keyframes list and
    format=''. For simplekeyframe params, returns an empty keyframes
    list and format='simplekeyframe' (mlt_geometry not yet supported).
    """
    from .clips_edit import _find_entry_for_clip

    track, entry, _ti = _find_entry_for_clip(tree, clip_id)
    filters = list(entry.findall("filter"))
    if effect_index < 0 or effect_index >= len(filters):
        raise NotFoundError(
            f"effect_index_out_of_range: effect_index={effect_index}, "
            f"effect_count={len(filters)}\n"
            f"fix: call get_timeline_summary to see valid indices"
        )
    filt = filters[effect_index]
    effect_id = ""
    for prop in filt.findall("property"):
        if prop.get("name") == "kdenlive:id" and prop.text:
            effect_id = prop.text
            break
    # Find the param's current value
    value = None
    for prop in filt.findall("property"):
        if prop.get("name") == param_name:
            value = prop.text or ""
            break
    if value is None:
        raise NotFoundError(
            f"param_not_found: effect '{effect_id}' (index {effect_index}) on "
            f"clip '{clip_id}' has no parameter named '{param_name}'\n"
            f"fix: call list_catalog to see valid parameter names for {effect_id}"
        )
    # Determine format from the value's structure (catalog not available here)
    if "=" in value and ";" in value:
        kfs = parse_animation_string(value)
        fmt = "animated"  # generic; catalog can refine in 2c
        keyframes = [{"frame": k.frame, "value": k.value, "type": k.type}
                     for k in kfs]
    else:
        keyframes = []
        fmt = ""
    return {
        "clip_id": clip_id,
        "effect_index": effect_index,
        "param_name": param_name,
        "format": fmt,
        "keyframes": keyframes,
    }
```

- [ ] **Step 2: Run the test to verify it passes**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. pytest phase2_project_engine/tests/test_ops_keyframes.py::test_list_keyframes_with_animation_string phase2_project_engine/tests/test_ops_keyframes.py::test_list_keyframes_empty -v 2>&1 | tail -5
```

Expected: 2 passes.

### Task 2.3: Write the failing test for `set_keyframe`

**Files:**
- Modify: `phase2_project_engine/tests/test_ops_keyframes.py` (append 3 tests)

- [ ] **Step 1: Append 3 tests**

```python
def test_set_keyframe_adds_new():
    from phase2_project_engine.ops.effects import apply_effect
    from phase2_project_engine.ops.keyframes import set_keyframe, list_keyframes
    tree = make_minimal_tree()
    _import_source(tree, "fake.mp4")
    _insert_clip(tree, "fake.mp4", "fake_id")
    apply_effect(tree, "2", "brightness",
                 params={"level": "0=1.0; 50=0.0"},
                 catalog=BRIGHTNESS_CATALOG)
    result = set_keyframe(tree, "2", 0, "level", 25, "0.5", "smooth")
    assert result["action"] == "added"
    kfs = list_keyframes(tree, "2", 0, "level")
    assert len(kfs["keyframes"]) == 3
    assert kfs["keyframes"][1] == {"frame": 25, "value": "0.5", "type": "~"}


def test_set_keyframe_updates_existing():
    from phase2_project_engine.ops.effects import apply_effect
    from phase2_project_engine.ops.keyframes import set_keyframe
    tree = make_minimal_tree()
    _import_source(tree, "fake.mp4")
    _insert_clip(tree, "fake.mp4", "fake_id")
    apply_effect(tree, "2", "brightness",
                 params={"level": "0=1.0; 25=0.5; 50=0.0"},
                 catalog=BRIGHTNESS_CATALOG)
    result = set_keyframe(tree, "2", 0, "level", 25, "0.7", "linear")
    assert result["action"] == "updated"
    assert result["value"] == "0.7"


def test_set_keyframe_invalid_type():
    from phase2_project_engine.errors import ValidationError
    from phase2_project_engine.ops.keyframes import set_keyframe
    tree = make_minimal_tree()
    with pytest.raises(ValidationError, match="invalid_type"):
        set_keyframe(tree, "2", 0, "level", 0, "1.0", "bogus_curve_type")
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. pytest phase2_project_engine/tests/test_ops_keyframes.py::test_set_keyframe_adds_new phase2_project_engine/tests/test_ops_keyframes.py::test_set_keyframe_updates_existing phase2_project_engine/tests/test_ops_keyframes.py::test_set_keyframe_invalid_type -v 2>&1 | tail -5
```

Expected: 3 failures with `AttributeError: module ... has no attribute 'set_keyframe'`.

### Task 2.4: Implement `set_keyframe`

**Files:**
- Modify: `phase2_project_engine/ops/keyframes.py` (append `set_keyframe`)

- [ ] **Step 1: Append `set_keyframe`**

```python
_TYPE_NAME_TO_CHAR = {
    "linear": "`",
    "discrete": "|",
    "hold": "!",
    "smooth": "~",
    "ease_in_a": "a", "ease_in_b": "b", "ease_in_c": "c", "ease_in_d": "d",
    "ease_out_a": "A", "ease_out_b": "B", "ease_out_c": "C", "ease_out_d": "D",
}


def _get_project_fps(tree: ProjectTree) -> float:
    """Return the project FPS (or 25.0 fallback).

    Reads from the tractor's frame_rate_num/frame_rate_den attributes.
    The actual attribute names depend on how ProjectTree exposes the
    profile; check phase2_project_engine/io.py.
    """
    try:
        tractor = tree.tractor
        # The tractor IS a multitrack in MLT; the profile is on the
        # root <mlt> element. Walk up to find it.
        root = tractor.getparent()
        while root is not None and root.tag != "mlt":
            root = root.getparent()
        if root is None:
            return 25.0
        profile = root.find("profile")
        if profile is None:
            return 25.0
        num = float(profile.get("frame_rate_num", "25"))
        den = float(profile.get("frame_rate_den", "1"))
        return num / den if den else 25.0
    except Exception:
        return 25.0


def set_keyframe(
    tree: ProjectTree,
    clip_id: str,
    effect_index: int,
    param_name: str,
    frame: int,
    value: str,
    type: str = "linear",
) -> dict:
    """Add or update a keyframe at `frame`.

    `type` is one of: linear, discrete, hold, smooth, or the 8 ease
    variants (a, b, c, d, A, B, C, D). Default is linear.
    """
    from .clips_edit import _find_entry_for_clip

    if type not in _TYPE_NAME_TO_CHAR:
        raise validation_error(
            f"invalid_type: type={type!r} is not in the allowed set\n"
            f"fix: pass one of {sorted(_TYPE_NAME_TO_CHAR.keys())}",
        )
    type_char = _TYPE_NAME_TO_CHAR[type]
    track, entry, _ti = _find_entry_for_clip(tree, clip_id)
    filters = list(entry.findall("filter"))
    if effect_index < 0 or effect_index >= len(filters):
        raise NotFoundError(
            f"effect_index_out_of_range: effect_index={effect_index}, "
            f"effect_count={len(filters)}\n"
            f"fix: call get_timeline_summary to see valid indices"
        )
    filt = filters[effect_index]
    # Find current value
    value_prop = None
    for prop in filt.findall("property"):
        if prop.get("name") == param_name:
            value_prop = prop
            break
    if value_prop is None:
        raise NotFoundError(
            f"param_not_found: effect at index {effect_index} on clip "
            f"{clip_id!r} has no parameter named {param_name!r}\n"
            f"fix: call list_catalog to see valid parameter names"
        )
    current_str = value_prop.text or ""
    kfs = parse_animation_string(current_str)
    # Compute the clip's effective duration in frames
    from ..io import _tc_to_sec
    out_sec = _tc_to_sec(entry.get("out", "00:00:00.000"))
    in_sec = _tc_to_sec(entry.get("in", "00:00:00.000"))
    fps = _get_project_fps(tree)
    clip_duration_frames = int(round((out_sec - in_sec) * fps))
    if frame < 0 or frame >= clip_duration_frames:
        raise validation_error(
            f"frame_out_of_range: frame={frame}, clip_duration_frames={clip_duration_frames}\n"
            f"fix: pass a frame in [0, {clip_duration_frames - 1}]",
        )
    # Find existing keyframe at this frame, or insert
    action = "added"
    for k in kfs:
        if k.frame == frame:
            k.value = value
            k.type = type_char
            action = "updated"
            break
    else:
        from .._keyframes import Keyframe
        kfs.append(Keyframe(frame=frame, value=value, type=type_char))
        kfs.sort(key=lambda k: k.frame)
    value_prop.text = serialize_keyframes(kfs)
    return {
        "clip_id": clip_id,
        "effect_index": effect_index,
        "param_name": param_name,
        "frame": frame,
        "value": value,
        "type": type,
        "action": action,
    }
```

- [ ] **Step 2: Run the test to verify it passes**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. pytest phase2_project_engine/tests/test_ops_keyframes.py::test_set_keyframe_adds_new phase2_project_engine/tests/test_ops_keyframes.py::test_set_keyframe_updates_existing phase2_project_engine/tests/test_ops_keyframes.py::test_set_keyframe_invalid_type -v 2>&1 | tail -10
```

Expected: 3 passes. (If `_get_project_fps` returns the wrong value, debug the FPS reading.)

### Task 2.5: Write the failing test for `remove_keyframe`

**Files:**
- Modify: `phase2_project_engine/tests/test_ops_keyframes.py` (append 2 tests)

- [ ] **Step 1: Append 2 tests**

```python
def test_remove_keyframe_existing():
    from phase2_project_engine.ops.effects import apply_effect
    from phase2_project_engine.ops.keyframes import remove_keyframe, list_keyframes
    tree = make_minimal_tree()
    _import_source(tree, "fake.mp4")
    _insert_clip(tree, "fake.mp4", "fake_id")
    apply_effect(tree, "2", "brightness",
                 params={"level": "0=1.0; 25=0.5; 50=0.0"},
                 catalog=BRIGHTNESS_CATALOG)
    result = remove_keyframe(tree, "2", 0, "level", 25)
    assert result["removed"] is True
    kfs = list_keyframes(tree, "2", 0, "level")
    assert len(kfs["keyframes"]) == 2


def test_remove_keyframe_nonexistent_is_noop():
    from phase2_project_engine.ops.effects import apply_effect
    from phase2_project_engine.ops.keyframes import remove_keyframe
    tree = make_minimal_tree()
    _import_source(tree, "fake.mp4")
    _insert_clip(tree, "fake.mp4", "fake_id")
    apply_effect(tree, "2", "brightness", params={"level": "0.5"},
                 catalog=BRIGHTNESS_CATALOG)
    result = remove_keyframe(tree, "2", 0, "level", 999)
    assert result["removed"] is False
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. pytest phase2_project_engine/tests/test_ops_keyframes.py::test_remove_keyframe_existing phase2_project_engine/tests/test_ops_keyframes.py::test_remove_keyframe_nonexistent_is_noop -v 2>&1 | tail -5
```

Expected: 2 failures with `AttributeError: module ... has no attribute 'remove_keyframe'`.

### Task 2.6: Implement `remove_keyframe`

**Files:**
- Modify: `phase2_project_engine/ops/keyframes.py` (append `remove_keyframe`)

- [ ] **Step 1: Append `remove_keyframe`**

```python
def remove_keyframe(
    tree: ProjectTree,
    clip_id: str,
    effect_index: int,
    param_name: str,
    frame: int,
) -> dict:
    """Remove the keyframe at `frame`. No error if no keyframe exists there."""
    from .clips_edit import _find_entry_for_clip

    track, entry, _ti = _find_entry_for_clip(tree, clip_id)
    filters = list(entry.findall("filter"))
    if effect_index < 0 or effect_index >= len(filters):
        raise NotFoundError(
            f"effect_index_out_of_range: effect_index={effect_index}, "
            f"effect_count={len(filters)}\n"
            f"fix: call get_timeline_summary to see valid indices"
        )
    filt = filters[effect_index]
    value_prop = None
    for prop in filt.findall("property"):
        if prop.get("name") == param_name:
            value_prop = prop
            break
    if value_prop is None:
        raise NotFoundError(
            f"param_not_found: effect at index {effect_index} on clip "
            f"{clip_id!r} has no parameter named {param_name!r}\n"
            f"fix: call list_catalog to see valid parameter names"
        )
    current_str = value_prop.text or ""
    kfs = parse_animation_string(current_str)
    removed = False
    new_kfs = [k for k in kfs if k.frame != frame]
    if len(new_kfs) != len(kfs):
        removed = True
    value_prop.text = serialize_keyframes(new_kfs)
    return {
        "clip_id": clip_id,
        "effect_index": effect_index,
        "param_name": param_name,
        "frame": frame,
        "removed": removed,
    }
```

- [ ] **Step 2: Run the test to verify it passes**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. pytest phase2_project_engine/tests/test_ops_keyframes.py -v 2>&1 | tail -10
```

Expected: 7 tests pass (2 list + 3 set + 2 remove).

### Task 2.7: Update `__init__.py`, `runtime.py`, and add ToolDefs

**Files:**
- Modify: `phase2_project_engine/ops/__init__.py` (+3 exports)
- Modify: `phase3_pyagent_core/runtime.py` (+3 OP_TABLE entries, +2 MUTATING_OPS entries)
- Create: `phase3_pyagent_core/tools/keyframes.py` (3 ToolDefs)

- [ ] **Step 1: Update `ops/__init__.py`**

```python
from .keyframes import list_keyframes, remove_keyframe, set_keyframe
# ...
    "list_keyframes",
    "set_keyframe",
    "remove_keyframe",
```

- [ ] **Step 2: Update `runtime.py`**

```python
# In OP_TABLE:
    "list_keyframes": "list_keyframes",
    "set_keyframe": "set_keyframe",
    "remove_keyframe": "remove_keyframe",
# In MUTATING_OPS (add; list_keyframes is read-only):
        "set_keyframe", "remove_keyframe",
```

- [ ] **Step 3: Create `tools/keyframes.py`**

```python
"""ToolDef definitions for the keyframe operations."""
from __future__ import annotations

from . import ToolDef  # adapt to the existing ToolDef import path


LIST_KEYFRAMES = ToolDef(
    name="pyagent_list_keyframes",
    label="List keyframes",
    description=(
        "Return the keyframes on a keyframable effect parameter. "
        "Returns an empty list if the param is not keyframable or has "
        "no keyframes. For simplekeyframe params (5 in the 26.04 catalog), "
        "returns format='simplekeyframe' and an empty keyframes list — "
        "mlt_geometry support is deferred to a later sub-project."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "clip_id": {"type": "string"},
            "effect_index": {"type": "integer"},
            "param_name": {"type": "string"},
        },
        "required": ["clip_id", "effect_index", "param_name"],
        "additionalProperties": False,
    },
    handler="list_keyframes",
    domain="keyframes",
    mutating=False,
)

SET_KEYFRAME = ToolDef(
    name="pyagent_set_keyframe",
    label="Set keyframe",
    description=(
        "Add a new keyframe at the given frame, or update the value/type "
        "of an existing one. `type` is one of: linear, discrete, hold, "
        "smooth, or 8 ease variants (a, b, c, d, A, B, C, D). Default "
        "is linear. `frame` is 0-based, relative to the clip's in-point."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "clip_id": {"type": "string"},
            "effect_index": {"type": "integer"},
            "param_name": {"type": "string"},
            "frame": {"type": "integer", "description": "0-based frame relative to clip's in-point"},
            "value": {"type": "string", "description": "Keyframe value (as string)"},
            "type": {"type": "string", "default": "linear",
                     "description": "One of: linear, discrete, hold, smooth, a, b, c, d, A, B, C, D"},
        },
        "required": ["clip_id", "effect_index", "param_name", "frame", "value"],
        "additionalProperties": False,
    },
    handler="set_keyframe",
    domain="keyframes",
    mutating=True,
)

REMOVE_KEYFRAME = ToolDef(
    name="pyagent_remove_keyframe",
    label="Remove keyframe",
    description=(
        "Remove the keyframe at the given frame. No error if no keyframe "
        "exists there; the response includes removed: false. For "
        "simplekeyframe params, raises simplekeyframe_format_unsupported."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "clip_id": {"type": "string"},
            "effect_index": {"type": "integer"},
            "param_name": {"type": "string"},
            "frame": {"type": "integer"},
        },
        "required": ["clip_id", "effect_index", "param_name", "frame"],
        "additionalProperties": False,
    },
    handler="remove_keyframe",
    domain="keyframes",
    mutating=True,
)
```

Add to the file's `all_tools()` list (or whatever the existing pattern is — match it).

- [ ] **Step 4: Verify `list_tools()` returns 34**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
PYTHONPATH=. python3 -c "from phase3_pyagent_core.runtime import list_tools; print(len(list_tools()))"
```

Expected: `34` (31 + 3 new).

### Task 2.8: Add golden-file entries for the 3 new tools

**Files:**
- Modify: `phase3_pyagent_core/tests/fixtures/golden_io.json` (+3 entries)
- Modify: `phase3_pyagent_core/tests/test_golden_io.py` (+3 parametrized cases)

- [ ] **Step 1: Add 3 entries to the golden file**

```json
{
  "op": "list_keyframes",
  "args": {"clip_id": "2", "effect_index": 0, "param_name": "level"},
  "setup": ("apply_effect", {"clip_id": "2", "effect_id": "brightness", "params": {"level": "0=1.0; 25~0.5; 50=0.0"}}),
  "expect_keys": ["clip_id", "effect_index", "param_name", "format", "keyframes"]
},
{
  "op": "set_keyframe",
  "args": {"clip_id": "2", "effect_index": 0, "param_name": "level", "frame": 30, "value": "0.4", "type": "smooth"},
  "setup": ("apply_effect", {"clip_id": "2", "effect_id": "brightness", "params": {"level": "0=1.0; 50=0.0"}}),
  "expect_keys": ["clip_id", "effect_index", "param_name", "frame", "value", "type", "action"]
},
{
  "op": "remove_keyframe",
  "args": {"clip_id": "2", "effect_index": 0, "param_name": "level", "frame": 25},
  "setup": ("apply_effect", {"clip_id": "2", "effect_id": "brightness", "params": {"level": "0=1.0; 25=0.5; 50=0.0"}}),
  "expect_keys": ["clip_id", "effect_index", "param_name", "frame", "removed"]
}
```

- [ ] **Step 2: Run the golden-file tests**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. pytest phase3_pyagent_core/tests/test_golden_io.py -v 2>&1 | tail -10
```

Expected: 3 new tests pass + all existing tests pass (18 → 21 total in this file).

### Task 2.9: Run the full test suite + commit Task 2

- [ ] **Step 1: Run the full test suite**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. timeout 180 pytest -q --no-header 2>&1 | tail -3
```

Expected: ~278-280 passed, 2 skipped, 1 warning.

- [ ] **Step 2: Update `BUGS_FIXED.md` if any bugs were found**

(Only if bugs were found during Task 2 implementation.)

- [ ] **Step 3: Commit Task 2**

```bash
cd /home/ah64/apps/mlt-pipeline-2b
git add pyagent-kdenlive-guide/phase2_project_engine/ops/keyframes.py \
        pyagent-kdenlive-guide/phase2_project_engine/ops/__init__.py \
        pyagent-kdenlive-guide/phase2_project_engine/tests/test_ops_keyframes.py \
        pyagent-kdenlive-guide/phase3_pyagent_core/runtime.py \
        pyagent-kdenlive-guide/phase3_pyagent_core/tools/keyframes.py \
        pyagent-kdenlive-guide/phase3_pyagent_core/tests/fixtures/golden_io.json \
        pyagent-kdenlive-guide/phase3_pyagent_core/tests/test_golden_io.py \
        pyagent-kdenlive-guide/BUGS_FIXED.md
git commit -m "[keyframes] add list_keyframes, set_keyframe, remove_keyframe"
```

---

## Task 3: Commit 3 — transitions (1 tool: `set_transition_property`)

### Task 3.1: Write the failing test for `set_transition_property`

**Files:**
- Modify: `phase2_project_engine/tests/test_ops_transitions.py` (append 2 tests)

- [ ] **Step 1: Append 2 tests**

```python
def test_set_transition_property_timing():
    """Change a transition's `in` timecode."""
    from phase2_project_engine.ops.clips import insert_clip
    from phase2_project_engine.ops.bin import import_media
    from phase2_project_engine.ops.transitions import (
        add_transition, set_transition_property,
    )
    tree = make_minimal_tree()
    import os
    fake1 = os.path.abspath("fake1.mp4")
    fake2 = os.path.abspath("fake2.mp4")
    src1 = import_media(tree, [fake1])[0]
    src2 = import_media(tree, [fake2])[0]
    insert_clip(tree, track_index=0, position_sec=0.0,
                source_id=src1, source_in_sec=0.0, source_out_sec=2.0)
    insert_clip(tree, track_index=0, position_sec=2.0,
                source_id=src2, source_in_sec=0.0, source_out_sec=2.0)
    add_transition(tree, clip_a_id="2", clip_b_id="3", kind="dissolve",
                   duration_sec=1.0)
    transitions = tree.tractor.findall(".//transition")
    assert len(transitions) == 1, f"Expected 1 transition, got {len(transitions)}"
    tr = transitions[0]
    tr_id = tr.get("id") or ""
    result = set_transition_property(tree, tr_id, "in", "00:00:00.250")
    assert result["prop_name"] == "in"
    assert tr.get("in") == "00:00:00.250"


def test_set_transition_property_reserved_name_rejected():
    """Reserved names like 'mlt_service' and 'id' are rejected."""
    from phase2_project_engine.errors import ValidationError
    from phase2_project_engine.ops.clips import insert_clip
    from phase2_project_engine.ops.bin import import_media
    from phase2_project_engine.ops.transitions import (
        add_transition, set_transition_property,
    )
    tree = make_minimal_tree()
    import os
    fake1 = os.path.abspath("fake1.mp4")
    fake2 = os.path.abspath("fake2.mp4")
    src1 = import_media(tree, [fake1])[0]
    src2 = import_media(tree, [fake2])[0]
    insert_clip(tree, track_index=0, position_sec=0.0,
                source_id=src1, source_in_sec=0.0, source_out_sec=2.0)
    insert_clip(tree, track_index=0, position_sec=2.0,
                source_id=src2, source_in_sec=0.0, source_out_sec=2.0)
    add_transition(tree, clip_a_id="2", clip_b_id="3", kind="dissolve",
                   duration_sec=1.0)
    tr_id = tree.tractor.findall(".//transition")[0].get("id") or ""
    with pytest.raises(ValidationError, match="prop_not_allowed"):
        set_transition_property(tree, tr_id, "mlt_service", "dissolve")
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. pytest phase2_project_engine/tests/test_ops_transitions.py::test_set_transition_property_timing phase2_project_engine/tests/test_ops_transitions.py::test_set_transition_property_reserved_name_rejected -v 2>&1 | tail -5
```

Expected: 2 failures with `AttributeError: module ... has no attribute 'set_transition_property'`.

### Task 3.2: Implement `set_transition_property`

**Files:**
- Modify: `phase2_project_engine/ops/transitions.py` (append `set_transition_property`)

- [ ] **Step 1: Append the op function**

```python
_RESERVED_PROP_NAMES = frozenset({"mlt_service", "id", "_childid", "kdenlive:id"})


def set_transition_property(
    tree: ProjectTree,
    transition_id: str,
    prop_name: str,
    value: str,
) -> dict:
    """Set any one property on a transition service.

    Reserved names (mlt_service, id, _childid, kdenlive:id) are rejected.
    All other prop names are accepted; integer coercion is applied
    for a_track/b_track.
    """
    if prop_name in _RESERVED_PROP_NAMES or prop_name.startswith("_"):
        raise validation_error(
            f"prop_not_allowed: prop_name={prop_name!r} is reserved\n"
            f"fix: pass a transition-specific property (e.g. 'in', 'out', "
            f"'a_track', 'b_track', 'geometry')",
        )
    # Find the transition by id
    transition = None
    for tr in tree.tractor.findall(".//transition"):
        if tr.get("id") == transition_id:
            transition = tr
            break
    if transition is None:
        raise NotFoundError(
            f"transition_not_found: no transition with id={transition_id!r}\n"
            f"fix: call get_timeline_summary to see valid transition ids"
        )
    # Find the existing prop (or none, if it's a new transition-specific param)
    previous_value = None
    target_prop = None
    for prop in transition.findall("property"):
        if prop.get("name") == prop_name:
            target_prop = prop
            previous_value = prop.text
            break
    # Coerce the value: timing/track props as timecode/integer
    if prop_name in ("a_track", "b_track"):
        try:
            coerced = str(int(value))
        except (TypeError, ValueError):
            raise validation_error(
                f"value_type_mismatch: a_track/b_track requires an integer, "
                f"got {value!r}\n"
                f"fix: pass an integer track index as a string",
            )
    elif prop_name in ("in", "out"):
        from ..io import _tc_to_sec
        try:
            _tc_to_sec(value)
            coerced = value
        except (TypeError, ValueError):
            raise validation_error(
                f"value_type_mismatch: {prop_name} requires a timecode, "
                f"got {value!r}\n"
                f"fix: pass a timecode like '00:00:00.500'",
            )
    else:
        coerced = str(value)
    if target_prop is not None:
        target_prop.text = coerced
    else:
        p = etree.SubElement(transition, "property")
        p.set("name", prop_name)
        p.text = coerced
    return {
        "transition_id": transition_id,
        "prop_name": prop_name,
        "previous_value": previous_value,
        "new_value": coerced,
    }
```

- [ ] **Step 2: Run the test to verify it passes**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. pytest phase2_project_engine/tests/test_ops_transitions.py::test_set_transition_property_timing phase2_project_engine/tests/test_ops_transitions.py::test_set_transition_property_reserved_name_rejected -v 2>&1 | tail -5
```

Expected: 2 passes.

### Task 3.3: Update `__init__.py`, `runtime.py`, and add ToolDef

**Files:**
- Modify: `phase2_project_engine/ops/__init__.py` (+1 export)
- Modify: `phase3_pyagent_core/runtime.py` (+1 OP_TABLE entry, +1 MUTATING_OPS entry)
- Modify: `phase3_pyagent_core/tools/transitions.py` (+1 ToolDef)

- [ ] **Step 1: Update `ops/__init__.py`**

```python
from .transitions import add_transition, remove_transition, set_transition_property
# ...
    "set_transition_property",
```

- [ ] **Step 2: Update `runtime.py`**

```python
# In OP_TABLE:
    "set_transition_property": "set_transition_property",
# In MUTATING_OPS:
        "set_transition_property",
```

- [ ] **Step 3: Update `tools/transitions.py`**

```python
SET_TRANSITION_PROPERTY = ToolDef(
    name="pyagent_set_transition_property",
    label="Set transition property",
    description=(
        "Set any one property on a transition service. Reserved names "
        "(mlt_service, id, _childid, kdenlive:id, anything starting with _) "
        "are rejected. Use for editing timing (in, out, a_track, b_track) "
        "or transition-specific params (e.g. 'geometry' for wipes)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "transition_id": {"type": "string"},
            "prop_name": {"type": "string"},
            "value": {"type": "string"},
        },
        "required": ["transition_id", "prop_name", "value"],
        "additionalProperties": False,
    },
    handler="set_transition_property",
    domain="transitions",
    mutating=True,
)
```

Add to the file's `all_tools()` list (or whatever the existing pattern is).

- [ ] **Step 4: Verify `list_tools()` returns 35**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
PYTHONPATH=. python3 -c "from phase3_pyagent_core.runtime import list_tools; print(len(list_tools()))"
```

Expected: `35` (34 + 1 new).

### Task 3.4: Add golden-file entry for `set_transition_property`

**Files:**
- Modify: `phase3_pyagent_core/tests/fixtures/golden_io.json` (+1 entry)
- Modify: `phase3_pyagent_core/tests/test_golden_io.py` (+1 parametrized case)

- [ ] **Step 1: Add 1 entry**

```json
{
  "op": "set_transition_property",
  "args": {"transition_id": "PLACEHOLDER", "prop_name": "in", "value": "00:00:00.250"},
  "setup": _setup_add_transition_then_set_prop,
  "expect_keys": ["transition_id", "prop_name", "previous_value", "new_value"]
}
```

**Note:** the existing `add_transition` returns the kdenlive:id. The golden case needs to read that id. Use a callable setup. Look at the 2a spec's `_setup_remove_transition` for the pattern; the 2b version is similar:

```python
def _setup_add_transition_then_set_prop(proj_path, catalog_path, args):
    """Add a transition, capture its id, then run the golden op."""
    from phase3_pyagent_core.cli import run_op
    code, resp = run_op("add_transition", {
        "clip_a_id": "2", "clip_b_id": "3",
        "kind": "dissolve", "duration_sec": 1.0,
    }, proj_path, catalog_path)
    # Find the transition id in the response. Check add_transition's
    # response shape (likely "transition_id" or "kdenlive_id" or "id").
    transition_id = resp.get("transition_id") or resp.get("id") or resp.get("kdenlive_id")
    args["transition_id"] = transition_id
    return args
```

Register the setup in `_SETUP` (add to the existing `_SETUP` dict in `test_golden_io.py`).

- [ ] **Step 2: Run the golden-file test**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. pytest phase3_pyagent_core/tests/test_golden_io.py -v 2>&1 | tail -10
```

Expected: 1 new test passes.

### Task 3.5: Run the full test suite + commit Task 3

- [ ] **Step 1: Run the full test suite**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. timeout 180 pytest -q --no-header 2>&1 | tail -3
```

Expected: ~279-281 passed, 2 skipped, 1 warning.

- [ ] **Step 2: Update `BUGS_FIXED.md` if any bugs were found**

(Only if bugs were found.)

- [ ] **Step 3: Commit Task 3**

```bash
cd /home/ah64/apps/mlt-pipeline-2b
git add pyagent-kdenlive-guide/phase2_project_engine/ops/transitions.py \
        pyagent-kdenlive-guide/phase2_project_engine/ops/__init__.py \
        pyagent-kdenlive-guide/phase2_project_engine/tests/test_ops_transitions.py \
        pyagent-kdenlive-guide/phase3_pyagent_core/runtime.py \
        pyagent-kdenlive-guide/phase3_pyagent_core/tools/transitions.py \
        pyagent-kdenlive-guide/phase3_pyagent_core/tests/fixtures/golden_io.json \
        pyagent-kdenlive-guide/phase3_pyagent_core/tests/test_golden_io.py \
        pyagent-kdenlive-guide/BUGS_FIXED.md
git commit -m "[transitions] add set_transition_property"
```

---

## Task 4: Commit 4 — track-effects + variable-speed (3 tools)

### Task 4.1: Write the failing test for `add_effect_to_track`

**Files:**
- Create: `phase2_project_engine/tests/test_ops_track_effects.py` (~180 lines, filled incrementally)

- [ ] **Step 1: Create the test file with imports and 2 tests**

```python
"""Tests for phase2_project_engine.ops.track_effects — add_effect_to_track, list_track_effects."""
from __future__ import annotations

import pytest

from phase2_project_engine.errors import NotFoundError, ValidationError
from phase2_project_engine.tests.ops_fixtures import make_minimal_tree


VOLUME_CATALOG = [
    {
        "kdenlive_id": "volume",
        "mlt_service": "volume",
        "name": "Volume",
        "kdenlive_type": "audio",
        "parameters": [{"name": "level", "type": "double", "default": "1"}],
    }
]


def test_add_effect_to_track_audio_track():
    """Add a volume effect to an audio track."""
    from phase2_project_engine.ops.track_effects import add_effect_to_track
    tree = make_minimal_tree()
    audio_track_idx = _find_audio_track_index(tree)
    result = add_effect_to_track(tree, audio_track_idx, "volume",
                                  params={"level": "0.5"},
                                  catalog=VOLUME_CATALOG)
    assert result["effect_id"] == "volume"
    assert result["effect_index"] == 0


def test_add_effect_to_track_video_effect_on_audio_track_rejected():
    """A video effect cannot be added to an audio track."""
    from phase2_project_engine.ops.track_effects import add_effect_to_track
    VIDEO_CATALOG = [
        {
            "kdenlive_id": "blur",
            "mlt_service": "blur",
            "name": "Blur",
            "kdenlive_type": "video",
            "parameters": [],
        }
    ]
    tree = make_minimal_tree()
    audio_track_idx = _find_audio_track_index(tree)
    with pytest.raises(ValidationError, match="effect_id_must_be_video"):
        add_effect_to_track(tree, audio_track_idx, "blur", catalog=VIDEO_CATALOG)


def _find_audio_track_index(tree):
    """Return the index of the first audio track in the tree."""
    from phase2_project_engine.tracks import get_tracks, is_audio_track
    tracks = get_tracks(tree)
    for i, tr in enumerate(tracks):
        if is_audio_track(tree, tr):
            return i
    raise RuntimeError("No audio track in fixture")
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. pytest phase2_project_engine/tests/test_ops_track_effects.py -v 2>&1 | tail -5
```

Expected: 2 failures with `ModuleNotFoundError: No module named 'phase2_project_engine.ops.track_effects'`.

### Task 4.2: Implement `add_effect_to_track`

**Files:**
- Create: `phase2_project_engine/ops/track_effects.py` (~80 lines for `add_effect_to_track`)

- [ ] **Step 1: Create the file with `add_effect_to_track`**

```python
"""Track-level effect operations: add_effect_to_track, list_track_effects."""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from lxml import etree

from ..errors import NotFoundError, ValidationError, validation_error
from ..io import ProjectTree
from ..tracks import get_tracks, is_audio_track
from ..validators import validate_effect_id


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
    Video effects cannot be added to audio tracks and vice versa.
    """
    if catalog is None:
        catalog = []
    kid = validate_effect_id(effect_id, catalog)
    cat_entry = next(
        (e for e in catalog if e.get("kdenlive_id") == kid), None
    )
    if cat_entry is None:
        raise validation_error(
            f"effect_id_unknown: effect {effect_id!r} is not in the catalog",
        )
    tracks = get_tracks(tree)
    if track_index < 0 or track_index >= len(tracks):
        raise NotFoundError(
            f"track_index_out_of_range: track_index={track_index}, "
            f"track_count={len(tracks)}\n"
            f"fix: call get_timeline_summary to see valid track indices"
        )
    track_tractor = tracks[track_index]
    is_audio = is_audio_track(tree, track_tractor)
    effect_type = cat_entry.get("kdenlive_type", "video")
    if is_audio and effect_type != "audio":
        raise validation_error(
            f"effect_id_must_be_audio: effect {kid!r} is {effect_type!r} but "
            f"track {track_index} is an audio track\n"
            f"fix: pass an audio effect (kdenlive_type='audio'), or call "
            f"add_effect_to_track on a video track"
        )
    if not is_audio and effect_type != "video":
        raise validation_error(
            f"effect_id_must_be_video: effect {kid!r} is {effect_type!r} but "
            f"track {track_index} is a video track\n"
            f"fix: pass a video effect (kdenlive_type='video'), or call "
            f"add_effect_to_track on an audio track"
        )
    # Build the <filter> on the track's tractor (BUG 9 fix: colon, not snake)
    filt = etree.SubElement(track_tractor, "filter")
    mlt = etree.SubElement(filt, "property")
    mlt.set("name", "mlt_service")
    mlt.text = cat_entry.get("mlt_service", kid)
    kdenlive_label = etree.SubElement(filt, "property")
    kdenlive_label.set("name", "kdenlive:id")
    kdenlive_label.text = kid
    # Apply params or defaults
    effective_params: dict[str, object] = dict(params) if params else {}
    if not effective_params:
        for p in cat_entry.get("parameters", []):
            if "default" in p:
                effective_params[p["name"]] = p["default"]
    for k, v in effective_params.items():
        p = etree.SubElement(filt, "property")
        p.set("name", k)
        p.text = str(v)
    filters = list(track_tractor.findall("filter"))
    return {
        "track_index": track_index,
        "effect_index": len(filters) - 1,
        "effect_id": kid,
    }
```

- [ ] **Step 2: Run the test to verify it passes**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. pytest phase2_project_engine/tests/test_ops_track_effects.py -v 2>&1 | tail -5
```

Expected: 2 passes.

### Task 4.3: Write the failing test for `list_track_effects`

**Files:**
- Modify: `phase2_project_engine/tests/test_ops_track_effects.py` (append 3 tests)

- [ ] **Step 1: Append 3 tests**

```python
def test_list_track_effects_empty():
    """An empty track effect stack returns an empty list."""
    from phase2_project_engine.ops.track_effects import list_track_effects
    tree = make_minimal_tree()
    result = list_track_effects(tree, 0)
    assert result["track_index"] == 0
    assert result["effects"] == []


def test_list_track_effects_with_added_effect():
    """After add_effect_to_track, list returns the effect with its params."""
    from phase2_project_engine.ops.track_effects import (
        add_effect_to_track, list_track_effects,
    )
    tree = make_minimal_tree()
    audio_track_idx = _find_audio_track_index(tree)
    add_effect_to_track(tree, audio_track_idx, "volume", params={"level": "0.5"},
                        catalog=VOLUME_CATALOG)
    result = list_track_effects(tree, audio_track_idx)
    assert result["track_index"] == audio_track_idx
    assert len(result["effects"]) == 1
    assert result["effects"][0]["effect_id"] == "volume"
    assert result["effects"][0]["params"]["level"] == "0.5"


def test_list_track_effects_track_index_out_of_range():
    from phase2_project_engine.ops.track_effects import list_track_effects
    tree = make_minimal_tree()
    with pytest.raises(NotFoundError, match="track_index_out_of_range"):
        list_track_effects(tree, 999)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. pytest phase2_project_engine/tests/test_ops_track_effects.py::test_list_track_effects_empty phase2_project_engine/tests/test_ops_track_effects.py::test_list_track_effects_with_added_effect phase2_project_engine/tests/test_ops_track_effects.py::test_list_track_effects_track_index_out_of_range -v 2>&1 | tail -5
```

Expected: 3 failures with `AttributeError: module ... has no attribute 'list_track_effects'`.

### Task 4.4: Implement `list_track_effects`

**Files:**
- Modify: `phase2_project_engine/ops/track_effects.py` (append `list_track_effects`)

- [ ] **Step 1: Append `list_track_effects`**

```python
def list_track_effects(tree: ProjectTree, track_index: int) -> dict:
    """Return the effect stack of `track_index`."""
    tracks = get_tracks(tree)
    if track_index < 0 or track_index >= len(tracks):
        raise NotFoundError(
            f"track_index_out_of_range: track_index={track_index}, "
            f"track_count={len(tracks)}\n"
            f"fix: call get_timeline_summary to see valid track indices"
        )
    track_tractor = tracks[track_index]
    filters = list(track_tractor.findall("filter"))
    effects = []
    for i, filt in enumerate(filters):
        effect_id = ""
        params: dict[str, str] = {}
        enabled = True
        for prop in filt.findall("property"):
            name = prop.get("name", "")
            if name == "kdenlive:id":
                effect_id = prop.text or ""
            elif name == "mlt_service":
                pass  # redundant with kdenlive:id
            elif name == "disable":
                enabled = (prop.text or "0") != "1"
            else:
                params[name] = prop.text or ""
        effects.append({
            "index": i,
            "effect_id": effect_id,
            "enabled": enabled,
            "params": params,
        })
    return {
        "track_index": track_index,
        "effects": effects,
    }
```

- [ ] **Step 2: Run the test to verify it passes**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. pytest phase2_project_engine/tests/test_ops_track_effects.py -v 2>&1 | tail -10
```

Expected: 5 tests pass (2 add + 3 list).

### Task 4.5: Write the failing test for `set_clip_speed_ramp`

**Files:**
- Modify: `phase2_project_engine/tests/test_ops_clips_edit.py` (append 2 tests)

- [ ] **Step 1: Append 2 tests**

```python
def test_set_clip_speed_ramp_basic():
    """A 3-keyframe ramp 0→1s @1x, 1→2s @2x, 2→3s @1x writes a timeremap link."""
    from phase2_project_engine.ops.bin import import_media
    from phase2_project_engine.ops.clips import insert_clip
    from phase2_project_engine.ops.clips_edit import set_clip_speed_ramp
    tree = make_minimal_tree()
    import os
    fake = os.path.abspath("fake.mp4")
    src = import_media(tree, [fake])[0]
    insert_clip(tree, track_index=0, position_sec=0.0,
                source_id=src, source_in_sec=0.0, source_out_sec=3.0)
    result = set_clip_speed_ramp(tree, "2", [
        {"time_ms": 0, "rate": 1.0},
        {"time_ms": 1000, "rate": 2.0},
        {"time_ms": 2000, "rate": 1.0},
    ])
    assert result["keyframes_added"] == 3
    assert result["min_rate"] == 1.0
    assert result["max_rate"] == 2.0


def test_set_clip_speed_ramp_time_monotonic_violation():
    from phase2_project_engine.errors import ValidationError
    from phase2_project_engine.ops.bin import import_media
    from phase2_project_engine.ops.clips import insert_clip
    from phase2_project_engine.ops.clips_edit import set_clip_speed_ramp
    tree = make_minimal_tree()
    import os
    fake = os.path.abspath("fake.mp4")
    src = import_media(tree, [fake])[0]
    insert_clip(tree, track_index=0, position_sec=0.0,
                source_id=src, source_in_sec=0.0, source_out_sec=3.0)
    with pytest.raises(ValidationError, match="time_monotonic_violation"):
        set_clip_speed_ramp(tree, "2", [
            {"time_ms": 1000, "rate": 2.0},
            {"time_ms": 500, "rate": 1.0},  # out of order
        ])
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. pytest phase2_project_engine/tests/test_ops_clips_edit.py::test_set_clip_speed_ramp_basic phase2_project_engine/tests/test_ops_clips_edit.py::test_set_clip_speed_ramp_time_monotonic_violation -v 2>&1 | tail -5
```

Expected: 2 failures with `AttributeError: module ... has no attribute 'set_clip_speed_ramp'`.

### Task 4.6: Implement `set_clip_speed_ramp`

**Files:**
- Modify: `phase2_project_engine/ops/clips_edit.py` (append `set_clip_speed_ramp`)

- [ ] **Step 1: Append the op function**

```python
def set_clip_speed_ramp(
    tree: ProjectTree,
    clip_id: str,
    keyframes: Sequence[Mapping[str, int | float]],
) -> dict:
    """Add or replace a keyframed speed ramp on a clip.

    Uses an <link mlt_service="timeremap"> element on the clip's
    producer chain. Replaces the entire existing ramp.
    """
    if not keyframes:
        raise validation_error(
            f"keyframes_empty: keyframes is an empty list\n"
            f"fix: pass at least one keyframe, e.g. "
            f"[{{'time_ms': 0, 'rate': 1.0}}]",
        )
    # Validate ranges
    for i, kf in enumerate(keyframes):
        t = int(kf["time_ms"])
        if t < 0:
            raise validation_error(
                f"time_out_of_range: time_ms={t} at index {i}\n"
                f"fix: pass a non-negative time_ms",
            )
        r = float(kf["rate"])
        if r <= 0.0 or r > 10.0:
            raise validation_error(
                f"rate_out_of_range: rate={r} at index {i} "
                f"(must be in (0.0, 10.0])\n"
                f"fix: pass a rate in (0.0, 10.0]",
            )
    sorted_kfs = sorted(keyframes, key=lambda k: int(k["time_ms"]))
    for i in range(1, len(sorted_kfs)):
        if int(sorted_kfs[i]["time_ms"]) <= int(sorted_kfs[i-1]["time_ms"]):
            raise validation_error(
                f"time_monotonic_violation: duplicate or out-of-order "
                f"time_ms at index {i}\n"
                f"fix: pass keyframes sorted ascending by time_ms, "
                f"no duplicates",
            )
    first = sorted_kfs[0]
    if int(first["time_ms"]) != 0 or float(first["rate"]) != 1.0:
        raise validation_error(
            f"first_keyframe_must_be_zero: first keyframe must be at "
            f"time_ms=0 and rate=1.0 (got time_ms={first['time_ms']}, "
            f"rate={first['rate']})\n"
            f"fix: prepend a keyframe at time_ms=0 with rate=1.0",
        )
    # Find the clip's entry
    track, entry, _ti = _find_entry_for_clip(tree, clip_id)
    # Find the clip's producer in the tree. The implementation depends on
    # how ProjectTree exposes producers; this is the trickiest part of
    # Task 4.6. Look at how clips_edit.py's `replace_clip_source` finds
    # the producer — it should have a similar pattern.
    #
    # For now, raise NotImplementedError if the producer can't be found.
    producer = _find_clip_producer(tree, entry)
    if producer is None:
        raise BackendError(
            f"could not find the producer for clip {clip_id!r}\n"
            f"fix: this is a pyagent internal error, please report"
        )
    # Remove any existing <link mlt_service="timeremap">
    for link in list(producer.findall("link")):
        if link.get("mlt_service") == "timeremap":
            producer.remove(link)
    # Build the time_map string (HH:MM:SS:FF=rate;...)
    fps = _get_project_fps(tree)
    parts = []
    for kf in sorted_kfs:
        t_sec = int(kf["time_ms"]) / 1000.0
        h = int(t_sec // 3600)
        m = int((t_sec % 3600) // 60)
        s = int(t_sec % 60)
        f = int(round((t_sec - int(t_sec)) * fps))
        if f >= int(fps):
            f = 0
            s += 1
        # Note: Kdenlive's write path adds +offset=1 on the last keyframe's
        # frame (clipmodel.cpp:556-567). For 2b we serialize the
        # value as-is; the offset is a render-time concern, not a
        # storage concern.
        parts.append(f"{h:02d}:{m:02d}:{s:02d}:{f:02d}={float(kf['rate']):.3f}")
    time_map = ";".join(parts) + ";"
    # Add the new <link mlt_service="timeremap">
    link = etree.SubElement(producer, "link")
    link.set("mlt_service", "timeremap")
    tm_prop = etree.SubElement(link, "property")
    tm_prop.set("name", "time_map")
    tm_prop.text = time_map
    pitch_prop = etree.SubElement(link, "property")
    pitch_prop.set("name", "pitch")
    pitch_prop.text = "1"
    img_prop = etree.SubElement(link, "property")
    img_prop.set("name", "image_mode")
    img_prop.text = "nearest"
    return {
        "clip_id": clip_id,
        "keyframes_added": len(sorted_kfs),
        "time_map": time_map,
        "min_rate": min(float(k["rate"]) for k in sorted_kfs),
        "max_rate": max(float(k["rate"]) for k in sorted_kfs),
    }


def _find_clip_producer(tree: ProjectTree, entry):
    """Return the <producer> element for the given <entry>, or None.

    Look at how replace_clip_source does it. If the producer is
    embedded inline in the entry (no separate <producer> element),
    this function should return the entry's parent or a sub-element.
    """
    # The producer for a clip can be:
    # 1. A child <producer> in the bin
    # 2. An inline <producer> nested in the entry
    # 3. A reference via the entry's `producer` attribute
    # The actual mechanism depends on how the project is loaded.
    # For 2b's initial implementation, walk up from the entry to
    # the bin and look for the matching producer.
    # TODO: implement based on the existing code
    raise NotImplementedError(
        "See replace_clip_source in clips_edit.py for the producer-finding "
        "pattern. The implementer should extract it into a shared helper."
    )
```

**Note on `_find_clip_producer`:** the implementer needs to figure out how the clip's producer is identified in the MLT XML for the current `ProjectTree`. The 2a spec had `replace_clip_source` (clips_edit.py) deal with similar producer-finding. Reuse that pattern by extracting it into a shared helper in `_helpers.py` or `clips_edit.py`.

**Note on `_get_project_fps`:** the helper from Task 2.4 should be moved to `_helpers.py` (or shared via a similar mechanism) and reused here. The two implementations must agree on how the project's FPS is read from the tree.

- [ ] **Step 2: Run the test to verify it passes**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. pytest phase2_project_engine/tests/test_ops_clips_edit.py::test_set_clip_speed_ramp_basic phase2_project_engine/tests/test_ops_clips_edit.py::test_set_clip_speed_ramp_time_monotonic_violation -v 2>&1 | tail -10
```

Expected: 2 passes. (If the producer-finding logic is incomplete, the basic test may fail with a BackendError; debug and fix.)

### Task 4.7: Update `__init__.py`, `runtime.py`, and add ToolDefs

**Files:**
- Modify: `phase2_project_engine/ops/__init__.py` (+3 exports: 2 from track_effects, 1 from clips_edit)
- Modify: `phase3_pyagent_core/runtime.py` (+3 OP_TABLE entries, +2 MUTATING_OPS entries)
- Create: `phase3_pyagent_core/tools/track_effects.py` (2 ToolDefs)
- Modify: `phase3_pyagent_core/tools/clips_edit.py` (+1 ToolDef)

- [ ] **Step 1: Update `ops/__init__.py`**

```python
from .track_effects import add_effect_to_track, list_track_effects
# ...
    "add_effect_to_track",
    "list_track_effects",
```

- [ ] **Step 2: Update `runtime.py`**

```python
# In OP_TABLE:
    "add_effect_to_track": "add_effect_to_track",
    "list_track_effects": "list_track_effects",
    "set_clip_speed_ramp": "set_clip_speed_ramp",
# In MUTATING_OPS (add; list_track_effects is read-only):
        "add_effect_to_track", "set_clip_speed_ramp",
```

- [ ] **Step 3: Create `tools/track_effects.py`**

```python
"""ToolDef definitions for the track-effect operations."""
from __future__ import annotations

from . import ToolDef  # adapt to the existing ToolDef import path


ADD_EFFECT_TO_TRACK = ToolDef(
    name="pyagent_add_effect_to_track",
    label="Add effect to track",
    description=(
        "Add a Kdenlive effect to a track (not a clip). The effect is "
        "added as a filter on the track's tractor, so it applies to "
        "every clip on the track. Video effects cannot be added to "
        "audio tracks and vice versa."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "track_index": {"type": "integer", "description": "0-based track index"},
            "effect_id": {"type": "string", "description": "Kdenlive effect id (e.g. 'volume', 'blur')"},
            "params": {"type": "object", "description": "Optional parameter overrides (defaults from catalog if omitted)"},
        },
        "required": ["track_index", "effect_id"],
        "additionalProperties": False,
    },
    handler="add_effect_to_track",
    domain="track-effects",
    mutating=True,
)

LIST_TRACK_EFFECTS = ToolDef(
    name="pyagent_list_track_effects",
    label="List track effects",
    description=(
        "Return the effect stack of a track. Each entry includes the "
        "effect_id, enabled state, and current parameter values."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "track_index": {"type": "integer"},
        },
        "required": ["track_index"],
        "additionalProperties": False,
    },
    handler="list_track_effects",
    domain="track-effects",
    mutating=False,
)
```

- [ ] **Step 4: Update `tools/clips_edit.py`**

```python
SET_CLIP_SPEED_RAMP = ToolDef(
    name="pyagent_set_clip_speed_ramp",
    label="Set clip speed ramp",
    description=(
        "Add or replace a keyframed speed ramp on a clip. Uses an "
        "<link mlt_service='timeremap'> element on the clip's producer. "
        "The first keyframe MUST be at time_ms=0 and rate=1.0. The ramp "
        "is replaced wholesale; the AI is expected to read get_timeline_summary "
        "or list_keyframes first if it wants to preserve existing keyframes."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "clip_id": {"type": "string"},
            "keyframes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "time_ms": {"type": "integer", "minimum": 0},
                        "rate": {"type": "number", "exclusiveMinimum": 0, "maximum": 10},
                    },
                    "required": ["time_ms", "rate"],
                },
                "description": "Sorted ascending by time_ms; first must be at time_ms=0 rate=1.0",
            },
        },
        "required": ["clip_id", "keyframes"],
        "additionalProperties": False,
    },
    handler="set_clip_speed_ramp",
    domain="clips-edit",
    mutating=True,
)
```

- [ ] **Step 5: Verify `list_tools()` returns 38**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
PYTHONPATH=. python3 -c "from phase3_pyagent_core.runtime import list_tools; print(len(list_tools()))"
```

Expected: `38` (35 + 3 new).

### Task 4.8: Add golden-file entries for the 3 new tools

**Files:**
- Modify: `phase3_pyagent_core/tests/fixtures/golden_io.json` (+3 entries)
- Modify: `phase3_pyagent_core/tests/test_golden_io.py` (+3 parametrized cases)

- [ ] **Step 1: Add 3 entries**

```json
{
  "op": "add_effect_to_track",
  "args": {"track_index": 0, "effect_id": "volume", "params": {"level": "0.5"}},
  "expect_keys": ["track_index", "effect_index", "effect_id"]
},
{
  "op": "list_track_effects",
  "args": {"track_index": 0},
  "setup": ("add_effect_to_track", {"track_index": 0, "effect_id": "volume", "params": {"level": "0.5"}}),
  "expect_keys": ["track_index", "effects"]
},
{
  "op": "set_clip_speed_ramp",
  "args": {"clip_id": "2", "keyframes": [{"time_ms": 0, "rate": 1.0}, {"time_ms": 1000, "rate": 2.0}, {"time_ms": 2000, "rate": 1.0}]},
  "expect_keys": ["clip_id", "keyframes_added", "time_map", "min_rate", "max_rate"]
}
```

- [ ] **Step 2: Run the golden-file tests**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. pytest phase3_pyagent_core/tests/test_golden_io.py -v 2>&1 | tail -10
```

Expected: 3 new tests pass + all existing tests pass.

### Task 4.9: Add the real-Kdenlive interop test

**Files:**
- Modify: `phase7_real_session/tests/test_e2e.py` (append 1 interop test, always skipped)

- [ ] **Step 1: Append the interop test**

```python
@skipif_kdenlive_missing
def test_2b_round_trip_through_real_kdenlive():
    """Build a project with a keyframed effect, a track effect, and a
    time-remapped clip. Open in real Kdenlive, save, re-load, and verify
    all three features survive.

    ACTIVATION: requires the Xvfb+Kdenlive harness extension documented
    in BUGS_FIXED T4.5. Currently always skipped."""
    pytest.skip("Real Kdenlive interop test is gated on the Xvfb harness extension")
```

- [ ] **Step 2: Verify the test is skipped (not failing)**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. pytest phase7_real_session/tests/test_e2e.py -v 2>&1 | tail -10
```

Expected: 1 new test SKIPPED + all existing tests pass/skip.

### Task 4.10: Run the full test suite + commit Task 4

- [ ] **Step 1: Run the full test suite**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. timeout 180 pytest -q --no-header 2>&1 | tail -3
```

Expected: ~280 passed (target), 3 skipped, 1 warning.

- [ ] **Step 2: Update `BUGS_FIXED.md` if any bugs were found**

(Only if bugs were found during Task 4.)

- [ ] **Step 3: Commit Task 4**

```bash
cd /home/ah64/apps/mlt-pipeline-2b
git add pyagent-kdenlive-guide/phase2_project_engine/ops/track_effects.py \
        pyagent-kdenlive-guide/phase2_project_engine/ops/clips_edit.py \
        pyagent-kdenlive-guide/phase2_project_engine/ops/__init__.py \
        pyagent-kdenlive-guide/phase2_project_engine/tests/test_ops_track_effects.py \
        pyagent-kdenlive-guide/phase2_project_engine/tests/test_ops_clips_edit.py \
        pyagent-kdenlive-guide/phase3_pyagent_core/runtime.py \
        pyagent-kdenlive-guide/phase3_pyagent_core/tools/track_effects.py \
        pyagent-kdenlive-guide/phase3_pyagent_core/tools/clips_edit.py \
        pyagent-kdenlive-guide/phase3_pyagent_core/tests/fixtures/golden_io.json \
        pyagent-kdenlive-guide/phase3_pyagent_core/tests/test_golden_io.py \
        pyagent-kdenlive-guide/phase7_real_session/tests/test_e2e.py \
        pyagent-kdenlive-guide/BUGS_FIXED.md
git commit -m "[track-effects] add add_effect_to_track, list_track_effects, set_clip_speed_ramp"
```

---

## Task 5: Final verification + merge to main

### Task 5.1: Run the full test suite (final check)

- [ ] **Step 1: Verify the spec's Definition of Done items pass**

```bash
cd /home/ah64/apps/mlt-pipeline-2b
echo "=== list_tools() count ==="
cd pyagent-kdenlive-guide
PYTHONPATH=. python3 -c "from phase3_pyagent_core.runtime import list_tools; ts=list_tools(); print(len(ts)); print('  expected 38')"
echo ""
echo "=== Module-size budget check (prod files <300 lines) ==="
for f in phase2_project_engine/ops/clips_edit.py \
         phase2_project_engine/ops/effects.py \
         phase2_project_engine/ops/transitions.py \
         phase2_project_engine/ops/keyframes.py \
         phase2_project_engine/ops/track_effects.py \
         phase3_pyagent_core/tools/keyframes.py \
         phase3_pyagent_core/tools/track_effects.py; do
  lines=$(wc -l < "$f")
  echo "  $lines  $f"
  if [ "$lines" -ge 300 ]; then echo "  !! OVER 300 !!"; fi
done
echo ""
echo "=== Test file budget check (test files <400 lines) ==="
for f in phase2_project_engine/tests/test_keyframes.py \
         phase2_project_engine/tests/test_ops_keyframes.py \
         phase2_project_engine/tests/test_ops_track_effects.py; do
  lines=$(wc -l < "$f")
  echo "  $lines  $f"
  if [ "$lines" -ge 400 ]; then echo "  !! OVER 400 !!"; fi
done
```

Expected: 38 in `list_tools()`, all prod files <300 lines, all test files <400 lines.

- [ ] **Step 2: Run the full test suite one more time**

```bash
cd /home/ah64/apps/mlt-pipeline-2b/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. timeout 180 pytest -q --no-header 2>&1 | tail -3
```

Expected: ~280 passed (279-282), 3 skipped, 1 warning.

- [ ] **Step 3: Verify the 19 existing tools' golden fixtures are unchanged**

```bash
cd /home/ah64/apps/mlt-pipeline-2b
git diff main pyagent-kdenlive-guide/phase3_pyagent_core/tests/fixtures/golden_io.json | head -20
```

Expected: only the 9 NEW entries differ from main; the existing 19 entries are byte-identical.

### Task 5.2: Merge to main

- [ ] **Step 1: Local merge (same pattern as 2a)**

```bash
cd /home/ah64/apps/mlt-pipeline
git checkout main
git pull 2>/dev/null || echo "(no remote or pull failed, OK)"
git merge add-editor-tools-2b
```

Expected: clean fast-forward merge (no conflicts expected — all 4 commits are direct descendants of `main`).

- [ ] **Step 2: Verify on merged result**

```bash
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. timeout 180 pytest -q --no-header 2>&1 | tail -3
PYTHONPATH=. python3 -c "from phase3_pyagent_core.runtime import list_tools; print(len(list_tools()))"
```

Expected: ~280 passed, 3 skipped, 1 warning; `list_tools()` = 38.

### Task 5.3: Clean up worktree

- [ ] **Step 1: Remove the worktree and branch**

```bash
cd /home/ah64/apps/mlt-pipeline
git worktree remove /home/ah64/apps/mlt-pipeline-2b --force
git worktree prune
git branch -d add-editor-tools-2b
```

Expected: worktree gone, branch deleted.

- [ ] **Step 2: Verify final state**

```bash
cd /home/ah64/apps/mlt-pipeline
git worktree list
git branch -a | head -10
git log --oneline -8
```

Expected: only the main worktree exists; only the `main` branch; the 2a commits + 4 new commits are at the top.

---

## Self-review

### 1. Spec coverage

Each section of the spec is implemented by at least one task:

| Spec section | Implementing task(s) |
|---|---|
| Problem statement (gaps in 2a's tool set) | All of Tasks 1-4 |
| Goals (9 new tools, 4 commits, 14 new error codes, 3-layer tests) | Tasks 1, 2, 3, 4 (each commit verifies against goals) |
| Non-goals (no undo/redo, no compound clips, no color scopes) | Plan does NOT include these; future sub-projects |
| Architecture / file layout | Task 0 (split) + Tasks 1-4 (file extensions) |
| The 9 tool schemas | Tasks 1.1-1.7, 2.1-2.9, 3.1-3.5, 4.1-4.10 |
| Storage of keyframe data (real Kdenlive format) | Task 0.4 (parse/serialize) + Task 2.2 (apply) |
| Storage of track effects (real Kdenlive format) | Task 4.2 |
| Storage of variable-rate speed (timeremap) | Task 4.6 |
| Catalog update (keyframes field) | Task 0.3 |
| 14 new error codes | Each task's tests include at least one error code |
| 3-layer testing strategy | Each task includes Layer 1 (golden) and Layer 2 (integration) tests; Task 4.9 adds Layer 3 |
| Test count budget (280 passed + 3 skipped) | Task 5.1 verifies |
| Commit plan (4 commits) | Tasks 1.7, 2.9, 3.5, 4.10 |
| Definition of done | Task 5.1 verifies each item |
| Risks | Risks are listed in the spec; not directly addressed in the plan but the mitigations are baked into the implementation choices |

### 2. Placeholder scan

- "TBD": none.
- "TODO": one in Task 4.6 (the `_find_clip_producer` helper); explicitly marked as needing extraction from `replace_clip_source`. This is intentional — the implementer should extract the helper, not skip it.
- "fill in details": none.
- "Add appropriate error handling" / "add validation": none — all error handling is explicit.
- "Similar to Task N": one reference in Task 2.4 (`_get_project_fps` reuses Task 2.4's earlier version). The reference is clear and the function is fully defined in the plan.
- All other code is complete.

### 3. Type consistency

| Function name | First defined in | Used in | Consistent? |
|---|---|---|---|
| `get_effect_param` | Task 1.2 | Task 1.3, 1.5, 1.6 | yes |
| `set_effect_param` | Task 1.4 | Task 1.5, 1.6 | yes |
| `list_keyframes` | Task 2.2 | Task 2.3, 2.5, 2.7, 2.8 | yes |
| `set_keyframe` | Task 2.4 | Task 2.5, 2.7, 2.8 | yes |
| `remove_keyframe` | Task 2.6 | Task 2.7, 2.8 | yes |
| `set_transition_property` | Task 3.2 | Task 3.3, 3.4 | yes |
| `add_effect_to_track` | Task 4.2 | Task 4.3, 4.4, 4.7, 4.8 | yes |
| `list_track_effects` | Task 4.4 | Task 4.7, 4.8 | yes |
| `set_clip_speed_ramp` | Task 4.6 | Task 4.7, 4.8 | yes |
| `_find_entry_for_clip` | used in Tasks 1, 2, 4 | private to clips_edit.py | yes (existing helper) |
| `parse_animation_string` | Task 0.4 (_keyframes.py) | Tasks 1, 2 | yes |
| `serialize_keyframes` | Task 0.4 (_keyframes.py) | Tasks 2 | yes |
| `is_keyframable_param` | Task 0.4 (_keyframes.py) | Tasks 1 | yes |
| `coerce_param_value` | Task 0.4 (_keyframes.py) | Tasks 1 | yes |
| `_get_project_fps` | Task 2.4 (keyframes.py) | Task 4.6 (clips_edit.py) | **DUPLICATION** — both files define it. The implementer should move it to `_helpers.py` after Task 2.4 and import it in Task 4.6. (Documented in Task 4.6 as a "Note".) |

### 4. Open issues for the implementer

The following are NOT placeholders but points the implementer should be aware of:

- **Task 0.2** (backend.py split): the implementer must decide whether to split based on the file's readability. The plan provides the split pattern but does not mandate it.
- **Task 2.4** (`_get_project_fps`): the implementer must verify the FPS reading from the project's profile works for the test fixture. The placeholder function may need to be adjusted based on the actual `ProjectTree` API.
- **Task 4.6** (`_find_clip_producer`): the implementer MUST extract this from `replace_clip_source` in `clips_edit.py`. The plan explicitly defers this to the implementer; the task cannot pass without it.
- **Task 4.6** (`_get_project_fps`): after Task 2.4, this should be moved to `_helpers.py` and shared.
- **Tasks 1.6, 2.8, 3.4, 4.8** (golden-file entries): the exact field names in `golden_io.json` may differ from `expect_keys` — the implementer must read 2-3 existing entries to confirm the file's convention.

These are intentional "the implementer knows the codebase better than the plan" handoffs, not plan failures.
