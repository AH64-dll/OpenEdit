# Analysis Report: Open Edit Test Suite & Pydantic Schema Test Structure

**Module Scope**: `open_edit/ir/types.py`, `open_edit/tests/`
**Target Milestone**: Milestone 1 — Operations Data Models (Pydantic)
**Investigator**: Explorer 2 (Milestone 1)

---

## 1. Test Suite Location & Path Structure

- **Repository Root**: `/home/ah64/apps/mlt-pipeline`
- **Package Directory**: `/home/ah64/apps/mlt-pipeline/open_edit`
- **Test Suite Directory**: `/home/ah64/apps/mlt-pipeline/open_edit/tests`
- **Schema Module Path**: `open_edit/ir/types.py` (`/home/ah64/apps/mlt-pipeline/open_edit/open_edit/ir/types.py`)
- **Unit Test Module Path for M1**: `open_edit/tests/test_ir/test_types.py` (`/home/ah64/apps/mlt-pipeline/open_edit/tests/test_ir/test_types.py`)

### Directory Layout
```
/home/ah64/apps/mlt-pipeline/open_edit/
├── open_edit/
│   └── ir/
│       ├── types.py          # Pydantic schemas (Operation base, clip ops, advanced ops, union)
│       ├── apply.py          # Timeline state derivation & operation application
│       └── validate.py       # Op validation logic
├── tests/
│   ├── __init__.py           # Package marker for tests
│   ├── conftest.py           # Pytest fixtures and sys.path configuration
│   ├── test_ir/
│   │   ├── test_types.py     # Schema & Pydantic validator unit tests
│   │   ├── test_apply.py     # Replay & timeline derivation tests
│   │   └── test_validate.py  # Referential & asset validation tests
│   ├── test_storage/
│   │   └── test_edit_graph.py # SQLite EditGraphStore tests
│   └── test_qc/, test_render/, test_sandbox/, test_serve/
└── pyproject.toml
```

---

## 2. Test Execution Environment Analysis

### Execution Directory & Python Path
1. **Working Directory Requirement**:
   - Commands must run with working directory set to `/home/ah64/apps/mlt-pipeline/open_edit`.
   - Running from root `/home/ah64/apps/mlt-pipeline` requires setting `PYTHONPATH=open_edit`.

2. **`sys.path` Configuration**:
   - `open_edit/tests/conftest.py` adds the root directory `/home/ah64/apps/mlt-pipeline/open_edit` to `sys.path` dynamically when `pytest` runs.
   - When running via `python3 -m unittest discover -s tests`, `PYTHONPATH=.` (or `PYTHONPATH=open_edit`) must be present in the execution environment so that `from open_edit.ir.types import ...` resolves cleanly.

### Test Runner Mechanics: Pytest vs. Python Unittest
- **Pytest Mechanics**:
  - `pytest` discovers functions named `test_*()` across `tests/` regardless of whether they are standalone functions or inside classes.
  - Command: `pytest tests/test_ir/test_types.py` (runs 26 tests in ~0.08s).
- **Unittest Discovery Mechanics**:
  - Command specified in Acceptance Criteria: `python3 -m unittest discover -s tests`
  - `unittest` discovery ONLY detects test methods defined inside classes inheriting from `unittest.TestCase`. Standalone `def test_*()` functions are skipped by `unittest discover` (resulting in `Ran 0 tests`).
- **Compatibility Requirement**:
  - To fulfill the project acceptance criterion (`python3 -m unittest discover -s tests` executes successfully with zero failures), all unit test modules (including `test_ir/test_types.py`) MUST wrap test cases inside `unittest.TestCase` subclasses.
  - `pytest` automatically discovers and runs `unittest.TestCase` classes as well, ensuring total compatibility across both runners.

---

## 3. Existing Test Helper Utilities

Located in `open_edit/tests/conftest.py` and `open_edit/tests/test_ir/test_types.py`:

1. **`tmp_notes_db` Fixture** (`open_edit/tests/conftest.py`):
   - Creates an isolated `NotesStore` SQLite database in a temporary directory for note testing.
2. **`tmp_project_with_assets` Fixture** (`open_edit/tests/conftest.py`):
   - Seeds Content-Addressable Storage (CAS) asset files and SQLite edit graph entries in a fresh `tmp_path`.
   - Returns a `Project(name="test", workdir=tmp_path)`.
3. **`new_id()` & `now_iso8601()` Helpers** (`open_edit/ir/types.py`):
   - `new_id()` generates UUID4 strings for `edit_id`, `clip_id`, `effect_id`.
   - `now_iso8601()` generates ISO-8601 UTC timestamp strings.

---

## 4. Operation Schemas & Validator Test Expectations (Milestone 1)

### Operation Schemas in `open_edit/ir/types.py`

