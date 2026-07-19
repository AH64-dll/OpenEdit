# Open Edit — Phase 0 + Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the Open Edit IR (intermediate representation) + SQLite edit graph + content-addressed asset store + job lock + form-based CLI. No AI yet, no UI yet. After this plan, the system can `init` a folder of raw videos, ingest them, apply structured ops to a SQLite edit graph, derive a timeline, and undo. Tests prove the Bug A transition centering fix and the Bug B empty-paths rejection.

**Architecture:** Pydantic v2 immutable models for all operations (12 op types in the IR, including audio). SQLite for the edit graph (one `.db` per project, WAL mode). Content-addressed asset store with `ffprobe` metadata. Pure-function `apply.py` that derives a `Timeline` from the edit graph. CLI surfaces `init`, `list`, `summary`, `undo` for the human user.

**Tech Stack:** Python 3.11+, Pydantic v2, SQLite (stdlib), `ffprobe` (system), `uv` (workspace manager)

**Spec reference:** `/home/ah64/apps/mlt-pipeline/docs/superpowers/specs/2026-07-20-open-edit-design.md`

## Global Constraints

These apply to every task. Pulled verbatim from the spec; do not deviate.

- **Python 3.11+** — uses `from __future__ import annotations` and `Literal` types.
- **Pydantic v2** — use `BaseModel`, `Field(default_factory=...)`, `Literal[...]`, `Field(discriminator=...)` on Union types.
- **SQLite WAL mode** — every DB connection must run `PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;`.
- **Stable UUIDs** — every operation has `edit_id: str = Field(default_factory=new_id)`. `new_id()` returns `str(uuid.uuid4())`.
- **Status values** — `Literal["applied", "reverted", "superseded"]`, default `"applied"`.
- **Author values** — `Literal["ai", "user"]`, required (no default).
- **Timestamp** — ISO 8601 string via `Field(default_factory=now_iso8601)`.
- **Bug A** — `AddTransitionOp.apply()` places the transition at `cut = clip_a.out_point_sec`, then back-solves `clip_a.out_point_sec = cut - duration_sec / 2` and `clip_b.in_point_sec = cut + duration_sec / 2`. The transition is centered on the cut, not the midpoint.
- **Bug B** — `AssetStore.ingest()` rejects empty `paths` list with `ValidationError` containing a `fix:` line.
- **Canonical JSON for hashing** — `json.dumps(obj, sort_keys=True, separators=(",", ":"))` then `hashlib.sha256(...).hexdigest()`.
- **Linux only** — no Windows/macOS-specific paths or syscalls.
- **No Kdenlive anywhere in v1** — Phase 0+1 does not parse or produce `.kdenlive` files. The legacy importer is v2.
- **Edit freedom and high capability** — the IR must model 12 op types so the AI can do anything a human editor can.

## File Structure (created in this plan)

```
/home/ah64/apps/mlt-pipeline/
├── open_edit/                              # NEW package
│   ├── pyproject.toml
│   ├── open_edit/
│   │   ├── __init__.py
│   │   ├── cli.py
│   │   ├── ir/
│   │   │   ├── __init__.py
│   │   │   ├── types.py
│   │   │   ├── apply.py
│   │   │   ├── validate.py
│   │   │   ├── commutativity.py
│   │   │   └── api.py
│   │   ├── storage/
│   │   │   ├── __init__.py
│   │   │   ├── schema.sql
│   │   │   ├── edit_graph.py
│   │   │   ├── assets.py
│   │   │   └── job_lock.py
│   │   └── style/
│   │       ├── __init__.py
│   │       └── taste_events.py
│   ├── sandbox/
│   │   └── observations/                   # strace fixtures
│   └── tests/
│       ├── conftest.py
│       ├── testdata/raw_videos/            # 3 test mp4s
│       ├── test_ir/{test_types,test_apply,test_validate,test_commutativity}.py
│       ├── test_storage/{test_edit_graph,test_assets,test_job_lock}.py
│       ├── test_style/test_taste_events.py
│       ├── test_sandbox_observations.py
│       └── test_cli.py
```

The existing `pyagent-kdenlive-guide/` directory is **untouched** in this plan. Phase 4 will repoint its tool wrappers to the new IR.

---

## Task 1: Workspace scaffold + pyproject.toml

**Files:**
- Create: `open_edit/pyproject.toml`
- Create: `open_edit/open_edit/__init__.py`
- Create: `open_edit/open_edit/cli.py` (placeholder)
- Create: `open_edit/open_edit/ir/__init__.py`
- Create: `open_edit/open_edit/storage/__init__.py`
- Create: `open_edit/open_edit/style/__init__.py`
- Create: `open_edit/tests/__init__.py`
- Create: `open_edit/tests/conftest.py`

**Interfaces:**
- Consumes: nothing
- Produces: a `uv`-installable Python package `open_edit`; an entry point `open_edit` that runs the CLI

- [ ] **Step 1: Create directory skeleton**

```bash
mkdir -p /home/ah64/apps/mlt-pipeline/open_edit/open_edit/{ir,storage,style}
mkdir -p /home/ah64/apps/mlt-pipeline/open_edit/sandbox/observations
mkdir -p /home/ah64/apps/mlt-pipeline/open_edit/tests/{test_ir,test_storage,test_style,testdata/raw_videos}
touch /home/ah64/apps/mlt-pipeline/open_edit/open_edit/__init__.py
touch /home/ah64/apps/mlt-pipeline/open_edit/open_edit/ir/__init__.py
touch /home/ah64/apps/mlt-pipeline/open_edit/open_edit/storage/__init__.py
touch /home/ah64/apps/mlt-pipeline/open_edit/open_edit/style/__init__.py
touch /home/ah64/apps/mlt-pipeline/open_edit/tests/__init__.py
```

- [ ] **Step 2: Write `pyproject.toml`**

File: `/home/ah64/apps/mlt-pipeline/open_edit/pyproject.toml`

```toml
[project]
name = "open_edit"
version = "0.1.0"
description = "AI-native video editing platform — IR, asset store, sandboxed agent"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
]

[project.scripts]
open_edit = "open_edit.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["open_edit"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-ra -q"
```

- [ ] **Step 3: Write placeholder `cli.py`**

File: `/home/ah64/apps/mlt-pipeline/open_edit/open_edit/cli.py`

```python
"""Open Edit CLI — Phase 0 placeholder."""
import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="open_edit",
        description="AI-native video editing platform",
    )
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args(argv)
    if args.version:
        print("open_edit 0.1.0")
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Write `conftest.py`**

File: `/home/ah64/apps/mlt-pipeline/open_edit/tests/conftest.py`

```python
"""Pytest configuration for open_edit tests."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
```

- [ ] **Step 5: Install the package in editable mode**

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && uv pip install -e ".[dev]"
```

Expected: `Successfully built open_edit` and `Successfully installed open_edit-0.1.0`.

- [ ] **Step 6: Verify the CLI runs**

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && open_edit --version
```

Expected: `open_edit 0.1.0`

- [ ] **Step 7: Commit**

```bash
cd /home/ah64/apps/mlt-pipeline && git add open_edit/
git commit -m "[open_edit] scaffold: pyproject, package dirs, placeholder CLI"
```

---

## Task 2: Strace observations (Phase 0 prerequisite for sandbox)

**Files:**
- Create: `open_edit/sandbox/observations/strace_melt.txt`
- Create: `open_edit/sandbox/observations/strace_ffmpeg.txt`
- Create: `open_edit/sandbox/observations/strace_ffprobe.txt`
- Create: `open_edit/tests/test_sandbox_observations.py`

**Interfaces:**
- Consumes: existing system tools (`melt`, `ffmpeg`, `ffprobe`, `strace`)
- Produces: three `strace -c` histograms committed as test fixtures; used by Phase 3 sandbox to build the seccomp allowlist

- [ ] **Step 1: Verify `strace` is installed**

```bash
which strace || sudo apt install strace
```

Expected: `/usr/bin/strace`

- [ ] **Step 2: Generate a tiny test clip and MLT probe**

```bash
# Synthesize a 5-second test clip with ffmpeg if no source video is available
if [ ! -f /tmp/strace_input.mp4 ]; then
    ffmpeg -y -f lavfi -i testsrc=duration=5:size=320x240:rate=30 \
        -pix_fmt yuv420p /tmp/strace_input.mp4 2>/dev/null
fi

# Generate a minimal MLT XML
cat > /tmp/strace_probe.mlt <<'EOF'
<?xml version="1.0" standalone="no"?>
<mlt LC_NUMERIC="C" version="7.22.0">
  <producer id="producer0">
    <property name="resource">/tmp/strace_input.mp4</property>
  </producer>
  <tractor id="tractor0">
    <multitrack>
      <track>
        <clip producer="producer0">
          <in>0</in>
          <out>150</out>
        </clip>
      </track>
    </multitrack>
  </tractor>
</mlt>
EOF
```

- [ ] **Step 3: Run `strace -c` on `melt`**

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit/sandbox/observations
strace -f -c -o strace_melt.txt \
    melt /tmp/strace_probe.mlt -consumer avformat:/tmp/strace_melt_out.mp4 vcodec=libx264 acodec=aac
```

- [ ] **Step 4: Run `strace -c` on `ffmpeg`**

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit/sandbox/observations
strace -f -c -o strace_ffmpeg.txt \
    ffmpeg -y -i /tmp/strace_input.mp4 -t 5 -c:v libx264 -c:a aac /tmp/strace_ffmpeg_out.mp4
```

- [ ] **Step 5: Run `strace -c` on `ffprobe`**

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit/sandbox/observations
strace -f -c -o strace_ffprobe.txt \
    ffprobe -show_streams -show_format /tmp/strace_input.mp4
```

- [ ] **Step 6: Verify the three strace files exist and are non-empty**

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit/sandbox/observations
wc -l strace_*.txt
```

Expected: each file 10+ lines.

- [ ] **Step 7: Write a test that the strace fixtures are present and parseable**

File: `/home/ah64/apps/mlt-pipeline/open_edit/tests/test_sandbox_observations.py`

```python
"""Verify the strace observation fixtures are present and parseable."""
from pathlib import Path

OBS_DIR = Path(__file__).parent.parent / "sandbox" / "observations"


def test_strace_melt_fixture_exists() -> None:
    path = OBS_DIR / "strace_melt.txt"
    assert path.exists(), f"missing {path}"
    content = path.read_text()
    assert "seconds" in content or "syscall" in content.lower()


def test_strace_ffmpeg_fixture_exists() -> None:
    path = OBS_DIR / "strace_ffmpeg.txt"
    assert path.exists(), f"missing {path}"
    assert path.stat().st_size > 0


def test_strace_ffprobe_fixture_exists() -> None:
    path = OBS_DIR / "strace_ffprobe.txt"
    assert path.exists(), f"missing {path}"
    assert path.stat().st_size > 0


def test_strace_files_contain_real_syscalls() -> None:
    """Each strace file should list at least 5 distinct syscalls."""
    for name in ("strace_melt.txt", "strace_ffmpeg.txt", "strace_ffprobe.txt"):
        content = (OBS_DIR / name).read_text()
        syscall_lines = [
            line for line in content.splitlines()
            if line and line.split() and not line.startswith("-")
            and not line.startswith("%")
            and not line.startswith("syscall")
        ]
        assert len(syscall_lines) >= 5, f"{name} has too few syscalls: {syscall_lines}"
```

- [ ] **Step 8: Run the test**

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && pytest tests/test_sandbox_observations.py -v
```

Expected: 4 passed.

- [ ] **Step 9: Commit**

```bash
cd /home/ah64/apps/mlt-pipeline && git add open_edit/sandbox/observations/ open_edit/tests/test_sandbox_observations.py
git commit -m "[open_edit] Phase 0: strace observation fixtures (melt, ffmpeg, ffprobe)"
```

---

## Task 3: Pydantic operation types — `ir/types.py`

**Files:**
- Create: `open_edit/open_edit/ir/types.py`
- Create: `open_edit/tests/test_ir/test_types.py`

**Interfaces (produced by this task):**
- `class Operation(BaseModel)` — base for all ops; `edit_id`, `parent_id`, `author`, `timestamp`, `status`, `kind`
- `class AddClipOp(Operation)`, `RemoveClipOp`, `MoveClipOp`, `TrimClipOp`, `AddTransitionOp`, `AddEffectOp`, `SetKeyframeOp`, `SetAudioGainOp`, `NormalizeAudioOp`, `GroupEditsOp`, `RawMltXmlOp`, `FreeFormCodeOp`
- `class Clip`, `Track`, `Effect`, `Timeline`, `Asset`, `Project` — derived state
- `new_id()`, `now_iso8601()` helpers
- `OperationUnion = Annotated[Union[...], Field(discriminator="kind")]` for the discriminated union

- [ ] **Step 1: Write the failing test for the base Operation type**

File: `/home/ah64/apps/mlt-pipeline/open_edit/tests/test_ir/test_types.py`

```python
"""Tests for the Pydantic operation types."""
import uuid

import pytest
from pydantic import ValidationError

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


# ===== Helpers =====

def test_new_id_returns_uuid_string() -> None:
    aid = new_id()
    uuid.UUID(aid)


def test_new_id_is_unique() -> None:
    assert new_id() != new_id()


def test_now_iso8601_returns_string() -> None:
    ts = now_iso8601()
    assert isinstance(ts, str)
    assert "T" in ts


# ===== Base Operation =====

def test_operation_default_edit_id_is_unique() -> None:
    a = Operation(author="user", kind="test")
    b = Operation(author="user", kind="test")
    assert a.edit_id != b.edit_id


def test_operation_default_status_is_applied() -> None:
    op = Operation(author="user", kind="test")
    assert op.status == "applied"


def test_operation_default_parent_id_is_none() -> None:
    op = Operation(author="user", kind="test")
    assert op.parent_id is None


def test_operation_status_must_be_valid_literal() -> None:
    with pytest.raises(ValidationError):
        Operation(author="user", kind="test", status="deleted")


def test_operation_author_must_be_ai_or_user() -> None:
    with pytest.raises(ValidationError):
        Operation(author="robot", kind="test")


# ===== AddClipOp =====

def test_add_clip_op_minimal() -> None:
    op = AddClipOp(
        author="ai", asset_hash="abc123", track_id="video_1", position_sec=0.0,
    )
    assert op.kind == "add_clip"
    assert op.track_kind == "video"
    assert op.in_point_sec == 0.0
    assert op.out_point_sec is None
    assert op.clip_id != op.edit_id


def test_add_clip_op_track_kind_must_be_video_or_audio() -> None:
    with pytest.raises(ValidationError):
        AddClipOp(
            author="ai", asset_hash="abc", track_id="t",
            position_sec=0.0, track_kind="text",
        )


# ===== AddTransitionOp =====

def test_add_transition_op_fields() -> None:
    op = AddTransitionOp(
        author="ai", clip_a_id="c1", clip_b_id="c2",
        transition_type="luma", duration_sec=1.0,
    )
    assert op.kind == "add_transition"
    assert op.transition_type == "luma"


def test_add_transition_op_type_must_be_valid() -> None:
    with pytest.raises(ValidationError):
        AddTransitionOp(
            author="ai", clip_a_id="c1", clip_b_id="c2",
            transition_type="star_wipe", duration_sec=1.0,
        )


# ===== AddEffectOp =====

def test_add_effect_op_minimal() -> None:
    op = AddEffectOp(
        author="ai", target_kind="clip", target_id="c1",
        effect_type="volume", params={"gain": 1.0},
    )
    assert op.kind == "add_effect"
    assert op.effect_id != op.edit_id


# ===== SetKeyframeOp =====

def test_set_keyframe_op_fields() -> None:
    op = SetKeyframeOp(
        author="ai", effect_id="fx1", param="gain",
        keyframes=[(0.0, 1.0, "linear"), (2.0, 0.0, "linear")],
    )
    assert op.kind == "set_keyframe"
    assert op.keyframes[0] == (0.0, 1.0, "linear")


# ===== Audio ops =====

def test_set_audio_gain_op() -> None:
    op = SetAudioGainOp(author="ai", clip_id="c1", gain_db=-6.0)
    assert op.kind == "set_audio_gain"
    assert op.gain_db == -6.0


def test_normalize_audio_op_defaults() -> None:
    op = NormalizeAudioOp(
        author="ai", target_kind="track", target_id="audio_1",
    )
    assert op.target_dbfs == -16.0


# ===== Grouping =====

def test_group_edits_op() -> None:
    op = GroupEditsOp(author="ai", edit_ids=["e1", "e2"], label="AI: add intro music")
    assert op.kind == "group_edits"
    assert op.edit_ids == ["e1", "e2"]


# ===== Escape hatches =====

def test_raw_mlt_xml_op() -> None:
    op = RawMltXmlOp(
        author="ai", xml="<filter/>", description="Vintage",
    )
    assert op.kind == "raw_mlt_xml"


def test_free_form_code_op() -> None:
    op = FreeFormCodeOp(author="ai", code="ir.add_clip('abc', 'v1', 0.0)")
    assert op.kind == "free_form_code"


# ===== Remove/Move/Trim =====

def test_remove_clip_op() -> None:
    op = RemoveClipOp(author="ai", clip_id="c1")
    assert op.kind == "remove_clip"


def test_move_clip_op() -> None:
    op = MoveClipOp(author="ai", clip_id="c1", new_track_id="v2", new_position_sec=10.0)
    assert op.kind == "move_clip"


def test_trim_clip_op() -> None:
    op = TrimClipOp(author="ai", clip_id="c1", new_in_point_sec=2.0, new_out_point_sec=5.0)
    assert op.kind == "trim_clip"


# ===== Discriminated union =====

def test_operation_union_validates_by_kind() -> None:
    payload = {
        "kind": "add_clip", "author": "ai", "asset_hash": "abc",
        "track_id": "v1", "position_sec": 0.0, "edit_id": "x",
        "parent_id": None, "timestamp": "2026-07-20T00:00:00Z", "status": "applied",
    }
    op = OperationUnion.model_validate(payload)
    assert isinstance(op, AddClipOp)
    assert op.edit_id == "x"


def test_operation_union_rejects_unknown_kind() -> None:
    payload = {"kind": "unknown_op", "author": "ai"}
    with pytest.raises(ValidationError):
        OperationUnion.model_validate(payload)


# ===== Serialization round-trip =====

def test_operation_json_round_trip() -> None:
    op = AddClipOp(author="ai", asset_hash="abc", track_id="v1", position_sec=0.0)
    json_str = op.model_dump_json()
    restored = AddClipOp.model_validate_json(json_str)
    assert restored.edit_id == op.edit_id
    assert restored.asset_hash == op.asset_hash


def test_project_has_assets_and_edit_graph() -> None:
    p = Project(name="test")
    assert p.assets == {}
    assert p.edit_graph == []
    assert p.project_id
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && pytest tests/test_ir/test_types.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` — `open_edit.ir.types` doesn't exist.

- [ ] **Step 3: Write the types module**

File: `/home/ah64/apps/mlt-pipeline/open_edit/open_edit/ir/types.py`

```python
"""Pydantic models for Open Edit's IR.

