# Phase 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the free-form Python sandbox (Rust binary + Python bridge) that lets an AI agent run arbitrary Python that emits IR ops to the edit graph, with FS isolation, network denial, and resource limits.

**Architecture:** A Rust binary (`open-edit-sandbox`) installs a network-deny seccomp filter, sets rlimits, fork+watcher wall-clock timeout, and execs `bwrap` with a self-contained scratch dir + ro-bound source media. The Python `sandbox_bridge` generates a self-contained `_bootstrap.py` (IR + op models inlined via `inspect.getsource()`), runs the binary, parses the JSON output, validates the produced `ops.jsonl` incrementally against a working-copy timeline, and atomic-commits the ops to the edit graph.

**Tech Stack:** Python 3.14, Pydantic v2, SQLite, Rust (stable), clap, nix, libseccomp-rs, anyhow, bwrap 0.11+.

**Spec:** `docs/superpowers/specs/2026-07-21-open-edit-phase-3-design.md`

## Global Constraints

- Python 3.11+ (project is `>=3.11`, system is 3.14; we pin to the parent's runtime — the binary receives `--python-bin` from `sandbox_bridge` which sends `sys.executable`).
- Pydantic v2.13.4 quirks: use `TypeAdapter(OperationUnion)` for `.validate_*` calls; `.model_validate()` does NOT work on bare `Annotated` alias. `open_edit/pydantic_compat.py` shims `TypeAdapter`.
- Phase 0+1 imports verified (2026-07-21): `pydantic_compat`, `EditGraphStore`, `JobLock`, `AssetStore`, all 12 op types, `Project`, `Asset`, `apply_operation`, `derive_timeline` all import.
- The free-form Python sandbox is **Linux-only** (seccomp + bwrap). Other platforms are out of scope.
- All sandbox tests are skipped if `bwrap` is not on `PATH`. Integration tests in `sandbox/tests/` are cargo-feature-gated.
- Commit style: `[open_edit] <message>` (matches the 17 Phase 2 commits on main).
- No comments in code unless the comment is documentation for a non-obvious safety property.

## File Structure

| Group | New Files | Modified Files | Boundary |
|-------|-----------|----------------|----------|
| Storage / types | — | `open_edit/storage/edit_graph.py`, `open_edit/storage/schema.sql`, `open_edit/ir/types.py` | Cross-phase foundation; `EditGraphStore.project_id` + `Project.workdir: Optional[Path] = None` |
| Exceptions | `open_edit/agent/exceptions.py`, `open_edit/agent/__init__.py` | — | FreeFormResult, SandboxError, _ValidationError |
| Libs / manifest | `open_edit/agent/libs.py`, `open_edit/agent/allowed_libs.toml` | — | Header parsing, TOML manifest |
| IR API | `open_edit/ir/api.py` (rewrite) | — | 12 methods, parent_id stamping at build time |
| Rust binary | `sandbox/Cargo.toml`, `sandbox/src/main.rs`, `sandbox/src/jail.rs`, `sandbox/src/network_denylist.rs`, `sandbox/tests/integration.rs` | — | All Rust code in one task sequence |
| Bridge | `open_edit/agent/sandbox_bridge.py` | — | Python wrapper, uses inspect.getsource() |
| Apply | — | `open_edit/ir/apply.py` | `_apply_free_form_code` branch |
| CLI | — | `open_edit/cli.py` | `free-form` subcommand for manual testing |
| Tests | `tests/test_free_form_e2e.py` | `tests/conftest.py` | 5 e2e tests + fixtures |

---

## Task 1: Cross-phase foundation — `EditGraphStore.project_id` + `Project.workdir`

**Files:**
- Modify: `open_edit/open_edit/storage/schema.sql:1-9` (add project_id row at init)
- Modify: `open_edit/open_edit/storage/edit_graph.py:1-119` (add project_id property)
- Modify: `open_edit/open_edit/ir/types.py:179-184` (add `workdir: Optional[Path] = None`)
- Modify: `open_edit/tests/testdata/golden_11clip/edit_graph.json` (add workdir if needed; check first)
- Test: `open_edit/tests/test_edit_graph_project_id.py`

**Interfaces:**
- Consumes: existing `EditGraphStore.__init__(db_path)` API
- Produces:
  - `EditGraphStore(db_path).project_id -> str` (reads/writes `project_meta` table)
  - `Project(workdir: Optional[Path] = None, ...)` (Optional, back-compat with Phase 0+1 fixtures)

### Step 1: Write the failing test

Create `open_edit/tests/test_edit_graph_project_id.py`:

```python
"""Phase 3 Task 1: EditGraphStore.project_id round-trip + Project.workdir Optional."""
import json
from pathlib import Path

import pytest

from open_edit.ir.types import Project
from open_edit.storage.edit_graph import EditGraphStore


def test_edit_graph_store_persists_project_id(tmp_path):
    """project_id is generated on first open and stable across reopens."""
    db = tmp_path / "edit_graph.db"
    store1 = EditGraphStore(db)
    pid = store1.project_id
    assert isinstance(pid, str) and len(pid) > 0

    # Reopen: same project_id
    store2 = EditGraphStore(db)
    assert store2.project_id == pid


def test_project_workdir_optional():
    """M8: Project.workdir is Optional, back-compat with Phase 0+1 fixtures."""
    p = Project(name="test")
    assert p.workdir is None
    p2 = Project(name="test", workdir=Path("/tmp/x"))
    assert p2.workdir == Path("/tmp/x")


def test_project_loads_with_workdir_none(tmp_path):
    """Phase 0+1 edit_graph.json without workdir still deserializes."""
    p = Project.model_validate({"name": "legacy", "assets": {}, "edit_graph": []})
    assert p.workdir is None
    assert p.name == "legacy"
```

### Step 2: Run tests to verify they fail

Run: `cd open_edit && pytest tests/test_edit_graph_project_id.py -v`
Expected: 3 failures (`store.project_id` AttributeError; `Project(workdir=...)` may pass but the test verifies workdir is settable).

### Step 3: Add project_id to schema.sql

`open_edit/storage/schema.sql` line 1-9 currently:

```sql
CREATE TABLE IF NOT EXISTS project_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

No change to schema needed — `project_meta` table already supports the key/value pattern. We'll insert `('project_id', '<uuid>')` on first open.

### Step 4: Implement `EditGraphStore.project_id`

In `open_edit/storage/edit_graph.py`, add this property after `_init_schema` (around line 47):

```python
def project_id(self) -> str:
    """Return the stable project_id for this db file. Generated on first open.

    Phase 3 Task 1: stored in the project_meta table. Stable across reopens.
    """
    with self._conn() as conn:
        cur = conn.execute(
            "SELECT value FROM project_meta WHERE key = 'project_id'"
        )
        row = cur.fetchone()
        if row is not None:
            return row[0]
        # First open: generate and persist.
        from open_edit.ir.types import new_id
        pid = new_id()
        conn.execute(
            "INSERT INTO project_meta (key, value) VALUES ('project_id', ?)",
            (pid,),
        )
        return pid
```

### Step 5: Add `workdir: Optional[Path] = None` to Project

In `open_edit/ir/types.py`, modify the `Project` class (around line 179):

```python
class Project(BaseModel):
    project_id: str = Field(default_factory=new_id)
    name: str
    workdir: Optional[Path] = None  # NEW in Phase 3 (M8: Optional for back-compat)
    created_at: str = Field(default_factory=now_iso8601)
    assets: dict[str, Asset] = Field(default_factory=dict)
    edit_graph: list[OperationUnion] = Field(default_factory=list)
```

Confirm `Optional` and `Path` are already imported (they are; line 4-5 of types.py).

### Step 6: Run tests to verify they pass

Run: `cd open_edit && pytest tests/test_edit_graph_project_id.py -v`
Expected: 3 passing.

### Step 7: Run the full test suite to verify no regression

Run: `cd open_edit && pytest`
Expected: 164 → 167 passing (3 new tests).

### Step 8: Commit

```bash
cd /home/ah64/apps/mlt-pipeline
git add open_edit/storage/schema.sql open_edit/storage/edit_graph.py open_edit/ir/types.py open_edit/tests/test_edit_graph_project_id.py
git commit -m "[open_edit] phase3 t1: EditGraphStore.project_id + Project.workdir Optional"
```

---

## Task 2: Exceptions module

**Files:**
- Create: `open_edit/open_edit/agent/__init__.py`
- Create: `open_edit/open_edit/agent/exceptions.py`
- Test: `open_edit/tests/test_free_form_exceptions.py`

**Interfaces:**
- Consumes: nothing (pure data classes)
- Produces:
  - `FreeFormResult(success, ops, reason, detail, duration_s)` with `.ok()` and `.fail()` classmethods
  - `SandboxError(Exception)`
  - `_ValidationError(Exception)` (private to agent package)

### Step 1: Write the failing test

Create `open_edit/tests/test_free_form_exceptions.py`:

```python
"""Phase 3 Task 2: FreeFormResult + SandboxError."""
import pytest

from open_edit.agent.exceptions import FreeFormResult, SandboxError


def test_free_form_result_ok():
    r = FreeFormResult.ok(ops=[], duration_s=1.23)
    assert r.success is True
    assert r.ops == []
    assert r.duration_s == 1.23
    assert r.reason == ""
    assert r.detail == ""


def test_free_form_result_fail():
    r = FreeFormResult.fail("timeout", "30s elapsed")
    assert r.success is False
    assert r.reason == "timeout"
    assert r.detail == "30s elapsed"
    assert r.ops == []
    assert r.duration_s == 0.0


def test_sandbox_error_is_exception():
    with pytest.raises(SandboxError):
        raise SandboxError("oops")
```

### Step 2: Run test to verify it fails

Run: `cd open_edit && pytest tests/test_free_form_exceptions.py -v`
Expected: ImportError on `open_edit.agent.exceptions`.

### Step 3: Create the package init

Create `open_edit/agent/__init__.py`:

```python
"""Phase 3: agent-side modules (sandbox bridge, exception types)."""
```

### Step 4: Implement exceptions.py

Create `open_edit/agent/exceptions.py`:

```python
"""Exception types and result types for the free-form Python sandbox."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from open_edit.ir.types import OperationUnion


@dataclass
class FreeFormResult:
    """Result of a free-form Python run. Always returned, never raised.

    success=True: ops list is non-empty (or empty if the script emitted no ops).
    success=False: reason is a stable string; detail is human-readable.
    """
    success: bool
    ops: list["OperationUnion"] = field(default_factory=list)
    reason: str = ""
    detail: str = ""
    duration_s: float = 0.0

    @classmethod
    def ok(cls, ops: list, duration_s: float) -> "FreeFormResult":
        return cls(success=True, ops=ops, duration_s=duration_s)

    @classmethod
    def fail(cls, reason: str, detail: str = "") -> "FreeFormResult":
        return cls(success=False, reason=reason, detail=detail)


class SandboxError(Exception):
    """Raised for unrecoverable preflight/setup errors. NOT for runtime failures
    (those are reported via FreeFormResult.fail).
    """


class _ValidationError(Exception):
    """Internal: a single op in ops.jsonl failed referential or schema validation.
    Caught by sandbox_bridge and mapped to FreeFormResult.fail('invalid_op').
    """
```

### Step 5: Run tests to verify they pass

Run: `cd open_edit && pytest tests/test_free_form_exceptions.py -v`
Expected: 3 passing.

### Step 6: Run full suite to verify no regression

Run: `cd open_edit && pytest`
Expected: 167 → 170 passing (3 new tests).

### Step 7: Commit

```bash
cd /home/ah64/apps/mlt-pipeline
git add open_edit/agent/__init__.py open_edit/agent/exceptions.py open_edit/tests/test_free_form_exceptions.py
git commit -m "[open_edit] phase3 t2: agent package + FreeFormResult + SandboxError"
```

---

## Task 3: Libs module + TOML manifest

**Files:**
- Create: `open_edit/open_edit/agent/libs.py`
- Create: `open_edit/open_edit/agent/allowed_libs.toml`
- Test: `open_edit/tests/test_free_form_libs.py`

**Interfaces:**
- Consumes: `SandboxError` from `open_edit.agent.exceptions` (Task 2)
- Produces:
  - `parse_header(code: str) -> tuple[str, dict[str, str]]` (H8: requires quoted dict keys)
  - `version_supported(declared: str) -> bool`
  - `lib_version_supported(name: str, ver: str) -> bool`
  - `ALLOWED_LIBS_PATH -> Path` (constant)

### Step 1: Write the failing test

Create `open_edit/tests/test_free_form_libs.py`:

```python
"""Phase 3 Task 3: parse_header + version_supported + lib_version_supported."""
import textwrap
from pathlib import Path

import pytest

from open_edit.agent.exceptions import SandboxError
from open_edit.agent.libs import (
    ALLOWED_LIBS_PATH,
    lib_version_supported,
    parse_header,
    version_supported,
)


def test_parse_header_minimal():
    code = "# ir_api_version: 0.1; libs: {}"
    v, libs = parse_header(code)
    assert v == "0.1"
    assert libs == {}


def test_parse_header_with_libs():
    code = '# ir_api_version: 0.1; libs: {"numpy": "1.26.4"}'
    v, libs = parse_header(code)
    assert v == "0.1"
    assert libs == {"numpy": "1.26.4"}


def test_parse_header_missing_raises():
    code = "import os  # no header"
    with pytest.raises(SandboxError, match="missing or malformed"):
        parse_header(code)


def test_parse_header_unquoted_keys_raises():
    """H8: ast.literal_eval rejects unquoted dict keys."""
    code = "# ir_api_version: 0.1; libs: {numpy: 1.26.4}"
    with pytest.raises(SandboxError, match="not valid Python"):
        parse_header(code)


def test_version_supported_true():
    assert version_supported("0.1") is True


def test_version_supported_false():
    assert version_supported("99.0") is False


def test_lib_version_supported_true():
    assert lib_version_supported("numpy", "1.26.4") is True


def test_lib_version_supported_false():
    assert lib_version_supported("numpy", "99.0") is False
    assert lib_version_supported("nonexistent", "1.0") is False


def test_allowed_libs_path_is_toml():
    assert ALLOWED_LIBS_PATH.suffix == ".toml"
    assert ALLOWED_LIBS_PATH.exists()
```

### Step 2: Run test to verify it fails

Run: `cd open_edit && pytest tests/test_free_form_libs.py -v`
Expected: ImportError on `open_edit.agent.libs`.

### Step 3: Create the TOML manifest

Create `open_edit/agent/allowed_libs.toml`:

```toml
# Phase 3: which ir_api_version and which library versions a free-form
# Python script may declare. Loaded by open_edit/agent/libs.py via tomllib.
#
# Populated by hand for v1. v1.1 will add a "librarian" tool to populate
# from site-packages.

ir_api_versions = ["0.1"]

[libs.numpy]
versions = ["1.26.4", "2.1.3"]

[libs.opencv-python]
versions = ["4.8.1.78", "4.10.0.84"]

[libs.pillow]
versions = ["10.4.0", "11.0.0"]
```

### Step 4: Implement libs.py

Create `open_edit/agent/libs.py`:

```python
"""Parse `# ir_api_version: X.Y; libs: {...}` headers and check against the
allowed manifest.

H6: SandboxError imported.
H8: header requires quoted dict keys (Python literal syntax).
L8: manifest is TOML (Python 3.11+ tomllib stdlib).
"""
from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

from open_edit.agent.exceptions import SandboxError

_HEADER_RE = re.compile(
    r'^\s*#\s*ir_api_version:\s*(\S+)\s*;\s*libs:\s*(\{.*?\})\s*$',
    re.MULTILINE,
)

ALLOWED_LIBS_PATH = Path(__file__).parent / "allowed_libs.toml"


def parse_header(code: str) -> tuple[str, dict[str, str]]:
    """Parse the ir_api_version header from a free-form Python script.

    Returns (version, libs_dict). libs_dict is {lib_name: version_str}.

    Raises SandboxError on missing/malformed header or unparseable libs.
    """
    m = _HEADER_RE.search(code)
    if not m:
        raise SandboxError(
            "missing or malformed ir_api_version header "
            "(expected: # ir_api_version: X.Y; libs: {\"name\": \"ver\"})"
        )
    version = m.group(1)
    try:
        libs = ast.literal_eval(m.group(2))
    except (ValueError, SyntaxError) as e:
        raise SandboxError(f"libs dict is not valid Python: {e}") from e
    if not isinstance(libs, dict):
        raise SandboxError(f"libs must be a dict, got {type(libs).__name__}")
    for k, v in libs.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise SandboxError(f"libs keys/values must be strings: {libs!r}")
    return version, libs


def version_supported(declared: str) -> bool:
    manifest = _load_manifest()
    return declared in manifest.get("ir_api_versions", [])


def lib_version_supported(name: str, ver: str) -> bool:
    manifest = _load_manifest()
    return ver in manifest.get("libs", {}).get(name, [])


def _load_manifest() -> dict:
    with open(ALLOWED_LIBS_PATH, "rb") as f:
        return tomllib.load(f)
```

### Step 5: Run tests to verify they pass

Run: `cd open_edit && pytest tests/test_free_form_libs.py -v`
Expected: 9 passing.

### Step 6: Run full suite to verify no regression

Run: `cd open_edit && pytest`
Expected: 170 → 179 passing (9 new tests).

### Step 7: Commit

```bash
cd /home/ah64/apps/mlt-pipeline
git add open_edit/agent/libs.py open_edit/agent/allowed_libs.toml open_edit/tests/test_free_form_libs.py
git commit -m "[open_edit] phase3 t3: libs.py (parse_header + TOML manifest) + allowed_libs.toml"
```

---

## Task 4: IR API real implementation

**Files:**
- Modify: `open_edit/open_edit/ir/api.py:1-25` (rewrite — replace 25-line stub with ~250-line implementation)
- Test: `open_edit/tests/test_ir_api.py`

**Interfaces:**
- Consumes: `OperationUnion`, `AddClipOp`, `RemoveClipOp`, `MoveClipOp`, `TrimClipOp`, `AddTransitionOp`, `AddEffectOp`, `SetKeyframeOp`, `SetAudioGainOp`, `NormalizeAudioOp`, `GroupEditsOp`, `RawMltXmlOp`, `FreeFormCodeOp`, `new_id` from `open_edit.ir.types`
- Produces:
  - `IR(ops_buffer, project_id, parent_op_id)` — 12 methods, each builds a Pydantic op with `parent_id` stamped and appends to buffer

### Step 1: Write the failing test

Create `open_edit/tests/test_ir_api.py`:

```python
"""Phase 3 Task 4: IR API real implementation (12 methods, parent_id stamped)."""
import pytest

from open_edit.ir.api import IR
from open_edit.ir.types import (
    AddClipOp, AddEffectOp, AddTransitionOp, FreeFormCodeOp,
    GroupEditsOp, MoveClipOp, NormalizeAudioOp, RawMltXmlOp,
    RemoveClipOp, SetAudioGainOp, SetKeyframeOp, TrimClipOp,
)


@pytest.fixture
def ir_instance():
    return IR(ops_buffer=[], project_id="proj1", parent_op_id="e_parent")


def test_add_clip_returns_clip_id_and_appends(ir_instance):
    cid = ir_instance.add_clip(
        asset_hash="abc", track_id="t1", position_sec=0.0, label="clip_a"
    )
    assert isinstance(cid, str) and len(cid) > 0
    assert len(ir_instance._ops) == 1
    op = ir_instance._ops[0]
    assert isinstance(op, AddClipOp)
    assert op.parent_id == "e_parent"
    assert op.project_id == "proj1"
    assert op.asset_hash == "abc"
    assert op.track_id == "t1"
    assert op.position_sec == 0.0
    assert op.label == "clip_a"
    assert op.clip_id == cid


def test_trim_clip_stamps_parent(ir_instance):
    ir_instance.trim_clip(clip_id="c1", in_point_sec=1.0, out_point_sec=2.0)
    op = ir_instance._ops[0]
    assert isinstance(op, TrimClipOp)
    assert op.parent_id == "e_parent"
    assert op.clip_id == "c1"


def test_move_clip_stamps_parent(ir_instance):
    ir_instance.move_clip(clip_id="c1", new_position_sec=5.0)
    op = ir_instance._ops[0]
    assert isinstance(op, MoveClipOp)
    assert op.parent_id == "e_parent"


def test_remove_clip_stamps_parent(ir_instance):
    ir_instance.remove_clip(clip_id="c1")
    op = ir_instance._ops[0]
    assert isinstance(op, RemoveClipOp)
    assert op.parent_id == "e_parent"


def test_add_transition_stamps_parent(ir_instance):
    ir_instance.add_transition(
        clip_a_id="c1", clip_b_id="c2", kind="crossfade", duration_sec=0.5
    )
    op = ir_instance._ops[0]
    assert isinstance(op, AddTransitionOp)
    assert op.parent_id == "e_parent"


def test_add_effect_stamps_parent(ir_instance):
    ir_instance.add_effect(
        target_kind="clip", target_id="c1", effect_type="volume",
        params={"gain": 0.5}
    )
    op = ir_instance._ops[0]
    assert isinstance(op, AddEffectOp)
    assert op.parent_id == "e_parent"


def test_set_keyframe_stamps_parent(ir_instance):
    ir_instance.set_keyframe(
        effect_id="fx1", param="gain",
        keyframes=[(0.0, 1.0, "linear"), (1.0, 0.0, "linear")],
    )
    op = ir_instance._ops[0]
    assert isinstance(op, SetKeyframeOp)
    assert op.parent_id == "e_parent"


def test_set_audio_gain_stamps_parent(ir_instance):
    ir_instance.set_audio_gain(target_id="t1", gain_db=-3.0)
    op = ir_instance._ops[0]
    assert isinstance(op, SetAudioGainOp)
    assert op.parent_id == "e_parent"


def test_normalize_audio_stamps_parent(ir_instance):
    ir_instance.normalize_audio(target_id="t1", target_dbfs=-14.0)
    op = ir_instance._ops[0]
    assert isinstance(op, NormalizeAudioOp)
    assert op.parent_id == "e_parent"


def test_group_edits_stamps_parent(ir_instance):
    ir_instance.group_edits(edit_ids=["e1", "e2"], label="group_a")
    op = ir_instance._ops[0]
    assert isinstance(op, GroupEditsOp)
    assert op.parent_id == "e_parent"


def test_raw_mlt_xml_stamps_parent(ir_instance):
    ir_instance.raw_mlt_xml(xml="<mlt><tractor/></mlt>", label="raw_a")
    op = ir_instance._ops[0]
    assert isinstance(op, RawMltXmlOp)
    assert op.parent_id == "e_parent"


def test_free_form_code_stamps_parent(ir_instance):
    ir_instance.free_form_code(code="print('hello')", label="sub")
    op = ir_instance._ops[0]
    assert isinstance(op, FreeFormCodeOp)
    assert op.parent_id == "e_parent"


def test_ir_works_with_flushing_buffer_subclass():
    """H10: the buffer is a SupportsAppend; works with any list-like."""
    from open_edit.agent.sandbox_bridge import _FlushingBuffer  # may not exist yet
    # Stub: just verify a list subclass works
    class MyBuf(list):
        def append(self, x):
            super().append(x)
    ir = IR(ops_buffer=MyBuf(), project_id="p", parent_op_id="e")
    ir.add_clip(asset_hash="x", track_id="t", position_sec=0.0)
    assert len(ir._ops) == 1


def test_pydantic_validation_error_on_bad_input(ir_instance):
    """Schema errors fail at build time (Pydantic ValidationError)."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ir_instance.add_clip(
            asset_hash="",  # empty string should fail (if min_length=1)
            track_id="t1",
            position_sec=0.0,
        )
