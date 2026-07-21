"""Empirical test harness for Milestone 3: Operation Replay & Derived State.

Tests SQLite EditGraphStore integration, operation tree replay, parent-child revert filtering,
status toggling, operation reordering, and derived state correctness.
"""

import sys
from pathlib import Path
import tempfile
import unittest
import sqlite3

sys.path.insert(0, "/home/ah64/apps/mlt-pipeline/open_edit")

from open_edit.storage.edit_graph import EditGraphStore
from open_edit.ir.apply import derive_timeline, apply_operation
from open_edit.ir.types import (
    AddClipOp,
    AddEffectOp,
    TrimClipOp,
    MoveClipOp,
    SetKeyframeOp,
    FreeFormCodeOp,
    GroupEditsOp,
    Project,
    Timeline,
)


class TestEmpiricalReplayAndDerivedState(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_m3_replay.db"
        self.store = EditGraphStore(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_sqlite_persistence_and_project_id(self):
        """Verify SQLite DB initialization, project_id creation and persistence."""
        pid1 = self.store.project_id
        self.assertIsInstance(pid1, str)
        self.assertGreater(len(pid1), 0)

        # Reopen same DB file
        store2 = EditGraphStore(self.db_path)
        self.assertEqual(store2.project_id, pid1)

    def test_parent_child_revert_cascade_filtering(self):
        """Test multi-level parent-child tree and assert reverted parents exclude children."""
        # 1. Create operations:
        # P1: Root clip op (creates clip 'clip_p1')
        p1 = AddClipOp(
            author="user",
            asset_hash="hash_p1",
            track_id="v1",
            position_sec=0.0,
            in_point_sec=0.0,
            out_point_sec=10.0,
        )
        self.store.append(p1)

        # C1 (child of P1): Add effect to clip_p1
        c1 = AddEffectOp(
            author="ai",
            target_kind="clip",
            target_id=p1.clip_id,
            effect_type="volume",
            params={"gain": 0.8},
            parent_id=p1.edit_id,
        )
        self.store.append(c1)

        # GC1 (child of C1 / grandchild of P1): Set keyframe on effect C1
        gc1 = SetKeyframeOp(
            author="ai",
            effect_id=c1.effect_id,
            param="gain",
            keyframes=[(0.0, 0.8, "linear"), (5.0, 0.2, "linear")],
            parent_id=c1.edit_id,
        )
        self.store.append(gc1)

        # C2 (child of P1): Trim clip_p1
        c2 = TrimClipOp(
            author="ai",
            clip_id=p1.clip_id,
            new_in_point_sec=1.0,
            new_out_point_sec=9.0,
            parent_id=p1.edit_id,
        )
        self.store.append(c2)

        # Independent op I1 (no parent)
        i1 = AddClipOp(
            author="user",
            asset_hash="hash_i1",
            track_id="v1",
            position_sec=10.0,
            in_point_sec=0.0,
            out_point_sec=5.0,
        )
        self.store.append(i1)

        # --- Check State 1: All Ops Applied ---
        ops = self.store.load_all()
        project = Project(name="test_proj", edit_graph=ops)
        timeline = derive_timeline(project)

        self.assertEqual(len(timeline.tracks[0].clips), 2)
        clip_p1 = next(c for c in timeline.tracks[0].clips if c.clip_id == p1.clip_id)
        clip_i1 = next(c for c in timeline.tracks[0].clips if c.clip_id == i1.clip_id)

        # Verify C2 trim applied
        self.assertEqual(clip_p1.in_point_sec, 1.0)
        self.assertEqual(clip_p1.out_point_sec, 9.0)
        # Verify C1 effect and GC1 keyframes applied
        self.assertEqual(len(clip_p1.effects), 1)
        self.assertEqual(clip_p1.effects[0].effect_id, c1.effect_id)
        self.assertIn("gain", clip_p1.effects[0].keyframes)
        self.assertEqual(len(clip_p1.effects[0].keyframes["gain"]), 2)

        # --- Check State 2: Revert Parent P1 ---
        self.store.update_status(p1.edit_id, "reverted")
        ops = self.store.load_all()
        project = Project(name="test_proj", edit_graph=ops)
        timeline = derive_timeline(project)

        # Since P1 is reverted, P1 and all its descendants (C1, GC1, C2) MUST be excluded!
        self.assertEqual(len(timeline.tracks[0].clips), 1)
        self.assertEqual(timeline.tracks[0].clips[0].clip_id, i1.clip_id)

        # --- Check State 3: Re-apply P1, Revert Child C1 ---
        self.store.update_status(p1.edit_id, "applied")
        self.store.update_status(c1.edit_id, "reverted")
        ops = self.store.load_all()
        project = Project(name="test_proj", edit_graph=ops)
        timeline = derive_timeline(project)

        self.assertEqual(len(timeline.tracks[0].clips), 2)
        clip_p1 = next(c for c in timeline.tracks[0].clips if c.clip_id == p1.clip_id)
        # C2 trim should still be applied
        self.assertEqual(clip_p1.in_point_sec, 1.0)
        self.assertEqual(clip_p1.out_point_sec, 9.0)
        # C1 effect and its child GC1 should be excluded!
        self.assertEqual(len(clip_p1.effects), 0)

        # --- Check State 4: Deep 4-level Parent-Child Chain ---
        # Level 1: Root P2
        p2 = FreeFormCodeOp(
            author="ai",
            code="pass",
        )
        self.store.append(p2)

        # Level 2: Child C3 (child of P2)
        c3 = AddClipOp(
            author="ai",
            asset_hash="hash_deep",
            track_id="v2",
            position_sec=0.0,
            in_point_sec=0.0,
            out_point_sec=4.0,
            parent_id=p2.edit_id,
        )
        self.store.append(c3)

        # Level 3: Grandchild GC2 (child of C3)
        gc2 = AddEffectOp(
            author="ai",
            target_kind="clip",
            target_id=c3.clip_id,
            effect_type="blur",
            params={"radius": 5.0},
            parent_id=c3.edit_id,
        )
        self.store.append(gc2)

        # Level 4: Great-Grandchild GGC1 (child of GC2)
        ggc1 = SetKeyframeOp(
            author="ai",
            effect_id=gc2.effect_id,
            param="radius",
            keyframes=[(0.0, 0.0, "linear"), (2.0, 5.0, "linear")],
            parent_id=gc2.edit_id,
        )
        self.store.append(ggc1)

        # Verify deep chain applied
        ops = self.store.load_all()
        project = Project(name="test_proj", edit_graph=ops)
        timeline = derive_timeline(project)
        track_v2 = next(t for t in timeline.tracks if t.track_id == "v2")
        self.assertEqual(len(track_v2.clips), 1)
        self.assertEqual(len(track_v2.clips[0].effects), 1)

        # Revert root parent P2
        self.store.update_status(p2.edit_id, "reverted")
        ops = self.store.load_all()
        project = Project(name="test_proj", edit_graph=ops)
        timeline = derive_timeline(project)

        # Track v2 should be empty or have no clips from C3/GC2/GGC1
        clips_v2 = [c for t in timeline.tracks if t.track_id == "v2" for c in t.clips]
        self.assertEqual(len(clips_v2), 0)

        # Revert middle ancestor GC2 while P2 and C3 are applied
        self.store.update_status(p2.edit_id, "applied")
        self.store.update_status(gc2.edit_id, "reverted")
        ops = self.store.load_all()
        project = Project(name="test_proj", edit_graph=ops)
        timeline = derive_timeline(project)

        clips_v2 = [c for t in timeline.tracks if t.track_id == "v2" for c in t.clips]
        self.assertEqual(len(clips_v2), 1)
        # Effect GC2 and keyframe GGC1 must be excluded
        self.assertEqual(len(clips_v2[0].effects), 0)

    def test_branching_tree_revert(self):
        """Test a branching tree where reverting one branch leaves sibling branches intact."""
        root = AddClipOp(
            author="user", asset_hash="root_asset", track_id="v1", position_sec=0.0
        )
        self.store.append(root)

        # Branch A
        b1_eff = AddEffectOp(
            author="ai", target_kind="clip", target_id=root.clip_id,
            effect_type="volume", params={"gain": 0.5}, parent_id=root.edit_id
        )
        self.store.append(b1_eff)

        # Branch B
        b2_trim = TrimClipOp(
            author="ai", clip_id=root.clip_id, new_in_point_sec=1.0, new_out_point_sec=4.0,
            parent_id=root.edit_id
        )
        self.store.append(b2_trim)

        # Revert Branch A
        self.store.update_status(b1_eff.edit_id, "reverted")
        project = Project(name="branch_test", edit_graph=self.store.load_all())
        tl = derive_timeline(project)

        clip = tl.tracks[0].clips[0]
        # Branch B (trim) applied
        self.assertEqual(clip.in_point_sec, 1.0)
        self.assertEqual(clip.out_point_sec, 4.0)
        # Branch A (effect) excluded
        self.assertEqual(len(clip.effects), 0)

    def test_operation_reordering_effects(self) -> None:
        """Test reordering operations in SQLite and verifying updated timeline derived state."""
        clip1 = AddClipOp(
            author="user",
            asset_hash="hash_reorder",
            track_id="v1",
            position_sec=0.0,
            in_point_sec=0.0,
            out_point_sec=10.0,
        )
        self.store.append(clip1)

        # Move 1: position -> 10.0
        move1 = MoveClipOp(
            author="user",
            clip_id=clip1.clip_id,
            new_track_id="v1",
            new_position_sec=10.0,
        )
        self.store.append(move1)

        # Move 2: position -> 20.0
        move2 = MoveClipOp(
            author="user",
            clip_id=clip1.clip_id,
            new_track_id="v1",
            new_position_sec=20.0,
        )
        self.store.append(move2)

        # Initial order: clip1 -> move1 (pos 10) -> move2 (pos 20)
        ops = self.store.load_all()
        project = Project(name="reorder_test", edit_graph=ops)
        timeline = derive_timeline(project)
        self.assertEqual(timeline.tracks[0].clips[0].position_sec, 20.0)

        # Reorder move1 and move2
        self.store.reorder(move1.edit_id, move2.edit_id)

        # Order now: clip1 -> move2 (pos 20) -> move1 (pos 10)
        ops = self.store.load_all()
        project = Project(name="reorder_test", edit_graph=ops)
        timeline = derive_timeline(project)
        self.assertEqual(timeline.tracks[0].clips[0].position_sec, 10.0)

    def test_status_toggling_applied_reverted_superseded(self) -> None:
        """Test transitions between applied, reverted, superseded."""
        op = AddClipOp(
            author="user", asset_hash="hash_toggle", track_id="v1", position_sec=0.0
        )
        self.store.append(op)

        # Check applied
        project = Project(name="toggle_test", edit_graph=self.store.load_all())
        self.assertEqual(len(derive_timeline(project).tracks[0].clips), 1)

        # Check reverted
        self.store.update_status(op.edit_id, "reverted")
        project = Project(name="toggle_test", edit_graph=self.store.load_all())
        self.assertEqual(len(derive_timeline(project).tracks), 0)

        # Check superseded
        self.store.update_status(op.edit_id, "superseded")
        project = Project(name="toggle_test", edit_graph=self.store.load_all())
        self.assertEqual(len(derive_timeline(project).tracks), 0)

        # Back to applied
        self.store.update_status(op.edit_id, "applied")
        project = Project(name="toggle_test", edit_graph=self.store.load_all())
        self.assertEqual(len(derive_timeline(project).tracks[0].clips), 1)

    def test_dangling_parent_id_handled_gracefully(self):
        """Test SQLite foreign key enforcement and in-memory derive_timeline fallback."""
        child = AddClipOp(
            author="user", asset_hash="dangling", track_id="v1", position_sec=0.0,
            parent_id="nonexistent_parent_id"
        )
        # 1. Store layer MUST reject appending dangling parent_id due to FOREIGN KEY constraint
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.append(child)

        # 2. In-memory project handling: if child op is in edit_graph, derive_timeline safely processes it
        project = Project(name="dangling_in_mem", edit_graph=[child])
        tl = derive_timeline(project)
        self.assertEqual(len(tl.tracks[0].clips), 1)
        self.assertEqual(tl.tracks[0].clips[0].asset_hash, "dangling")


if __name__ == "__main__":
    unittest.main()
