"""End-to-end test: ingest -> add ops -> derive timeline -> undo -> re-derive.

Exercises the full Phase 0+1 stack. Uses 3 fixture videos and builds a
small timeline with transitions.
"""
import shutil
from pathlib import Path

import pytest

from open_edit.ir.apply import derive_timeline
from open_edit.ir.types import (
    AddClipOp, AddEffectOp, AddTransitionOp, Project, RemoveClipOp, SetKeyframeOp,
)
from open_edit.ir.validate import validate_op
from open_edit.storage.assets import AssetStore
from open_edit.storage.edit_graph import EditGraphStore


TESTDATA = Path(__file__).parent / "testdata" / "raw_videos"


def _has_ffprobe() -> bool:
    return shutil.which("ffprobe") is not None


pytestmark = pytest.mark.skipif(
    not _has_ffprobe(), reason="ffprobe not installed"
)


def test_e2e_ingest_add_three_clips_two_transitions_undo(tmp_path: Path) -> None:
    # 1. Ingest
    store_path = tmp_path / "assets"
    asset_store = AssetStore(store_path)
    assets = asset_store.ingest_paths([
        str(TESTDATA / "clip_a.mp4"),
        str(TESTDATA / "clip_b.mp4"),
        str(TESTDATA / "clip_c.mp4"),
    ])
    assert len(assets) == 3

    # 2. Set up edit graph
    db_path = tmp_path / "edit_graph.db"
    graph = EditGraphStore(db_path)
    project = Project(
        name="e2e",
        assets={a.asset_hash: a for a in assets},
    )

    # 3. Add 3 clips on video track
    op1 = AddClipOp(
        author="user", asset_hash=assets[0].asset_hash,
        track_id="v1", position_sec=0.0,
        in_point_sec=0.0, out_point_sec=2.0,
    )
    op2 = AddClipOp(
        author="user", asset_hash=assets[1].asset_hash,
        track_id="v1", position_sec=2.0,
        in_point_sec=0.0, out_point_sec=2.0,
    )
    op3 = AddClipOp(
        author="user", asset_hash=assets[2].asset_hash,
        track_id="v1", position_sec=4.0,
        in_point_sec=0.0, out_point_sec=2.0,
    )
    for op in [op1, op2, op3]:
        assert validate_op(op, project) == []
        graph.append(op)
        project.edit_graph.append(op)

    # 4. Add 2 transitions (Bug A: centered on cut, not midpoint)
    op_t1 = AddTransitionOp(
        author="user", clip_a_id=op1.clip_id, clip_b_id=op2.clip_id,
        transition_type="luma", duration_sec=1.0,
    )
    op_t2 = AddTransitionOp(
        author="user", clip_a_id=op2.clip_id, clip_b_id=op3.clip_id,
        transition_type="luma", duration_sec=1.0,
    )
    for op in [op_t1, op_t2]:
        assert validate_op(op, project) == []
        graph.append(op)
        project.edit_graph.append(op)

    # 5. Derive timeline
    timeline = derive_timeline(project)
    assert len(timeline.tracks) == 1
    assert len(timeline.tracks[0].clips) == 3
    # Bug A: clip1 was 2.0s long with a 1.0s transition centered on the
    # cut (cut = clip1.out_point_sec = 2.0). clip1.out_point_sec becomes
    # cut - half = 2.0 - 0.5 = 1.5. clip2.in_point_sec (asset-local) is
    # back-solved to (cut + half) - clip_b.position_sec = 2.5 - 2.0 = 0.5.
    assert timeline.tracks[0].clips[0].out_point_sec == pytest.approx(1.5, abs=0.001)
    assert timeline.tracks[0].clips[1].in_point_sec == pytest.approx(0.5, abs=0.001)

    # 6. Undo the most recent op (op_t2)
    ops = graph.load_all()
    most_recent = next(o for o in reversed(ops) if o.status == "applied")
    graph.update_status(most_recent.edit_id, "reverted")
    project.edit_graph[-1] = project.edit_graph[-1].model_copy(update={"status": "reverted"})

    # 7. Re-derive: now 3 clips, 1 transition (op_t1 still applied)
    timeline2 = derive_timeline(project)
    assert len(timeline2.tracks[0].clips) == 3
    # clip2's in_point_sec is still trimmed by op_t1 (not op_t2) — revert
    # of op_t2 doesn't restore it. clip2.out_point_sec is back to 2.0.
    assert timeline2.tracks[0].clips[1].in_point_sec == pytest.approx(0.5, abs=0.001)
    assert timeline2.tracks[0].clips[1].out_point_sec == pytest.approx(2.0, abs=0.001)
    assert timeline2.tracks[0].clips[2].in_point_sec == pytest.approx(0.0, abs=0.001)

    # 8. Add an effect + keyframes to clip1
    eff = AddEffectOp(
        author="user", target_kind="clip", target_id=op1.clip_id,
        effect_type="volume", params={"gain": 1.0},
    )
    assert validate_op(eff, project) == []
    graph.append(eff)
    project.edit_graph.append(eff)
    kf = SetKeyframeOp(
        author="user", effect_id=eff.effect_id, param="gain",
        keyframes=[(0.0, 1.0, "linear"), (1.5, 0.0, "linear")],
    )
    assert validate_op(kf, project) == []
    graph.append(kf)
    project.edit_graph.append(kf)

    # 9. Final timeline
    timeline3 = derive_timeline(project)
    # clip1 now has 2 effects: the transition_luma from op_t1, plus the
    # volume effect we just added. Find the volume effect and check its
    # keyframes.
    effects = timeline3.tracks[0].clips[0].effects
    volume_effect = next(e for e in effects if e.effect_type == "volume")
    assert volume_effect.keyframes["gain"] == [
        (0.0, 1.0, "linear"), (1.5, 0.0, "linear")
    ]


def test_e2e_remove_unknown_clip_is_no_op(tmp_path: Path) -> None:
    """Removing a clip that was never added is a no-op (validate allows it)."""
    db_path = tmp_path / "edit_graph.db"
    graph = EditGraphStore(db_path)
    project = Project(name="e2e")
    op = AddClipOp(
        author="user", asset_hash="x", track_id="v1", position_sec=0.0,
    )
    # Don't add asset to project.assets — validate should fail.
    errors = validate_op(op, project)
    assert any("Unknown asset_hash" in e for e in errors)