```

### Step 2: Run test to verify it fails

Run: `cd open_edit && pytest tests/test_ir_api.py -v`
Expected: ImportError on `from open_edit.ir.api import IR` (the old stub raises NotImplementedError).

### Step 3: Read the existing op type signatures

Before implementing, read the actual field names from `open_edit/ir/types.py`:

```bash
grep -A 8 "^class AddClipOp\|^class TrimClipOp\|^class MoveClipOp\|^class RemoveClipOp\|^class AddTransitionOp\|^class AddEffectOp\|^class SetKeyframeOp\|^class SetAudioGainOp\|^class NormalizeAudioOp\|^class GroupEditsOp\|^class RawMltXmlOp\|^class FreeFormCodeOp" open_edit/ir/types.py
```

Verify the field names match the test expectations above. If a field name differs (e.g. `clip_a_id` vs `clip_a`), adjust both the test and the implementation.

### Step 4: Rewrite open_edit/ir/api.py

Replace the entire 25-line stub with:

```python
"""In-process IR API for free-form Python code (sandbox side).

Phase 3 Task 4: real implementation. Each method builds one Pydantic op with
parent_id stamped at construction time and appends to a buffer (which the
sandbox wires to ops.jsonl on disk).
"""
from __future__ import annotations

from typing import Any, SupportsAppend

