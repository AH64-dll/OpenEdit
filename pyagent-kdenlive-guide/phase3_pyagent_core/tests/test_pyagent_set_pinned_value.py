"""Phase 4 Task 7: pyagent_set_pinned_value tool."""
from __future__ import annotations

from unittest.mock import patch


def test_set_pinned_value_writes_to_profile(tmp_path):
    """The wrapper should call style.aggregate.set_pinned(key, value)."""
    args = {
        "key": "aspect_ratio",
        "value": "9:16",
        "project_path": str(tmp_path / "fake.kdenlive"),
    }
    with patch(
        "open_edit.agent.tools.pyagent_set_pinned_value.set_pinned",
        return_value=None,
    ) as mock_set:
        from open_edit.agent.tools.pyagent_set_pinned_value import set_pinned_value
        result = set_pinned_value(args, str(tmp_path / "fake.kdenlive"))
    assert result == {"status": "ok"}
    call_args = mock_set.call_args.args
    assert call_args[0] == "aspect_ratio"
    assert call_args[1] == "9:16"
