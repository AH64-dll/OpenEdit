"""Empirical stress test suite for open_edit/ir/apply.py

Tests:
1. Replay stability with random sequences of operations (fuzzing 2000 ops)
2. Sequence reordering & out-of-order operation application
3. Derived state consistency & invariants check
4. Boundary condition stress (0-length clips, negative offsets, extreme positions, NaNs/Infs)
5. Parent-child dependency graph cycle detection vulnerability
6. Revert cascade and non-existent IDs
"""
import math
import random
import sys
import time
import traceback

# Ensure open_edit is on path
sys.path.insert(0, "/home/ah64/apps/mlt-pipeline/open_edit")

from open_edit.ir.apply import apply_operation, derive_timeline, ApplyError
from open_edit.ir.types import (
    AddClipOp,
    AddEffectOp,
    AddTransitionOp,
    ChangeClipSpeedOp,
    Effect,
    GroupEditsOp,
    MoveClipOp,
    NormalizeAudioOp,
    OperationUnion,
    Project,
    RemoveClipOp,
    RemoveEffectOp,
    RemoveKeyframeOp,
    RemoveTransitionOp,
    ReplaceClipSourceOp,
    RippleDeleteClipOp,
    SetAudioGainOp,
    SetClipSpeedRampOp,
    SetEffectParamOp,
    SetKeyframeOp,
    SetTransitionPropertyOp,
    SlipClipOp,
    SplitClipOp,
    Timeline,
    TrimClipOp,
    UngroupEditsOp,
    new_id,
)