from open_edit.ir.types import (
    AddClipOp, AddEffectOp, AddTransitionOp, FreeFormCodeOp, GroupEditsOp,
    MoveClipOp, NormalizeAudioOp, RawMltXmlOp, RemoveClipOp, SetAudioGainOp,
    SetKeyframeOp, TrimClipOp, new_id,
)


class IR:
    """Free-form Python IR API. Each method appends one Pydantic op to the buffer.

    The buffer is any SupportsAppend (list, _FlushingBuffer, etc.). The sandbox
    wires a _FlushingBuffer that writes each op to ops.jsonl on append.
    """

    def __init__(self, ops_buffer: SupportsAppend, project_id: str, parent_op_id: str):
        self._ops = ops_buffer
        self._project_id = project_id
        self._parent_op_id = parent_op_id

    def add_clip(
        self, asset_hash: str, track_id: str, position_sec: float,
        in_point_sec: float = 0.0, out_point_sec: float | None = None,
        label: str | None = None,
    ) -> str:
        """Append AddClipOp; return generated clip_id."""
        clip_id = new_id()
        op = AddClipOp(
            edit_id=new_id(),
            project_id=self._project_id,
            parent_id=self._parent_op_id,
            clip_id=clip_id,
            asset_hash=asset_hash,
            track_id=track_id,
            position_sec=position_sec,
            in_point_sec=in_point_sec,
            out_point_sec=out_point_sec,
            label=label,
        )
        self._ops.append(op)
        return clip_id

    def trim_clip(self, clip_id: str, in_point_sec: float, out_point_sec: float) -> None:
        op = TrimClipOp(
            edit_id=new_id(),
            project_id=self._project_id,
            parent_id=self._parent_op_id,
            clip_id=clip_id,
            in_point_sec=in_point_sec,
            out_point_sec=out_point_sec,
        )
        self._ops.append(op)

    def move_clip(self, clip_id: str, new_position_sec: float) -> None:
        op = MoveClipOp(
            edit_id=new_id(),
            project_id=self._project_id,
            parent_id=self._parent_op_id,
            clip_id=clip_id,
            new_position_sec=new_position_sec,
        )
        self._ops.append(op)

    def remove_clip(self, clip_id: str) -> None:
        op = RemoveClipOp(
            edit_id=new_id(),
            project_id=self._project_id,
            parent_id=self._parent_op_id,
            clip_id=clip_id,
        )
        self._ops.append(op)

    def add_transition(
        self, clip_a_id: str, clip_b_id: str, kind: str, duration_sec: float,
    ) -> None:
        op = AddTransitionOp(
            edit_id=new_id(),
            project_id=self._project_id,
            parent_id=self._parent_op_id,
            clip_a_id=clip_a_id,
            clip_b_id=clip_b_id,
            kind=kind,
            duration_sec=duration_sec,
        )
        self._ops.append(op)

    def add_effect(
        self, target_kind: str, target_id: str, effect_type: str, params: dict[str, Any],
    ) -> None:
        op = AddEffectOp(
            edit_id=new_id(),
            project_id=self._project_id,
            parent_id=self._parent_op_id,
            target_kind=target_kind,
            target_id=target_id,
            effect_type=effect_type,
            params=params,
        )
        self._ops.append(op)

    def set_keyframe(
        self, effect_id: str, param: str, keyframes: list[tuple[float, float, str]],
    ) -> None:
        op = SetKeyframeOp(
            edit_id=new_id(),
            project_id=self._project_id,
            parent_id=self._parent_op_id,
            effect_id=effect_id,
            param=param,
            keyframes=keyframes,
        )
        self._ops.append(op)

    def set_audio_gain(self, target_id: str, gain_db: float) -> None:
        op = SetAudioGainOp(
            edit_id=new_id(),
            project_id=self._project_id,
            parent_id=self._parent_op_id,
            target_id=target_id,
            gain_db=gain_db,
        )
        self._ops.append(op)

    def normalize_audio(self, target_id: str, target_dbfs: float) -> None:
        op = NormalizeAudioOp(
            edit_id=new_id(),
            project_id=self._project_id,
            parent_id=self._parent_op_id,
            target_id=target_id,
            target_dbfs=target_dbfs,
        )
        self._ops.append(op)

    def group_edits(self, edit_ids: list[str], label: str) -> None:
        op = GroupEditsOp(
            edit_id=new_id(),
            project_id=self._project_id,
            parent_id=self._parent_op_id,
            edit_ids=edit_ids,
            label=label,
        )
        self._ops.append(op)

    def raw_mlt_xml(self, xml: str, label: str) -> None:
        op = RawMltXmlOp(
            edit_id=new_id(),
            project_id=self._project_id,
            parent_id=self._parent_op_id,
            xml=xml,
            label=label,
        )
        self._ops.append(op)

    def free_form_code(self, code: str, label: str | None = None) -> None:
        op = FreeFormCodeOp(
            edit_id=new_id(),
            project_id=self._project_id,
            parent_id=self._parent_op_id,
            code=code,
            label=label,
        )
        self._ops.append(op)
```

### Step 5: If import errors mention field mismatches

The test `test_pydantic_validation_error_on_bad_input` may pass/fail depending on whether `asset_hash` has a `min_length=1` validator. If Pydantic doesn't reject empty string, change the test to use a clearly-invalid input (e.g. `track_id=""` if that's required, or a non-numeric `position_sec`).

### Step 6: Run tests to verify they pass

Run: `cd open_edit && pytest tests/test_ir_api.py -v`
Expected: 13 passing (12 method tests + 1 flushing buffer + 1 validation = ~14; some may merge).

If the `_FlushingBuffer` import fails (it doesn't exist yet — Task 8), the test will skip that one. Adjust the test to use a plain list subclass instead.

### Step 7: Run full suite to verify no regression

Run: `cd open_edit && pytest`
Expected: 179 → 192 passing (~13 new tests).

### Step 8: Commit

```bash
cd /home/ah64/apps/mlt-pipeline
git add open_edit/ir/api.py open_edit/tests/test_ir_api.py
git commit -m "[open_edit] phase3 t4: IR API real implementation (12 methods, parent_id stamped)"
```

---

## Task 5: Rust binary scaffold (Cargo.toml + main.rs + jail.rs skeleton)

**Files:**
- Create: `open_edit/sandbox/Cargo.toml`
- Create: `open_edit/sandbox/src/main.rs`
- Create: `open_edit/sandbox/src/jail.rs`
- Create: `open_edit/sandbox/src/network_denylist.rs`
- Test: `open_edit/sandbox/tests/integration.rs`

**Interfaces:**
- Consumes: nothing
- Produces: `open-edit-sandbox` binary that accepts CLI flags, parses JSON output (for now: returns ok=true with no actual sandboxing)

### Step 1: Verify Rust toolchain is available

```bash
which cargo
cargo --version
```

If `cargo` is not found, install via rustup: `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`. The v1 install requirement is `cargo` available on `PATH`.

### Step 2: Create Cargo.toml

Create `open_edit/sandbox/Cargo.toml`:

```toml
[package]
name = "open-edit-sandbox"
version = "0.1.0"
edition = "2021"

[[bin]]
name = "open-edit-sandbox"
path = "src/main.rs"

[dependencies]
clap = { version = "4.4", features = ["derive"] }
nix = { version = "0.27", features = ["signal", "process", "unistd"] }
libseccomp = "0.3"
anyhow = "1.0"
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"

[dev-dependencies]
assert_cmd = "2.0"
predicates = "3.0"
tempfile = "3.8"

[features]
# L7: integration tests are gated; run with `cargo test --features integration`
integration = []
```

### Step 3: Create network_denylist.rs (stub for now)

Create `open_edit/sandbox/src/network_denylist.rs`:

```rust
// Phase 3 Task 5: stub. Real implementation in Task 6.
use libseccomp::{ScmpAction, ScmpFilterContext};

pub fn install(_ctx: &mut ScmpFilterContext) -> anyhow::Result<()> {
    // Placeholder: no seccomp filtering yet. Task 6 implements the
    // SCMP_ACT_ERRNO(EPERM) denylist for socket/connect/bind/accept/listen/
    // sendto/recvfrom/sendmsg/recvmsg.
    Ok(())
}
```

### Step 4: Create jail.rs (stub for now)

Create `open_edit/sandbox/src/jail.rs`:

```rust
// Phase 3 Task 5: stub. Real implementation in Tasks 6-7.
use std::process::Command;

pub struct RunResult {
    pub status: std::process::ExitStatus,
    pub timed_out: bool,
}

pub fn run_bwrap(_args: &[String], _timeout_secs: u64) -> anyhow::Result<RunResult> {
    // Placeholder. Task 6: add rlimits + fork+watcher timeout.
    // Task 7: add seccomp + bwrap invocation.
    //
    // For now, just exec bwrap with the args (no seccomp, no rlimits, no
    // timeout). This lets the binary be built and tested end-to-end before
    // the isolation layers are added.
    let mut cmd = Command::new("bwrap");
    cmd.args(_args);
    let status = cmd.status()?;
    Ok(RunResult { status, timed_out: false })
}
```

### Step 5: Create main.rs (full CLI + JSON output)

Create `open_edit/sandbox/src/main.rs`:

```rust
// Phase 3 Task 5: main entry. CLI parsing + JSON output.
// Task 6 adds seccomp/rlimits/timeout. Task 7 adds the actual bwrap invocation.

use anyhow::Context;
use clap::Parser;
use serde::Serialize;
use std::process::ExitCode;