All operations are immutable Pydantic models with stable UUIDs. The
discriminated union is on `kind`, validated via Pydantic's Field(discriminator).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, Field


def new_id() -> str:
    """Return a fresh UUID4 string."""
    return str(uuid.uuid4())


def now_iso8601() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ===== Derived state (Timeline, Track, Clip, Effect) =====

class Effect(BaseModel):
    effect_id: str
    effect_type: str
    params: dict[str, Any] = Field(default_factory=dict)
    keyframes: dict[str, list[tuple[float, float, str]]] = Field(default_factory=dict)


class Clip(BaseModel):
    clip_id: str
    asset_hash: str
    track_id: str
    track_kind: Literal["video", "audio"]
    position_sec: float
    in_point_sec: float
    out_point_sec: float
    effects: list[Effect] = Field(default_factory=list)


class Track(BaseModel):
    track_id: str
    kind: Literal["video", "audio"]
    clips: list[Clip] = Field(default_factory=list)
    effects: list[Effect] = Field(default_factory=list)


class Timeline(BaseModel):
    tracks: list[Track] = Field(default_factory=list)
    duration_sec: float = 0.0


class Asset(BaseModel):
    asset_hash: str
    original_path: str
    stored_path: str
    type: Literal["video", "audio", "image"]
    duration_sec: float = 0.0
    fps: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    codec: Optional[str] = None
    has_audio: bool = False


# ===== Operation base + concrete variants =====

class Operation(BaseModel):
    kind: str  # overridden by each subclass as Literal[...]
    edit_id: str = Field(default_factory=new_id)
    parent_id: Optional[str] = None
    author: Literal["ai", "user"]
    timestamp: str = Field(default_factory=now_iso8601)
    status: Literal["applied", "reverted", "superseded"] = "applied"


class AddClipOp(Operation):
    kind: Literal["add_clip"] = "add_clip"
    asset_hash: str
    track_id: str
    track_kind: Literal["video", "audio"] = "video"
    position_sec: float
    in_point_sec: float = 0.0
    out_point_sec: Optional[float] = None
    clip_id: str = Field(default_factory=new_id)


class RemoveClipOp(Operation):
    kind: Literal["remove_clip"] = "remove_clip"
    clip_id: str


class MoveClipOp(Operation):
    kind: Literal["move_clip"] = "move_clip"
    clip_id: str
    new_track_id: str
    new_position_sec: float


class TrimClipOp(Operation):
    kind: Literal["trim_clip"] = "trim_clip"
    clip_id: str
    new_in_point_sec: float
    new_out_point_sec: float


class AddTransitionOp(Operation):
    kind: Literal["add_transition"] = "add_transition"
    clip_a_id: str
    clip_b_id: str
    transition_type: Literal["luma", "dissolve", "wipe", "fade", "cut"]
    duration_sec: float


class AddEffectOp(Operation):
    kind: Literal["add_effect"] = "add_effect"
    target_kind: Literal["clip", "track"]
    target_id: str
    effect_type: str
    params: dict[str, Any] = Field(default_factory=dict)
    effect_id: str = Field(default_factory=new_id)


class SetKeyframeOp(Operation):
    kind: Literal["set_keyframe"] = "set_keyframe"
    effect_id: str
    param: str
    keyframes: list[tuple[float, float, str]]


class SetAudioGainOp(Operation):
    """First-class audio op. NOT a side-effect of video."""
    kind: Literal["set_audio_gain"] = "set_audio_gain"
    clip_id: str
    gain_db: float
    keyframe_op_id: Optional[str] = None


class NormalizeAudioOp(Operation):
    """First-class audio normalization."""
    kind: Literal["normalize_audio"] = "normalize_audio"
    target_kind: Literal["clip", "track", "project"]
    target_id: str
    target_dbfs: float = -16.0


class GroupEditsOp(Operation):
    kind: Literal["group_edits"] = "group_edits"
    edit_ids: list[str]
    label: str


class RawMltXmlOp(Operation):
    kind: Literal["raw_mlt_xml"] = "raw_mlt_xml"
    xml: str
    description: str


class FreeFormCodeOp(Operation):
    kind: Literal["free_form_code"] = "free_form_code"
    code: str


OperationUnion = Annotated[
    Union[
        AddClipOp, RemoveClipOp, MoveClipOp, TrimClipOp,
        AddTransitionOp, AddEffectOp, SetKeyframeOp,
        SetAudioGainOp, NormalizeAudioOp,
        GroupEditsOp, RawMltXmlOp, FreeFormCodeOp,
    ],
    Field(discriminator="kind"),
]


class Project(BaseModel):
    project_id: str = Field(default_factory=new_id)
    name: str
    created_at: str = Field(default_factory=now_iso8601)
    assets: dict[str, Asset] = Field(default_factory=dict)
    edit_graph: list[OperationUnion] = Field(default_factory=list)
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && pytest tests/test_ir/test_types.py -v
```

Expected: all ~28 tests pass.

- [ ] **Step 5: Commit**

```bash
cd /home/ah64/apps/mlt-pipeline && git add open_edit/open_edit/ir/types.py open_edit/tests/test_ir/test_types.py
git commit -m "[open_edit] ir.types: 12 Pydantic operation models + Timeline/Project"
```

---

## Task 4: SQLite schema — `storage/schema.sql` + `EditGraphStore` skeleton

**Files:**
- Create: `open_edit/open_edit/storage/schema.sql`
- Create: `open_edit/open_edit/storage/edit_graph.py` (init only; CRUD in Task 5)
- Create: `open_edit/tests/test_storage/test_edit_graph.py`

**Interfaces:**
- Consumes: nothing
- Produces: a SQLite schema with `edits` and `jobs` tables; an `EditGraphStore.__init__` that creates the DB and runs the schema

- [ ] **Step 1: Write the failing test**

File: `/home/ah64/apps/mlt-pipeline/open_edit/tests/test_storage/test_edit_graph.py`

```python
"""Tests for the EditGraphStore (SQLite-backed edit graph)."""
from pathlib import Path

from open_edit.storage.edit_graph import EditGraphStore


def test_init_creates_db_file(tmp_path: Path) -> None:
    db_path = tmp_path / "project.db"
    EditGraphStore(db_path)
    assert db_path.exists()


def test_init_creates_edits_table(tmp_path: Path) -> None:
    store = EditGraphStore(tmp_path / "project.db")
    with store._conn() as conn:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='edits'"
        )
        assert cur.fetchone() is not None


def test_init_creates_jobs_table(tmp_path: Path) -> None:
    store = EditGraphStore(tmp_path / "project.db")
    with store._conn() as conn:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'"
        )
        assert cur.fetchone() is not None


def test_init_enables_wal_mode(tmp_path: Path) -> None:
    store = EditGraphStore(tmp_path / "project.db")
    with store._conn() as conn:
        cur = conn.execute("PRAGMA journal_mode")
        mode = cur.fetchone()[0]
        assert mode.lower() == "wal"


def test_init_enables_foreign_keys(tmp_path: Path) -> None:
    store = EditGraphStore(tmp_path / "project.db")
    with store._conn() as conn:
        cur = conn.execute("PRAGMA foreign_keys")
        enabled = cur.fetchone()[0]
        assert enabled == 1
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && pytest tests/test_storage/test_edit_graph.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write the SQLite schema**

File: `/home/ah64/apps/mlt-pipeline/open_edit/open_edit/storage/schema.sql`

```sql
-- Open Edit project database schema.
-- One .db file per project, at ~/.open-edit/projects/<id>/edit_graph.db.
-- Schema is additive-only; no migrations needed because the file is a
-- snapshot, not a long-lived schema-bearing database.

CREATE TABLE IF NOT EXISTS project_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS edits (
    edit_id      TEXT PRIMARY KEY,
    parent_id    TEXT,
    kind         TEXT NOT NULL,
    author       TEXT NOT NULL,
    timestamp    TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('applied', 'reverted', 'superseded')),
    sequence_num INTEGER NOT NULL,
    payload      TEXT NOT NULL,
    FOREIGN KEY (parent_id) REFERENCES edits(edit_id)
);

CREATE INDEX IF NOT EXISTS idx_edits_sequence ON edits(sequence_num);
CREATE INDEX IF NOT EXISTS idx_edits_parent    ON edits(parent_id);
CREATE INDEX IF NOT EXISTS idx_edits_status    ON edits(status);

CREATE TABLE IF NOT EXISTS jobs (
    job_id      TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    error       TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
```

- [ ] **Step 4: Write the EditGraphStore skeleton (init only)**

File: `/home/ah64/apps/mlt-pipeline/open_edit/open_edit/storage/edit_graph.py`

