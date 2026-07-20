"""CLI tests for `open_edit notes` (Phase 4 T6, M1: add + dismiss actions)."""
import json
import subprocess
from pathlib import Path

import pytest

from open_edit.storage.notes import NotesStore, NoteStatus, TimestampAnchor, ReviewNote, NoteSource
from datetime import datetime, timezone


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["open_edit", *args],
        capture_output=True, text=True, check=False,
    )


def test_notes_list_subcommand(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    NotesStore(project_dir / "notes.db").append(ReviewNote(
        project_id="p1",
        anchor=TimestampAnchor(t_start=0.0, t_end=1.0),
        text="hi",
        source=NoteSource.typed,
        status=NoteStatus.pending,
        created_at=datetime.now(timezone.utc).isoformat(),
    ))
    result = _run("notes", "list", "p1", "--project-dir", str(project_dir))
    assert result.returncode == 0, result.stderr
    assert "hi" in result.stdout
    assert "pending" in result.stdout


def test_notes_add_subcommand(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    anchor = json.dumps({"anchor_type": "timestamp", "t_start": 0.0, "t_end": 1.0})
    result = _run(
        "notes", "add", "p1",
        "--project-dir", str(project_dir),
        "--text", "from-cli",
        "--anchor", anchor,
    )
    assert result.returncode == 0, result.stderr
    notes = NotesStore(project_dir / "notes.db").list_all("p1")
    assert len(notes) == 1
    assert notes[0].text == "from-cli"
    assert notes[0].status == NoteStatus.pending


def test_notes_dismiss_subcommand(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    store = NotesStore(project_dir / "notes.db")
    note_id = store.append(ReviewNote(
        project_id="p1",
        anchor=TimestampAnchor(t_start=0.0, t_end=1.0),
        text="dismiss me",
        source=NoteSource.typed,
        status=NoteStatus.pending,
        created_at=datetime.now(timezone.utc).isoformat(),
    ))
    result = _run(
        "notes", "dismiss", "p1", note_id,
        "--project-dir", str(project_dir),
    )
    assert result.returncode == 0, result.stderr
    notes = store.list_all("p1")
    assert len(notes) == 1
    assert notes[0].status == NoteStatus.dismissed