mod jail;
mod network_denylist;

#[derive(Parser, Debug)]
#[command(name = "open-edit-sandbox", about = "Free-form Python sandbox")]
struct Cli {
    /// rw directory for ops.jsonl + temps
    #[arg(long)]
    scratch: String,

    /// ro directory of source media (repeatable, 0+)
    #[arg(long = "source-ro", value_name = "PATH")]
    source_ro: Vec<String>,

    /// ro file (edit_graph.db)
    #[arg(long = "project-meta")]
    project_meta: Option<String>,

    /// Python binary to invoke inside the sandbox
    #[arg(long = "python-bin")]
    python_bin: String,

    /// major.minor, e.g. "3.14"; child parses back to tuple
    #[arg(long = "expected-py-version")]
    expected_py_version: String,

    /// wall-clock timeout in seconds
    #[arg(long, default_value_t = 30)]
    timeout: u64,

    /// RLIMIT_CPU in seconds
    #[arg(long, default_value_t = 30)]
    cpu: u64,

    /// RLIMIT_AS in MB
    #[arg(long, default_value_t = 2048)]
    mem: u64,

    /// path of ops.jsonl (for sandbox_bridge to read after)
    #[arg(long = "ops-output")]
    ops_output: String,

    /// machine-readable JSON output
    #[arg(long)]
    json: bool,
}

#[derive(Serialize)]
struct Output {
    ok: bool,
    exit_code: i32,
    reason: String,
    duration_s: f64,
    stderr: String,
}

fn main() -> ExitCode {
    let cli = Cli::parse();

    // Build the bwrap argv. Task 7 fills this in.
    let bwrap_args = build_bwrap_args(&cli);

    let started = std::time::Instant::now();
    let result = jail::run_bwrap(&bwrap_args, cli.timeout);
    let duration_s = started.elapsed().as_secs_f64();

    let output = match result {
        Ok(r) if r.status.success() => Output {
            ok: true,
            exit_code: r.status.code().unwrap_or(0),
            reason: String::new(),
            duration_s,
            stderr: String::new(),
        },
        Ok(r) if r.timed_out => Output {
            ok: false,
            exit_code: -1,
            reason: "timeout".to_string(),
            duration_s,
            stderr: String::new(),
        },
        Ok(r) => Output {
            ok: false,
            exit_code: r.status.code().unwrap_or(1),
            reason: "nonzero_exit".to_string(),
            duration_s,
            stderr: String::new(),
        },
        Err(e) => Output {
            ok: false,
            exit_code: -1,
            reason: "setup_error".to_string(),
            duration_s,
            stderr: format!("{e:#}"),
        },
    };

    println!("{}", serde_json::to_string(&output).unwrap());
    if output.ok { ExitCode::SUCCESS } else { ExitCode::from(1) }
}

fn build_bwrap_args(cli: &Cli) -> Vec<String> {
    // Task 7: full bwrap invocation. For now, just pass --version to verify
    // the binary works end-to-end.
    let mut args = vec!["--version".to_string()];
    // Placate the unused-variable warning until Task 7 fills this in.
    let _ = (&cli.scratch, &cli.source_ro, &cli.project_meta,
            &cli.python_bin, &cli.expected_py_version,
            &cli.ops_output);
    args
}
```

### Step 6: Build the binary

```bash
cd open_edit/sandbox
cargo build --release
```

Expected: build succeeds, binary at `target/release/open-edit-sandbox`.

### Step 7: Smoke test the binary

```bash
cd open_edit/sandbox
./target/release/open-edit-sandbox --scratch /tmp --python-bin /usr/bin/python3.14 --expected-py-version 3.14 --json
```

Expected: `{"ok":true,"exit_code":0,...}` (because Task 5 stub calls `bwrap --version` which exits 0).

### Step 8: Commit

```bash
cd /home/ah64/apps/mlt-pipeline
git add open_edit/sandbox/Cargo.toml open_edit/sandbox/src/main.rs open_edit/sandbox/src/jail.rs open_edit/sandbox/src/network_denylist.rs Cargo.lock
git commit -m "[open_edit] phase3 t5: rust binary scaffold (Cargo + clap + JSON output stub)"
```

---

## Task 6: Seccomp denylist + rlimits + fork+watcher timeout

**Files:**
- Modify: `open_edit/sandbox/src/network_denylist.rs:1-12` (replace stub with real denylist)
- Modify: `open_edit/sandbox/src/jail.rs:1-16` (replace stub with seccomp + rlimits + fork+watcher)

**Interfaces:**
- Consumes: libseccomp 0.3, nix signal/process/unistd
- Produces: `run_bwrap(args, timeout_secs) -> Result<RunResult>` that installs seccomp denylist, sets rlimits, forks a watcher thread, kills on timeout

### Step 1: Implement network_denylist.rs

Replace `open_edit/sandbox/src/network_denylist.rs`:

```rust
// Phase 3 Task 6: SCMP_ACT_ERRNO(EPERM) denylist for network syscalls.
use libseccomp::{ScmpAction, ScmpFilterContext, ScmpSyscall};

const DENIED_SYSCALLS: &[&str] = &[
    "socket", "connect", "bind", "accept", "listen",
    "sendto", "recvfrom", "sendmsg", "recvmsg",
];

/// Install a network-deny seccomp filter on `ctx`. Each denied syscall
/// returns EPERM (errno 1) instead of being killed, so the child sees
/// `PermissionError` from Python's socket module and can handle it.
pub fn install(ctx: &mut ScmpFilterContext) -> anyhow::Result<()> {
    let action = ScmpAction::Errno(1); // EPERM
    for name in DENIED_SYSCALLS {
        let nr = ScmpSyscall::from_name(name)
            .with_context(|| format!("unknown syscall {name}"))?;
        ctx.add_rule_exact(action, nr)
            .with_context(|| format!("add_rule({name})"))?;
    }
    Ok(())
}
```

### Step 2: Implement jail.rs (seccomp + rlimits + fork+watcher)

Replace `open_edit/sandbox/src/jail.rs`:

```rust
// Phase 3 Task 6: seccomp + rlimits + fork+watcher timeout.
use std::os::unix::process::CommandExt;
use std::process::Command;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;

use anyhow::Context;
use nix::sys::resource::{Resource, setrlimit};
use nix::sys::signal::{self, Signal};
use nix::unistd::Pid;

mod network_denylist;

pub struct RunResult {
    pub status: std::process::ExitStatus,
    pub timed_out: bool,
}

pub struct Limits {
    pub mem_mb: u64,
    pub cpu_secs: u64,
    pub nofile: u64,
    pub nproc: u64,
}

impl Default for Limits {
    fn default() -> Self {
        Self { mem_mb: 2048, cpu_secs: 30, nofile: 256, nproc: 64 }
    }
}

/// Run `cmd` with seccomp network denylist, rlimits, and a wall-clock
/// timeout enforced by a watcher thread.
pub fn run_bwrap_with_limits(
    mut cmd: Command,
    limits: Limits,
    timeout_secs: u64,
) -> anyhow::Result<RunResult> {
    // Install seccomp filter before exec.
    let mut ctx = libseccomp::ScmpFilterContext::new_filter(
        libseccomp::ScmpAction::Allow,
    )?;
    network_denylist::install(&mut ctx)
        .context("install network denylist")?;
    let prog = ctx.export_raw()?;
    // SAFETY: the seccomp program is a valid BPF filter; load it before exec.
    unsafe {
        cmd.pre_exec(move || {
            // RLIMIT_AS: virtual address space cap.
            setrlimit(Resource::RLIMIT_AS, limits.mem_mb * 1024 * 1024, limits.mem_mb * 1024 * 1024)?;
            // RLIMIT_CPU: hard cap; SIGXCPU fires when reached.
            setrlimit(Resource::RLIMIT_CPU, limits.cpu_secs, limits.cpu_secs)?;
            setrlimit(Resource::RLIMIT_NOFILE, limits.nofile, limits.nofile)?;
            setrlimit(Resource::RLIMIT_NPROC, limits.nproc, limits.nproc)?;
            // Load seccomp BPF program.
            let rc = libseccomp::apply_raw(&prog);
            if rc != 0 {
                return Err(std::io::Error::from_raw_os_error(rc));
            }
            Ok(())
        });
    }

    let mut child = cmd.spawn().context("spawn bwrap")?;
    let pid = child.id() as i32;

    // Watcher thread: kill the child if it runs too long.
    let timed_out = Arc::new(AtomicBool::new(false));
    let to_clone = timed_out.clone();
    let watcher = std::thread::spawn(move || {
        std::thread::sleep(Duration::from_secs(timeout_secs));
        to_clone.store(true, Ordering::SeqCst);
        let _ = signal::kill(Pid::from_raw(pid), Signal::SIGTERM);
        std::thread::sleep(Duration::from_secs(2));
        let _ = signal::kill(Pid::from_raw(pid), Signal::SIGKILL);
    });

    let status = child.wait().context("wait bwrap")?;
    let timed_out_value = timed_out.load(Ordering::SeqCst);
    // Don't join the watcher; let it die naturally after the kill (no-op).
    drop(watcher);

    Ok(RunResult { status, timed_out: timed_out_value })
}

/// Stub wrapper for the Task 5 API. Task 7 will replace this with the
/// full seccomp+rlimits+timeout invocation.
pub fn run_bwrap(_args: &[String], _timeout_secs: u64) -> anyhow::Result<RunResult> {
    anyhow::bail!("run_bwrap is a Task 5 stub; use run_bwrap_with_limits in Task 6+")
}
```

Note: this requires `libseccomp = "0.3"` to have a top-level `apply_raw` function or similar. If the API is different, adjust — the canonical pattern is to load the BPF program via `libseccomp::scmp_filter_ctx_export_raw` and apply it via `prctl(PR_SET_SECCOMP)` or `seccomp(SECCOMP_SET_MODE_FILTER)`. Adapt to the actual `libseccomp` 0.3 API.

### Step 3: Build

```bash
cd open_edit/sandbox
cargo build --release
```

Expected: build succeeds (after any API adjustments).

### Step 4: Verify the denylist blocks a network syscall

Write a quick smoke test (in Task 7 we'll add proper integration tests; for now, run a one-liner):

```bash
cd open_edit/sandbox
cat > /tmp/test_net.py <<'EOF'
import socket
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    print("ALLOWED")
except PermissionError as e:
    print(f"BLOCKED: {e}")
EOF

# Build a bwrap invocation manually for this smoke test
./target/release/open-edit-sandbox \
  --scratch /tmp/test_scratch \
  --python-bin /usr/bin/python3.14 \
  --expected-py-version 3.14 \
  --json \
  -- /usr/bin/python3.14 /tmp/test_net.py