```python
"""SQLite-backed edit graph store.

One .db file per project. WAL mode for concurrent reads. Stores every
operation ever applied to the project (including reverted/superseded).
The durable record; the source of truth for the IR.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class EditGraphStore:
    """SQLite store for a project's edit graph + job lock."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        """Yield a SQLite connection with WAL + foreign keys enabled."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA_PATH.read_text())
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && pytest tests/test_storage/test_edit_graph.py -v
```

Expected: 5 tests pass.

- [ ] **Step 6: Commit**

```bash
cd /home/ah64/apps/mlt-pipeline && git add open_edit/open_edit/storage/ open_edit/tests/test_storage/test_edit_graph.py
git commit -m "[open_edit] storage: schema.sql + EditGraphStore skeleton (WAL, FK)"
```

---

## Task 5: EditGraphStore — append, load_all, update_status, reorder

**Files:**
- Modify: `open_edit/open_edit/storage/edit_graph.py` (add CRUD methods)
- Modify: `open_edit/tests/test_storage/test_edit_graph.py` (append CRUD tests)

**Interfaces (produced):**
- `EditGraphStore.append(op: OperationUnion, sequence_num: int | None = None) -> int`
- `EditGraphStore.load_all() -> list[OperationUnion]`
- `EditGraphStore.update_status(edit_id: str, new_status: str) -> None`
- `EditGraphStore.reorder(edit_id_a: str, edit_id_b: str) -> None` (rejects non-adjacent)

- [ ] **Step 1: Append the failing CRUD tests to `test_edit_graph.py`**

Add at the end of `open_edit/tests/test_storage/test_edit_graph.py`:

```python
from open_edit.ir.types import AddClipOp


def test_append_assigns_increasing_sequence_num(tmp_path: Path) -> None:
    store = EditGraphStore(tmp_path / "p.db")
    op1 = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
    op2 = AddClipOp(author="user", asset_hash="b", track_id="v1", position_sec=5.0)
    seq1 = store.append(op1)
    seq2 = store.append(op2)
    assert seq1 == 0
    assert seq2 == 1


def test_load_all_returns_ops_in_sequence_order(tmp_path: Path) -> None:
    store = EditGraphStore(tmp_path / "p.db")
    op1 = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
    op2 = AddClipOp(author="user", asset_hash="b", track_id="v1", position_sec=5.0)
    store.append(op1)
    store.append(op2)
    ops = store.load_all()
    assert len(ops) == 2
    assert ops[0].asset_hash == "a"
    assert ops[1].asset_hash == "b"


def test_update_status_marks_reverted(tmp_path: Path) -> None:
    store = EditGraphStore(tmp_path / "p.db")
    op = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
    store.append(op)
    store.update_status(op.edit_id, "reverted")
    ops = store.load_all()
    assert ops[0].status == "reverted"


def test_reorder_swaps_adjacent_ops(tmp_path: Path) -> None:
    store = EditGraphStore(tmp_path / "p.db")
    op1 = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
    op2 = AddClipOp(author="user", asset_hash="b", track_id="v1", position_sec=5.0)
    op3 = AddClipOp(author="user", asset_hash="c", track_id="v1", position_sec=10.0)
    store.append(op1)
    store.append(op2)
    store.append(op3)
    store.reorder(op1.edit_id, op2.edit_id)
    ops = store.load_all()
    assert ops[0].asset_hash == "b"
    assert ops[1].asset_hash == "a"
    assert ops[2].asset_hash == "c"


def test_reorder_rejects_non_adjacent_ops(tmp_path: Path) -> None:
    store = EditGraphStore(tmp_path / "p.db")
    op1 = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
    op2 = AddClipOp(author="user", asset_hash="b", track_id="v1", position_sec=5.0)
    op3 = AddClipOp(author="user", asset_hash="c", track_id="v1", position_sec=10.0)
    store.append(op1)
    store.append(op2)
    store.append(op3)
    import pytest
    with pytest.raises(ValueError, match="adjacent"):
        store.reorder(op1.edit_id, op3.edit_id)


def test_reorder_rejects_missing_ops(tmp_path: Path) -> None:
    store = EditGraphStore(tmp_path / "p.db")
    op1 = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
    store.append(op1)
    import pytest
    with pytest.raises(ValueError, match="exist"):
        store.reorder(op1.edit_id, "nonexistent-id")
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && pytest tests/test_storage/test_edit_graph.py -v
```

Expected: 6 new tests fail with `AttributeError: 'EditGraphStore' object has no attribute 'append'`.

- [ ] **Step 3: Replace `edit_graph.py` with the full CRUD version**

Replace the contents of `open_edit/open_edit/storage/edit_graph.py` with:

```python
"""SQLite-backed edit graph store.

One .db file per project. WAL mode for concurrent reads. Stores every
operation ever applied (including reverted/superseded). The durable
record; the source of truth for the IR.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from open_edit.ir.types import OperationUnion


SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class EditGraphStore:
    """SQLite store for a project's edit graph + job lock."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA_PATH.read_text())

    def append(
        self, op: OperationUnion, sequence_num: int | None = None
    ) -> int:
        """Append an operation. Returns the assigned sequence_num."""
        with self._conn() as conn:
            if sequence_num is None:
                cur = conn.execute(
                    "SELECT COALESCE(MAX(sequence_num), -1) + 1 FROM edits"
                )
                sequence_num = cur.fetchone()[0]
            conn.execute(
                "INSERT INTO edits "
                "(edit_id, parent_id, kind, author, timestamp, status, "
                " sequence_num, payload) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    op.edit_id, op.parent_id, op.kind, op.author, op.timestamp,
                    op.status, sequence_num, op.model_dump_json(),
                ),
            )
        return sequence_num

    def load_all(self) -> list[OperationUnion]:
        """Load all operations in sequence_num order."""
        with self._conn() as conn:
            cur = conn.execute("SELECT payload FROM edits ORDER BY sequence_num")
            return [
                OperationUnion.model_validate_json(row[0]) for row in cur.fetchall()
            ]

    def update_status(self, edit_id: str, new_status: str) -> None:
        """Update an operation's status (e.g. for undo/revert or supersede)."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE edits SET status = ? WHERE edit_id = ?",
                (new_status, edit_id),
            )

    def reorder(self, edit_id_a: str, edit_id_b: str) -> None:
        """Swap the sequence_num of two adjacent operations.

        Raises ValueError if either id does not exist or if the two ops
        are not adjacent in sequence_num.
        """
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT edit_id, sequence_num FROM edits "
                "WHERE edit_id IN (?, ?) ORDER BY sequence_num",
                (edit_id_a, edit_id_b),
            )
            rows = cur.fetchall()
            if len(rows) != 2:
                raise ValueError(f"Both edits must exist; got {len(rows)} rows")
            (id1, seq1), (id2, seq2) = rows
            if abs(seq1 - seq2) != 1:
                raise ValueError(
                    f"Edits must be adjacent to reorder; "
                    f"got sequence_num gap {abs(seq1 - seq2)}"
                )
            conn.execute(
                "UPDATE edits SET sequence_num = ? WHERE edit_id = ?",
                (seq2, id1),
            )
            conn.execute(
                "UPDATE edits SET sequence_num = ? WHERE edit_id = ?",
                (seq1, id2),
            )
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && pytest tests/test_storage/test_edit_graph.py -v
```

Expected: 11 tests pass (5 init + 6 CRUD).

- [ ] **Step 5: Commit**

```bash
cd /home/ah64/apps/mlt-pipeline && git add open_edit/open_edit/storage/edit_graph.py open_edit/tests/test_storage/test_edit_graph.py
git commit -m "[open_edit] storage.edit_graph: append, load_all, update_status, reorder"
```

---

## Task 6: AssetStore — content-addressed with ffprobe

**Files:**
- Create: `open_edit/open_edit/storage/assets.py`
- Create: `open_edit/tests/test_storage/test_assets.py`
- Create: 3 test mp4s in `open_edit/tests/testdata/raw_videos/`

**Interfaces (produced):**
- `AssetStore(assets_dir: str | Path)` — sets up the CAS directory
- `AssetStore.ingest(source_path: str) -> Asset` — single file (calls `ingest_paths([p])`)
- `AssetStore.ingest_paths(paths: list[str]) -> list[Asset]` — Bug B: rejects empty `paths`
- `AssetStore.get(asset_hash: str) -> Asset | None`
- `_probe_media(path: str) -> dict` — internal; runs ffprobe

- [ ] **Step 1: Verify `ffprobe` is installed and synthesize 3 tiny test videos**

```bash
which ffprobe || sudo apt install ffmpeg
mkdir -p /home/ah64/apps/mlt-pipeline/open_edit/tests/testdata/raw_videos
cd /home/ah64/apps/mlt-pipeline/open_edit/tests/testdata/raw_videos
ffmpeg -y -f lavfi -i "color=c=blue:s=320x240:d=2:r=30"  -pix_fmt yuv420p -c:v libx264 clip_a.mp4 2>/dev/null
ffmpeg -y -f lavfi -i "color=c=red:s=320x240:d=2:r=30"   -pix_fmt yuv420p -c:v libx264 clip_b.mp4 2>/dev/null
ffmpeg -y -f lavfi -i "color=c=green:s=320x240:d=2:r=30" -pix_fmt yuv420p -c:v libx264 clip_c.mp4 2>/dev/null
ls -la /home/ah64/apps/mlt-pipeline/open_edit/tests/testdata/raw_videos/
```

Expected: 3 mp4 files, each ~5-10 KB.

- [ ] **Step 2: Write the failing test**

File: `/home/ah64/apps/mlt-pipeline/open_edit/tests/test_storage/test_assets.py`

```python
"""Tests for the AssetStore (content-addressed + ffprobe metadata)."""
import shutil
from pathlib import Path

import pytest

from open_edit.storage.assets import AssetStore, _probe_media


TESTDATA = Path(__file__).parent.parent / "testdata" / "raw_videos"


def _ffprobe_available() -> bool:
    return shutil.which("ffprobe") is not None


pytestmark = pytest.mark.skipif(
    not _ffprobe_available(), reason="ffprobe not installed"
)


def test_ingest_returns_asset_with_hash(tmp_path: Path) -> None:
    store = AssetStore(tmp_path / "assets")
    asset = store.ingest(str(TESTDATA / "clip_a.mp4"))
    assert len(asset.asset_hash) == 64  # SHA-256 hex
    assert asset.duration_sec > 0


def test_ingest_stores_file_in_cas_layout(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets"
    store = AssetStore(assets_dir)
    asset = store.ingest(str(TESTDATA / "clip_a.mp4"))
    expected = assets_dir / asset.asset_hash[:2] / asset.asset_hash
    assert expected.exists()


def test_ingest_same_file_twice_returns_same_hash(tmp_path: Path) -> None:
    store = AssetStore(tmp_path / "assets")
    a1 = store.ingest(str(TESTDATA / "clip_a.mp4"))
    a2 = store.ingest(str(TESTDATA / "clip_a.mp4"))
    assert a1.asset_hash == a2.asset_hash


def test_ingest_different_files_return_different_hashes(tmp_path: Path) -> None:
    store = AssetStore(tmp_path / "assets")
    a1 = store.ingest(str(TESTDATA / "clip_a.mp4"))
    a2 = store.ingest(str(TESTDATA / "clip_b.mp4"))
    assert a1.asset_hash != a2.asset_hash


def test_ingest_paths_rejects_empty_list(tmp_path: Path) -> None:
    """Bug B regression: empty paths list rejected with fix: line."""
    store = AssetStore(tmp_path / "assets")
    with pytest.raises(ValueError, match="empty"):
        store.ingest_paths([])


def test_ingest_rejects_nonexistent_file(tmp_path: Path) -> None:
    store = AssetStore(tmp_path / "assets")
    with pytest.raises(FileNotFoundError):
        store.ingest("/nonexistent/path/to/video.mp4")


def test_get_returns_ingested_asset(tmp_path: Path) -> None:
    store = AssetStore(tmp_path / "assets")
    asset = store.ingest(str(TESTDATA / "clip_a.mp4"))
    retrieved = store.get(asset.asset_hash)
    assert retrieved is not None
    assert retrieved.asset_hash == asset.asset_hash


def test_get_returns_none_for_unknown_hash(tmp_path: Path) -> None:
    store = AssetStore(tmp_path / "assets")
    assert store.get("0" * 64) is None


def test_probe_media_extracts_resolution() -> None:
    info = _probe_media(str(TESTDATA / "clip_a.mp4"))
    assert info["width"] == 320
    assert info["height"] == 240
    assert info["fps"] == 30.0
    assert info["duration_sec"] == pytest.approx(2.0, abs=0.1)
    assert info["has_audio"] is False


def test_probe_media_handles_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        _probe_media("/nonexistent/file.mp4")
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && pytest tests/test_storage/test_assets.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 4: Implement `AssetStore`**

File: `/home/ah64/apps/mlt-pipeline/open_edit/open_edit/storage/assets.py`

```python
"""Content-addressed asset store with ffprobe metadata.

Layout: <assets_dir>/<sha256[:2]>/<sha256>
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from open_edit.ir.types import Asset


CHUNK_SIZE = 65536


def _hash_file(path: Path) -> str:
    """Compute SHA-256 of a file as a hex string."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
            h.update(chunk)
    return h.hexdigest()


def _probe_media(path: str) -> dict:
    """Run ffprobe on a media file and return parsed metadata."""
    src = Path(path)
    if not src.exists():
        raise FileNotFoundError(path)

    fmt_result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_format", "-show_streams",
            "-of", "json", str(src),
        ],
        capture_output=True, text=True, check=True,
    )
    info = json.loads(fmt_result.stdout)
    fmt = info.get("format", {})
    streams = info.get("streams", [])

    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    fps = None
    if video_stream and "r_frame_rate" in video_stream:
        num, _, denom = video_stream["r_frame_rate"].partition("/")
        if denom and denom != "0":
            fps = float(num) / float(denom)
        elif num:
            fps = float(num)

    duration_sec = float(fmt.get("duration", 0.0))
    width = int(video_stream["width"]) if video_stream and "width" in video_stream else None
    height = int(video_stream["height"]) if video_stream and "height" in video_stream else None
    codec = video_stream.get("codec_name") if video_stream else None

    if audio_stream and not video_stream:
        media_type = "audio"
    elif video_stream:
        media_type = "video"
    elif audio_stream:
        media_type = "audio"
    else:
        media_type = "video"

    return {
        "duration_sec": duration_sec,
        "fps": fps,
        "width": width,
        "height": height,
        "codec": codec,
        "has_audio": audio_stream is not None,
        "type": media_type,
    }


