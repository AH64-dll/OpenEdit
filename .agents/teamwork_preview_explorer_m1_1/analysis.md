# Milestone 1: Operations Data Models (Pydantic) — Analysis Report

## Executive Summary
This report analyzes the existing Pydantic models in `open_edit/open_edit/ir/types.py`, validation logic in `open_edit/open_edit/ir/validate.py`, environment specifics (Python 3.14.5, Pydantic 2.13.4), and test framework compatibility for Milestone 1.

---

## 1. Existing Codebase Analysis

### File Structure
- Module path: `/home/ah64/apps/mlt-pipeline/open_edit/open_edit/ir/types.py`
- Validation module: `/home/ah64/apps/mlt-pipeline/open_edit/open_edit/ir/validate.py`
- Compatibility shim: `/home/ah64/apps/mlt-pipeline/open_edit/open_edit/pydantic_compat.py`
- Tests module: `/home/ah64/apps/mlt-pipeline/open_edit/tests/test_ir/test_types.py`

### Base Model: `Operation`
Defined in `open_edit/ir/types.py` (lines 87–94):
```python
class Operation(BaseModel):
    kind: str  # Overridden by each subclass as Literal[...]
    edit_id: str = Field(default_factory=new_id)
    parent_id: Optional[str] = None
    author: Literal["ai", "user"]
    timestamp: str = Field(default_factory=now_iso8601)
    status: Literal["applied", "reverted", "superseded"] = "applied"
    originating_note_id: Optional[str] = None
```

### Analysis of Required Operation Schemas
All 10 operation schemas requested in Milestone 1 are defined in `types.py`:

| # | Operation Schema | Defined in `types.py` | Key Fields & Default Values |
|---|---|---|---|
| 1 | `AddClipOp` | Lines 97–105 | `kind = "add_clip"`, `asset_hash`, `track_id`, `track_kind` (`"video"\|"audio"` default `"video"`), `position_sec`, `in_point_sec` (default 0.0), `out_point_sec` (`Optional[float]`), `clip_id` |
| 2 | `RemoveClipOp` | Lines 108–110 | `kind = "remove_clip"`, `clip_id` |
| 3 | `MoveClipOp` | Lines 113–117 | `kind = "move_clip"`, `clip_id`, `new_track_id`, `new_position_sec` |
| 4 | `TrimClipOp` | Lines 120–124 | `kind = "trim_clip"`, `clip_id`, `new_in_point_sec`, `new_out_point_sec` |
| 5 | `AddTransitionOp` | Lines 127–132 | `kind = "add_transition"`, `clip_a_id`, `clip_b_id`, `transition_type` (`"luma"\|"dissolve"\|"wipe"\|"fade"\|"cut"`), `duration_sec` |
| 6 | `AddEffectOp` | Lines 147–153 | `kind = "add_effect"`, `target_kind` (`"clip"\|"track"`), `target_id`, `effect_type`, `params` (default `{}`), `effect_id` |
| 7 | `SetKeyframeOp` | Lines 171–175 | `kind = "set_keyframe"`, `effect_id`, `param`, `keyframes` (`list[tuple[float, float, str]]`) |
| 8 | `GroupEditsOp` | Lines 238–241 | `kind = "group_edits"`, `edit_ids`, `label` |
| 9 | `RawMltXmlOp` | Lines 249–252 | `kind = "raw_mlt_xml"`, `xml`, `description` |
| 10 | `FreeFormCodeOp` | Lines 255–260 | `kind = "free_form_code"`, `code`, `timeout_sec` (default 30), `mem_mb` (default 512), `label` |

*Note*: Additional operations present in `types.py` include: `RemoveTransitionOp`, `SetTransitionPropertyOp`, `RemoveEffectOp`, `SetEffectParamOp`, `RemoveKeyframeOp`, `SlipClipOp`, `RippleDeleteClipOp`, `ChangeClipSpeedOp`, `SplitClipOp`, `ReplaceClipSourceOp`, `SetClipSpeedRampOp`, `SetAudioGainOp`, `NormalizeAudioOp`, and `UngroupEditsOp`.