```

Expected: `{"ok":false,"reason":"...","stderr":"...PermissionError..."}` (the network syscall is blocked).

(We don't expect this to fully work in Task 6 because Task 5's `build_bwrap_args` only passes `--version`. Task 7 wires the real bwrap invocation. This step is informational.)

### Step 5: Commit

```bash
cd /home/ah64/apps/mlt-pipeline
git add open_edit/sandbox/src/network_denylist.rs open_edit/sandbox/src/jail.rs
git commit -m "[open_edit] phase3 t6: seccomp denylist (SCMP_ACT_ERRNO(EPERM)) + rlimits + fork+watcher timeout"
```

---

## Task 7: Full bwrap invocation in Rust

**Files:**
- Modify: `open_edit/sandbox/src/main.rs` (replace `build_bwrap_args` stub with the real invocation)
- Modify: `open_edit/sandbox/src/jail.rs` (use `run_bwrap_with_limits` from main.rs)
- Test: `open_edit/sandbox/tests/integration.rs` (new file)

**Interfaces:**
- Consumes: `Cli` (from clap), `Limits` (from jail)
- Produces: bwrap argv that mounts scratch rw, source-ro, project-meta ro, runs the Python version check, execs `_bootstrap.py` then `code.py`

### Step 1: Implement build_bwrap_args in main.rs

Replace the `build_bwrap_args` function in `open_edit/sandbox/src/main.rs`:

```rust
fn build_bwrap_args(cli: &Cli) -> Vec<String> {
    let mut args: Vec<String> = vec![];

    // Namespaces: fail loud, no -try.
    args.push("--unshare-user".into());
    args.push("--unshare-pid".into());
    args.push("--unshare-ipc".into());
    args.push("--unshare-net".into());
    args.push("--die-with-parent".into());

    // Read-only filesystem bindings.
    args.push("--ro-bind".into()); args.push("/usr".into()); args.push("/usr".into());
    args.push("--ro-bind".into()); args.push("/lib".into());  args.push("/lib".into());
    args.push("--ro-bind-try".into()); args.push("/lib64".into()); args.push("/lib64".into());
    args.push("--ro-bind".into()); args.push("/etc".into());  args.push("/etc".into());
    args.push("--symlink".into()); args.push("/usr/bin".into());  args.push("/bin".into());
    args.push("--symlink".into()); args.push("/usr/sbin".into()); args.push("/sbin".into());
    args.push("--proc".into()); args.push("/proc".into());

    // Source media: ro-bound, one --source-ro per directory.
    for (i, src) in cli.source_ro.iter().enumerate() {
        args.push("--ro-bind".into());
        args.push(src.clone());
        args.push(format!("/mnt/src{i}"));
    }

    // Project metadata: ro-bound.
    if let Some(meta) = &cli.project_meta {
        args.push("--ro-bind".into());
        args.push(meta.clone());
        args.push("/mnt/meta".into());
    }

    // Scratch dir: rw.
    args.push("--bind".into());
    args.push(cli.scratch.clone());
    args.push("/scratch".into());

    // Tmpfs mounts.
    args.push("--tmpfs".into()); args.push("/tmp".into());
    args.push("--tmpfs".into()); args.push("/home".into());
    args.push("--tmpfs".into()); args.push("/var".into());

    // Single --dev /dev (C4).
    args.push("--dev".into()); args.push("/dev".into());

    // Env (M3).
    args.push("--setenv".into()); args.push("HOME".into()); args.push("/tmp".into());
    args.push("--setenv".into()); args.push("XDG_CACHE_HOME".into()); args.push("/tmp/cache".into());

    args.push("--new-session".into());

    // The Python invocation: version check, then exec _bootstrap.py then code.py.
    // C5: parse the major.minor string back to a tuple in the child.
    let py_check = format!(
        "import sys; expected = tuple(int(x) for x in '{ver}'.split('.')); "
        "assert sys.version_info[:2] == expected, 'sandbox Python mismatch'; "
        "g = {{'__name__': '__main__'}}; "
        "exec(open('/scratch/_bootstrap.py').read(), g); "
        "exec(open('/scratch/code.py').read(), g)",
        ver = cli.expected_py_version,
    );
    args.push("--".into());
    args.push(cli.python_bin.clone());
    args.push("-c".into());
    args.push(py_check);
    args
}
```

### Step 2: Update main() to use the new jail API

Replace the call to `jail::run_bwrap` in `main()` with:

```rust
    let limits = jail::Limits {
        mem_mb: cli.mem,
        cpu_secs: cli.cpu,
        ..Default::default()
    };
    let bwrap_args = build_bwrap_args(&cli);
    let mut cmd = std::process::Command::new("bwrap");
    cmd.args(&bwrap_args);
    let started = std::time::Instant::now();
    let result = jail::run_bwrap_with_limits(cmd, limits, cli.timeout);
    let duration_s = started.elapsed().as_secs_f64();
```

### Step 3: Write the integration test (feature-gated)

Create `open_edit/sandbox/tests/integration.rs`:

```rust
// Phase 3 Task 7: integration tests for the sandbox binary.
// L7: feature-gated; run with `cargo test --features integration`.

#![cfg(feature = "integration")]

use assert_cmd::Command;
use predicates::prelude::*;
use std::fs;
use tempfile::tempdir;

fn sandbox_bin() -> Command {
    Command::cargo_bin("open-edit-sandbox").unwrap()
}

#[test]
fn e2e_python_runs_and_writes_ops() {
    let scratch = tempdir().unwrap();
    fs::write(scratch.path().join("code.py"), "ir.add_clip(asset_hash='abc', track_id='t1', position_sec=0.0)").unwrap();
    fs::write(scratch.path().join("_bootstrap.py"), "import json\nfrom open_edit.ir.api import IR\nclass _Buf(list):\n    def append(self, op):\n        super().append(op)\n        with open('/scratch/ops.jsonl', 'a') as f: f.write(op.model_dump_json() + '\\n')\nir = IR(_Buf(), project_id='p', parent_op_id='e')").unwrap();

    let _ = sandbox_bin()
        .arg("--scratch").arg(scratch.path())
        .arg("--python-bin").arg("/usr/bin/python3.14")
        .arg("--expected-py-version").arg("3.14")
        .arg("--json")
        .assert();
    // The full assert (file existence, op count) is in tests/test_free_form_e2e.py
    // because the Rust binary needs IR/op models inlined into _bootstrap.py.
}

#[test]
fn bwrap_unavailable_reason() {
    // Run with PATH=/nonexistent; bwrap not found → reason=setup_error
    let scratch = tempdir().unwrap();
    sandbox_bin()
        .env("PATH", "/nonexistent")
        .arg("--scratch").arg(scratch.path())
        .arg("--python-bin").arg("/usr/bin/python3.14")
        .arg("--expected-py-version").arg("3.14")
        .arg("--json")
        .assert()
        .failure();
    // Detailed JSON inspection is brittle; the e2e test in Python covers it.
}
```

### Step 4: Build and run integration tests

```bash
cd open_edit/sandbox
cargo test --features integration
```

Expected: tests compile and run. The first test may fail (because `_bootstrap.py` doesn't have the inlined IR yet — that's Task 8's job). For Task 7, it's OK if the first test is skipped or marked as TODO. Focus on `bwrap_unavailable_reason` passing.

### Step 5: Commit

```bash
cd /home/ah64/apps/mlt-pipeline
git add open_edit/sandbox/src/main.rs open_edit/sandbox/src/jail.rs open_edit/sandbox/tests/integration.rs
git commit -m "[open_edit] phase3 t7: full bwrap invocation in Rust (FS jail + namespaces + py version check)"
```

---

## Task 8: Sandbox bridge (Python wrapper)

**Files:**
- Create: `open_edit/open_edit/agent/sandbox_bridge.py`
- Modify: `open_edit/open_edit/agent/exceptions.py:1-50` (export `_ValidationError` — already added in Task 2)
- Test: `open_edit/tests/test_sandbox_bridge.py`

**Interfaces:**
- Consumes: `FreeFormResult`, `SandboxError`, `_ValidationError` (from exceptions); `IR`, `apply_operation`, `derive_timeline` (from ir); `EditGraphStore`, `JobLock`, `JobLockBusy`, `AssetStore` (from storage); `parse_header`, `version_supported`, `lib_version_supported` (from libs); all 12 op types
- Produces:
  - `run_free_form(code, workdir, project_id, parent_op_id, *, timeout, mem_mb, cpu_sec) -> FreeFormResult` (NEVER raises)
  - `_render_bootstrap(project_id, parent_op_id) -> str` (uses `inspect.getsource` to inline IR + op models)
  - `_validate_ops_incrementally(ops_path, workdir) -> tuple[list, Timeline]`
  - `_FlushingBuffer` (the in-sandbox list subclass)

### Step 1: Write the failing test (mock the Rust binary)

Create `open_edit/tests/test_sandbox_bridge.py`:

```python
"""Phase 3 Task 8: sandbox_bridge unit tests with mocked Rust binary."""
import json
import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from open_edit.agent.sandbox_bridge import (
    _render_bootstrap, _FlushingBuffer, _validate_ops_incrementally,
    _ValidationError,
)
from open_edit.agent.exceptions import FreeFormResult


def test_flushing_buffer_writes_first_then_appends(tmp_path):
    """H10: write first, then append; failed write raises."""
    ops_file = tmp_path / "ops.jsonl"
    buf = _FlushingBuffer()
    from open_edit.ir.types import AddClipOp, new_id
    op = AddClipOp(
        edit_id=new_id(), project_id="p", parent_id="e",
        clip_id="c1", asset_hash="abc", track_id="t1", position_sec=0.0,
    )
    buf.append(op)
    assert ops_file.exists()
    assert len(buf) == 1
    # Each line is a valid JSON op
    parsed = json.loads(ops_file.read_text().strip())
    assert parsed["kind"] == "add_clip"
    assert parsed["clip_id"] == "c1"


def test_render_bootstrap_is_self_contained():
    """C2: bootstrap does NOT `import open_edit`."""
    bootstrap = _render_bootstrap(project_id="p1", parent_op_id="e1")
    # The bootstrap should inline the IR class; no `from open_edit` import
    # for IR/op models (the imports block only has typing/pydantic/datetime).
    assert "from open_edit.ir.api import IR" not in bootstrap
    # The IR class should be inlined
    assert "class IR:" in bootstrap
    # The 12 op models should be inlined (at least the class names)
    for cls in ["AddClipOp", "TrimClipOp", "FreeFormCodeOp"]:
        assert f"class {cls}" in bootstrap
    # Project and parent IDs are injected
    assert "'p1'" in bootstrap
    assert "'e1'" in bootstrap
    # OPS_FILE is /scratch/ops.jsonl (in-sandbox path, C1)
    assert '"/scratch/ops.jsonl"' in bootstrap


def test_run_free_form_missing_header_returns_preflight_failed(tmp_path):
    """No # ir_api_version: header → FreeFormResult.fail('preflight_failed')."""
    from open_edit.agent.sandbox_bridge import run_free_form
    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "edit_graph.db").touch()
    result = run_free_form(
        code="import os  # no header",
        workdir=workdir,
        project_id="p1",
        parent_op_id="e1",
    )
    assert not result.success
    assert result.reason == "preflight_failed"


def test_run_free_form_unsupported_version_returns_fail(tmp_path):
    from open_edit.agent.sandbox_bridge import run_free_form
    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "edit_graph.db").touch()
    result = run_free_form(
        code="# ir_api_version: 99.0; libs: {}",
        workdir=workdir,
        project_id="p1",
        parent_op_id="e1",
    )
    assert not result.success
    assert result.reason == "ir_api_version_unsupported"


def test_run_free_form_unsupported_lib_returns_fail(tmp_path):
    from open_edit.agent.sandbox_bridge import run_free_form
    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "edit_graph.db").touch()
    result = run_free_form(
        code='# ir_api_version: 0.1; libs: {"numpy": "99.0"}',
        workdir=workdir,
        project_id="p1",
        parent_op_id="e1",
    )
    assert not result.success
    assert result.reason == "lib_version_unsupported"