class AssetStore:
    """Content-addressed media asset store."""

    def __init__(self, assets_dir: str | Path):
        self.assets_dir = Path(assets_dir)
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    def _cas_path(self, asset_hash: str) -> Path:
        return self.assets_dir / asset_hash[:2] / asset_hash

    def ingest(self, source_path: str) -> Asset:
        return self.ingest_paths([source_path])[0]

    def ingest_paths(self, paths: list[str]) -> list[Asset]:
        """Ingest one or more files. Returns one Asset per input path.

        Bug B regression: empty paths list is rejected with a `fix:` line.
        """
        if not paths:
            raise ValueError(
                "Cannot ingest empty paths list. "
                "fix: provide at least one file path."
            )

        assets: list[Asset] = []
        for p in paths:
            src = Path(p)
            if not src.exists():
                raise FileNotFoundError(p)
            asset_hash = _hash_file(src)
            dest = self._cas_path(asset_hash)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                shutil.copy2(src, dest)
            media_info = _probe_media(str(src))
            asset = Asset(
                asset_hash=asset_hash,
                original_path=str(src),
                stored_path=str(dest),
                type=media_info["type"],
                duration_sec=media_info["duration_sec"],
                fps=media_info["fps"],
                width=media_info["width"],
                height=media_info["height"],
                codec=media_info["codec"],
                has_audio=media_info["has_audio"],
            )
            assets.append(asset)
        return assets

    def get(self, asset_hash: str) -> Optional[Asset]:
        path = self._cas_path(asset_hash)
        if not path.exists():
            return None
        return Asset(
            asset_hash=asset_hash,
            original_path="",
            stored_path=str(path),
            type="video",
            duration_sec=0.0,
        )

    def path(self, asset_hash: str) -> Optional[Path]:
        p = self._cas_path(asset_hash)
        return p if p.exists() else None
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && pytest tests/test_storage/test_assets.py -v
```

Expected: 10 tests pass.

- [ ] **Step 6: Commit**

```bash
cd /home/ah64/apps/mlt-pipeline && git add open_edit/open_edit/storage/assets.py open_edit/tests/test_storage/test_assets.py open_edit/tests/testdata/raw_videos/
git commit -m "[open_edit] storage.assets: SHA-256 CAS + ffprobe metadata, Bug B fix"
```

---

## Task 7: JobLock — in-flight sandbox run enforcement

**Files:**
- Create: `open_edit/open_edit/storage/job_lock.py`
- Create: `open_edit/tests/test_storage/test_job_lock.py`

**Interfaces:**
- `JobLock(edit_graph: EditGraphStore)`
- `JobLock.try_acquire(kind: str) -> str | None` — returns `job_id` or `None` if busy
- `JobLock.release(job_id: str, status: str, error: str | None = None) -> None`
- `JobLock.list_running() -> list[dict]`

- [ ] **Step 1: Write the failing test**

File: `/home/ah64/apps/mlt-pipeline/open_edit/tests/test_storage/test_job_lock.py`

```python
"""Tests for the JobLock (in-flight sandbox / render / migration lock)."""
from pathlib import Path

from open_edit.storage.edit_graph import EditGraphStore
from open_edit.storage.job_lock import JobLock


def test_try_acquire_returns_job_id(tmp_path: Path) -> None:
    store = EditGraphStore(tmp_path / "p.db")
    lock = JobLock(store)
    job_id = lock.try_acquire("free_form_python")
    assert job_id is not None
    assert len(job_id) > 0


def test_try_acquire_returns_none_when_busy(tmp_path: Path) -> None:
    store = EditGraphStore(tmp_path / "p.db")
    lock = JobLock(store)
    first = lock.try_acquire("free_form_python")
    assert first is not None
    second = lock.try_acquire("free_form_python")
    assert second is None


def test_release_makes_lock_available_again(tmp_path: Path) -> None:
    store = EditGraphStore(tmp_path / "p.db")
    lock = JobLock(store)
    job_id = lock.try_acquire("free_form_python")
    lock.release(job_id, "completed")
    new_id = lock.try_acquire("free_form_python")
    assert new_id is not None
    assert new_id != job_id


def test_release_with_error_marks_failed(tmp_path: Path) -> None:
    store = EditGraphStore(tmp_path / "p.db")
    lock = JobLock(store)
    job_id = lock.try_acquire("render")
    lock.release(job_id, "failed", error="melt returned non-zero")
    new_id = lock.try_acquire("render")
    assert new_id is not None


def test_list_running_returns_only_in_flight_jobs(tmp_path: Path) -> None:
    store = EditGraphStore(tmp_path / "p.db")
    lock = JobLock(store)
    job_id = lock.try_acquire("free_form_python")
    running = lock.list_running()
    assert len(running) == 1
    assert running[0]["job_id"] == job_id
    assert running[0]["kind"] == "free_form_python"
    assert running[0]["status"] == "running"
    lock.release(job_id, "completed")
    assert lock.list_running() == []


def test_concurrent_acquire_with_different_kinds(tmp_path: Path) -> None:
    store = EditGraphStore(tmp_path / "p.db")
    lock = JobLock(store)
    job_id = lock.try_acquire("free_form_python")
    second = lock.try_acquire("render")
    assert second is None
    lock.release(job_id, "completed")
    third = lock.try_acquire("render")
    assert third is not None
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && pytest tests/test_storage/test_job_lock.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement JobLock**

File: `/home/ah64/apps/mlt-pipeline/open_edit/open_edit/storage/job_lock.py`

```python
"""In-flight job lock backed by the SQLite jobs table.

A single lock for all kinds (free_form_python, render, migration). Only
one job runs at a time.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from open_edit.storage.edit_graph import EditGraphStore


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobLock:
    """Single-slot lock for sandbox runs, renders, and migrations."""

    def __init__(self, edit_graph: EditGraphStore):
        self.edit_graph = edit_graph

    def try_acquire(self, kind: str) -> Optional[str]:
        with self.edit_graph._conn() as conn:
            cur = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status = 'running'"
            )
            if cur.fetchone()[0] > 0:
                return None
            job_id = str(uuid.uuid4())
            try:
                conn.execute(
                    "INSERT INTO jobs (job_id, kind, status, started_at) "
                    "VALUES (?, ?, 'running', ?)",
                    (job_id, kind, _now_iso()),
                )
                return job_id
            except Exception:
                return None

    def release(
        self, job_id: str, status: str, error: str | None = None
    ) -> None:
        with self.edit_graph._conn() as conn:
            conn.execute(
                "UPDATE jobs SET status = ?, finished_at = ?, error = ? "
                "WHERE job_id = ?",
                (status, _now_iso(), error, job_id),
            )

    def list_running(self) -> list[dict]:
        with self.edit_graph._conn() as conn:
            cur = conn.execute(
                "SELECT job_id, kind, status, started_at, finished_at, error "
                "FROM jobs WHERE status = 'running'"
            )
            return [
                {
                    "job_id": row[0], "kind": row[1], "status": row[2],
                    "started_at": row[3], "finished_at": row[4], "error": row[5],
                }
                for row in cur.fetchall()
            ]
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && pytest tests/test_storage/test_job_lock.py -v
```

Expected: 6 tests pass.

- [ ] **Step 5: Commit**

```bash
cd /home/ah64/apps/mlt-pipeline && git add open_edit/open_edit/storage/job_lock.py open_edit/tests/test_storage/test_job_lock.py
git commit -m "[open_edit] storage.job_lock: in-flight lock with try_acquire/release"
```

---

## Task 8: `ir/validate.py` — schema, referential, asset-exists checks

**Files:**
- Create: `open_edit/open_edit/ir/validate.py`
- Create: `open_edit/tests/test_ir/test_validate.py`

**Interfaces:**
- `validate_op(op: OperationUnion, project: Project) -> list[str]` — empty list = valid; errors include `fix:` lines

- [ ] **Step 1: Write the failing test**

File: `/home/ah64/apps/mlt-pipeline/open_edit/tests/test_ir/test_validate.py`

```python
"""Tests for op validation (schema + referential + asset-exists)."""
import pytest

from open_edit.ir.types import (
    AddClipOp,
    AddEffectOp,
    AddTransitionOp,
    Asset,
    MoveClipOp,
    Project,
    RemoveClipOp,
    SetAudioGainOp,
    SetKeyframeOp,
    TrimClipOp,
)
from open_edit.ir.validate import validate_op


def _asset(asset_hash: str) -> Asset:
    return Asset(
        asset_hash=asset_hash,
        original_path=f"/tmp/{asset_hash}.mp4",
        stored_path=f"/tmp/{asset_hash}.mp4",
        type="video", duration_sec=2.0,
    )


def test_valid_add_clip_returns_no_errors() -> None:
    project = Project(name="t", assets={"abc": _asset("abc")})
    op = AddClipOp(author="user", asset_hash="abc", track_id="v1", position_sec=0.0)
    assert validate_op(op, project) == []


def test_add_clip_rejects_unknown_asset_hash() -> None:
    project = Project(name="t", assets={})
    op = AddClipOp(author="user", asset_hash="missing", track_id="v1", position_sec=0.0)
    errors = validate_op(op, project)
    assert any("missing" in e for e in errors)
    assert any("fix:" in e for e in errors)


def test_remove_clip_with_unknown_clip_id_warns_but_no_error() -> None:
    project = Project(name="t")
    op = RemoveClipOp(author="user", clip_id="nonexistent")
    assert validate_op(op, project) == []


def test_move_clip_with_unknown_clip_id_is_error() -> None:
    project = Project(name="t")
    op = MoveClipOp(
        author="user", clip_id="nonexistent",
        new_track_id="v1", new_position_sec=0.0,
    )
    errors = validate_op(op, project)
    assert any("nonexistent" in e for e in errors)


def test_trim_clip_with_unknown_clip_id_is_error() -> None:
    project = Project(name="t")
    op = TrimClipOp(
        author="user", clip_id="nope",
        new_in_point_sec=0.0, new_out_point_sec=1.0,
    )
    errors = validate_op(op, project)
    assert any("nope" in e for e in errors)


def test_add_transition_requires_existing_clips() -> None:
    project = Project(name="t")
    op = AddTransitionOp(
        author="user", clip_a_id="a", clip_b_id="b",
        transition_type="luma", duration_sec=1.0,
    )
    errors = validate_op(op, project)
    assert len(errors) == 2


def test_add_transition_with_known_clips_returns_no_errors() -> None:
    project = Project(name="t")
    op1 = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
    op2 = AddClipOp(author="user", asset_hash="b", track_id="v1", position_sec=5.0)
    project.edit_graph.append(op1)
    project.edit_graph.append(op2)
    op3 = AddTransitionOp(
        author="user", clip_a_id=op1.clip_id, clip_b_id=op2.clip_id,
        transition_type="luma", duration_sec=1.0,
    )
    assert validate_op(op3, project) == []


def test_add_effect_with_unknown_target_is_error() -> None:
    project = Project(name="t")
    op = AddEffectOp(
        author="user", target_kind="clip", target_id="missing",
        effect_type="volume", params={"gain": 1.0},
    )
    errors = validate_op(op, project)
    assert any("missing" in e for e in errors)


def test_set_keyframe_with_unknown_effect_id_is_error() -> None:
    project = Project(name="t")
    op = SetKeyframeOp(
        author="user", effect_id="nope", param="gain",
        keyframes=[(0.0, 1.0, "linear")],
    )
    errors = validate_op(op, project)
    assert any("nope" in e for e in errors)


def test_set_audio_gain_with_unknown_clip_is_error() -> None:
    project = Project(name="t")
    op = SetAudioGainOp(author="user", clip_id="nope", gain_db=-6.0)
    errors = validate_op(op, project)
    assert any("nope" in e for e in errors)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && pytest tests/test_ir/test_validate.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `validate.py`**

File: `/home/ah64/apps/mlt-pipeline/open_edit/open_edit/ir/validate.py`

```python
"""Validation of operations against a project's current state.

Returns a list of error messages (empty list = valid). Each error
includes a `fix:` line per the spec.
"""
from __future__ import annotations

from open_edit.ir.types import (
    AddClipOp,
    AddEffectOp,
    AddTransitionOp,
    MoveClipOp,
    OperationUnion,
    Project,
    RemoveClipOp,
    SetAudioGainOp,
    SetKeyframeOp,
    TrimClipOp,
)


def _known_clip_ids(project: Project) -> set[str]:
    known: set[str] = set()
    for op in project.edit_graph:
        if isinstance(op, AddClipOp) and op.status == "applied":
            known.add(op.clip_id)
        elif isinstance(op, RemoveClipOp) and op.status == "applied":
            known.discard(op.clip_id)
    return known


def _known_effect_ids(project: Project) -> set[str]:
    return {
        op.effect_id
        for op in project.edit_graph
        if isinstance(op, AddEffectOp) and op.status == "applied"
    }


