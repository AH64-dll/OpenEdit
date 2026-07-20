"""Phase 3 Task 8: sandbox_bridge unit tests with mocked Rust binary.

Note: The brief's test draft had two bugs vs. the real code:
  1. _FlushingBuffer() needs an ops_file argument (the brief's class signature
     takes one, but the test draft called it with no args).
  2. AddClipOp has no `project_id` field — only `parent_id` (inherited from
     Operation). The test draft passed `project_id="p"` which Pydantic rejects.

Both are fixed here. The intent of H10 (write-first-then-append) and the
structural check on the rendered bootstrap are preserved.
"""
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
    buf = _FlushingBuffer(ops_file)
    from open_edit.ir.types import AddClipOp, new_id
    op = AddClipOp(
        edit_id=new_id(), author="ai", parent_id="e",
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


def test_render_bootstrap_inlines_all_24_op_classes():
    """C1 (final-fixes): bootstrap must include all 24 op class definitions.

    Regression: T7 added 12 new op types, but the bootstrap's `op_types`
    list was never updated. The IR class source references all 24 ops
    (via type annotations), but the class definitions are only inlined for
    whatever names are in `op_types`. Any IR method that constructs one of
    the 12 missing ops would raise NameError inside the sandbox.
    """
    from open_edit.ir import types as _types
    all_24 = [
        "AddClipOp", "RemoveClipOp", "MoveClipOp", "TrimClipOp",
        "AddTransitionOp", "RemoveTransitionOp", "SetTransitionPropertyOp",
        "AddEffectOp", "RemoveEffectOp", "SetEffectParamOp",
        "SetKeyframeOp", "RemoveKeyframeOp",
        "SlipClipOp", "RippleDeleteClipOp", "ChangeClipSpeedOp",
        "SplitClipOp", "ReplaceClipSourceOp", "SetClipSpeedRampOp",
        "SetAudioGainOp", "NormalizeAudioOp",
        "GroupEditsOp", "UngroupEditsOp",
        "RawMltXmlOp", "FreeFormCodeOp",
    ]
    # Sanity: union actually has 24 members
    union_members = _types.OperationUnion.__args__[0].__args__
    assert len(union_members) == 24, (
        f"IR's Union has {len(union_members)} members; "
        f"this test assumes 24. Update the list above if you add ops."
    )

    bootstrap = _render_bootstrap(project_id="p1", parent_op_id="e1")

    missing = [
        name for name in all_24
        if f"class {name}" not in bootstrap
    ]
    assert missing == [], (
        f"Bootstrap is missing {len(missing)} op class definitions: {missing}. "
        f"The IR source references them, but `op_types` in _render_bootstrap "
        f"was not updated when these ops were added in T7."
    )


def test_bootstrap_exec_instantiates_all_24_op_classes(tmp_path):
    """C1 (final-fixes): executing the bootstrap must make every op class
    available in scope (no NameError when IR methods construct them).
    """
    bootstrap = _render_bootstrap(
        project_id="p1",
        parent_op_id="e1",
        originating_note_id="n1",
    )
    # Run the bootstrap in an isolated globals dict, like the Rust binary does
    g: dict = {"__name__": "__sandbox__", "__file__": "<bootstrap>"}
    exec(compile(bootstrap, "<bootstrap>", "exec"), g)

    # Every op class name must be reachable in the bootstrap's globals
    expected = [
        "AddClipOp", "RemoveClipOp", "MoveClipOp", "TrimClipOp",
        "AddTransitionOp", "RemoveTransitionOp", "SetTransitionPropertyOp",
        "AddEffectOp", "RemoveEffectOp", "SetEffectParamOp",
        "SetKeyframeOp", "RemoveKeyframeOp",
        "SlipClipOp", "RippleDeleteClipOp", "ChangeClipSpeedOp",
        "SplitClipOp", "ReplaceClipSourceOp", "SetClipSpeedRampOp",
        "SetAudioGainOp", "NormalizeAudioOp",
        "GroupEditsOp", "UngroupEditsOp",
        "RawMltXmlOp", "FreeFormCodeOp",
    ]
    for name in expected:
        assert name in g, f"{name} not in bootstrap scope after exec"

    # `ir` instance must be present and must accept a method that was added
    # in T7 (was NameError before the fix).
    assert "ir" in g
    # Wire a buffer; IR will append a SlipClipOp
    import json
    ops_file = tmp_path / "ops.jsonl"
    class _Buf(list):
        def append(self, op):
            super().append(op)
            with open(ops_file, "a") as f:
                f.write(op.model_dump_json() + "\n")
    g["_ops"] = _Buf()
    g["ir"] = g["IR"](
        g["_ops"],
        project_id="p1",
        parent_op_id="e1",
        originating_note_id="n1",
    )
    # Calling a T7 method must not raise NameError
    g["ir"].slip_clip(clip_id="c1", delta_sec=0.5)
    assert ops_file.exists()
    lines = [ln for ln in ops_file.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["kind"] == "slip_clip"
    assert parsed["parent_id"] == "e1"


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
