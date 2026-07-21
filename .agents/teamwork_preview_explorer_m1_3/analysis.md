# Analysis Report: Open Edit IR Operations Data Models & Cross-Module References

**Milestone**: Milestone 1 - Operations Data Models (Pydantic)  
**Target File**: `open_edit/ir/types.py`  
**Explorer**: Explorer 3  
**Date**: 2026-07-21  

---

## 1. Overview & Cross-Module References

The Intermediate Representation (IR) of Open Edit centers on an append-only log of immutable Pydantic operations defined in `open_edit/ir/types.py`. Every modification to an edit graph is captured as an operation model inheriting from `Operation`. Operations are stored in SQLite via `open_edit/storage/edit_graph.py` and projected onto a derived `Timeline` state via `open_edit/ir/apply.py`.

### Cross-Module Usage Map

| Module | Reference Type | Usage Description |
|---|---|---|
| `open_edit/ir/types.py` | Definition | Defines `Operation` base class, 24 concrete operation subclasses (including the 10 target ops), `OperationUnion` discriminated union, `Project`, `Timeline`, `Track`, `Clip`, `Effect`, `Asset`, `WordAlignment`, `new_id()`, `now_iso8601()`. |
| `open_edit/ir/api.py` | Construction / Builder | `IR` class exposes helper methods (`add_clip`, `remove_clip`, `move_clip`, `trim_clip`, `add_transition`, `add_effect`, `set_keyframe`, `group_edits`, `raw_mlt_xml`, `free_form_code`, etc.) that stamp `edit_id=new_id()`, `author="ai"`, `parent_id`, and `originating_note_id`, appending Pydantic ops to the sandbox ops buffer. |
| `open_edit/ir/apply.py` | Replay Engine | `apply_operation(timeline, op)` updates `Timeline` for each applied operation. Replay skips `op.status != "applied"`. `FreeFormCodeOp` and `GroupEditsOp` are no-ops during timeline derivation. `_apply_free_form_code` runs scripts in sandbox and appends generated child ops. `derive_timeline(project)` replays all ops in sequence order. |
| `open_edit/ir/validate.py` | Validation Engine | `validate_op(op, project, catalog)` checks op fields against current project state (e.g. clip/asset existence, time constraints, catalog effect types/targets). |
| `open_edit/ir/commutativity.py` | Optimization | Analyzes operation pairs (`is_independent(op_a, op_b)`) to determine whether reordering is safe. |
| `open_edit/storage/edit_graph.py` | Persistence Layer | SQLite `edits` table store. Uses `op.model_dump_json()` on `append()`, and `TypeAdapter(OperationUnion).validate_json(payload)` on `load_all()`. Sets `op.status` from DB column. |
| `open_edit/cli.py` | CLI Interface | Commands `list`, `summary`, `undo`, `free_form`, `render` consume `OperationUnion` and `Project` to inspect edit graphs and derive timelines. |
| `open_edit/agent/sandbox_bridge.py` | Execution Bridge | `run_free_form()` executes scripts inside Rust `bwrap` sandbox, reading produced ops from `ops.jsonl` via `TypeAdapter(OperationUnion).validate_json()`. |
| `open_edit/render/ingest.py` | XML Ingestion | `ingest_mlt_xml()` parses raw MLT XML into a `RawMltXmlOp` and derived synthetic child ops (`AddClipOp`, `AddEffectOp`). |
| `open_edit/render/orchestrator.py` | Rendering Pipeline | Reads `AddClipOp` and derived `Timeline` to drive MLT render process. |
| `open_edit/serve/tool_schemas.py` | API Documentation | Documents the 24 operation kinds, payload schemas, and `IR` builder usage for agent tool invocations. |

---

## 2. Base Model & Discriminator Architecture

### Base `Operation` Class (`open_edit/ir/types.py:87-95`)

All operation models inherit from `Operation`:

```python
class Operation(BaseModel):
    kind: str  # Overridden in concrete subclasses as Literal["..."]
    edit_id: str = Field(default_factory=new_id)
    parent_id: Optional[str] = None
    author: Literal["ai", "user"]
    timestamp: str = Field(default_factory=now_iso8601)
    status: Literal["applied", "reverted", "superseded"] = "applied"
    originating_note_id: Optional[str] = None
```

- **`kind`**: Unique string discriminator (snake_case matching subclass intent).
- **`edit_id`**: Stable UUIDv4 string (default factory `new_id()`). Unique for every operation.
- **`parent_id`**: Optional UUID string referencing a parent operation (e.g. `FreeFormCodeOp` or `GroupEditsOp`) when an operation is generated as a child.
- **`author`**: Originator of the edit, restricted to `"ai"` or `"user"`.
- **`timestamp`**: ISO 8601 UTC timestamp string (default factory `now_iso8601()`).
- **`status`**: Operation state in edit graph. Allowed values: `"applied"`, `"reverted"`, `"superseded"`. Default is `"applied"`.
- **`originating_note_id`**: Optional string linking operation to a user feedback note.