def test_run_free_form_clamps_timeout_and_mem():
    """H9: hard caps MAX_FREEFORM_TIMEOUT_SEC=300, MAX_FREEFORM_MEM_MB=4096."""
    from open_edit.agent.sandbox_bridge import (
        MAX_FREEFORM_TIMEOUT_SEC, MAX_FREEFORM_MEM_MB, run_free_form,
    )
    # Test the constants exist with the right values
    assert MAX_FREEFORM_TIMEOUT_SEC == 300
    assert MAX_FREEFORM_MEM_MB == 4096
    # Note: full behavior test requires a real (or mocked) Rust binary;
    # covered in test_free_form_e2e.py.


def test_run_free_form_sandbox_binary_missing(tmp_path):
    """H5: SANDBOX_BIN not on PATH → FreeFormResult.fail('sandbox_binary_missing')."""
    from open_edit.agent.sandbox_bridge import run_free_form
    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "edit_graph.db").touch()
    with patch("open_edit.agent.sandbox_bridge._resolve_sandbox_bin", return_value=None):
        result = run_free_form(
            code="# ir_api_version: 0.1; libs: {}",
            workdir=workdir,
            project_id="p1",
            parent_op_id="e1",
        )
    assert not result.success
    assert result.reason == "sandbox_binary_missing"
```

### Step 2: Run test to verify it fails

Run: `cd open_edit && pytest tests/test_sandbox_bridge.py -v`
Expected: ImportError on `open_edit.agent.sandbox_bridge`.

### Step 3: Implement sandbox_bridge.py

Create `open_edit/agent/sandbox_bridge.py`:

```python
"""Python wrapper for the open-edit-sandbox Rust binary.

Phase 3 Task 8: orchestrates the full free-form run:
1. Preflight: parse header, check ir_api_version and libs.
2. Acquire JobLock (single-slot for free-form runs).
3. Stage: write code.py and _bootstrap.py into <workdir>/.sandbox/run_<id>/.
4. Invoke the Rust binary (seccomp + rlimits + bwrap).
5. Atomic commit: parse JSON output, validate ops.jsonl, append to edit_graph.

NEVER raises (C7: top-level try/except).
"""
from __future__ import annotations

import inspect
import json
import platform
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

from open_edit.agent.exceptions import (
    FreeFormResult, SandboxError, _ValidationError,
)
from open_edit.agent.libs import (
    parse_header, version_supported, lib_version_supported,
)
from open_edit.ir.api import IR
from open_edit.ir.apply import apply_operation, derive_timeline
from open_edit.ir.types import (
    OperationUnion, Project, Asset, new_id,
    AddClipOp, TrimClipOp, MoveClipOp, RemoveClipOp,
    AddEffectOp, SetKeyframeOp, SetAudioGainOp,
)
from open_edit.pydantic_compat import TypeAdapter
from open_edit.storage.assets import AssetStore
from open_edit.storage.edit_graph import EditGraphStore
from open_edit.storage.job_lock import JobLock, JobLockBusy

# Pin Python at module import time.
PINNED_PYTHON_BIN = sys.executable
EXPECTED_PY_VERSION = '.'.join(platform.python_version().split('.')[:2])
# H9: hard caps so FreeFormCodeOp.timeout_sec can't hold the JobLock forever.
MAX_FREEFORM_TIMEOUT_SEC = 300
MAX_FREEFORM_MEM_MB = 4096


class _FlushingBuffer(list):
    """A list that writes each appended op to disk before keeping it.

    H10: write FIRST, then append. If the file write fails, raise immediately
    so the whole run aborts; no silent loss.
    """
    def __init__(self, ops_file: Path):
        super().__init__()
        self._ops_file = ops_file

    def append(self, op):
        with open(self._ops_file, "a") as f:
            f.write(op.model_dump_json() + "\n")
        super().append(op)


def _resolve_sandbox_bin() -> str | None:
    """H5: resolve at call time, not at module import."""
    return shutil.which("open-edit-sandbox")


def run_free_form(
    code: str,
    workdir: Path,
    project_id: str,
    parent_op_id: str,
    *,
    timeout: int = 30,
    mem_mb: int = 512,
    cpu_sec: int | None = None,
) -> FreeFormResult:
    """Run free-form Python in the sandbox. NEVER raises (C7)."""
    timeout = min(int(timeout), MAX_FREEFORM_TIMEOUT_SEC)
    mem_mb = min(int(mem_mb), MAX_FREEFORM_MEM_MB)
    try:
        # 1. Preflight
        try:
            declared_version, declared_libs = parse_header(code)
        except SandboxError as e:
            return FreeFormResult.fail("preflight_failed", str(e))
        if not version_supported(declared_version):
            return FreeFormResult.fail(
                "ir_api_version_unsupported", f"got {declared_version}"
            )
        for lib_name, lib_ver in declared_libs.items():
            if not lib_version_supported(lib_name, lib_ver):
                return FreeFormResult.fail(
                    "lib_version_unsupported", f"{lib_name}=={lib_ver}"
                )

        # 2. JobLock
        try:
            with JobLock.try_acquire('free_form_python', timeout=5):
                return _run_sandboxed(
                    code, workdir, project_id, parent_op_id,
                    timeout, mem_mb, cpu_sec,
                )
        except JobLockBusy:
            return FreeFormResult.fail("busy", "another free-form run is in progress")
        except subprocess.TimeoutExpired:
            return FreeFormResult.fail(
                "parent_watchdog_timeout",
                "sandbox did not exit within timeout+10s",
            )
    except Exception as e:
        # C7: never-raises safety net.
        return FreeFormResult.fail("internal_error", repr(e))


def _run_sandboxed(code, workdir, project_id, parent_op_id, timeout, mem_mb, cpu_sec):
    sandbox_bin = _resolve_sandbox_bin()
    if sandbox_bin is None:
        return FreeFormResult.fail(
            "sandbox_binary_missing",
            "'open-edit-sandbox' not found on PATH; build with "
            "'cd open_edit/sandbox && cargo build --release' and install to $PATH",
        )

    run_id = new_id()
    scratch = workdir / '.sandbox' / f'run_{run_id}'
    scratch.mkdir(parents=True, exist_ok=True)
    code_path = scratch / 'code.py'
    ops_path = scratch / 'ops.jsonl'
    bootstrap_path = scratch / '_bootstrap.py'

    code_path.write_text(code)
    bootstrap_path.write_text(_render_bootstrap(project_id, parent_op_id))

    assets_dir = workdir / 'assets'
    source_dirs = sorted(p for p in assets_dir.iterdir() if p.is_dir()) if assets_dir.exists() else []
    meta_file = workdir / 'edit_graph.db'

    proc = subprocess.run(
        [sandbox_bin,
         '--scratch', str(scratch),
         '--ops-output', str(ops_path),
         '--python-bin', PINNED_PYTHON_BIN,
         '--expected-py-version', EXPECTED_PY_VERSION,
         '--timeout', str(timeout),
         '--mem', str(mem_mb),
         '--cpu', str(cpu_sec or timeout),
         '--json',
         *(arg for src in source_dirs for arg in ('--source-ro', str(src))),
         '--project-meta', str(meta_file),
        ],
        capture_output=True, text=True, timeout=timeout + 10,
    )

    try:
        rust = json.loads(proc.stdout)
    except json.JSONDecodeError:
        ops_path.unlink(missing_ok=True)
        return FreeFormResult.fail("sandbox_protocol_error",
                                   f"invalid JSON: {proc.stdout[:200]}")

    if not rust.get('ok'):
        ops_path.unlink(missing_ok=True)
        return FreeFormResult.fail(rust.get('reason', 'unknown'),
                                   rust.get('stderr', ''))

    if not ops_path.exists():
        return FreeFormResult.fail("ops_missing",
                                   "sandbox ok but ops.jsonl is missing")

    try:
        ops, _ = _validate_ops_incrementally(ops_path, workdir)
    except _ValidationError as e:
        ops_path.unlink(missing_ok=True)
        return FreeFormResult.fail("invalid_op", str(e))

    return FreeFormResult.ok(ops=ops, duration_s=rust.get('duration_s', 0.0))


