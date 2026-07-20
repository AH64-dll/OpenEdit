"""Phase 4 Task 2: WS broadcast is project-scoped (audit H4)."""
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from phase4_chat_ui import ws as ws_module
from phase4_chat_ui.ws.handlers import handle_note_add


@pytest.fixture
def isolated_notes_db(tmp_path, monkeypatch):
    """Redirect get_notes_db_path() to a tmp file so the test never touches ~/.open_edit_notes."""
    db_path = tmp_path / "notes.db"

    def fake_db_path(project_id: str) -> Path:
        return db_path

    monkeypatch.setattr(ws_module.handlers, "get_notes_db_path", fake_db_path)
    return db_path


def test_note_add_broadcasts_to_project(isolated_notes_db):
    async def run():
        broadcast = AsyncMock()
        ws = AsyncMock()
        await handle_note_add(
            ws,
            project_id="p1",
            msg={
                "anchor": {"anchor_type": "timestamp", "t_start": 0.0, "t_end": 1.0},
                "text": "test",
                "source": "typed",
            },
            broadcast=broadcast,
        )
        broadcast.assert_called_once()
        call_args = broadcast.call_args[0]
        assert call_args[0] == "p1"
        assert call_args[1]["type"] == "note_list"
        assert call_args[1]["project_id"] == "p1"
        # And the note was actually persisted to the isolated db, not ~/.open_edit_notes.
        assert isolated_notes_db.exists()

    asyncio.run(run())


def test_parse_anchor_rejects_unknown_type():
    """M2: parse_anchor must raise ValueError for an unknown anchor_type
    rather than silently fall through to TimestampAnchor (which would either
    drop the op_id/region data or, worse, crash the connection on a bad
    signature)."""
    from phase4_chat_ui.ws.handlers import parse_anchor

    with pytest.raises(ValueError, match="anchor_type"):
        parse_anchor({"anchor_type": "wat", "t_start": 0.0, "t_end": 1.0})


def test_parse_anchor_accepts_known_types():
    """M2: timestamp/region/op all still parse correctly after the unknown-type guard."""
    from phase4_chat_ui.ws.handlers import parse_anchor

    a1 = parse_anchor({"anchor_type": "timestamp", "t_start": 0.0, "t_end": 1.0})
    a2 = parse_anchor({"anchor_type": "region", "x": 0, "y": 0, "w": 1, "h": 1, "t_start": 0.0, "t_end": 1.0})
    a3 = parse_anchor({"anchor_type": "op", "op_id": "op_1"})
    assert a1.anchor_type == "timestamp"
    assert a2.anchor_type == "region"
    assert a3.anchor_type == "op"


def test_handle_note_update_delegates_to_store(isolated_notes_db):
    """M3: handle_note_update must persist text and status via NotesStore.update,
    not by opening a separate sqlite3 connection. Asserts the post-update
    note_list broadcast reflects the new text and the dismissed status."""
    from phase4_chat_ui.ws.handlers import handle_note_add, handle_note_update

    async def run():
        broadcast = AsyncMock()
        ws = AsyncMock()
        # Seed a note via the standard add path.
        await handle_note_add(
            ws,
            project_id="p1",
            msg={
                "anchor": {"anchor_type": "timestamp", "t_start": 0.0, "t_end": 1.0},
                "text": "before",
                "source": "typed",
            },
            broadcast=broadcast,
        )
        # Pull the note_id out of the broadcast payload.
        notes_after_add = broadcast.call_args[0][1]["notes"]
        note_id = notes_after_add[0]["note_id"]
        broadcast.reset_mock()

        await handle_note_update(
            ws,
            project_id="p1",
            msg={"note_id": note_id, "text": "after", "status": "dismissed"},
            broadcast=broadcast,
        )

        broadcast.assert_called_once()
        notes_after_update = broadcast.call_args[0][1]["notes"]
        assert len(notes_after_update) == 1
        assert notes_after_update[0]["note_id"] == note_id
        assert notes_after_update[0]["text"] == "after"
        assert notes_after_update[0]["status"] == "dismissed"

    asyncio.run(run())
