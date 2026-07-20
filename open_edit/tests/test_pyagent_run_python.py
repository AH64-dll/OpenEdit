"""Tests for the pyagent_run_python wrapper (agent/tools/).

The wrapper translates LLM-supplied args (which may forget to set
parent_op_id) into a run_free_form() call that requires a non-None
parent_op_id string.
"""
import re
from unittest.mock import patch

import pytest

from open_edit.agent.tools.pyagent_run_python import run_python


def _captured_args(call_kwargs: dict) -> dict:
    """Extract the kwargs that run_free_form was called with."""
    return call_kwargs


def test_run_python_missing_parent_op_id_gets_default(tmp_path):
    """I4: if the LLM forgets `parent_op_id`, the wrapper must supply a default
    rather than passing `None` (which would propagate into every op's
    parent_id, and `_validate_references` rejects parent_id=None).
    """
    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "edit_graph.db").touch()

    captured = {}

    def fake_run_free_form(**kwargs):
        captured.update(kwargs)
        from open_edit.agent.exceptions import FreeFormResult
        return FreeFormResult.ok(ops=[], duration_s=0.0)

    args = {
        "code": "# ir_api_version: 0.1; libs: {}\npass\n",
        "project_id": "p1",
        # parent_op_id intentionally OMITTED
    }
    with patch(
        "open_edit.agent.tools.pyagent_run_python.run_free_form",
        side_effect=fake_run_free_form,
    ):
        result = run_python(args, project_path=str(workdir))

    assert result["status"] == "ok"
    parent_op_id = captured.get("parent_op_id")
    assert parent_op_id is not None, (
        f"run_python passed parent_op_id={parent_op_id!r}; "
        f"missing arg should default to a generated id, not None"
    )
    # The convention in the fix is pyagent_<12 hex>
    assert re.fullmatch(r"pyagent_[0-9a-f]{12}", parent_op_id), (
        f"Unexpected default format: {parent_op_id!r}"
    )


def test_run_python_explicit_parent_op_id_is_preserved(tmp_path):
    """I4 (sanity): when the LLM does supply parent_op_id, the wrapper
    must not overwrite it.
    """
    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "edit_graph.db").touch()

    captured = {}

    def fake_run_free_form(**kwargs):
        captured.update(kwargs)
        from open_edit.agent.exceptions import FreeFormResult
        return FreeFormResult.ok(ops=[], duration_s=0.0)

    args = {
        "code": "# ir_api_version: 0.1; libs: {}\npass\n",
        "project_id": "p1",
        "parent_op_id": "user_explicit_id_42",
    }
    with patch(
        "open_edit.agent.tools.pyagent_run_python.run_free_form",
        side_effect=fake_run_free_form,
    ):
        run_python(args, project_path=str(workdir))

    assert captured["parent_op_id"] == "user_explicit_id_42"
