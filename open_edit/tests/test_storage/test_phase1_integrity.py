"""Tests for Phase 1 storage integrity features."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from open_edit.ir.types import AddClipOp, RemoveClipOp
from open_edit.storage.edit_graph import EditGraphStore


class TestPhase1Integrity(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "project.db"
        self.store = EditGraphStore(self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _raw(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def test_schema_user_version_is_2(self) -> None:
        conn = self._raw()
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(version, 2)

    def test_append_writes_status_event(self) -> None:
        op = AddClipOp(
            author="user",
            asset_hash="h",
            track_id="v1",
            track_kind="video",
            position_sec=0.0,
            in_point_sec=0.0,
            out_point_sec=1.0,
        )
        self.store.append(op)
        conn = self._raw()
        try:
            rows = conn.execute(
                "SELECT from_status, to_status, reason FROM edit_status_events "
                "WHERE edit_id = ?",
                (op.edit_id,),
            ).fetchall()
        finally:
            conn.close()
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0][0])
        self.assertEqual(rows[0][1], "applied")
        self.assertEqual(rows[0][2], "append")

    def test_update_status_writes_status_event(self) -> None:
        op = AddClipOp(author="user", asset_hash="h", track_id="v1", position_sec=0.0)
        self.store.append(op)
        self.store.update_status(op.edit_id, "reverted", reason="undo")
        conn = self._raw()
        try:
            rows = conn.execute(
                "SELECT from_status, to_status, reason FROM edit_status_events "
                "WHERE edit_id = ? ORDER BY changed_at, rowid",
                (op.edit_id,),
            ).fetchall()
        finally:
            conn.close()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][0], "applied")
        self.assertEqual(rows[1][1], "reverted")
        self.assertEqual(rows[1][2], "undo")

    def test_command_roundtrip_and_idempotency(self) -> None:
        cid = "cmd-1"
        self.assertFalse(self.store.command_exists(cid))
        self.store.record_command(cid, "proj", "add_clip", payload_hash="ph")
        self.assertTrue(self.store.command_exists(cid))

        self.store.record_command(cid, "proj", "different_tool")
        conn = self._raw()
        try:
            tool = conn.execute(
                "SELECT tool_name FROM commands WHERE command_id = ?", (cid,)
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(tool, "add_clip")

        self.assertIsNone(self.store.get_command_result(cid))
        self.store.finish_command(cid, status="done", result_json='{"ok": true}')
        self.assertEqual(self.store.get_command_result(cid), '{"ok": true}')

    def test_timeline_snapshot_roundtrip(self) -> None:
        self.assertIsNone(self.store.load_timeline_snapshot("hash1"))
        self.store.save_timeline_snapshot("hash1", "proj", '{"tracks": []}')
        self.assertEqual(
            self.store.load_timeline_snapshot("hash1"), '{"tracks": []}'
        )

    def test_load_all_preserves_sequence_order(self) -> None:
        ops = [
            AddClipOp(
                author="user",
                asset_hash=f"h{i}",
                track_id="v1",
                track_kind="video",
                position_sec=float(i),
                in_point_sec=0.0,
                out_point_sec=1.0,
            )
            for i in range(3)
        ]
        for op in ops:
            self.store.append(op)
        loaded = self.store.load_all()
        self.assertEqual(
            [o.edit_id for o in loaded], [o.edit_id for o in ops]
        )


if __name__ == "__main__":
    unittest.main()