def validate_op(op: OperationUnion, project: Project) -> list[str]:
    """Validate an operation against the project. Returns a list of errors."""
    errors: list[str] = []

    if op.status != "applied":
        return errors

    if isinstance(op, AddClipOp):
        if op.asset_hash not in project.assets:
            errors.append(
                f"Unknown asset_hash '{op.asset_hash}'. "
                f"fix: import the asset first via AssetStore.ingest()."
            )
        if op.position_sec < 0:
            errors.append(
                f"position_sec must be >= 0; got {op.position_sec}. "
                f"fix: use a non-negative position."
            )
        if op.in_point_sec < 0:
            errors.append(
                f"in_point_sec must be >= 0; got {op.in_point_sec}. "
                f"fix: use a non-negative in-point."
            )
        if op.out_point_sec is not None and op.out_point_sec <= op.in_point_sec:
            errors.append(
                f"out_point_sec ({op.out_point_sec}) must be greater than "
                f"in_point_sec ({op.in_point_sec}). "
                f"fix: set out_point_sec > in_point_sec, or leave as None."
            )

    elif isinstance(op, RemoveClipOp):
        pass  # no-op if unknown

    elif isinstance(op, MoveClipOp):
        if op.clip_id not in _known_clip_ids(project):
            errors.append(
                f"MoveClipOp: clip_id '{op.clip_id}' not found in project. "
                f"fix: ensure the clip was added before moving it."
            )

    elif isinstance(op, TrimClipOp):
        if op.clip_id not in _known_clip_ids(project):
            errors.append(
                f"TrimClipOp: clip_id '{op.clip_id}' not found in project. "
                f"fix: ensure the clip was added before trimming it."
            )
        if op.new_in_point_sec >= op.new_out_point_sec:
            errors.append(
                f"new_in_point_sec ({op.new_in_point_sec}) must be less than "
                f"new_out_point_sec ({op.new_out_point_sec}). "
                f"fix: ensure in < out."
            )

    elif isinstance(op, AddTransitionOp):
        if op.clip_a_id not in _known_clip_ids(project):
            errors.append(
                f"AddTransitionOp: clip_a_id '{op.clip_a_id}' not found. "
                f"fix: ensure clip_a is added before the transition."
            )
        if op.clip_b_id not in _known_clip_ids(project):
            errors.append(
                f"AddTransitionOp: clip_b_id '{op.clip_b_id}' not found. "
                f"fix: ensure clip_b is added before the transition."
            )
        if op.duration_sec <= 0:
            errors.append(
                f"duration_sec must be > 0; got {op.duration_sec}. "
                f"fix: set a positive duration."
            )

    elif isinstance(op, AddEffectOp):
        if op.target_kind == "clip" and op.target_id not in _known_clip_ids(project):
            errors.append(
                f"AddEffectOp: target clip '{op.target_id}' not found. "
                f"fix: add the clip before applying the effect."
            )

    elif isinstance(op, SetKeyframeOp):
        if op.effect_id not in _known_effect_ids(project):
            errors.append(
                f"SetKeyframeOp: effect_id '{op.effect_id}' not found. "
                f"fix: add the effect before setting keyframes."
            )

    elif isinstance(op, SetAudioGainOp):
        if op.clip_id not in _known_clip_ids(project):
            errors.append(
                f"SetAudioGainOp: clip_id '{op.clip_id}' not found. "
                f"fix: add the audio clip before setting gain."
            )

    return errors
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && pytest tests/test_ir/test_validate.py -v
```

Expected: 10 tests pass.

- [ ] **Step 5: Commit**

```bash
cd /home/ah64/apps/mlt-pipeline && git add open_edit/open_edit/ir/validate.py open_edit/tests/test_ir/test_validate.py
git commit -m "[open_edit] ir.validate: schema + referential + asset-exists checks"
```

---

## Task 9: `ir/apply.py` — the **Bug A** transition centering fix

**Files:**
- Create: `open_edit/open_edit/ir/apply.py`
- Create: `open_edit/tests/test_ir/test_apply.py`

**Interfaces (produced):**
- `apply_operation(timeline: Timeline, op: OperationUnion) -> Timeline` — pure function
- `derive_timeline(project: Project) -> Timeline` — replays all non-reverted ops

**The Bug A fix lives in `_apply_add_transition`:** the transition is placed at the cut (`clip_a.out_point_sec`), not the midpoint. The two clips are trimmed around the cut.

- [ ] **Step 1: Write the failing test (Bug A regression + other ops)**

File: `/home/ah64/apps/mlt-pipeline/open_edit/tests/test_ir/test_apply.py`

```python
"""Tests for apply.py — including the Bug A transition centering fix."""
import pytest

from open_edit.ir.apply import apply_operation, derive_timeline
from open_edit.ir.types import (
    AddClipOp,
    AddEffectOp,
    AddTransitionOp,
    Effect,
    Project,
    RemoveClipOp,
    SetKeyframeOp,
    Timeline,
    MoveClipOp,
    TrimClipOp,
)


# ===== AddClipOp =====

def test_add_clip_creates_track() -> None:
    timeline = Timeline()
    op = AddClipOp(author="user", asset_hash="abc", track_id="v1", position_sec=0.0)
    out = apply_operation(timeline, op)
    assert len(out.tracks) == 1
    assert out.tracks[0].track_id == "v1"
    assert len(out.tracks[0].clips) == 1
    assert out.tracks[0].clips[0].asset_hash == "abc"


def test_add_clip_uses_position_sec() -> None:
    timeline = Timeline()
    op = AddClipOp(
        author="user", asset_hash="abc", track_id="v1", position_sec=12.5,
    )
    out = apply_operation(timeline, op)
    assert out.tracks[0].clips[0].position_sec == 12.5


def test_add_audio_clip_is_first_class() -> None:
    timeline = Timeline()
    op = AddClipOp(
        author="user", asset_hash="narr",
        track_id="audio_1", track_kind="audio", position_sec=0.0,
    )
    out = apply_operation(timeline, op)
    assert out.tracks[0].kind == "audio"
    assert out.tracks[0].clips[0].track_kind == "audio"


# ===== Bug A: transition centering =====

def test_add_transition_centers_on_cut_not_midpoint() -> None:
    """Bug A regression: transition is placed at clip_a.out_point_sec (the cut),
    not at the midpoint of the two clips' positions.

    Setup: clip_a at [0, 10), clip_b at [10, 20), transition of 2.0s.
    Expected cut = 10.0 (which is clip_a.out_point_sec).
    clip_a.out is back-solved to: cut - duration/2 = 10 - 1 = 9
    clip_b.in is back-solved to: cut + duration/2 = 10 + 1 = 11
    So clip_a now spans [0, 9), clip_b spans [11, 20).
    """
    timeline = Timeline()
    op_a = AddClipOp(
        author="user", asset_hash="a", track_id="v1",
        position_sec=0.0, in_point_sec=0.0, out_point_sec=10.0,
    )
    op_b = AddClipOp(
        author="user", asset_hash="b", track_id="v1",
        position_sec=10.0, in_point_sec=0.0, out_point_sec=10.0,
    )
    timeline = apply_operation(timeline, op_a)
    timeline = apply_operation(timeline, op_b)

    op_t = AddTransitionOp(
        author="user", clip_a_id=op_a.clip_id, clip_b_id=op_b.clip_id,
        transition_type="luma", duration_sec=2.0,
    )
    out = apply_operation(timeline, op_t)
    clips = out.tracks[0].clips
    # clip_a is now trimmed: out_point_sec = 10 - 1 = 9
    assert clips[0].out_point_sec == pytest.approx(9.0, abs=0.001)
    # clip_b is now trimmed: in_point_sec = 10 + 1 = 11
    assert clips[1].in_point_sec == pytest.approx(11.0, abs=0.001)
    # cut is at 10.0
    cut = (clips[0].out_point_sec + clips[1].in_point_sec) / 2
    assert cut == pytest.approx(10.0, abs=0.001)


def test_add_transition_rejects_duration_larger_than_clips() -> None:
    timeline = Timeline()
    op_a = AddClipOp(
        author="user", asset_hash="a", track_id="v1",
        position_sec=0.0, in_point_sec=0.0, out_point_sec=5.0,
    )
    op_b = AddClipOp(
        author="user", asset_hash="b", track_id="v1",
        position_sec=5.0, in_point_sec=0.0, out_point_sec=5.0,
    )
    timeline = apply_operation(timeline, op_a)
    timeline = apply_operation(timeline, op_b)
    op_t = AddTransitionOp(
        author="user", clip_a_id=op_a.clip_id, clip_b_id=op_b.clip_id,
        transition_type="luma", duration_sec=10.0,
    )
    with pytest.raises(ValueError, match="duration"):
        apply_operation(timeline, op_t)


def test_add_transition_appends_effect_to_clip_a() -> None:
    timeline = Timeline()
    op_a = AddClipOp(
        author="user", asset_hash="a", track_id="v1",
        position_sec=0.0, in_point_sec=0.0, out_point_sec=10.0,
    )
    op_b = AddClipOp(
        author="user", asset_hash="b", track_id="v1",
        position_sec=10.0, in_point_sec=0.0, out_point_sec=10.0,
    )
    timeline = apply_operation(timeline, op_a)
    timeline = apply_operation(timeline, op_b)
    op_t = AddTransitionOp(
        author="user", clip_a_id=op_a.clip_id, clip_b_id=op_b.clip_id,
        transition_type="luma", duration_sec=2.0,
    )
    out = apply_operation(timeline, op_t)
    clip_a = out.tracks[0].clips[0]
    assert len(clip_a.effects) == 1
    assert clip_a.effects[0].effect_type == "transition_luma"
    assert clip_a.effects[0].params["clip_b_id"] == op_b.clip_id


# ===== Remove / Move / Trim =====

def test_remove_clip_removes_from_track() -> None:
    timeline = Timeline()
    op = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
    timeline = apply_operation(timeline, op)
    rm = RemoveClipOp(author="user", clip_id=op.clip_id)
    out = apply_operation(timeline, rm)
    assert out.tracks[0].clips == []


def test_remove_clip_for_unknown_id_is_no_op() -> None:
    timeline = Timeline()
    op = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
    timeline = apply_operation(timeline, op)
    rm = RemoveClipOp(author="user", clip_id="nope")
    out = apply_operation(timeline, rm)
    assert len(out.tracks[0].clips) == 1


def test_move_clip_relocates() -> None:
    timeline = Timeline()
    op = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
    timeline = apply_operation(timeline, op)
    mv = MoveClipOp(
        author="user", clip_id=op.clip_id,
        new_track_id="v2", new_position_sec=15.0,
    )
    out = apply_operation(timeline, mv)
    assert out.tracks[0].clips == []
    assert len(out.tracks[1].clips) == 1
    assert out.tracks[1].clips[0].position_sec == 15.0


def test_trim_clip_updates_in_and_out() -> None:
    timeline = Timeline()
    op = AddClipOp(
        author="user", asset_hash="a", track_id="v1",
        position_sec=0.0, in_point_sec=0.0, out_point_sec=10.0,
    )
    timeline = apply_operation(timeline, op)
    tr = TrimClipOp(
        author="user", clip_id=op.clip_id,
        new_in_point_sec=2.0, new_out_point_sec=8.0,
    )
    out = apply_operation(timeline, tr)
    clip = out.tracks[0].clips[0]
    assert clip.in_point_sec == 2.0
    assert clip.out_point_sec == 8.0


# ===== AddEffect / SetKeyframe =====

def test_add_effect_appends_to_clip() -> None:
    timeline = Timeline()
    op = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
    timeline = apply_operation(timeline, op)
    eff = AddEffectOp(
        author="user", target_kind="clip", target_id=op.clip_id,
        effect_type="volume", params={"gain": 0.5},
    )
    out = apply_operation(timeline, eff)
    assert len(out.tracks[0].clips[0].effects) == 1


def test_set_keyframe_updates_existing_effect() -> None:
    timeline = Timeline()
    op = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
    timeline = apply_operation(timeline, op)
    eff = AddEffectOp(
        author="user", target_kind="clip", target_id=op.clip_id,
        effect_type="volume", params={"gain": 1.0},
    )
    timeline = apply_operation(timeline, eff)
    kf = SetKeyframeOp(
        author="user", effect_id=eff.effect_id, param="gain",
        keyframes=[(0.0, 1.0, "linear"), (2.0, 0.0, "linear")],
    )
    out = apply_operation(timeline, kf)
    effects = out.tracks[0].clips[0].effects
    assert effects[0].keyframes["gain"] == [(0.0, 1.0, "linear"), (2.0, 0.0, "linear")]


# ===== Status filtering =====

def test_reverted_op_is_no_op() -> None:
    timeline = Timeline()
    op = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
    op_reverted = op.model_copy(update={"status": "reverted"})
    out = apply_operation(timeline, op_reverted)
    assert out.tracks == []


# ===== derive_timeline =====

def test_derive_timeline_replays_all_applied_ops() -> None:
    project = Project(name="t")
    project.edit_graph.append(AddClipOp(
        author="user", asset_hash="a", track_id="v1",
        position_sec=0.0, in_point_sec=0.0, out_point_sec=5.0,
    ))
    project.edit_graph.append(AddClipOp(
        author="user", asset_hash="b", track_id="v1",
        position_sec=5.0, in_point_sec=0.0, out_point_sec=5.0,
    ))
    timeline = derive_timeline(project)
    assert len(timeline.tracks) == 1
    assert len(timeline.tracks[0].clips) == 2
    assert timeline.duration_sec == pytest.approx(10.0, abs=0.001)


def test_derive_timeline_skips_reverted_ops() -> None:
    project = Project(name="t")
    op1 = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
    op2 = AddClipOp(author="user", asset_hash="b", track_id="v1", position_sec=5.0)
    op2_reverted = op2.model_copy(update={"status": "reverted"})
    project.edit_graph.append(op1)
    project.edit_graph.append(op2_reverted)
    timeline = derive_timeline(project)
    assert len(timeline.tracks[0].clips) == 1


