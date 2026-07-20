"""Phase 4 Task 7: pyagent_get_pending_notes tool."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock


def _make_project_dir(tmp_path: Path) -> Path:
    project_path = tmp_path / "project"
    project_path.mkdir()
    (project_path / "edit_graph.db").touch()
    return project_path


def test_get_pending_notes_returns_list(tmp_path):
    project_path = _make_project_dir(tmp_path)
    args = {
        "project_id": "p1",
        "project_path": str(project_path / "fake.kdenlive"),
    }
    fake_notes = []
    fake_store = MagicMock()
    fake_store.list_pending.return_value = fake_notes
    with patch(
        "open_edit.agent.tools.pyagent_get_pending_notes.NotesStore",
        return_value=fake_store,
    ):
        from open_edit.agent.tools.pyagent_get_pending_notes import get_pending_notes
        result = get_pending_notes(args, str(project_path))
    assert result["notes"] == []
    assert result["remaining_count"] == 0


def test_get_pending_notes_summary_only(tmp_path):
    project_path = _make_project_dir(tmp_path)
    args = {
        "project_id": "p1",
        "project_path": str(project_path / "fake.kdenlive"),
        "summary_only": True,
    }
    note = MagicMock()
    note.note_id = "n1"
    note.anchor.model_dump.return_value = {
        "anchor_type": "timestamp", "t_start": 0.0, "t_end": 1.0,
    }
    note.text = "Hello world"
    fake_store = MagicMock()
    fake_store.list_pending.return_value = [note]
    with patch(
        "open_edit.agent.tools.pyagent_get_pending_notes.NotesStore",
        return_value=fake_store,
    ):
        from open_edit.agent.tools.pyagent_get_pending_notes import get_pending_notes
        result = get_pending_notes(args, str(project_path))
    assert len(result["notes"]) == 1
    assert result["notes"][0]["note_id"] == "n1"
    assert result["notes"][0]["text_preview"] == "Hello world"