| Schema | Kind (`kind`) | Core Attributes & Default Factories | Validation Rules / Rejections |
|--------|---------------|--------------------------------------|--------------------------------|
| `Operation` (Base) | N/A | `edit_id` (default `new_id()`), `author`, `status` (default `"applied"`), `timestamp`, `parent_id` | `author` must be `"user"` or `"ai"`. `status` must be `"applied"` or `"reverted"`. Rejects invalid values. |
| `AddClipOp` | `add_clip` | `asset_hash`, `track_id`, `track_kind` (default `"video"`), `position_sec`, `in_point_sec` (default `0.0`), `out_point_sec`, `clip_id` (default `new_id()`) | `track_kind` must be `"video"` or `"audio"`. Rejects invalid track kinds (e.g. `"text"`). |
| `RemoveClipOp` | `remove_clip` | `clip_id` | Requires valid `clip_id` string. |
| `MoveClipOp` | `move_clip` | `clip_id`, `new_track_id`, `new_position_sec` | Requires valid target track and position. |
| `TrimClipOp` | `trim_clip` | `clip_id`, `new_in_point_sec`, `new_out_point_sec` | Requires valid numeric in/out points. |
| `AddTransitionOp` | `add_transition` | `clip_a_id`, `clip_b_id`, `transition_type`, `duration_sec` | `transition_type` must be `"luma"`, `"dissolve"`, or `"wipe"`. Rejects invalid types (e.g. `"star_wipe"`). |
| `AddEffectOp` | `add_effect` | `target_kind`, `target_id`, `effect_type`, `params`, `effect_id` (default `new_id()`) | `target_kind` must be `"clip"` or `"track"`. |
| `SetKeyframeOp` | `set_keyframe` | `effect_id`, `param`, `keyframes` | Keyframes must be list of `(time, value, interpolation)` tuples. |
| `GroupEditsOp` | `group_edits` | `edit_ids`, `label` | `edit_ids` must be a list of edit ID strings. |
| `RawMltXmlOp` | `raw_mlt_xml` | `xml`, `description` | Requires valid MLT XML string. |
| `FreeFormCodeOp` | `free_form_code` | `code` | Requires python code string. |
| `SetAudioGainOp` | `set_audio_gain` | `clip_id`, `gain_db` | Gain in dB float. |
| `NormalizeAudioOp` | `normalize_audio` | `target_kind`, `target_id`, `target_dbfs` (default `-16.0`) | `target_dbfs` float. |
| `OperationUnion` | Polymorphic | Discriminated union on `kind` | Discriminates model type based on `kind`. Rejects unknown `kind`. |

---

## 5. Recommended Unit Test Suite Structure for `open_edit/ir/types.py`

To ensure 100% test coverage and compliance with both `python3 -m unittest discover -s tests` and `pytest`:

```python
"""Tests for Pydantic operation types in open_edit/ir/types.py."""
import unittest
import uuid
import pytest
from pydantic import TypeAdapter, ValidationError

from open_edit.ir.types import (
    AddClipOp,
    AddEffectOp,
    AddTransitionOp,
    FreeFormCodeOp,
    GroupEditsOp,
    MoveClipOp,
    NormalizeAudioOp,
    Operation,
    OperationUnion,
    Project,
    RawMltXmlOp,
    RemoveClipOp,
    SetAudioGainOp,
    SetKeyframeOp,
    TrimClipOp,
    new_id,
    now_iso8601,
)


class TestHelpers(unittest.TestCase):
    def test_new_id_returns_uuid_string(self) -> None:
        aid = new_id()
        uuid.UUID(aid)

    def test_new_id_is_unique(self) -> None:
        self.assertNotEqual(new_id(), new_id())

    def test_now_iso8601_returns_string(self) -> None:
        ts = now_iso8601()
        self.assertIsInstance(ts, str)
        self.assertIn("T", ts)


class TestBaseOperation(unittest.TestCase):
    def test_operation_default_edit_id_is_unique(self) -> None:
        a = Operation(author="user", kind="test")
        b = Operation(author="user", kind="test")
        self.assertNotEqual(a.edit_id, b.edit_id)

    def test_operation_default_status_is_applied(self) -> None:
        op = Operation(author="user", kind="test")
        self.assertEqual(op.status, "applied")

    def test_operation_default_parent_id_is_none(self) -> None:
        op = Operation(author="user", kind="test")
        self.assertIsNone(op.parent_id)

    def test_operation_status_must_be_valid_literal(self) -> None:
        with self.assertRaises(ValidationError):
            Operation(author="user", kind="test", status="deleted")

    def test_operation_author_must_be_ai_or_user(self) -> None:
        with self.assertRaises(ValidationError):
            Operation(author="robot", kind="test")


class TestBasicClipOperations(unittest.TestCase):
    def test_add_clip_op_minimal(self) -> None:
        op = AddClipOp(
            author="ai", asset_hash="abc123", track_id="video_1", position_sec=0.0,
        )
        self.assertEqual(op.kind, "add_clip")
        self.assertEqual(op.track_kind, "video")
        self.assertEqual(op.in_point_sec, 0.0)
        self.assertIsNone(op.out_point_sec)
        self.assertNotEqual(op.clip_id, op.edit_id)

    def test_add_clip_op_track_kind_validation(self) -> None:
        with self.assertRaises(ValidationError):
            AddClipOp(
                author="ai", asset_hash="abc", track_id="t",
                position_sec=0.0, track_kind="text",
            )

    def test_remove_clip_op(self) -> None:
        op = RemoveClipOp(author="ai", clip_id="c1")
        self.assertEqual(op.kind, "remove_clip")
        self.assertEqual(op.clip_id, "c1")

    def test_move_clip_op(self) -> None:
        op = MoveClipOp(author="ai", clip_id="c1", new_track_id="v2", new_position_sec=10.0)
        self.assertEqual(op.kind, "move_clip")
        self.assertEqual(op.new_track_id, "v2")
        self.assertEqual(op.new_position_sec, 10.0)

    def test_trim_clip_op(self) -> None:
        op = TrimClipOp(author="ai", clip_id="c1", new_in_point_sec=2.0, new_out_point_sec=5.0)
        self.assertEqual(op.kind, "trim_clip")
        self.assertEqual(op.new_in_point_sec, 2.0)
        self.assertEqual(op.new_out_point_sec, 5.0)


class TestAdvancedOperations(unittest.TestCase):
    def test_add_transition_op_fields(self) -> None:
        op = AddTransitionOp(
            author="ai", clip_a_id="c1", clip_b_id="c2",
            transition_type="luma", duration_sec=1.0,
        )
        self.assertEqual(op.kind, "add_transition")
        self.assertEqual(op.transition_type, "luma")

    def test_add_transition_op_type_validation(self) -> None:
        with self.assertRaises(ValidationError):
            AddTransitionOp(
                author="ai", clip_a_id="c1", clip_b_id="c2",
                transition_type="star_wipe", duration_sec=1.0,
            )

    def test_add_effect_op_minimal(self) -> None:
        op = AddEffectOp(
            author="ai", target_kind="clip", target_id="c1",
            effect_type="volume", params={"gain": 1.0},
        )
        self.assertEqual(op.kind, "add_effect")
        self.assertNotEqual(op.effect_id, op.edit_id)

    def test_set_keyframe_op_fields(self) -> None:
        op = SetKeyframeOp(
            author="ai", effect_id="fx1", param="gain",
            keyframes=[(0.0, 1.0, "linear"), (2.0, 0.0, "linear")],
        )
        self.assertEqual(op.kind, "set_keyframe")
        self.assertEqual(op.keyframes[0], (0.0, 1.0, "linear"))

    def test_group_edits_op(self) -> None:
        op = GroupEditsOp(author="ai", edit_ids=["e1", "e2"], label="AI: intro")
        self.assertEqual(op.kind, "group_edits")
        self.assertEqual(op.edit_ids, ["e1", "e2"])

    def test_raw_mlt_xml_op(self) -> None:
        op = RawMltXmlOp(author="ai", xml="<filter/>", description="Vintage")
        self.assertEqual(op.kind, "raw_mlt_xml")

    def test_free_form_code_op(self) -> None:
        op = FreeFormCodeOp(author="ai", code="ir.add_clip('abc', 'v1', 0.0)")
        self.assertEqual(op.kind, "free_form_code")


class TestAudioOperations(unittest.TestCase):
    def test_set_audio_gain_op(self) -> None:
        op = SetAudioGainOp(author="ai", clip_id="c1", gain_db=-6.0)
        self.assertEqual(op.kind, "set_audio_gain")
        self.assertEqual(op.gain_db, -6.0)

    def test_normalize_audio_op_defaults(self) -> None:
        op = NormalizeAudioOp(author="ai", target_kind="track", target_id="audio_1")
        self.assertEqual(op.target_dbfs, -16.0)


class TestDiscriminatedUnionAndSerialization(unittest.TestCase):
    def test_operation_union_validates_by_kind(self) -> None:
        payload = {
            "kind": "add_clip", "author": "ai", "asset_hash": "abc",
            "track_id": "v1", "position_sec": 0.0, "edit_id": "x",
            "parent_id": None, "timestamp": "2026-07-20T00:00:00Z", "status": "applied",
        }
        op = TypeAdapter(OperationUnion).validate_python(payload)
        self.assertIsInstance(op, AddClipOp)
        self.assertEqual(op.edit_id, "x")

    def test_operation_union_rejects_unknown_kind(self) -> None:
        payload = {"kind": "unknown_op", "author": "ai"}
        with self.assertRaises(ValidationError):
            TypeAdapter(OperationUnion).validate_python(payload)

    def test_operation_json_round_trip(self) -> None:
        op = AddClipOp(author="ai", asset_hash="abc", track_id="v1", position_sec=0.0)
        json_str = op.model_dump_json()
        restored = AddClipOp.model_validate_json(json_str)
        self.assertEqual(restored.edit_id, op.edit_id)
        self.assertEqual(restored.asset_hash, op.asset_hash)

    def test_project_defaults(self) -> None:
        p = Project(name="test")
        self.assertEqual(p.assets, {})
        self.assertEqual(p.edit_graph, [])
        self.assertTrue(bool(p.project_id))
```