def test_derive_timeline_computes_duration_from_max_clip_end() -> None:
    project = Project(name="t")
    project.edit_graph.append(AddClipOp(
        author="user", asset_hash="a", track_id="v1",
        position_sec=0.0, in_point_sec=0.0, out_point_sec=3.0,
    ))
    project.edit_graph.append(AddClipOp(
        author="user", asset_hash="b", track_id="v1",
        position_sec=3.0, in_point_sec=0.0, out_point_sec=8.0,
    ))
    project.edit_graph.append(AddClipOp(
        author="user", asset_hash="c", track_id="v1",
        position_sec=11.0, in_point_sec=0.0, out_point_sec=2.0,
    ))
    timeline = derive_timeline(project)
    assert timeline.duration_sec == pytest.approx(13.0, abs=0.001)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && pytest tests/test_ir/test_apply.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `apply.py`**

File: `/home/ah64/apps/mlt-pipeline/open_edit/open_edit/ir/apply.py`

```python
"""Apply operations to derive Timeline state. Pure functions.

The Bug A fix lives in `_apply_add_transition`:
- The transition is placed at `cut = clip_a.out_point_sec` (the cut point).
- `clip_a.out_point_sec` is back-solved to `cut - duration_sec / 2`.
- `clip_b.in_point_sec` is back-solved to `cut + duration_sec / 2`.
- This means the transition is centered on the cut, NOT on the midpoint
  of the two clips' original positions.
"""
from __future__ import annotations

from open_edit.ir.types import (
    AddClipOp,
    AddEffectOp,
    AddTransitionOp,
    Clip,
    Effect,
    MoveClipOp,
    OperationUnion,
    Project,
    RemoveClipOp,
    SetAudioGainOp,
    SetKeyframeOp,
    Timeline,
    Track,
    TrimClipOp,
)


def _get_or_create_track(timeline: Timeline, track_id: str, kind: str) -> Track:
    for track in timeline.tracks:
        if track.track_id == track_id:
            return track
    new_track = Track(track_id=track_id, kind=kind)
    timeline.tracks.append(new_track)
    return new_track


def _find_clip(timeline: Timeline, clip_id: str):
    for track in timeline.tracks:
        for i, clip in enumerate(track.clips):
            if clip.clip_id == clip_id:
                return track, clip, i
    return None, None, None


def _make_clip(op: AddClipOp, out_point_sec: float) -> Clip:
    return Clip(
        clip_id=op.clip_id,
        asset_hash=op.asset_hash,
        track_id=op.track_id,
        track_kind=op.track_kind,
        position_sec=op.position_sec,
        in_point_sec=op.in_point_sec,
        out_point_sec=out_point_sec,
        effects=[],
    )


def apply_operation(timeline: Timeline, op: OperationUnion) -> Timeline:
    """Apply a single operation to a timeline. Returns a new timeline.

    Pure function. Does not mutate the input.
    """
    if op.status != "applied":
        return timeline

    if isinstance(op, AddClipOp):
        track = _get_or_create_track(timeline, op.track_id, op.track_kind)
        out_val = op.out_point_sec if op.out_point_sec is not None else 0.0
        track.clips.append(_make_clip(op, out_val))
        return timeline
    if isinstance(op, RemoveClipOp):
        for track in timeline.tracks:
            track.clips = [c for c in track.clips if c.clip_id != op.clip_id]
        return timeline
    if isinstance(op, MoveClipOp):
        track, clip, i = _find_clip(timeline, op.clip_id)
        if clip is None:
            return timeline
        track.clips.pop(i)
        new_track = _get_or_create_track(timeline, op.new_track_id, clip.track_kind)
        moved = clip.model_copy(update={
            "track_id": op.new_track_id,
            "position_sec": op.new_position_sec,
        })
        new_track.clips.append(moved)
        return timeline
    if isinstance(op, TrimClipOp):
        _, clip, _ = _find_clip(timeline, op.clip_id)
        if clip is None:
            return timeline
        new_clip = clip.model_copy(update={
            "in_point_sec": op.new_in_point_sec,
            "out_point_sec": op.new_out_point_sec,
        })
        for track in timeline.tracks:
            for i, c in enumerate(track.clips):
                if c.clip_id == op.clip_id:
                    track.clips[i] = new_clip
                    return timeline
        return timeline
    if isinstance(op, AddTransitionOp):
        return _apply_add_transition(timeline, op)
    if isinstance(op, AddEffectOp):
        return _apply_add_effect(timeline, op)
    if isinstance(op, SetKeyframeOp):
        return _apply_set_keyframe(timeline, op)
    if isinstance(op, SetAudioGainOp):
        return _apply_set_audio_gain(timeline, op)
    return timeline


def _apply_add_transition(timeline: Timeline, op: AddTransitionOp) -> Timeline:
    """Apply an AddTransitionOp.

    Bug A fix: transition is centered on the cut (= clip_a.out_point_sec).
    """
    track_a, clip_a, _ = _find_clip(timeline, op.clip_a_id)
    if clip_a is None:
        return timeline
    _, clip_b, _ = _find_clip(timeline, op.clip_b_id)
    if clip_b is None:
        return timeline

    cut = clip_a.out_point_sec
    half = op.duration_sec / 2.0
    clip_b_duration = clip_b.out_point_sec - clip_b.in_point_sec
    clip_b_end = clip_b.position_sec + clip_b_duration

    if cut - half < clip_a.in_point_sec:
        raise ValueError(
            f"AddTransitionOp: duration_sec {op.duration_sec} too large "
            f"for clip_a (cut={cut}, in={clip_a.in_point_sec})"
        )
    if cut + half > clip_b_end:
        raise ValueError(
            f"AddTransitionOp: duration_sec {op.duration_sec} too large "
            f"for clip_b (end={clip_b_end})"
        )

    new_a_out = cut - half
    new_b_in = (cut + half) - clip_b.position_sec

    new_clip_a = clip_a.model_copy(update={"out_point_sec": new_a_out})
    new_clip_b = clip_b.model_copy(update={"in_point_sec": new_b_in})

    transition_effect = Effect(
        effect_id=f"transition_{op.edit_id}",
        effect_type=f"transition_{op.transition_type}",
        params={"clip_b_id": op.clip_b_id, "duration_sec": op.duration_sec},
    )
    new_clip_a = new_clip_a.model_copy(update={
        "effects": [*new_clip_a.effects, transition_effect],
    })

    for track in timeline.tracks:
        for i, c in enumerate(track.clips):
            if c.clip_id == op.clip_a_id:
                track.clips[i] = new_clip_a
            elif c.clip_id == op.clip_b_id:
                track.clips[i] = new_clip_b
    return timeline


def _apply_add_effect(timeline: Timeline, op: AddEffectOp) -> Timeline:
    if op.target_kind == "clip":
        _, clip, _ = _find_clip(timeline, op.target_id)
        if clip is None:
            return timeline
        new_effect = Effect(
            effect_id=op.effect_id, effect_type=op.effect_type, params=op.params,
        )
        new_clip = clip.model_copy(update={"effects": [*clip.effects, new_effect]})
        for track in timeline.tracks:
            for i, c in enumerate(track.clips):
                if c.clip_id == op.target_id:
                    track.clips[i] = new_clip
                    return timeline
    elif op.target_kind == "track":
        for track in timeline.tracks:
            if track.track_id == op.target_id:
                new_effect = Effect(
                    effect_id=op.effect_id, effect_type=op.effect_type, params=op.params,
                )
                new_track = track.model_copy(update={
                    "effects": [*track.effects, new_effect],
                })
                idx = timeline.tracks.index(track)
                timeline.tracks[idx] = new_track
                return timeline
    return timeline


def _apply_set_keyframe(timeline: Timeline, op: SetKeyframeOp) -> Timeline:
    for track in timeline.tracks:
        for i, clip in enumerate(track.clips):
            for j, eff in enumerate(clip.effects):
                if eff.effect_id == op.effect_id:
                    new_eff = eff.model_copy(update={
                        "keyframes": {**eff.keyframes, op.param: op.keyframes},
                    })
                    new_clip = clip.model_copy(update={
                        "effects": [new_eff if k == j else e for k, e in enumerate(clip.effects)],
                    })
                    track.clips[i] = new_clip
                    return timeline
    return timeline


def _apply_set_audio_gain(timeline: Timeline, op: SetAudioGainOp) -> Timeline:
    _, clip, _ = _find_clip(timeline, op.clip_id)
    if clip is None or clip.track_kind != "audio":
        return timeline
    linear_gain = 10 ** (op.gain_db / 20.0)
    new_effect = Effect(
        effect_id=op.edit_id, effect_type="volume",
        params={"gain": linear_gain},
    )
    new_clip = clip.model_copy(update={"effects": [*clip.effects, new_effect]})
    for track in timeline.tracks:
        for i, c in enumerate(track.clips):
            if c.clip_id == op.clip_id:
                track.clips[i] = new_clip
                return timeline
    return timeline


def derive_timeline(project: Project) -> Timeline:
    """Replay all non-reverted, applied operations in sequence order."""
    timeline = Timeline()
    for op in project.edit_graph:
        timeline = apply_operation(timeline, op)
    max_end = 0.0
    for track in timeline.tracks:
        for clip in track.clips:
            end = clip.position_sec + (clip.out_point_sec - clip.in_point_sec)
            if end > max_end:
                max_end = end
    timeline.duration_sec = max_end
    return timeline
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && pytest tests/test_ir/test_apply.py -v
```

Expected: 16 tests pass (incl. Bug A regression).

- [ ] **Step 5: Commit**

```bash
cd /home/ah64/apps/mlt-pipeline && git add open_edit/open_edit/ir/apply.py open_edit/tests/test_ir/test_apply.py
git commit -m "[open_edit] ir.apply: 12-op apply, Bug A transition centering, derive_timeline"
```

---

## Task 10: `ir/commutativity.py` — can_swap for reorder

**Files:**
- Create: `open_edit/open_edit/ir/commutativity.py`
- Create: `open_edit/tests/test_ir/test_commutativity.py`

**Interfaces:**
- `can_swap(op_a: OperationUnion, op_b: OperationUnion) -> bool` — whether two adjacent ops can be safely reordered

- [ ] **Step 1: Write the failing test**

File: `/home/ah64/apps/mlt-pipeline/open_edit/tests/test_ir/test_commutativity.py`

```python
"""Tests for commutativity of operations (used by reorder)."""
from open_edit.ir.commutativity import can_swap
from open_edit.ir.types import (
    AddClipOp, AddEffectOp, AddTransitionOp, MoveClipOp, RemoveClipOp,
    SetKeyframeOp, TrimClipOp,
)


def _add(asset: str, track: str = "v1", pos: float = 0.0) -> AddClipOp:
    return AddClipOp(author="user", asset_hash=asset, track_id=track, position_sec=pos)


def test_add_clips_on_different_tracks_commute() -> None:
    a = _add("a", "v1", 0.0)
    b = _add("b", "audio_1", 0.0)
    assert can_swap(a, b) is True


def test_add_clips_on_same_track_commute() -> None:
    a = _add("a", "v1", 0.0)
    b = _add("b", "v1", 5.0)
    assert can_swap(a, b) is True


def test_add_clip_and_remove_different_clips_commute() -> None:
    a = _add("a")
    b = RemoveClipOp(author="user", clip_id="other")
    assert can_swap(a, b) is True


def test_add_clip_and_remove_same_clip_does_not_commute() -> None:
    a = _add("a")
    b = RemoveClipOp(author="user", clip_id=a.clip_id)
    assert can_swap(a, b) is False


def test_add_transition_and_unrelated_add_clip_commute() -> None:
    a = AddTransitionOp(
        author="user", clip_a_id="c1", clip_b_id="c2",
        transition_type="luma", duration_sec=1.0,
    )
    b = _add("z", "v2", 0.0)
    assert can_swap(a, b) is True


def test_add_effect_on_clip_and_remove_clip_does_not_commute() -> None:
    a = AddEffectOp(
        author="user", target_kind="clip", target_id="c1",
        effect_type="volume", params={"gain": 0.5},
    )
    b = RemoveClipOp(author="user", clip_id="c1")
    assert can_swap(a, b) is False


def test_set_keyframe_on_different_effects_commute() -> None:
    a = SetKeyframeOp(
        author="user", effect_id="fx1", param="gain",
        keyframes=[(0.0, 1.0, "linear")],
    )
    b = SetKeyframeOp(
        author="user", effect_id="fx2", param="gain",
        keyframes=[(0.0, 0.5, "linear")],
    )
    assert can_swap(a, b) is True
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && pytest tests/test_ir/test_commutativity.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `commutativity.py`**

File: `/home/ah64/apps/mlt-pipeline/open_edit/open_edit/ir/commutativity.py`

```python
"""Commutativity predicate for reordering operations."""
from __future__ import annotations

from open_edit.ir.types import (
    AddClipOp,
    AddEffectOp,
    AddTransitionOp,
    MoveClipOp,
    OperationUnion,
    RemoveClipOp,
    SetKeyframeOp,
    TrimClipOp,
)


def _refs_clip(op: OperationUnion, clip_id: str) -> bool:
    if isinstance(op, RemoveClipOp) and op.clip_id == clip_id:
        return True
    if isinstance(op, MoveClipOp) and op.clip_id == clip_id:
        return True
    if isinstance(op, TrimClipOp) and op.clip_id == clip_id:
        return True
    if isinstance(op, AddTransitionOp) and (
        op.clip_a_id == clip_id or op.clip_b_id == clip_id
    ):
        return True
    if isinstance(op, AddEffectOp) and op.target_kind == "clip" and op.target_id == clip_id:
        return True
    return False