### Discriminated Union: `OperationUnion`
Defined in `types.py` (lines 263–276):
```python
OperationUnion = Annotated[
    Union[
        AddClipOp, RemoveClipOp, MoveClipOp, TrimClipOp,
        AddTransitionOp, RemoveTransitionOp, SetTransitionPropertyOp,
        AddEffectOp, RemoveEffectOp, SetEffectParamOp,
        SetKeyframeOp, RemoveKeyframeOp,
        SlipClipOp, RippleDeleteClipOp, ChangeClipSpeedOp,
        SplitClipOp, ReplaceClipSourceOp, SetClipSpeedRampOp,
        SetAudioGainOp, NormalizeAudioOp,
        GroupEditsOp, UngroupEditsOp,
        RawMltXmlOp, FreeFormCodeOp,
    ],
    Field(discriminator="kind"),
]
```

---

## 2. Validation & Pydantic Specifics

### Pydantic Environment Specifics
- **Python Version**: 3.14.5
- **Pydantic Version**: 2.13.4
- **Discriminated Union Polymorphic Deserialization**:
  In Pydantic v2, `OperationUnion` is an `Annotated[Union[...], Field(discriminator="kind")]` type rather than a `BaseModel` subclass. Direct invocation like `OperationUnion.model_validate(...)` raises an exception.
  **Correct Usage**:
  ```python
  from pydantic import TypeAdapter
  op = TypeAdapter(OperationUnion).validate_python(payload_dict)
  op_json = TypeAdapter(OperationUnion).validate_json(json_str)
  ```
  `open_edit/open_edit/pydantic_compat.py` documents this shim behavior.

### Intrinsic vs Contextual Validation
Currently, schema validation is divided into two layers:
1. **Intrinsic Model Constraints (Pydantic models)**:
   - Field types (`str`, `float`, `int`, `Optional[...]`)
   - Enum literals (`Literal["video", "audio"]`, `Literal["luma", "dissolve", ...]`)
   - Default values (`edit_id`, `timestamp`, `clip_id`, `effect_id`)
2. **Contextual & Semantic Validation (`open_edit/ir/validate.py`)**:
   - `validate_op(op, project)` checks project-level constraints:
     - `position_sec >= 0` and `in_point_sec >= 0` for `AddClipOp`
     - `out_point_sec > in_point_sec` if `out_point_sec` is provided
     - `new_in_point_sec < new_out_point_sec` for `TrimClipOp`
     - `duration_sec > 0` for `AddTransitionOp`
     - Asset existence (`op.asset_hash in project.assets`)
     - Referenced clip existence (`clip_id in project`)
     - Effect catalog compatibility (`effect_type` in catalog, target kind match)

### Optional Missing Field Validators in Schemas
If intrinsic Pydantic validators are desired directly on model classes, `@field_validator` / `@model_validator` in Pydantic v2 can be added:
- `AddClipOp`: Validate `position_sec >= 0`, `in_point_sec >= 0`, `out_point_sec > in_point_sec` if not None.
- `TrimClipOp`: Validate `new_in_point_sec < new_out_point_sec`.
- `AddTransitionOp`: Validate `duration_sec > 0` and `clip_a_id != clip_b_id`.
- `FreeFormCodeOp`: Validate `timeout_sec > 0` and `mem_mb > 0`.

---

## 3. Test Runner Specifics

- The existing unit tests in `open_edit/tests/test_ir/test_types.py` consist of 26 pytest test functions.
- Command execution result: `python3 -m pytest tests/test_ir/test_types.py` succeeds with **26 passed in 0.09s**.
- Note on `python3 -m unittest discover -s tests`: Standard `unittest` runner looks for `unittest.TestCase` subclasses. Because test functions use pytest conventions (`def test_...()`), `unittest discover` reports 0 tests unless run via `pytest`.

---

## 4. Recommended Implementation Strategy

1. **Schema Integrity**: Preserve existing class hierarchy in `open_edit/open_edit/ir/types.py` as it matches specification requirements for all 10 operations.
2. **Deserialization Pattern**: Ensure all parsers use `TypeAdapter(OperationUnion)` for polymorphic operation decoding.
3. **Validator Cohesion**: Ensure any new Pydantic validators added to `types.py` produce standard `ValidationError`s that complement `validate_op()` checks without breaking existing tests.
4. **Verification**: Run `python3 -m pytest tests/test_ir/test_types.py` to confirm all 26 tests pass cleanly.
