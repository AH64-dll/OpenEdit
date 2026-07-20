"""Phase 4 Task 2: WS broadcast is project-scoped (audit H4)."""
import asyncio
import unittest
from unittest.mock import AsyncMock

from phase4_chat_ui.ws.handlers import handle_note_add


class TestNoteAddBroadcast(unittest.TestCase):
    def test_note_add_broadcasts_to_project(self):
        async def run():
            broadcast = AsyncMock()
            ws = AsyncMock()
            await handle_note_add(
                ws,
                project_id="p1",
                msg={"anchor": {"anchor_type": "timestamp", "t_start": 0.0, "t_end": 1.0}, "text": "test", "source": "typed"},
                broadcast=broadcast,
            )
            broadcast.assert_called_once()
            call_args = broadcast.call_args[0]
            assert call_args[0] == "p1"
            assert call_args[1]["type"] == "note_list"
            assert call_args[1]["project_id"] == "p1"
        asyncio.run(run())