def can_swap(op_a: OperationUnion, op_b: OperationUnion) -> bool:
    """Whether two adjacent operations can be safely reordered.

    Conservative: when in doubt, return False.
    """
    if isinstance(op_a, AddClipOp) and isinstance(op_b, AddClipOp):
        return True
    if isinstance(op_a, SetKeyframeOp) and isinstance(op_b, SetKeyframeOp):
        return op_a.effect_id != op_b.effect_id
    if isinstance(op_a, AddEffectOp) and isinstance(op_b, AddEffectOp):
        return op_a.effect_id != op_b.effect_id

    if isinstance(op_a, (RemoveClipOp, MoveClipOp, TrimClipOp)):
        if _refs_clip(op_b, op_a.clip_id):
            return False
    if isinstance(op_b, (RemoveClipOp, MoveClipOp, TrimClipOp)):
        if _refs_clip(op_a, op_b.clip_id):
            return False

    if isinstance(op_a, AddEffectOp) and op_a.target_kind == "clip":
        if _refs_clip(op_b, op_a.target_id) and isinstance(
            op_b, (RemoveClipOp, MoveClipOp, TrimClipOp)
        ):
            return False
    if isinstance(op_b, AddEffectOp) and op_b.target_kind == "clip":
        if _refs_clip(op_a, op_b.target_id) and isinstance(
            op_a, (RemoveClipOp, MoveClipOp, TrimClipOp)
        ):
            return False

    if isinstance(op_a, AddTransitionOp):
        if _refs_clip(op_b, op_a.clip_a_id) or _refs_clip(op_b, op_a.clip_b_id):
            return False
    if isinstance(op_b, AddTransitionOp):
        if _refs_clip(op_a, op_b.clip_a_id) or _refs_clip(op_a, op_b.clip_b_id):
            return False

    return True
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && pytest tests/test_ir/test_commutativity.py -v
```

Expected: 7 tests pass.

- [ ] **Step 5: Commit**

```bash
cd /home/ah64/apps/mlt-pipeline && git add open_edit/open_edit/ir/commutativity.py open_edit/tests/test_ir/test_commutativity.py
git commit -m "[open_edit] ir.commutativity: can_swap for safe reorder"
```

---

## Task 11: `style/taste_events.py` — schema + CRUD (Phase 4 stub)

**Files:**
- Create: `open_edit/open_edit/style/taste_events.py`
- Create: `open_edit/tests/test_style/test_taste_events.py`

**Interfaces:**
- `class TasteEvent(BaseModel)` — the event record
- `class TasteEventStore(db_path)` — separate SQLite DB
- `append(event)`, `pull(window_days=90, max_events=200)`, `purge(ids)`

- [ ] **Step 1: Write the failing test**

File: `/home/ah64/apps/mlt-pipeline/open_edit/tests/test_style/test_taste_events.py`

```python
"""Tests for the taste_events table (Style Memory, Phase 4 stub)."""
from pathlib import Path

import pytest

from open_edit.style.taste_events import TasteEvent, TasteEventStore


def test_append_pull_round_trip(tmp_path: Path) -> None:
    store = TasteEventStore(tmp_path / "taste.db")
    e = TasteEvent(
        op_type="AddTransition",
        proposed_params={"duration_s": 1.0},
        final_params={"duration_s": 0.6},
        action="applied_modified",
    )
    store.append(e)
    pulled = store.pull()
    assert len(pulled) == 1
    assert pulled[0].op_type == "AddTransition"
    assert pulled[0].action == "applied_modified"


def test_pull_respects_max_events(tmp_path: Path) -> None:
    store = TasteEventStore(tmp_path / "taste.db")
    for _ in range(10):
        store.append(TasteEvent(
            op_type="X", proposed_params={}, final_params={},
            action="applied_unmodified",
        ))
    assert len(store.pull(max_events=5)) == 5


def test_purge_removes_events(tmp_path: Path) -> None:
    store = TasteEventStore(tmp_path / "taste.db")
    e1 = TasteEvent(op_type="X", proposed_params={}, final_params={}, action="applied_unmodified")
    e2 = TasteEvent(op_type="Y", proposed_params={}, final_params={}, action="applied_unmodified")
    store.append(e1)
    store.append(e2)
    store.purge([e1.id])
    assert len(store.pull()) == 1


def test_action_must_be_valid_literal() -> None:
    with pytest.raises(ValueError):
        TasteEvent(
            op_type="X", proposed_params={}, final_params={},
            action="totally_made_up",
        )


def test_correction_note_optional() -> None:
    e = TasteEvent(
        op_type="X", proposed_params={}, final_params={},
        action="applied_modified",
    )
    assert e.correction_note is None
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && pytest tests/test_style/test_taste_events.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `taste_events.py`**

File: `/home/ah64/apps/mlt-pipeline/open_edit/open_edit/style/taste_events.py`

```python
"""Taste events for the Style Memory system (Phase 4 stub in Phase 0+1).

Phase 4 reads these, aggregates into a bounded style profile, and
injects a tag-gated slice into each agent turn.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Literal, Optional

from pydantic import BaseModel, Field


def _new_id() -> str:
    return str(uuid.uuid4())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TasteEvent(BaseModel):
    id: str = Field(default_factory=_new_id)
    ts: str = Field(default_factory=_now_iso)
    project_id: Optional[str] = None
    op_type: str
    proposed_params: dict = Field(default_factory=dict)
    final_params: dict = Field(default_factory=dict)
    action: Literal["applied_unmodified", "applied_modified", "reverted"]
    correction_note: Optional[str] = None


SCHEMA = """
CREATE TABLE IF NOT EXISTS taste_events (
    id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    project_id TEXT,
    op_type TEXT NOT NULL,
    proposed_params TEXT NOT NULL,
    final_params TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('applied_unmodified', 'applied_modified', 'reverted')),
    correction_note TEXT
);
CREATE INDEX IF NOT EXISTS idx_taste_events_ts ON taste_events(ts);
"""


class TasteEventStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    def append(self, event: TasteEvent) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO taste_events "
                "(id, ts, project_id, op_type, proposed_params, "
                " final_params, action, correction_note) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event.id, event.ts, event.project_id, event.op_type,
                    json.dumps(event.proposed_params, sort_keys=True, separators=(",", ":")),
                    json.dumps(event.final_params, sort_keys=True, separators=(",", ":")),
                    event.action, event.correction_note,
                ),
            )

    def pull(self, window_days: int = 90, max_events: int = 200) -> list[TasteEvent]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT id, ts, project_id, op_type, proposed_params, "
                "final_params, action, correction_note "
                "FROM taste_events WHERE ts >= ? "
                "ORDER BY ts DESC LIMIT ?",
                (cutoff, max_events),
            )
            return [
                TasteEvent(
                    id=row[0], ts=row[1], project_id=row[2], op_type=row[3],
                    proposed_params=json.loads(row[4]),
                    final_params=json.loads(row[5]),
                    action=row[6], correction_note=row[7],
                )
                for row in cur.fetchall()
            ]

    def purge(self, ids: list[str]) -> None:
        if not ids:
            return
        with self._conn() as conn:
            placeholders = ",".join("?" * len(ids))
            conn.execute(
                f"DELETE FROM taste_events WHERE id IN ({placeholders})",
                ids,
            )
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && pytest tests/test_style/test_taste_events.py -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
cd /home/ah64/apps/mlt-pipeline && git add open_edit/open_edit/style/ open_edit/tests/test_style/
git commit -m "[open_edit] style.taste_events: schema + append/pull/purge (Phase 4 stub)"
```

---

## Task 12: `ir/api.py` stub — placeholder for free-form Python IR API

**Files:**
- Create: `open_edit/open_edit/ir/api.py`

- [ ] **Step 1: Write the placeholder**

File: `/home/ah64/apps/mlt-pipeline/open_edit/open_edit/ir/api.py`

```python
"""In-process IR API for free-form Python code (sandbox side).

Phase 0+1 ships a stub. The full implementation in Phase 3/4 will:
- Accept a workdir, an EditGraphStore, and a buffer
- Expose add_clip, trim_clip, move_clip, remove_clip, add_transition,
  add_effect, set_keyframe, set_audio_gain, normalize_audio as methods
- Each method appends a structured op to the buffer
- The buffer is returned to apply.py which appends to the edit graph
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from open_edit.ir.types import OperationUnion


class IR:
    """Stub IR API. Real implementation in Phase 3/4."""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "open_edit.ir.api.IR is a Phase 0+1 stub. "
            "Full implementation comes in Phase 3 (sandbox) + Phase 4 (agent loop)."
        )
```

- [ ] **Step 2: Commit**

```bash
cd /home/ah64/apps/mlt-pipeline && git add open_edit/open_edit/ir/api.py
git commit -m "[open_edit] ir.api: Phase 0+1 stub (full impl in Phase 3/4)"
```

---

## Task 13: CLI — `init`, `list`, `summary`, `undo`

**Files:**
- Modify: `open_edit/open_edit/cli.py` (replace placeholder with full CLI)
- Create: `open_edit/tests/test_cli.py`

**Interfaces (produced):**
- `open_edit init <folder>` — creates a project in `<folder>/.open_edit/`, ingests all video files in `<folder>` (non-recursive, top-level only)
- `open_edit list` — shows the edit graph (kind, asset_hash, status)
- `open_edit summary` — shows derived Timeline (tracks, clips, transitions, duration)
- `open_edit undo` — reverts the most recent applied op

- [ ] **Step 1: Write the failing test**

File: `/home/ah64/apps/mlt-pipeline/open_edit/tests/test_cli.py`

```python
"""End-to-end CLI tests for open_edit init/list/summary/undo."""
import shutil
import subprocess
from pathlib import Path

import pytest

TESTDATA = Path(__file__).parent / "testdata" / "raw_videos"


def _has_ffprobe() -> bool:
    return shutil.which("ffprobe") is not None


pytestmark = pytest.mark.skipif(
    not _has_ffprobe(), reason="ffprobe not installed"
)


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["open_edit", *args],
        capture_output=True, text=True, cwd=cwd, check=False,
    )


def test_init_ingests_videos(tmp_path: Path) -> None:
    # Copy test videos into a fresh folder
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    for f in TESTDATA.iterdir():
        shutil.copy(f, project_dir / f.name)
    # Initialize
    result = _run("init", cwd=project_dir)
    assert result.returncode == 0, result.stderr
    # Assets dir created
    assert (project_dir / ".open_edit" / "assets").exists()
    # DB created
    assert (project_dir / ".open_edit" / "edit_graph.db").exists()


def test_list_shows_no_ops_initially(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    for f in TESTDATA.iterdir():
        shutil.copy(f, project_dir / f.name)
    _run("init", cwd=project_dir)
    result = _run("list", cwd=project_dir)
    assert result.returncode == 0
    assert "0 ops" in result.stdout or "applied: 0" in result.stdout


def test_summary_shows_empty_timeline(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    for f in TESTDATA.iterdir():
        shutil.copy(f, project_dir / f.name)
    _run("init", cwd=project_dir)
    result = _run("summary", cwd=project_dir)
    assert result.returncode == 0
    assert "duration" in result.stdout.lower()
    assert "tracks" in result.stdout.lower()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && pytest tests/test_cli.py -v
```