### Discriminated Union (`open_edit/ir/types.py:263-276`)

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

- Pydantic v2 `TypeAdapter(OperationUnion).validate_json(json_str)` uses `kind` to route deserialization to the exact concrete subclass.

---

## 3. Detailed Operation Specifications (The 10 Target Operations)

### 1. `AddClipOp` (`open_edit/ir/types.py:97-105`)
- **`kind`**: `Literal["add_clip"] = "add_clip"`
- **`asset_hash`**: `str` — Hash referencing ingested media asset in `project.assets`.
- **`track_id`**: `str` — Target track identifier (e.g. `"v1"`, `"a1"`, `"video_graphics"`).
- **`track_kind`**: `Literal["video", "audio"] = "video"` — Track type.
- **`position_sec`**: `float` — Timeline start position in seconds (must be >= 0.0).
- **`in_point_sec`**: `float = 0.0` — Sub-clip asset in-point in seconds (must be >= 0.0).
- **`out_point_sec`**: `Optional[float] = None` — Sub-clip asset out-point in seconds (must be > `in_point_sec` when set).
- **`clip_id`**: `str = Field(default_factory=new_id)` — Unique UUID for the created clip instance.
- **Replay Behavior** (`apply.py:75-79`): Calls `_get_or_create_track(timeline, op.track_id, op.track_kind)`, constructs `Clip`, appends to `track.clips`.
- **Validation Rules** (`validate.py:79-100`): Asserts `asset_hash` in `project.assets`, `position_sec >= 0`, `in_point_sec >= 0`, `out_point_sec > in_point_sec` if present.

### 2. `RemoveClipOp` (`open_edit/ir/types.py:108-111`)
- **`kind`**: `Literal["remove_clip"] = "remove_clip"`
- **`clip_id`**: `str` — Target clip UUID to remove.
- **Replay Behavior** (`apply.py:80-83`): Removes matching clip from all tracks: `track.clips = [c for c in track.clips if c.clip_id != op.clip_id]`.
- **Validation Rules** (`validate.py:102-103`): No-op validation if unknown (passes safely).

### 3. `MoveClipOp` (`open_edit/ir/types.py:113-118`)
- **`kind`**: `Literal["move_clip"] = "move_clip"`
- **`clip_id`**: `str` — Target clip UUID.
- **`new_track_id`**: `str` — Destination track identifier.
- **`new_position_sec`**: `float` — New timeline start position in seconds.
- **Replay Behavior** (`apply.py:84-95`): Locates clip, removes from old track, creates/retrieves `new_track_id`, updates `track_id` and `position_sec`, appends to new track.
- **Validation Rules** (`validate.py:105-110`): Asserts `clip_id` exists in project active clips.

### 4. `TrimClipOp` (`open_edit/ir/types.py:120-125`)
- **`kind`**: `Literal["trim_clip"] = "trim_clip"`
- **`clip_id`**: `str` — Target clip UUID.
- **`new_in_point_sec`**: `float` — New asset in-point in seconds.
- **`new_out_point_sec`**: `float` — New asset out-point in seconds.
- **Replay Behavior** (`apply.py:96-109`): Finds clip and updates `in_point_sec` and `out_point_sec`.
- **Validation Rules** (`validate.py:112-123`): Asserts `clip_id` exists and `new_in_point_sec < new_out_point_sec`.

### 5. `AddTransitionOp` (`open_edit/ir/types.py:127-133`)
- **`kind`**: `Literal["add_transition"] = "add_transition"`
- **`clip_a_id`**: `str` — Outgoing clip UUID.
- **`clip_b_id`**: `str` — Incoming clip UUID.
- **`transition_type`**: `Literal["luma", "dissolve", "wipe", "fade", "cut"]` — Allowed transition types.
- **`duration_sec`**: `float` — Transition duration in seconds (must be > 0).
- **Replay Behavior** (`apply.py:176-251`): Center-on-cut algorithm. Computes timeline cut point: `cut = clip_a.position_sec + (clip_a.out_point_sec - clip_a.in_point_sec)`. Adjusts `clip_a.out_point_sec` to `cut - duration/2` and `clip_b.in_point_sec` to `cut + duration/2`. Appends transition effect to `clip_a.effects`. Raises `ValueError` if transition duration exceeds clip bounds.
- **Validation Rules** (`validate.py:125-140`): Asserts `clip_a_id` and `clip_b_id` exist and `duration_sec > 0`.