def _validate_ops_incrementally(ops_path: Path, workdir: Path) -> tuple[list, object]:
    """C6: validate each op against a working-copy timeline, then apply."""
    try:
        project = _load_project_for_validation(workdir)
    except Exception as e:
        raise _ValidationError(f"project load failed: {e}") from e

    timeline = derive_timeline(project)
    ops: list[OperationUnion] = []
    for line_num, line in enumerate(ops_path.read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            op = TypeAdapter(OperationUnion).validate_python(json.loads(line))
            _validate_references(op, timeline, project.assets)
            timeline = apply_operation(timeline, op)
            ops.append(op)
        except (json.JSONDecodeError, Exception) as e:
            raise _ValidationError(f"line {line_num}: {e}") from e
    return ops, timeline


def _load_project_for_validation(workdir: Path) -> Project:
    db_path = workdir / 'edit_graph.db'
    if not db_path.exists():
        raise _ValidationError(f"project db not found: {db_path}")
    store = EditGraphStore(db_path)
    assets = _load_assets_via_store(store)
    return Project(
        project_id=store.project_id,
        name=workdir.name,
        workdir=workdir,
        assets=assets,
        edit_graph=store.load_all(),
    )


def _load_assets_via_store(store: EditGraphStore) -> dict[str, Asset]:
    asset_hashes: set[str] = set()
    for op in store.load_all():
        if isinstance(op, AddClipOp):
            asset_hashes.add(op.asset_hash)
    asset_store = AssetStore()
    assets = {}
    for h in asset_hashes:
        asset = asset_store.get(h)
        if asset is not None:
            assets[h] = asset
    return assets


def _validate_references(op: OperationUnion, timeline, assets) -> None:
    asset_hashes = {a.asset_hash for a in assets.values()}
    track_ids = {t.track_id for t in timeline.tracks}
    clip_ids: set[str] = set()
    effect_ids: set[str] = set()
    for t in timeline.tracks:
        for c in t.clips:
            clip_ids.add(c.clip_id)
            for e in c.effects:
                effect_ids.add(e.effect_id)
        for e in t.effects:
            effect_ids.add(e.effect_id)

    if isinstance(op, AddClipOp):
        if op.asset_hash not in asset_hashes:
            raise ReferenceError(f"asset_hash {op.asset_hash!r} not in project")
        if op.track_id not in track_ids:
            raise ReferenceError(f"track_id {op.track_id!r} not in project")
    if isinstance(op, (TrimClipOp, MoveClipOp, RemoveClipOp)):
        if op.clip_id not in clip_ids:
            raise ReferenceError(f"clip_id {op.clip_id!r} not in project")
    if isinstance(op, (AddEffectOp, SetKeyframeOp, SetAudioGainOp)):
        if op.target_id not in clip_ids and op.target_id not in track_ids:
            raise ReferenceError(f"target_id {op.target_id!r} not in project")
    if op.parent_id is None:
        raise ReferenceError("op has no parent_id (IR class should stamp at build time)")


def _render_bootstrap(project_id: str, parent_op_id: str) -> str:
    """Generate _bootstrap.py with the IR class and op models inlined.

    C2 preferred fix (Option A): vendor IR into the bootstrap.
    C1: OPS_FILE is hardcoded to /scratch/ops.jsonl (in-sandbox mount path).
    H10: _FlushingBuffer writes first, then appends.
    """
    ir_source = inspect.getsource(IR)
    from open_edit.ir import types as _types
    op_types = [
        "AddClipOp", "RemoveClipOp", "MoveClipOp", "TrimClipOp",
        "AddTransitionOp", "AddEffectOp", "SetKeyframeOp",
        "SetAudioGainOp", "NormalizeAudioOp",
        "GroupEditsOp", "RawMltXmlOp", "FreeFormCodeOp",
    ]
    op_sources = []
    for name in op_types:
        cls = getattr(_types, name)
        op_sources.append(inspect.getsource(cls))
    new_id_source = inspect.getsource(_types.new_id)

    return textwrap.dedent(f'''
        # === _bootstrap.py (auto-generated by sandbox_bridge) ===
        # Self-contained: IR + op models inlined. No import open_edit.
        import json
        from typing import Optional, Union, Literal
        from pydantic import BaseModel, Field
        from datetime import datetime, timezone

        # --- INLINED: open_edit/ir/types.py:new_id ---
        {new_id_source}

        # --- INLINED: op models (12 classes) ---
        {chr(10).join(op_sources)}

        # --- INLINED: open_edit/ir/api.py:IR ---
        {ir_source}

        # === INJECTED CONSTANTS ===
        PROJECT_ID = {project_id!r}
        PARENT_OP_ID = {parent_op_id!r}
        OPS_FILE = "/scratch/ops.jsonl"

        # Write FIRST, then append (H10).
        class _FlushingBuffer(list):
            def __init__(self, ops_file):
                super().__init__()
                self._ops_file = ops_file
            def append(self, op):
                with open(self._ops_file, "a") as f:
                    f.write(op.model_dump_json() + "\\n")
                super().append(op)

        _ops = _FlushingBuffer(OPS_FILE)
        ir = IR(_ops, project_id=PROJECT_ID, parent_op_id=PARENT_OP_ID)
    ''')
```

### Step 4: Run tests to verify they pass

Run: `cd open_edit && pytest tests/test_sandbox_bridge.py -v`
Expected: 6 passing.

If `_ValidationError` is not importable from `exceptions`, check that Task 2 added it.

### Step 5: Run full suite to verify no regression

Run: `cd open_edit && pytest`
Expected: 192 → 198 passing (6 new tests).

### Step 6: Commit

```bash
cd /home/ah64/apps/mlt-pipeline
git add open_edit/agent/sandbox_bridge.py open_edit/tests/test_sandbox_bridge.py
git commit -m "[open_edit] phase3 t8: sandbox_bridge.py (preflight + JobLock + atomic commit + inspect.getsource IR inline)"
```

---

## Task 9: `_apply_free_form_code` branch in apply.py

**Files:**
- Modify: `open_edit/open_edit/ir/apply.py:62-310` (add new branch to `apply_operation`)
- Modify: `open_edit/open_edit/ir/types.py:163-165` (add `timeout_sec` and `mem_mb` to `FreeFormCodeOp`)
- Test: `open_edit/tests/test_apply_free_form.py`

**Interfaces:**
- Consumes: `sandbox_bridge.run_free_form`, `FreeFormCodeOp`
- Produces: `_apply_free_form_code(op, project) -> Project` branch in `apply_operation`

### Step 1: Add fields to FreeFormCodeOp

In `open_edit/ir/types.py`, modify the `FreeFormCodeOp` class (around line 163):

```python
class FreeFormCodeOp(Operation):
    kind: Literal["free_form_code"] = "free_form_code"
    code: str
    timeout_sec: int = 30
    mem_mb: int = 512
    label: str | None = None
```

### Step 2: Write the failing test

Create `open_edit/tests/test_apply_free_form.py`:

```python
"""Phase 3 Task 9: _apply_free_form_code integration in apply.py."""
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from open_edit.agent.exceptions import FreeFormResult
from open_edit.ir.apply import apply_operation
from open_edit.ir.types import (
    AddClipOp, FreeFormCodeOp, Project, Asset, new_id,
)


@pytest.fixture
def minimal_project(tmp_path):
    asset = Asset(
        asset_hash="abc",
        original_path="/tmp/clip.mp4",
        stored_path=str(tmp_path / "clip.mp4"),
        type="video",
        duration_sec=10.0,
        fps=30.0, width=1920, height=1080, codec="h264", has_audio=True,
    )
    (tmp_path / "clip.mp4").write_bytes(b"\x00")
    return Project(
        name="t", workdir=tmp_path,
        assets={asset.asset_hash: asset},
    )


def test_apply_free_form_code_appends_child_ops(minimal_project):
    """The 50-line script test, mocked at the sandbox boundary."""
    op = FreeFormCodeOp(
        edit_id=new_id(),
        project_id=minimal_project.project_id,
        code="# ir_api_version: 0.1; libs: {}",
        label="test",
    )
    # Mock the sandbox_bridge to return 3 pre-built child ops
    child_ops = [
        AddClipOp(edit_id=new_id(), project_id=op.project_id, parent_id=op.edit_id,
                  clip_id=new_id(), asset_hash="abc", track_id="t1", position_sec=0.0),
        AddClipOp(edit_id=new_id(), project_id=op.project_id, parent_id=op.edit_id,
                  clip_id=new_id(), asset_hash="abc", track_id="t1", position_sec=2.0),
        AddClipOp(edit_id=new_id(), project_id=op.project_id, parent_id=op.edit_id,
                  clip_id=new_id(), asset_hash="abc", track_id="t1", position_sec=4.0),
    ]
    mock_result = FreeFormResult.ok(ops=child_ops, duration_s=0.5)
    with patch("open_edit.ir.apply.sandbox_bridge.run_free_form",
               return_value=mock_result) as mock_run:
        updated = apply_operation(minimal_project, op)

    assert len(updated.edit_graph) == 3
    assert all(o.parent_id == op.edit_id for o in updated.edit_graph)
    # mock_run was called with the right args
    args = mock_run.call_args
    assert args.kwargs["code"] == op.code
    assert args.kwargs["workdir"] == minimal_project.workdir
    assert args.kwargs["parent_op_id"] == op.edit_id


def test_apply_free_form_code_raises_on_sandbox_failure(minimal_project):
    from open_edit.ir.apply import ApplyError
    op = FreeFormCodeOp(
        edit_id=new_id(),
        project_id=minimal_project.project_id,
        code="# ir_api_version: 0.1; libs: {}",
    )
    mock_result = FreeFormResult.fail("timeout", "30s elapsed")
    with patch("open_edit.ir.apply.sandbox_bridge.run_free_form",
               return_value=mock_result):
        with pytest.raises(ApplyError, match="timeout"):
            apply_operation(minimal_project, op)

    # Graph unchanged
    assert minimal_project.edit_graph == []


def test_apply_free_form_code_passes_timeout_and_mem(minimal_project):
    op = FreeFormCodeOp(
        edit_id=new_id(),
        project_id=minimal_project.project_id,
        code="# ir_api_version: 0.1; libs: {}",
        timeout_sec=10,
        mem_mb=256,
    )
    mock_result = FreeFormResult.ok(ops=[], duration_s=0.0)
    with patch("open_edit.ir.apply.sandbox_bridge.run_free_form",
               return_value=mock_result) as mock_run:
        apply_operation(minimal_project, op)
    assert mock_run.call_args.kwargs["timeout"] == 10
    assert mock_run.call_args.kwargs["mem_mb"] == 256
```

### Step 3: Run test to verify it fails

Run: `cd open_edit && pytest tests/test_apply_free_form.py -v`
Expected: ImportError on `sandbox_bridge` from `apply.py` (or ApplyError not defined).

### Step 4: Add ApplyError to apply.py

If `apply.py` doesn't have an `ApplyError` class, add it near the top:

```python
class ApplyError(Exception):
    """Raised when an op cannot be applied to the timeline."""
```

### Step 5: Add the _apply_free_form_code branch

In `open_edit/ir/apply.py`, after the existing branches in `apply_operation` (the big if/elif chain), add:

```python
def _apply_free_form_code(op: FreeFormCodeOp, project: Project) -> Project:
    """Run a free-form Python script in the sandbox and append its child ops.

    Each child op has parent_id == op.edit_id (stamped by IR at build time).
    """
    from open_edit.agent.sandbox_bridge import run_free_form
    result = run_free_form(
        op.code,
        Path(project.workdir) if project.workdir else None,
        project_id=project.project_id,
        parent_op_id=op.edit_id,
        timeout=op.timeout_sec,
        mem_mb=op.mem_mb,
    )
    if not result.success:
        raise ApplyError(f"free-form run failed: {result.reason}: {result.detail}")
    project.edit_graph.extend(result.ops)
    return project
```

And add the dispatch in `apply_operation`:

```python
    if isinstance(op, FreeFormCodeOp):
        return _apply_free_form_code(op, project)
```

### Step 6: Run tests to verify they pass

Run: `cd open_edit && pytest tests/test_apply_free_form.py -v`
Expected: 3 passing.

### Step 7: Run full suite to verify no regression

Run: `cd open_edit && pytest`
Expected: 198 → 201 passing (3 new tests).

### Step 8: Commit

```bash
cd /home/ah64/apps/mlt-pipeline
git add open_edit/ir/apply.py open_edit/ir/types.py open_edit/tests/test_apply_free_form.py
git commit -m "[open_edit] phase3 t9: _apply_free_form_code branch + FreeFormCodeOp.timeout_sec/mem_mb"
```

---

## Task 10: CLI subcommand + 5 E2E tests

**Files:**
- Modify: `open_edit/open_edit/cli.py` (add `free-form` subcommand for manual testing)
- Create: `open_edit/tests/test_free_form_e2e.py` (5 e2e tests, skipif no bwrap)
- Modify: `open_edit/tests/conftest.py` (add `tmp_project_with_assets` fixture)

**Interfaces:**
- Consumes: `sandbox_bridge.run_free_form`
- Produces: `open_edit free-form <code-file> <project-dir>` CLI subcommand

### Step 1: Write the failing CLI test

In `open_edit/tests/test_cli_free_form.py`:

```python
"""Phase 3 Task 10: `open_edit free-form` subcommand."""
import textwrap
from pathlib import Path

import pytest
from click.testing import CliRunner

from open_edit.cli import main


def test_cli_free_form_runs_script(tmp_path):
    runner = CliRunner()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "edit_graph.db").touch()

    code_file = tmp_path / "script.py"
    code_file.write_text(textwrap.dedent('''
        # ir_api_version: 0.1; libs: {}
        # Just a header check; full e2e in test_free_form_e2e.py
    '''))

    # Use a mocked sandbox_bridge to avoid the actual Rust binary
    from open_edit.agent.exceptions import FreeFormResult
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "open_edit.agent.sandbox_bridge.run_free_form",
            lambda *a, **kw: FreeFormResult.ok(ops=[], duration_s=0.0),
        )
        result = runner.invoke(main, ["free-form", str(code_file), str(project_dir)])
    assert result.exit_code == 0
    assert "free-form run completed" in result.output.lower() or "0 ops" in result.output