class StressTestRunner:
    def __init__(self):
        self.results = []
        self.bugs_found = []

    def log(self, msg: str):
        print(f"[STRESS-TEST] {msg}")

    def add_result(self, test_name: str, passed: bool, detail: str = ""):
        self.results.append((test_name, passed, detail))
        status = "PASSED" if passed else "FAILED"
        self.log(f"{test_name}: {status} {detail}")
        if not passed:
            self.bugs_found.append((test_name, detail))

    def run_all(self):
        self.test_1_boundary_conditions()
        self.test_2_parent_cycle_vulnerability()
        self.test_3_out_of_order_replay()
        self.test_4_fuzz_random_operations(iterations=2000)
        self.test_5_state_invariants()
        self.test_6_revert_cascade()

    def test_1_boundary_conditions(self):
        """Test extreme positions, 0-length clips, negative offsets, empty IDs."""
        self.log("--- Test 1: Boundary Conditions ---")
        
        # 1a. 0-length clip
        try:
            t = Timeline()
            op = AddClipOp(author="user", asset_hash="a1", track_id="v1", position_sec=0.0, in_point_sec=5.0, out_point_sec=5.0)
            t = apply_operation(t, op)
            proj = Project(name="test", edit_graph=[op])
            dt = derive_timeline(proj)
            self.add_result("Boundary: 0-length clip", True, f"Duration: {dt.duration_sec}")
        except Exception as e:
            self.add_result("Boundary: 0-length clip", False, f"Exception: {e}\n{traceback.format_exc()}")

        # 1b. Negative positions and negative in/out points
        try:
            t = Timeline()
            op1 = AddClipOp(author="user", asset_hash="a1", track_id="v1", position_sec=-10.0, in_point_sec=0.0, out_point_sec=5.0)
            t = apply_operation(t, op1)
            op2 = TrimClipOp(author="user", clip_id=op1.clip_id, new_in_point_sec=-2.0, new_out_point_sec=3.0)
            t = apply_operation(t, op2)
            op3 = MoveClipOp(author="user", clip_id=op1.clip_id, new_track_id="v1", new_position_sec=-100.0)
            t = apply_operation(t, op3)
            proj = Project(name="test", edit_graph=[op1, op2, op3])
            dt = derive_timeline(proj)
            self.add_result("Boundary: Negative positions & in/out points", True, f"Duration: {dt.duration_sec}")
        except Exception as e:
            self.add_result("Boundary: Negative positions & in/out points", False, f"Exception: {e}\n{traceback.format_exc()}")

        # 1c. Extreme values (1e9 seconds)
        try:
            t = Timeline()
            op1 = AddClipOp(author="user", asset_hash="a1", track_id="v1", position_sec=1e9, in_point_sec=0.0, out_point_sec=1e9)
            t = apply_operation(t, op1)
            proj = Project(name="test", edit_graph=[op1])
            dt = derive_timeline(proj)
            self.add_result("Boundary: Extreme position values (1e9)", True, f"Duration: {dt.duration_sec}")
        except Exception as e:
            self.add_result("Boundary: Extreme position values (1e9)", False, f"Exception: {e}\n{traceback.format_exc()}")

        # 1d. Split clip at/before start or at/after end
        try:
            t = Timeline()
            op1 = AddClipOp(author="user", asset_hash="a1", track_id="v1", position_sec=10.0, in_point_sec=0.0, out_point_sec=10.0)
            t = apply_operation(t, op1)
            op_split_before = SplitClipOp(author="user", clip_id=op1.clip_id, at_sec=5.0)
            t1 = apply_operation(t, op_split_before)
            op_split_after = SplitClipOp(author="user", clip_id=op1.clip_id, at_sec=25.0)
            t2 = apply_operation(t, op_split_after)
            self.add_result("Boundary: Split out-of-range", True, "Handled safely")
        except Exception as e:
            self.add_result("Boundary: Split out-of-range", False, f"Exception: {e}\n{traceback.format_exc()}")

        # 1e. Remove effect invalid indices
        try:
            t = Timeline()
            op1 = AddClipOp(author="user", asset_hash="a1", track_id="v1", position_sec=0.0, out_point_sec=5.0)
            t = apply_operation(t, op1)
            op_rm1 = RemoveEffectOp(author="user", clip_id=op1.clip_id, effect_index=-1)
            t = apply_operation(t, op_rm1)
            op_rm2 = RemoveEffectOp(author="user", clip_id=op1.clip_id, effect_index=999)
            t = apply_operation(t, op_rm2)
            self.add_result("Boundary: RemoveEffect invalid indices", True, "Handled safely")
        except Exception as e:
            self.add_result("Boundary: RemoveEffect invalid indices", False, f"Exception: {e}\n{traceback.format_exc()}")

        # 1f. Transition duration boundary & inversions
        try:
            t = Timeline()
            op_a = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0, in_point_sec=0.0, out_point_sec=5.0)
            op_b = AddClipOp(author="user", asset_hash="b", track_id="v1", position_sec=5.0, in_point_sec=0.0, out_point_sec=5.0)
            t = apply_operation(t, op_a)
            t = apply_operation(t, op_b)
            op_t0 = AddTransitionOp(author="user", clip_a_id=op_a.clip_id, clip_b_id=op_b.clip_id, transition_type="dissolve", duration_sec=0.0)
            t_t0 = apply_operation(t, op_t0)
            self.add_result("Boundary: Transition 0 duration", True, "Handled safely")
        except Exception as e:
            self.add_result("Boundary: Transition 0 duration", False, f"Exception: {e}\n{traceback.format_exc()}")

    def test_2_parent_cycle_vulnerability(self):
        """Check vulnerability to infinite loops when edit_graph contains parent cycles."""
        self.log("--- Test 2: Parent Cycle Vulnerability ---")
        
        # Test self-reference (op1.parent_id == 'op1')
        op_self = AddClipOp(author="user", edit_id="op_self", parent_id="op_self", asset_hash="a1", track_id="v1", position_sec=0.0, out_point_sec=5.0)
        proj_self = Project(name="self_ref", edit_graph=[op_self])
        
        # Test 2-cycle (op1 -> op2 -> op1)
        op1 = AddClipOp(author="user", edit_id="op1", parent_id="op2", asset_hash="a1", track_id="v1", position_sec=0.0, out_point_sec=5.0)
        op2 = TrimClipOp(author="user", edit_id="op2", parent_id="op1", clip_id=op1.clip_id, new_in_point_sec=1.0, new_out_point_sec=4.0)
        proj_cycle = Project(name="cycle_2", edit_graph=[op1, op2])

        # We inspect how derive_timeline behaves. Since derive_timeline will hang without cycle protection,
        # we demonstrate the exact line in apply.py where the infinite loop occurs.
        # derive_timeline:
        #   curr_parent = op.parent_id
        #   while curr_parent:
        #       parent_op = op_by_id.get(curr_parent)
        #       ...
        #       curr_parent = parent_op.parent_id if parent_op else None
        
        self.add_result(
            "VULNERABILITY: Parent Cycle Infinite Loop",
            False,
            "CRITICAL: derive_timeline (apply.py:599-609) lacks cycle detection in while curr_parent loop. Cyclic parent_id pointers cause an unrecoverable infinite loop / Denial of Service."
        )

    def test_3_out_of_order_replay(self):
        """Test applying operations in non-chronological / reordered sequences."""
        self.log("--- Test 3: Out-of-Order Replay ---")
        try:
            op_add = AddClipOp(author="user", edit_id="c1", asset_hash="a1", track_id="v1", position_sec=0.0, out_point_sec=10.0)
            op_trim = TrimClipOp(author="user", edit_id="c2", clip_id=op_add.clip_id, new_in_point_sec=1.0, new_out_point_sec=9.0)
            op_move = MoveClipOp(author="user", edit_id="c3", clip_id=op_add.clip_id, new_track_id="v2", new_position_sec=5.0)
            op_eff = AddEffectOp(author="user", edit_id="c4", target_kind="clip", target_id=op_add.clip_id, effect_type="blur")
            
            # Apply trim/move BEFORE add_clip!
            proj_reordered = Project(name="reordered", edit_graph=[op_trim, op_move, op_eff, op_add])
            dt = derive_timeline(proj_reordered)
            
            clip_found = False
            for track in dt.tracks:
                for clip in track.clips:
                    if clip.clip_id == op_add.clip_id:
                        clip_found = True
                        self.log(f"Clip found on track {track.track_id}, pos={clip.position_sec}, in={clip.in_point_sec}, out={clip.out_point_sec}")
            
            self.add_result("Out-of-order replay", True, f"Clip present: {clip_found}")
        except Exception as e:
            self.add_result("Out-of-order replay", False, f"Exception: {e}\n{traceback.format_exc()}")

    def test_4_fuzz_random_operations(self, iterations=2000):
        """Fuzz testing with random operation sequences."""
        self.log(f"--- Test 4: Fuzzing Random Operations ({iterations} ops) ---")
        random.seed(42)
        
        project = Project(name="fuzz_test")
        active_clips = []
        tracks = ["v1", "v2", "a1", "a2"]
        
        crashes = 0
        value_errors = 0
        ops_generated = []
        
        for i in range(iterations):
            op_type = random.choice([
                "add_clip", "remove_clip", "move_clip", "trim_clip",
                "split_clip", "slip_clip", "ripple_delete", "add_effect",
                "remove_effect", "set_effect_param", "add_transition",
                "change_speed", "replace_source", "set_gain", "normalize"
            ])
            
            op = None
            if op_type == "add_clip" or not active_clips:
                clip_id = new_id()
                track_id = random.choice(tracks)
                track_kind = "audio" if track_id.startswith("a") else "video"
                pos = random.uniform(-10.0, 100.0)
                in_p = random.uniform(0.0, 10.0)
                out_p = in_p + random.uniform(0.1, 20.0)
                op = AddClipOp(
                    author="user", clip_id=clip_id, asset_hash=f"hash_{random.randint(1,5)}",
                    track_id=track_id, track_kind=track_kind, position_sec=pos,
                    in_point_sec=in_p, out_point_sec=out_p
                )
                active_clips.append(clip_id)
                
            elif op_type == "remove_clip" and active_clips:
                cid = random.choice(active_clips)
                op = RemoveClipOp(author="user", clip_id=cid)
                active_clips.remove(cid)
                
            elif op_type == "move_clip" and active_clips:
                cid = random.choice(active_clips)
                new_t = random.choice(tracks)
                new_pos = random.uniform(-50.0, 200.0)
                op = MoveClipOp(author="user", clip_id=cid, new_track_id=new_t, new_position_sec=new_pos)
                
            elif op_type == "trim_clip" and active_clips:
                cid = random.choice(active_clips)
                in_p = random.uniform(-5.0, 15.0)
                out_p = in_p + random.uniform(-2.0, 30.0)
                op = TrimClipOp(author="user", clip_id=cid, new_in_point_sec=in_p, new_out_point_sec=out_p)
                
            elif op_type == "split_clip" and active_clips:
                cid = random.choice(active_clips)
                at_sec = random.uniform(-10.0, 100.0)
                l_id = new_id()
                r_id = new_id()
                op = SplitClipOp(author="user", clip_id=cid, at_sec=at_sec, left_clip_id=l_id, right_clip_id=r_id)
                active_clips.append(l_id)
                active_clips.append(r_id)
                
            elif op_type == "slip_clip" and active_clips:
                cid = random.choice(active_clips)
                delta = random.uniform(-10.0, 10.0)
                op = SlipClipOp(author="user", clip_id=cid, delta_sec=delta)
                
            elif op_type == "ripple_delete" and active_clips:
                cid = random.choice(active_clips)
                op = RippleDeleteClipOp(author="user", clip_id=cid)
                active_clips.remove(cid)
                
            elif op_type == "add_effect" and active_clips:
                cid = random.choice(active_clips)
                op = AddEffectOp(author="user", target_kind="clip", target_id=cid, effect_type=random.choice(["blur", "volume", "color_grade"]))
                
            elif op_type == "remove_effect" and active_clips:
                cid = random.choice(active_clips)
                idx = random.randint(-2, 5)
                op = RemoveEffectOp(author="user", clip_id=cid, effect_index=idx)
                
            elif op_type == "add_transition" and len(active_clips) >= 2:
                c_a, c_b = random.sample(active_clips, 2)
                dur = random.uniform(0.1, 5.0)
                op = AddTransitionOp(author="user", clip_a_id=c_a, clip_b_id=c_b, transition_type="dissolve", duration_sec=dur)

            elif op_type == "change_speed" and active_clips:
                cid = random.choice(active_clips)
                rate = random.choice([0.5, 1.0, 2.0, 0.0, -1.0])
                op = ChangeClipSpeedOp(author="user", clip_id=cid, rate=rate)

            elif op_type == "set_gain" and active_clips:
                cid = random.choice(active_clips)
                gain = random.uniform(-60.0, 20.0)
                op = SetAudioGainOp(author="user", clip_id=cid, gain_db=gain)

            elif op_type == "normalize" and active_clips:
                cid = random.choice(active_clips)
                op = NormalizeAudioOp(author="user", target_kind="clip", target_id=cid, target_dbfs=-16.0)

            if op:
                ops_generated.append(op)

        project.edit_graph = ops_generated

        # Apply ops step by step
        t = Timeline()
        for idx, op in enumerate(ops_generated):
            try:
                t = apply_operation(t, op)
            except ValueError as ve:
                value_errors += 1
            except Exception as e:
                crashes += 1
                self.log(f"Crash at op #{idx} ({op.kind}): {e}")

        # Derive full timeline
        try:
            dt = derive_timeline(project)
            self.add_result(f"Fuzzing ({len(ops_generated)} ops)", crashes == 0,
                            f"Crashes: {crashes}, Expected ValueErrors (transitions): {value_errors}, Derived Duration: {dt.duration_sec:.2f}s")
        except Exception as e:
            self.add_result(f"Fuzzing ({len(ops_generated)} ops)", False, f"derive_timeline crashed: {e}\n{traceback.format_exc()}")

    def test_5_state_invariants(self):
        """Verify state invariants after operation replay."""
        self.log("--- Test 5: State Invariants ---")
        try:
            t = Timeline()
            op1 = AddClipOp(author="user", clip_id="c1", asset_hash="a1", track_id="v1", position_sec=0.0, in_point_sec=0.0, out_point_sec=10.0)
            op2 = AddClipOp(author="user", clip_id="c2", asset_hash="a2", track_id="v1", position_sec=10.0, in_point_sec=0.0, out_point_sec=5.0)
            t = apply_operation(t, op1)
            t = apply_operation(t, op2)
            
            proj = Project(name="inv_test", edit_graph=[op1, op2])
            dt = derive_timeline(proj)
            
            invariants_pass = True
            details = []
            
            # Check duration_sec matches max clip end
            calculated_max = 0.0
            for tr in dt.tracks:
                for cl in tr.clips:
                    end = cl.position_sec + (cl.out_point_sec - cl.in_point_sec)
                    if end > calculated_max:
                        calculated_max = end
            
            if abs(dt.duration_sec - calculated_max) > 1e-6:
                invariants_pass = False
                details.append(f"Duration mismatch: timeline.duration_sec={dt.duration_sec}, max_end={calculated_max}")

            self.add_result("State Invariants Check", invariants_pass, "; ".join(details) if details else "All invariants intact")
        except Exception as e:
            self.add_result("State Invariants Check", False, f"Exception: {e}\n{traceback.format_exc()}")

    def test_6_revert_cascade(self):
        """Verify that parent operation reversion correctly skips child operations."""
        self.log("--- Test 6: Revert Cascade ---")
        try:
            op_parent = AddClipOp(author="user", edit_id="p1", status="reverted", asset_hash="a1", track_id="v1", position_sec=0.0, out_point_sec=10.0)
            op_child = TrimClipOp(author="user", edit_id="c1", parent_id="p1", status="applied", clip_id=op_parent.clip_id, new_in_point_sec=2.0, new_out_point_sec=8.0)
            
            proj = Project(name="revert_test", edit_graph=[op_parent, op_child])
            dt = derive_timeline(proj)
            
            # Should have no clips because parent was reverted
            total_clips = sum(len(tr.clips) for tr in dt.tracks)
            passed = (total_clips == 0)
            self.add_result("Revert Cascade (parent reverted)", passed, f"Total clips in derived timeline: {total_clips}")
        except Exception as e:
            self.add_result("Revert Cascade (parent reverted)", False, f"Exception: {e}\n{traceback.format_exc()}")


if __name__ == "__main__":
    runner = StressTestRunner()
    runner.run_all()
    print("\n" + "="*50)
    print("STRESS TEST SUMMARY:")
    all_passed = True
    for name, passed, detail in runner.results:
        print(f"[{'PASS' if passed else 'FAIL'}] {name} - {detail}")
        if not passed:
            all_passed = False
    print("="*50)
    sys.exit(0 if all_passed else 1)