### 6. `AddEffectOp` (`open_edit/ir/types.py:147-154`)
- **`kind`**: `Literal["add_effect"] = "add_effect"`
- **`target_kind`**: `Literal["clip", "track"]` — Target level.
- **`target_id`**: `str` — Clip UUID or Track identifier.
- **`effect_type`**: `str` — MLT service name (e.g. `"volume"`, `"brightness"`, `"luma"`, `"contrast"`, `"eq"`, `"saturation"`).
- **`params`**: `dict[str, Any] = Field(default_factory=dict)` — Effect parameter dictionary.
- **`effect_id`**: `str = Field(default_factory=new_id)` — Unique UUID for the effect instance.
- **Replay Behavior** (`apply.py:254-280`): Appends `Effect(effect_id=op.effect_id, effect_type=op.effect_type, params=op.params)` to clip or track `effects`.
- **Validation Rules** (`validate.py:142-162`): Asserts `effect_type` is known in `EffectCatalog`, `target_kind` matches catalog allowed targets, and `target_id` exists if `target_kind == "clip"`.

### 7. `SetKeyframeOp` (`open_edit/ir/types.py:171-176`)
- **`kind`**: `Literal["set_keyframe"] = "set_keyframe"`
- **`effect_id`**: `str` — Target effect UUID.
- **`param`**: `str` — Target parameter name.
- **`keyframes`**: `list[tuple[float, float, str]]` — List of `(time_sec, value, interpolation)` tuples (where interpolation is `"discrete"`, `"linear"`, or `"smooth"`).
- **Replay Behavior** (`apply.py:283-296`): Updates `effect.keyframes[op.param] = op.keyframes` on the matching `Effect`.
- **Validation Rules** (`validate.py:164-169`): Asserts `effect_id` exists in project applied effects.

### 8. `GroupEditsOp` (`open_edit/ir/types.py:238-242`)
- **`kind`**: `Literal["group_edits"] = "group_edits"`
- **`edit_ids`**: `list[str]` — List of child `edit_id` strings grouped together.
- **`label`**: `str` — Human-readable description for the edit group.
- **Replay Behavior** (`apply.py:120-121`): No-op during timeline derivation (returns `timeline` unmodified). Structural grouping metadata.

### 9. `RawMltXmlOp` (`open_edit/ir/types.py:249-253`)
- **`kind`**: `Literal["raw_mlt_xml"] = "raw_mlt_xml"`
- **`xml`**: `str` — Raw MLT XML snippet/document string.
- **`description`**: `str` — Explanation of the XML block.
- **Replay Behavior** (`apply.py:124`): Replayed as no-op during timeline state derivation. Parsed by `render/ingest.py` into synthetic child operations (`AddClipOp`, `AddEffectOp`, etc.) during XML ingestion.

### 10. `FreeFormCodeOp` (`open_edit/ir/types.py:255-260`)
- **`kind`**: `Literal["free_form_code"] = "free_form_code"`
- **`code`**: `str` — Python script string executed in the bwrap sandbox.
- **`timeout_sec`**: `int = 30` — Sandbox execution timeout in seconds.
- **`mem_mb`**: `int = 512` — Sandbox memory limit in megabytes.
- **`label`**: `Optional[str] = None` — Optional script label.
- **Replay Behavior** (`apply.py:122-123` & `317-341`): `apply_operation` skips execution (no-op) during `derive_timeline` to allow idempotent replay without re-executing code. `_apply_free_form_code` runs `run_free_form()` in sandbox and appends generated child ops (with `parent_id == op.edit_id`) to `project.edit_graph`.

---

## 4. Serialization & Persistence Requirements

1. **JSON Serialization**:
   - Every operation model must serialize cleanly via `.model_dump_json()`.
   - Deserialization uses `TypeAdapter(OperationUnion).validate_json(payload)`.

2. **SQLite Edit Graph Mapping** (`storage/edit_graph.py`):
   - Table `edits`: `(edit_id TEXT PRIMARY KEY, parent_id TEXT, kind TEXT, author TEXT, timestamp TEXT, status TEXT, sequence_num INTEGER, payload TEXT)`.
   - On `append(op)`: DB columns are populated directly from `op` attributes (`op.edit_id`, `op.parent_id`, `op.kind`, `op.author`, `op.timestamp`, `op.status`, `payload=op.model_dump_json()`).
   - On `load_all()`: Loads `payload` and `status`, runs `op = TypeAdapter(OperationUnion).validate_json(payload)`, overrides `op.status = row['status']`.

3. **Immutability & Pydantic Config**:
   - Operations are immutable data structures representing discrete events in the edit history. Updating status or copying operations uses `model_copy(update={...})`.

---

## 5. Summary of Interface Compatibility Rules

1. **Inheritance & Discriminator**: All ops inherit from `Operation` and define explicit `kind: Literal["..."]` matching `OperationUnion`.
2. **Deterministic Defaults**: Default factories must be callable (`new_id`, `now_iso8601`, `dict`, `list`).
3. **Pure Timeline Derivation**: `apply_operation(timeline, op)` MUST remain a pure function (`Timeline -> Timeline`). Ops that produce child ops (`FreeFormCodeOp`, `RawMltXmlOp`, `GroupEditsOp`) are no-ops in `apply_operation` so replay remains fast, idempotent, and deterministic.