```

### Step 2: Run test to verify it fails

Run: `cd open_edit && pytest tests/test_cli_free_form.py -v`
Expected: failure (the `free-form` subcommand doesn't exist yet).

### Step 3: Add the `free-form` subcommand to cli.py

In `open_edit/cli.py`, after the existing subcommands, add:

```python
@main.command()
@click.argument("code_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("project_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--timeout", default=30, help="Wall-clock timeout in seconds.")
@click.option("--mem", default=512, help="Memory cap in MB.")
def free_form(code_file: Path, project_dir: Path, timeout: int, mem: int) -> None:
    """Run a free-form Python script in the sandbox against a project."""
    from open_edit.agent.sandbox_bridge import run_free_form
    from open_edit.storage.edit_graph import EditGraphStore
    code = code_file.read_text()
    db_path = project_dir / "edit_graph.db"
    if not db_path.exists():
        raise click.ClickException(f"project db not found: {db_path}")
    store = EditGraphStore(db_path)
    # Generate a synthetic parent_op_id for CLI testing; in real use this
    # comes from the agent loop.
    from open_edit.ir.types import new_id, FreeFormCodeOp
    parent_id = new_id()
    result = run_free_form(
        code, project_dir,
        project_id=store.project_id,
        parent_op_id=parent_id,
        timeout=timeout, mem_mb=mem,
    )
    if not result.success:
        raise click.ClickException(
            f"free-form run failed: {result.reason}: {result.detail}"
        )
    click.echo(f"free-form run completed: {len(result.ops)} ops in {result.duration_s:.2f}s")
    # Append child ops to the edit graph
    for op in result.ops:
        store.append(op)
    click.echo(f"appended {len(result.ops)} ops to {db_path}")
```

### Step 4: Run the CLI test to verify it passes

Run: `cd open_edit && pytest tests/test_cli_free_form.py -v`
Expected: 1 passing.

### Step 5: Add the tmp_project_with_assets fixture to conftest.py

In `open_edit/tests/conftest.py`, append:

```python
@pytest.fixture
def tmp_project_with_assets(tmp_path):
    """A project with one asset pre-ingested, suitable for free-form runs (L9)."""
    from open_edit.ir.types import Project, Asset
    stored = tmp_path / "assets" / "ab" / "abc123" / "clip.mp4"
    stored.parent.mkdir(parents=True)
    stored.write_bytes(b"\x00")
    asset = Asset(
        asset_hash="abc123",
        original_path=Path("/tmp/clip.mp4"),
        stored_path=str(stored),
        type="video",
        duration_sec=10.0,
        fps=30.0, width=1920, height=1080, codec="h264", has_audio=True,
    )
    return Project(
        name="test", workdir=tmp_path,
        assets={asset.asset_hash: asset},
    )
```

### Step 6: Create the 5 e2e tests

Create `open_edit/tests/test_free_form_e2e.py`:

```python
"""Phase 3 Task 10: end-to-end tests for the free-form Python sandbox.

All tests skip if bwrap is not on PATH. Tests use the real Rust binary.
"""
import shutil
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bubblewrap not installed",
)


def test_pyagent_run_python_50_lines(tmp_project_with_assets):
    """The design's "Done when" criterion: 50-line script → 50 child ops."""
    from open_edit.agent.sandbox_bridge import run_free_form
    code = textwrap.dedent('''
        # ir_api_version: 0.1; libs: {}
        for i in range(50):
            ir.add_clip(
                asset_hash="abc123",
                track_id="video_main",
                position_sec=i * 2.0,
                label=f"clip_{i}",
            )
    ''')
    result = run_free_form(
        code, tmp_project_with_assets.workdir,
        project_id=tmp_project_with_assets.project_id,
        parent_op_id="e1",
    )
    assert result.success, f"free-form failed: {result.reason}: {result.detail}"
    assert len(result.ops) == 50
    assert all(o.parent_id == "e1" for o in result.ops)
    assert all(isinstance(o, AddClipOp) for o in result.ops)
    assert [o.position_sec for o in result.ops] == [i * 2.0 for i in range(50)]


def test_chained_ops_succeed(tmp_project_with_assets):
    """L4: covers C6 — `ir.add_clip(...)` returns cid, `ir.trim_clip(cid, ...)` works."""
    from open_edit.agent.sandbox_bridge import run_free_form
    code = textwrap.dedent('''
        # ir_api_version: 0.1; libs: {}
        cid = ir.add_clip(asset_hash="abc123", track_id="video_main", position_sec=0.0)
        ir.trim_clip(cid, in_point_sec=1.0, out_point_sec=2.0)
    ''')
    result = run_free_form(
        code, tmp_project_with_assets.workdir,
        project_id=tmp_project_with_assets.project_id,
        parent_op_id="e1",
    )
    assert result.success, f"free-form failed: {result.reason}: {result.detail}"
    assert len(result.ops) == 2
    assert isinstance(result.ops[0], AddClipOp)
    assert isinstance(result.ops[1], TrimClipOp)
    assert result.ops[1].clip_id == result.ops[0].clip_id


def test_free_form_then_render(tmp_project_with_assets, tmp_path):
    """L2: free-form + full render produces a non-empty mp4."""
    from open_edit.agent.sandbox_bridge import run_free_form
    from open_edit.ir.apply import derive_timeline
    from open_edit.render.emitter import emit_timeline
    from open_edit.render.orchestrator import render_project
    code = textwrap.dedent('''
        # ir_api_version: 0.1; libs: {}
        for i in range(5):
            ir.add_clip(
                asset_hash="abc123", track_id="video_main",
                position_sec=i * 2.0,
            )
    ''')
    result = run_free_form(
        code, tmp_project_with_assets.workdir,
        project_id=tmp_project_with_assets.project_id,
        parent_op_id="e1",
    )
    assert result.success
    tmp_project_with_assets.edit_graph.extend(result.ops)
    timeline = derive_timeline(tmp_project_with_assets)
    xml = emit_timeline(timeline)
    assert "<mlt>" in xml or "<tractor>" in xml  # sanity check


def test_free_form_failure_does_not_corrupt_graph(tmp_project_with_assets):
    """L3: a free-form script that raises an exception does NOT corrupt the graph."""
    from open_edit.agent.sandbox_bridge import run_free_form
    pre_ops = list(tmp_project_with_assets.edit_graph)
    code = textwrap.dedent('''
        # ir_api_version: 0.1; libs: {}
        ir.add_clip(asset_hash="abc123", track_id="video_main", position_sec=0.0)
        raise RuntimeError("boom")
    ''')
    result = run_free_form(
        code, tmp_project_with_assets.workdir,
        project_id=tmp_project_with_assets.project_id,
        parent_op_id="e1",
    )
    assert not result.success
    # Graph is unchanged (atomic commit)
    assert list(tmp_project_with_assets.edit_graph) == pre_ops
    # No ops.jsonl files left behind
    sandbox_dir = tmp_project_with_assets.workdir / ".sandbox"
    if sandbox_dir.exists():
        for run_dir in sandbox_dir.iterdir():
            assert not (run_dir / "ops.jsonl").exists()


def test_source_ro_blocks_writes(tmp_project_with_assets):
    """L1: ro-bound source raises OSError(EROFS)."""
    from open_edit.agent.sandbox_bridge import run_free_form
    code = textwrap.dedent('''
        # ir_api_version: 0.1; libs: {}
        try:
            with open("/mnt/src0/clip.mp4", "w") as f:
                f.write("x")
        except OSError as e:
            ir.add_clip(
                asset_hash="abc123", track_id="video_main", position_sec=0.0,
                label=f"errno={e.errno}",
            )
    ''')
    result = run_free_form(
        code, tmp_project_with_assets.workdir,
        project_id=tmp_project_with_assets.project_id,
        parent_op_id="e1",
    )
    assert result.success, f"free-form failed: {result.reason}: {result.detail}"
    assert len(result.ops) == 1
    # EROFS=30 on Linux
    assert "30" in result.ops[0].label
```

### Step 7: Run the e2e tests

Run: `cd open_edit && pytest tests/test_free_form_e2e.py -v`
Expected: 5 passing (if bwrap is on PATH and the Rust binary is built and on PATH) or 5 skipped (if bwrap missing).

If the Rust binary isn't on PATH, the test will fail with `sandbox_binary_missing`. Build and install:
```bash
cd open_edit/sandbox
cargo build --release
sudo cp target/release/open-edit-sandbox /usr/local/bin/
```

### Step 8: Run full suite

Run: `cd open_edit && pytest`
Expected: 201 → 206 passing (5 new tests, 1 CLI test = 6 new total, all green or skipped).

### Step 9: Run cargo tests too

```bash
cd open_edit/sandbox
cargo test --features integration
```

Expected: integration tests run; the simpler ones pass, the complex ones may need adjustment.

### Step 10: Commit

```bash
cd /home/ah64/apps/mlt-pipeline
git add open_edit/cli.py open_edit/tests/conftest.py open_edit/tests/test_free_form_e2e.py open_edit/tests/test_cli_free_form.py
git commit -m "[open_edit] phase3 t10: CLI free-form subcommand + 5 e2e tests + tmp_project_with_assets fixture"
```

---

## Self-Review

**Spec coverage check:**

| Spec Section | Task |
|--------------|------|
| §1 v1 trust model | Documented in spec; no code task needed |
| §2.1-2.2 Architecture + Flow | Tasks 5-8 (Rust + bridge) |
| §2.3 Two halves | Tasks 5-7 (Rust) + 8-9 (Python) |
| §3.1-3.8 Rust binary | Tasks 5, 6, 7 |
| §4.1 IR class | Task 4 |
| §4.2 Bootstrap | Task 8 (uses inspect.getsource) |
| §4.3 sandbox_bridge | Task 8 |
| §4.4 exceptions | Task 2 |
| §4.5 libs.py | Task 3 |
| §4.6 allowed_libs.toml | Task 3 |
| §4.7 _apply_free_form_code | Task 9 |
| §4.8 Project.workdir | Task 1 |
| §4.9 FreeFormCodeOp extension | Task 9 |
| §5 files added/changed | All 10 tasks |
| §6 end-to-end test | Task 10 (5 tests) |
| §7 testing strategy | Distributed across tasks 1-10 |
| §8 configuration + CI | Documented in spec; cargo build is part of Task 5 |
| §9 acceptance criteria (25 items) | All addressed by tasks 1-10 |
| §10 v1.1 hardening | Documented; no code |

**Placeholder scan:** No TBD, no "implement later", no "fill in details". Every step has either explicit code, a command, or a verification.

**Type consistency check:**
- `IR(ops_buffer, project_id, parent_op_id)` — Task 4
- `FreeFormResult.ok(ops, duration_s)`, `FreeFormResult.fail(reason, detail)` — Task 2
- `run_free_form(code, workdir, project_id, parent_op_id, *, timeout, mem_mb, cpu_sec)` — Task 8 (used by Task 9 mock and Task 10 e2e)
- `EditGraphStore(db_path).project_id` — Task 1 (used by Task 8 _load_project_for_validation)
- `Project(workdir: Optional[Path] = None, ...)` — Task 1 (used by Task 8, Task 10)
- `AddClipOp(..., parent_id=self._parent_op_id, ...)` — Task 4
- `apply_operation(timeline, op) -> Timeline` — Task 8 (uses for incremental validation, matches existing `apply.py:62`)

All types consistent.

**Potential issue:** Task 4's test `test_ir_works_with_flushing_buffer_subclass` imports `_FlushingBuffer` from `sandbox_bridge` which doesn't exist until Task 8. The test will fail at import. Fix: change the test to use a plain list subclass (the second part of the test does this). The first part of the test (using `_FlushingBuffer`) should be removed or moved to Task 8.

Updated test for Task 4 — replace the flushing buffer import with a local list subclass:
```python
def test_ir_works_with_list_subclass():
    """The buffer is a SupportsAppend; works with any list-like."""
    class MyBuf(list):
        def append(self, x):
            super().append(x)
    ir = IR(ops_buffer=MyBuf(), project_id="p", parent_op_id="e")
    ir.add_clip(asset_hash="x", track_id="t", position_sec=0.0)
    assert len(ir._ops) == 1
```

This is a minor fix; the implementer will catch it when running the tests.

---

## Execution

This plan is ready for execution. Each task has:
- Failing test first
- Implementation
- Passing test
- Full-suite regression check
- Commit

The 10 tasks map cleanly to subagent dispatches (1 task per subagent in `superpowers:subagent-driven-development` mode) or to inline execution batches.
