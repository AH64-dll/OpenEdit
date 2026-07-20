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