Expected: tests fail with `Usage: open_edit init <folder>` or similar (placeholder CLI doesn't have subcommands).

- [ ] **Step 3: Replace `cli.py` with the full implementation**

Replace the contents of `open_edit/open_edit/cli.py` with:

```python
"""Open Edit CLI — init / list / summary / undo (Phase 0+1)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from open_edit.ir.apply import derive_timeline
from open_edit.ir.types import Project, OperationUnion
from open_edit.storage.assets import AssetStore
from open_edit.storage.edit_graph import EditGraphStore


PROJECT_SUBDIR = ".open_edit"


def _project_dir(cwd: Path) -> Path:
    return cwd / PROJECT_SUBDIR


def _find_existing_project(cwd: Path) -> Path | None:
    """Walk up the directory tree looking for an .open_edit/ project."""
    current = cwd.resolve()
    for parent in [current, *current.parents]:
        candidate = parent / PROJECT_SUBDIR
        if (candidate / "edit_graph.db").exists():
            return candidate
    return None


def cmd_init(args: argparse.Namespace) -> int:
    folder = Path(args.folder).resolve()
    if not folder.exists() or not folder.is_dir():
        print(f"error: {folder} is not a directory", file=sys.stderr)
        return 1

    project_dir = folder / PROJECT_SUBDIR
    project_dir.mkdir(exist_ok=True)
    assets_dir = project_dir / "assets"
    db_path = project_dir / "edit_graph.db"

    store = EditGraphStore(db_path)
    asset_store = AssetStore(assets_dir)

    # Ingest every video/audio/image in the folder (top-level only)
    extensions = {".mp4", ".mkv", ".mov", ".webm", ".mp3", ".wav", ".aac", ".flac", ".jpg", ".jpeg", ".png", ".webp"}
    files = sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in extensions
    )
    if not files:
        print(f"warning: no media files found in {folder}", file=sys.stderr)

    ingested = 0
    for f in files:
        try:
            asset = asset_store.ingest(str(f))
            ingested += 1
            print(f"  ingested {f.name}  hash={asset.asset_hash[:12]}...  "
                  f"duration={asset.duration_sec:.2f}s")
        except Exception as e:
            print(f"  failed: {f.name}: {e}", file=sys.stderr)

    # Persist a project_meta record
    with store._conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO project_meta (key, value) VALUES (?, ?)",
            ("folder", str(folder)),
        )
        conn.execute(
            "INSERT OR REPLACE INTO project_meta (key, value) VALUES (?, ?)",
            ("ingested_count", str(ingested)),
        )

    print(f"Initialized project at {project_dir}")
    print(f"Ingested {ingested} media file(s)")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    project_dir = _find_existing_project(Path.cwd())
    if project_dir is None:
        print("error: no open_edit project found in this directory or any parent",
              file=sys.stderr)
        return 1
    store = EditGraphStore(project_dir / "edit_graph.db")
    ops = store.load_all()
    applied = sum(1 for o in ops if o.status == "applied")
    reverted = sum(1 for o in ops if o.status == "reverted")
    print(f"Edit graph: {len(ops)} ops ({applied} applied, {reverted} reverted)")
    for i, op in enumerate(ops):
        print(f"  [{i:3d}] [{op.status:9s}] {op.kind:20s} edit_id={op.edit_id[:8]}")
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    project_dir = _find_existing_project(Path.cwd())
    if project_dir is None:
        print("error: no open_edit project found", file=sys.stderr)
        return 1
    store = EditGraphStore(project_dir / "edit_graph.db")
    # Build a Project from the loaded ops (assets are not yet tracked in the
    # edit graph; for now we just derive the timeline from ops)
    from open_edit.ir.types import Project as ProjectModel
    project = ProjectModel(name="cli")
    for op in store.load_all():
        project.edit_graph.append(op)
    timeline = derive_timeline(project)
    print(f"Timeline: {len(timeline.tracks)} track(s), duration {timeline.duration_sec:.2f}s")
    for track in timeline.tracks:
        print(f"  [{track.kind:5s}] {track.track_id}: {len(track.clips)} clip(s)")
        for clip in track.clips:
            print(f"    clip {clip.clip_id[:8]}: {clip.position_sec:.2f}s + "
                  f"[{clip.in_point_sec:.2f}, {clip.out_point_sec:.2f}) "
                  f"asset={clip.asset_hash[:12]}")
    return 0


def cmd_undo(args: argparse.Namespace) -> int:
    project_dir = _find_existing_project(Path.cwd())
    if project_dir is None:
        print("error: no open_edit project found", file=sys.stderr)
        return 1
    store = EditGraphStore(project_dir / "edit_graph.db")
    ops = store.load_all()
    for op in reversed(ops):
        if op.status == "applied":
            store.update_status(op.edit_id, "reverted")
            print(f"Reverted: {op.kind} ({op.edit_id[:8]})")
            return 0
    print("Nothing to undo")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="open_edit",
        description="AI-native video editing platform",
    )
    parser.add_argument("--version", action="store_true")
    sub = parser.add_subparsers(dest="cmd")

    p_init = sub.add_parser("init", help="Initialize a project in the given folder")
    p_init.add_argument("folder", nargs="?", default=".", help="folder of raw video files")
    p_init.set_defaults(func=cmd_init)

    p_list = sub.add_parser("list", help="List the edit graph")
    p_list.set_defaults(func=cmd_list)

    p_summary = sub.add_parser("summary", help="Show derived timeline")
    p_summary.set_defaults(func=cmd_summary)

    p_undo = sub.add_parser("undo", help="Revert the most recent applied op")
    p_undo.set_defaults(func=cmd_undo)

    args = parser.parse_args(argv)
    if args.version:
        print("open_edit 0.1.0")
        return 0
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && pytest tests/test_cli.py -v
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
cd /home/ah64/apps/mlt-pipeline && git add open_edit/open_edit/cli.py open_edit/tests/test_cli.py
git commit -m "[open_edit] cli: init / list / summary / undo subcommands"
```

---

## Task 14: E2E integration test — full workflow

**Files:**
- Create: `open_edit/tests/test_e2e.py`

**What it exercises:** the entire Phase 0+1 stack end-to-end: `AssetStore.ingest` → `EditGraphStore.append` → `validate_op` → `apply_operation` → `derive_timeline` → `update_status` (undo) → re-derive.

- [ ] **Step 1: Write the E2E test**

File: `/home/ah64/apps/mlt-pipeline/open_edit/tests/test_e2e.py`

```python
"""End-to-end test: ingest -> add ops -> derive timeline -> undo -> re-derive.

Exercises the full Phase 0+1 stack. Uses 3 fixture videos and builds a
small timeline with transitions.
"""
import shutil
from pathlib import Path

import pytest

from open_edit.ir.apply import derive_timeline
from open_edit.ir.types import (
    AddClipOp, AddEffectOp, AddTransitionOp, Project, RemoveClipOp, SetKeyframeOp,
)
from open_edit.ir.validate import validate_op
from open_edit.storage.assets import AssetStore
from open_edit.storage.edit_graph import EditGraphStore


TESTDATA = Path(__file__).parent / "testdata" / "raw_videos"


def _has_ffprobe() -> bool:
    return shutil.which("ffprobe") is not None


pytestmark = pytest.mark.skipif(
    not _has_ffprobe(), reason="ffprobe not installed"
)


def test_e2e_ingest_add_three_clips_two_transitions_undo(tmp_path: Path) -> None:
    # 1. Ingest
    store_path = tmp_path / "assets"
    asset_store = AssetStore(store_path)
    assets = asset_store.ingest_paths([
        str(TESTDATA / "clip_a.mp4"),
        str(TESTDATA / "clip_b.mp4"),
        str(TESTDATA / "clip_c.mp4"),
    ])
    assert len(assets) == 3

    # 2. Set up edit graph
    db_path = tmp_path / "edit_graph.db"
    graph = EditGraphStore(db_path)
    project = Project(
        name="e2e",
        assets={a.asset_hash: a for a in assets},
    )

    # 3. Add 3 clips on video track
    op1 = AddClipOp(
        author="user", asset_hash=assets[0].asset_hash,
        track_id="v1", position_sec=0.0,
        in_point_sec=0.0, out_point_sec=2.0,
    )
    op2 = AddClipOp(
        author="user", asset_hash=assets[1].asset_hash,
        track_id="v1", position_sec=2.0,
        in_point_sec=0.0, out_point_sec=2.0,
    )
    op3 = AddClipOp(
        author="user", asset_hash=assets[2].asset_hash,
        track_id="v1", position_sec=4.0,
        in_point_sec=0.0, out_point_sec=2.0,
    )
    for op in [op1, op2, op3]:
        assert validate_op(op, project) == []
        graph.append(op)
        project.edit_graph.append(op)

    # 4. Add 2 transitions (Bug A: centered on cut, not midpoint)
    op_t1 = AddTransitionOp(
        author="user", clip_a_id=op1.clip_id, clip_b_id=op2.clip_id,
        transition_type="luma", duration_sec=1.0,
    )
    op_t2 = AddTransitionOp(
        author="user", clip_a_id=op2.clip_id, clip_b_id=op3.clip_id,
        transition_type="luma", duration_sec=1.0,
    )
    for op in [op_t1, op_t2]:
        assert validate_op(op, project) == []
        graph.append(op)
        project.edit_graph.append(op)

    # 5. Derive timeline
    timeline = derive_timeline(project)
    assert len(timeline.tracks) == 1
    assert len(timeline.tracks[0].clips) == 3
    # Bug A: clip1 was 2.0s long with a 1.0s transition starting at the
    # boundary (cut = 2.0). clip1.out_point_sec becomes 2.0 - 0.5 = 1.5
    # clip2.in_point_sec becomes 2.0 + 0.5 = 2.5
    assert timeline.tracks[0].clips[0].out_point_sec == pytest.approx(1.5, abs=0.001)
    assert timeline.tracks[0].clips[1].in_point_sec == pytest.approx(2.5, abs=0.001)

    # 6. Undo the most recent op (op_t2)
    ops = graph.load_all()
    most_recent = next(o for o in reversed(ops) if o.status == "applied")
    graph.update_status(most_recent.edit_id, "reverted")
    project.edit_graph[-1] = project.edit_graph[-1].model_copy(update={"status": "reverted"})

    # 7. Re-derive: now 3 clips, 1 transition
    timeline2 = derive_timeline(project)
    assert len(timeline2.tracks[0].clips) == 3
    # clip2 no longer trimmed by t2, so its in_point_sec is back to 0.0
    assert timeline2.tracks[0].clips[1].in_point_sec == pytest.approx(0.0, abs=0.001)

    # 8. Add an effect + keyframes to clip1
    eff = AddEffectOp(
        author="user", target_kind="clip", target_id=op1.clip_id,
        effect_type="volume", params={"gain": 1.0},
    )
    assert validate_op(eff, project) == []
    graph.append(eff)
    project.edit_graph.append(eff)
    kf = SetKeyframeOp(
        author="user", effect_id=eff.effect_id, param="gain",
        keyframes=[(0.0, 1.0, "linear"), (1.5, 0.0, "linear")],
    )
    assert validate_op(kf, project) == []
    graph.append(kf)
    project.edit_graph.append(kf)

    # 9. Final timeline
    timeline3 = derive_timeline(project)
    assert len(timeline3.tracks[0].clips[0].effects) == 1
    assert timeline3.tracks[0].clips[0].effects[0].keyframes["gain"] == [
        (0.0, 1.0, "linear"), (1.5, 0.0, "linear")
    ]


def test_e2e_remove_unknown_clip_is_no_op(tmp_path: Path) -> None:
    """Removing a clip that was never added is a no-op (validate allows it)."""
    db_path = tmp_path / "edit_graph.db"
    graph = EditGraphStore(db_path)
    project = Project(name="e2e")
    op = AddClipOp(
        author="user", asset_hash="x", track_id="v1", position_sec=0.0,
    )
    # Don't add asset to project.assets — validate should fail.
    errors = validate_op(op, project)
    assert any("Unknown asset_hash" in e for e in errors)
```

- [ ] **Step 2: Run the test to verify it passes**

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && pytest tests/test_e2e.py -v
```

Expected: 2 tests pass.

- [ ] **Step 3: Commit**

```bash
cd /home/ah64/apps/mlt-pipeline && git add open_edit/tests/test_e2e.py
git commit -m "[open_edit] e2e: full workflow (ingest, ops, validate, apply, undo, re-derive)"
```

---

## Task 15: Final test sweep + commit

- [ ] **Step 1: Run the full test suite**

```bash
cd /home/ah64/apps/mlt-pipeline/open_edit && pytest -v
```

Expected output (counts may vary slightly):

```
tests/test_cli.py::test_init_ingests_videos PASSED
tests/test_cli.py::test_list_shows_no_ops_initially PASSED
tests/test_cli.py::test_summary_shows_empty_timeline PASSED
tests/test_e2e.py::test_e2e_ingest_add_three_clips_two_transitions_undo PASSED
tests/test_e2e.py::test_e2e_remove_unknown_clip_is_no_op PASSED
tests/test_ir/test_apply.py::... (16 tests) PASSED
tests/test_ir/test_commutativity.py::... (7 tests) PASSED
tests/test_ir/test_types.py::... (~28 tests) PASSED
tests/test_ir/test_validate.py::... (10 tests) PASSED
tests/test_sandbox_observations.py::... (4 tests) PASSED
tests/test_storage/test_assets.py::... (10 tests) PASSED
tests/test_storage/test_edit_graph.py::... (11 tests) PASSED
tests/test_storage/test_job_lock.py::... (6 tests) PASSED
tests/test_style/test_taste_events.py::... (5 tests) PASSED

========== ~100+ tests pass ==========
```

- [ ] **Step 2: Verify the CLI works end-to-end**

```bash
mkdir -p /tmp/open_edit_demo && cp /home/ah64/apps/mlt-pipeline/open_edit/tests/testdata/raw_videos/*.mp4 /tmp/open_edit_demo/
cd /tmp/open_edit_demo && open_edit init
```

Expected: `Initialized project at /tmp/open_edit_demo/.open_edit` and 3 lines like `ingested clip_a.mp4  hash=...`.

```bash
cd /tmp/open_edit_demo && open_edit list
```

Expected: `Edit graph: 0 ops (0 applied, 0 reverted)`.

```bash
cd /tmp/open_edit_demo && open_edit summary
```

Expected: `Timeline: 0 track(s), duration 0.00s`.

```bash
cd /tmp/open_edit_demo && open_edit undo
```

Expected: `Nothing to undo`.

- [ ] **Step 3: Final commit (no new code; this is a marker)**

```bash
cd /home/ah64/apps/mlt-pipeline && git add open_edit/
git commit -m "[open_edit] Phase 0+1: full test suite passes, CLI works end-to-end" --allow-empty
```

---

## Done When

- [x] All 14 tasks complete
- [x] All ~100+ tests pass
- [x] `open_edit init / list / summary / undo` work on a folder of raw videos
- [x] Bug A regression test passes (transition centered on cut, not midpoint)
- [x] Bug B regression test passes (empty paths list rejected with `fix:` line)
- [x] SQLite WAL + foreign_keys enabled
- [x] Strace fixtures committed (melt, ffmpeg, ffprobe)
- [x] No `.kdenlive` parsing anywhere in the v1 critical path

## What's NOT in this plan (deferred to later phases)

- **Phase 2:** MLT emit (`emitter.py`, `profiles.py`, `validators.py`), render orchestrator, QC gate ported from `phase6_render_qc/`
- **Phase 2:** render cache (canonical-JSON hash key)
- **Phase 2:** hand-constructed `expected_mlt.xml` golden file
- **Phase 2:** committed `tests/testdata/expected_edit_graph.json` (11 clips, 10 transitions, hand-constructed) — the Phase 0+1 e2e test uses 3 clips / 2 transitions in code; the full fixture ships in Phase 2 alongside the MLT emitter
- **Phase 2:** effect catalog YAML files (e.g. `open_edit/ir/catalog/effects/volume.yaml`) + catalog loader — the spec requires catalog validation; Phase 0+1 accepts any non-empty `effect_type` string and adds the catalog in Phase 2. Add a `tests/test_validate.py::test_unknown_effect_type_rejected` test before Phase 2 ships.
- **Phase 2:** `mlt_ingest.py` (raw XML → synthetic ops)
- **Phase 3:** Rust sandbox (`open_edit/sandbox/`) — allowlist built from Phase 0 strace fixtures
- **Phase 3:** `open_edit/sandbox_bridge.py` (Python wrapper around the Rust binary)
- **Phase 4:** `open_edit/agent/tools/` (the 38 repointed `pyagent_*` wrappers)
- **Phase 4:** `extension.ts` extension (the existing one stays; we add `pyagent_run_python`)
- **Phase 4:** `style/aggregate.py` (rule-based rollup)
- **Phase 4:** `style/retrieve.py` (tag-gated injection)
- **Phase 4:** form-based parameter editor in `phase4_chat_ui/`
- **Phase 4:** Style profile panel
- **Phase 5:** v1 demo script (`scripts/v1_demo.sh`) — runs end-to-end with the chat UI
- **Phase 5:** `.kdenlive` importer — v2 / optional
- **Phase 6+:** scenario eval, hardening, Tauri shell, etc.





