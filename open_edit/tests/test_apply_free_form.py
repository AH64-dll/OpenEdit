"""Phase 3 Task 9: _apply_free_form_code integration in apply.py.

Brief deviations (mirroring Task 8's report):
- The brief calls `apply_operation(minimal_project, op) -> Project`, but the
  actual `apply_operation` signature is `(timeline, op) -> Timeline` (used
  by all 200 existing tests). We test `_apply_free_form_code` directly.
- The brief passes `project_id=...` to AddClipOp / FreeFormCodeOp, but
  neither has a `project_id` field (Task 8's test_sandbox_bridge.py:6-7
  noted the same bug). We drop it.
- The brief patches `open_edit.ir.apply.sandbox_bridge.run_free_form`, but
  `apply.py` does not import `sandbox_bridge` at module level (it uses a
  local import inside the function to avoid a circular import). We patch
  at the source: `open_edit.agent.sandbox_bridge.run_free_form`.
"""
from unittest.mock import patch

import pytest

from open_edit.agent.exceptions import FreeFormResult
from open_edit.ir.apply import ApplyError, _apply_free_form_code
from open_edit.ir.types import (
    AddClipOp, Asset, FreeFormCodeOp, Project, new_id,
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
    """Mocked sandbox returns 3 child ops; they are appended to the project."""
    op = FreeFormCodeOp(
        edit_id=new_id(),
        author="ai",
        code="# ir_api_version: 0.1; libs: {}",
        label="test",
    )
    child_ops = [
        AddClipOp(edit_id=new_id(), author="ai", parent_id=op.edit_id,
                  clip_id=new_id(), asset_hash="abc", track_id="t1", position_sec=0.0),
        AddClipOp(edit_id=new_id(), author="ai", parent_id=op.edit_id,
                  clip_id=new_id(), asset_hash="abc", track_id="t1", position_sec=2.0),
        AddClipOp(edit_id=new_id(), author="ai", parent_id=op.edit_id,
                  clip_id=new_id(), asset_hash="abc", track_id="t1", position_sec=4.0),
    ]
    mock_result = FreeFormResult.ok(ops=child_ops, duration_s=0.5)
    with patch("open_edit.agent.sandbox_bridge.run_free_form",
               return_value=mock_result) as mock_run:
        updated = _apply_free_form_code(op, minimal_project)

    assert len(updated.edit_graph) == 3
    assert all(o.parent_id == op.edit_id for o in updated.edit_graph)
    args = mock_run.call_args
    assert args.kwargs["code"] == op.code
    assert args.kwargs["workdir"] == minimal_project.workdir
    assert args.kwargs["parent_op_id"] == op.edit_id


def test_apply_free_form_code_raises_on_sandbox_failure(minimal_project):
    """Sandbox returns failure → ApplyError; edit_graph unchanged."""
    op = FreeFormCodeOp(
        edit_id=new_id(),
        author="ai",
        code="# ir_api_version: 0.1; libs: {}",
    )
    mock_result = FreeFormResult.fail("timeout", "30s elapsed")
    with patch("open_edit.agent.sandbox_bridge.run_free_form",
               return_value=mock_result):
        with pytest.raises(ApplyError, match="timeout"):
            _apply_free_form_code(op, minimal_project)

    assert minimal_project.edit_graph == []


def test_apply_free_form_code_passes_timeout_and_mem(minimal_project):
    """timeout_sec and mem_mb from the op are forwarded to run_free_form."""
    op = FreeFormCodeOp(
        edit_id=new_id(),
        author="ai",
        code="# ir_api_version: 0.1; libs: {}",
        timeout_sec=10,
        mem_mb=256,
    )
    mock_result = FreeFormResult.ok(ops=[], duration_s=0.0)
    with patch("open_edit.agent.sandbox_bridge.run_free_form",
               return_value=mock_result) as mock_run:
        _apply_free_form_code(op, minimal_project)
    assert mock_run.call_args.kwargs["timeout"] == 10
    assert mock_run.call_args.kwargs["mem_mb"] == 256
