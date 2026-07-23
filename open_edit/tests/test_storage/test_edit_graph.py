"""Tests for the EditGraphStore (SQLite-backed edit graph)."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from open_edit.ir.types import (
    AddClipOp,
    RemoveClipOp,
    MoveClipOp,
    TrimClipOp,
    AddTransitionOp,
    AddEffectOp,
    SetKeyframeOp,
    GroupEditsOp,
    RawMltXmlOp,
    FreeFormCodeOp,
)
from open_edit.storage.edit_graph import EditGraphStore


class TestEditGraphStore(unittest.TestCase):
    """Unit tests for SQLite-backed EditGraphStore."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)
        self.db_path = self.tmp_path / "project.db"
        self.store = EditGraphStore(self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_init_creates_db_file(self) -> None:
        self.assertTrue(self.db_path.exists())

    def test_init_creates_edits_table(self) -> None:
        with self.store._conn() as conn:
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='edits'"
            )
            self.assertIsNotNone(cur.fetchone())

    def test_init_creates_jobs_table(self) -> None:
        with self.store._conn() as conn:
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'"
            )
            self.assertIsNotNone(cur.fetchone())

    def test_init_creates_project_meta_table(self) -> None:
        with self.store._conn() as conn:
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='project_meta'"
            )
            self.assertIsNotNone(cur.fetchone())

    def test_init_enables_wal_mode(self) -> None:
        with self.store._conn() as conn:
            cur = conn.execute("PRAGMA journal_mode")
            mode = cur.fetchone()[0]
            self.assertEqual(mode.lower(), "wal")

    def test_init_enables_foreign_keys(self) -> None:
        with self.store._conn() as conn:
            cur = conn.execute("PRAGMA foreign_keys")
            enabled = cur.fetchone()[0]
            self.assertEqual(enabled, 1)

    def test_project_id_generation_and_persistence(self) -> None:
        # First access generates a valid project_id
        pid1 = self.store.project_id
        self.assertIsInstance(pid1, str)
        self.assertGreater(len(pid1), 0)

        # Verify SQL row directly in project_meta table
        with self.store._conn() as conn:
            cur = conn.execute(
                "SELECT value FROM project_meta WHERE key = 'project_id'"
            )
            row = cur.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], pid1)

        # Subsequent access on same instance returns identical project_id
        self.assertEqual(self.store.project_id, pid1)

        # Reopening the store with the same DB file returns persistent project_id
        store2 = EditGraphStore(self.db_path)
        self.assertEqual(store2.project_id, pid1)

    def test_append_and_load_all_10_operation_schemas(self) -> None:
        # Define sample instances for all 10 operation schemas
        # References are ordered so each op targets a clip/effect that
        # already exists (the append guard enforces reference integrity).
        ops = [
            AddClipOp(
                author="user",
                asset_hash="hash_add_clip",
                track_id="v1",
                track_kind="video",
                position_sec=0.0,
                in_point_sec=1.0,
                out_point_sec=5.0,
                clip_id="c1",
            ),
            MoveClipOp(
                author="ai",
                clip_id="c1",
                new_track_id="v2",
                new_position_sec=10.0,
            ),
            AddClipOp(
                author="user",
                asset_hash="hash_add_clip",
                track_id="v1",
                track_kind="video",
                position_sec=0.0,
                in_point_sec=1.0,
                out_point_sec=5.0,
                clip_id="c2",
            ),
            TrimClipOp(
                author="user",
                clip_id="c2",
                new_in_point_sec=2.0,
                new_out_point_sec=8.0,
            ),
            RemoveClipOp(
                author="user",
                clip_id="c1",
            ),
            AddClipOp(
                author="user",
                asset_hash="hash_add_clip",
                track_id="v1",
                track_kind="video",
                position_sec=0.0,
                in_point_sec=1.0,
                out_point_sec=5.0,
                clip_id="ca",
            ),
            AddClipOp(
                author="user",
                asset_hash="hash_add_clip",
                track_id="v1",
                track_kind="video",
                position_sec=0.0,
                in_point_sec=1.0,
                out_point_sec=5.0,
                clip_id="cb",
            ),
            AddTransitionOp(
                author="user",
                clip_a_id="ca",
                clip_b_id="cb",
                transition_type="dissolve",
                duration_sec=1.5,
            ),
            AddClipOp(
                author="user",
                asset_hash="hash_add_clip",
                track_id="v1",
                track_kind="video",
                position_sec=0.0,
                in_point_sec=1.0,
                out_point_sec=5.0,
                clip_id="ce",
            ),
            AddEffectOp(
                author="ai",
                target_kind="clip",
                target_id="ce",
                effect_type="frei0r.blur",
                params={"amount": 0.75},
                effect_id="eff_kf",
            ),
            SetKeyframeOp(
                author="user",
                effect_id="eff_kf",
                param="blur_amount",
                keyframes=[(0.0, 0.0, "linear"), (1.0, 1.0, "linear")],
            ),
            GroupEditsOp(
                author="user",
                edit_ids=["edit_1", "edit_2"],
                label="Group test",
            ),
            RawMltXmlOp(
                author="user",
                xml="<mlt><profile/></mlt>",
                description="Raw XML injection",
            ),
            FreeFormCodeOp(
                author="ai",
                code="print('Hello World')",
                timeout_sec=30,
                mem_mb=512,
                label="Freeform code test",
            ),
        ]

        expected_classes = [
            AddClipOp,
            MoveClipOp,
            AddClipOp,
            TrimClipOp,
            RemoveClipOp,
            AddClipOp,
            AddClipOp,
            AddTransitionOp,
            AddClipOp,
            AddEffectOp,
            SetKeyframeOp,
            GroupEditsOp,
            RawMltXmlOp,
            FreeFormCodeOp,
        ]

        assigned_seqs = []
        for index, op in enumerate(ops):
            seq = self.store.append(op)
            assigned_seqs.append(seq)
            self.assertEqual(seq, index)

            # Direct SQLite insertion check
            with self.store._conn() as conn:
                cur = conn.execute(
                    "SELECT edit_id, parent_id, kind, author, timestamp, status, sequence_num, payload "
                    "FROM edits WHERE edit_id = ?",
                    (op.edit_id,),
                )
                row = cur.fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row[0], op.edit_id)
                self.assertEqual(row[1], op.parent_id)
                self.assertEqual(row[2], op.kind)
                self.assertEqual(row[3], op.author)
                self.assertEqual(row[4], op.timestamp)
                self.assertEqual(row[5], op.status)
                self.assertEqual(row[6], index)
                self.assertTrue(len(row[7]) > 0)

        # History query via load_all()
        loaded_ops = self.store.load_all()
        self.assertEqual(len(loaded_ops), len(ops))

        for idx, (original, loaded, expected_cls) in enumerate(zip(ops, loaded_ops, expected_classes)):
            self.assertIsInstance(loaded, expected_cls)
            self.assertEqual(loaded.edit_id, original.edit_id)
            self.assertEqual(loaded.kind, original.kind)
            self.assertEqual(loaded.author, original.author)
            self.assertEqual(loaded.status, original.status)
            self.assertEqual(loaded.timestamp, original.timestamp)

        # Specific field verifications
        self.assertEqual(loaded_ops[0].asset_hash, "hash_add_clip")
        self.assertEqual(loaded_ops[1].new_track_id, "v2")
        self.assertEqual(loaded_ops[3].new_in_point_sec, 2.0)
        self.assertEqual(loaded_ops[7].transition_type, "dissolve")
        self.assertEqual(loaded_ops[9].params["amount"], 0.75)
        self.assertEqual(loaded_ops[10].keyframes, [(0.0, 0.0, "linear"), (1.0, 1.0, "linear")])
        self.assertEqual(loaded_ops[11].edit_ids, ["edit_1", "edit_2"])
        self.assertEqual(loaded_ops[12].xml, "<mlt><profile/></mlt>")
        self.assertEqual(loaded_ops[13].code, "print('Hello World')")

    def test_status_updates(self) -> None:
        op = AddClipOp(author="user", asset_hash="hash_status", track_id="v1", position_sec=0.0)
        self.store.append(op)

        # Verify initial status is applied
        ops = self.store.load_all()
        self.assertEqual(ops[0].status, "applied")

        # Update to reverted
        self.store.update_status(op.edit_id, "reverted")
        with self.store._conn() as conn:
            cur = conn.execute("SELECT status FROM edits WHERE edit_id = ?", (op.edit_id,))
            self.assertEqual(cur.fetchone()[0], "reverted")
        ops = self.store.load_all()
        self.assertEqual(ops[0].status, "reverted")

        # Update to superseded
        self.store.update_status(op.edit_id, "superseded")
        with self.store._conn() as conn:
            cur = conn.execute("SELECT status FROM edits WHERE edit_id = ?", (op.edit_id,))
            self.assertEqual(cur.fetchone()[0], "superseded")
        ops = self.store.load_all()
        self.assertEqual(ops[0].status, "superseded")

        # Update back to applied
        self.store.update_status(op.edit_id, "applied")
        ops = self.store.load_all()
        self.assertEqual(ops[0].status, "applied")

    def test_load_all_preserves_sequence_ordering(self) -> None:
        op1 = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
        op2 = AddClipOp(author="user", asset_hash="b", track_id="v1", position_sec=5.0)
        op3 = AddClipOp(author="user", asset_hash="c", track_id="v1", position_sec=10.0)

        self.store.append(op1)
        self.store.append(op2)
        self.store.append(op3)

        ops = self.store.load_all()
        self.assertEqual(len(ops), 3)
        self.assertEqual([o.asset_hash for o in ops], ["a", "b", "c"])

    def test_reorder_swaps_adjacent_ops(self) -> None:
        op1 = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
        op2 = AddClipOp(author="user", asset_hash="b", track_id="v1", position_sec=5.0)
        op3 = AddClipOp(author="user", asset_hash="c", track_id="v1", position_sec=10.0)

        self.store.append(op1)
        self.store.append(op2)
        self.store.append(op3)

        self.store.reorder(op1.edit_id, op2.edit_id)
        ops = self.store.load_all()
        self.assertEqual([o.asset_hash for o in ops], ["b", "a", "c"])

    def test_reorder_rejects_non_adjacent_ops(self) -> None:
        op1 = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
        op2 = AddClipOp(author="user", asset_hash="b", track_id="v1", position_sec=5.0)
        op3 = AddClipOp(author="user", asset_hash="c", track_id="v1", position_sec=10.0)

        self.store.append(op1)
        self.store.append(op2)
        self.store.append(op3)

        with self.assertRaisesRegex(ValueError, "adjacent"):
            self.store.reorder(op1.edit_id, op3.edit_id)

    def test_reorder_rejects_missing_ops(self) -> None:
        op1 = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
        self.store.append(op1)

        with self.assertRaisesRegex(ValueError, "exist"):
            self.store.reorder(op1.edit_id, "nonexistent-id")


if __name__ == "__main__":
    unittest.main()
