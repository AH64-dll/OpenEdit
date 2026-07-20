"""Phase 4 Task 7: pyagent_add_marker (new, in open_edit/agent/tools/)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock


def _make_project_dir(tmp_path: Path) -> Path:
    project_path = tmp_path / "project"
    project_path.mkdir()
    (project_path / "edit_graph.db").touch()
    return project_path


def test_add_marker_writes_note_with_source_agent(tmp_path):
    project_path = _make_project_dir(tmp_path)
    args = {
        "project_id": "p1",
        "project_path": str(project_path / "fake.kdenlive"),
        "t_start": 5.0,
        "t_end": 6.0,
        "text": "marker label",
    }
    fake_store = MagicMock()
    fake_store.append.return_value = "note_abc"
    with patch(
        "open_edit.agent.tools.pyagent_add_marker.NotesStore",
        return_value=fake_store,
    ):
        from open_edit.agent.tools.pyagent_add_marker import add_marker
        result = add_marker(args, str(project_path))
    assert result["status"] == "ok"
    assert "note_id" in result
    fake_store.append.assert_called_once()
    written_note = fake_store.append.call_args.args[0]
    assert written_note.project_id == "p1"
    assert written_note.anchor.t_start == 5.0
    assert written_note.anchor.t_end == 6.0
    assert written_note.text == "marker label"
    assert written_note.source.value == "agent"


def test_add_marker_defaults_t_end_to_t_start(tmp_path):
    project_path = _make_project_dir(tmp_path)
    args = {
        "project_id": "p1",
        "project_path": str(project_path / "fake.kdenlive"),
        "t_start": 3.0,
    }
    fake_store = MagicMock()
    fake_store.append.return_value = "note_xyz"
    with patch(
        "open_edit.agent.tools.pyagent_add_marker.NotesStore",
        return_value=fake_store,
    ):
        from open_edit.agent.tools.pyagent_add_marker import add_marker
        result = add_marker(args, str(project_path))
    assert result["status"] == "ok"
    written_note = fake_store.append.call_args.args[0]
    assert written_note.anchor.t_start == 3.0
    assert written_note.anchor.t_end == 3.0
