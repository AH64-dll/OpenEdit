"""Phase 4 Task 7: pyagent_get_style_profile tool."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


def test_get_style_profile_returns_slice(tmp_path):
    """The wrapper should call style.retrieve.get_slice(op_type)."""
    args = {"op_type": "AddTransition", "project_path": str(tmp_path / "fake.kdenlive")}
    expected = {"transitions": {"preferred": ["dissolve"], "confidence": 0.5}}
    with patch(
        "open_edit.agent.tools.pyagent_get_style_profile.get_slice",
        return_value=expected,
    ) as mock_get:
        from open_edit.agent.tools.pyagent_get_style_profile import get_style_profile
        result = get_style_profile(args, str(tmp_path / "fake.kdenlive"))
    assert result == expected
    call_args = mock_get.call_args.args
    assert call_args[0] == "AddTransition"


def test_get_style_profile_unknown_op_type(tmp_path):
    """Unknown op_type returns the corrections slice (per retrieve.py)."""
    args = {"op_type": "TotallyUnknown", "project_path": str(tmp_path / "fake.kdenlive")}
    from open_edit.agent.tools.pyagent_get_style_profile import get_style_profile
    result = get_style_profile(args, str(tmp_path / "fake.kdenlive"))
    assert isinstance(result, dict)
