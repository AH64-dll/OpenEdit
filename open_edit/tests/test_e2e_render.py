"""End-to-end render test: ingest -> ops -> melt -> QC -> cache.

Ingest 3 fixture videos, apply 3 AddClipOp + 1 AddTransitionOp, render via
the orchestrator, verify the output is a non-empty MP4, verify the cache
key is stable, and verify a second render hits the cache.
"""
import shutil
from pathlib import Path

import pytest

from open_edit.ir.types import AddClipOp, AddTransitionOp, Project
from open_edit.render.cache import canonical_json_hash
from open_edit.render.orchestrator import render_project
from open_edit.storage.assets import AssetStore
from open_edit.storage.edit_graph import EditGraphStore


TESTDATA = Path(__file__).parent / "testdata" / "raw_videos"


def _has_required() -> bool:
    return shutil.which("melt") is not None and shutil.which("ffmpeg") is not None


pytestmark = pytest.mark.skipif(
    not _has_required(), reason="melt + ffmpeg required"
)


def test_e2e_render_three_clips_with_transition(tmp_path: Path) -> None:
    """Ingest 3 clips, add a transition, render via melt, verify QC gate."""
    project_dir = tmp_path
    open_edit_dir = project_dir / ".open_edit"
    open_edit_dir.mkdir(parents=True, exist_ok=True)

    # 1. Ingest (assets live under .open_edit/assets, matching the
    #    orchestrator's path resolution)
    asset_store = AssetStore(open_edit_dir / "assets")
    assets = asset_store.ingest_paths([
        str(TESTDATA / "clip_a.mp4"),
        str(TESTDATA / "clip_b.mp4"),
        str(TESTDATA / "clip_c.mp4"),
    ])
    assert len(assets) == 3

    # 2. Build edit graph (db lives under .open_edit/edit_graph.db, where
    #    the orchestrator expects to find it)
    graph = EditGraphStore(open_edit_dir / "edit_graph.db")
    project = Project(name="e2e", assets={a.asset_hash: a for a in assets})

    op1 = AddClipOp(author="user", asset_hash=assets[0].asset_hash,
                    track_id="v1", position_sec=0.0, in_point_sec=0.0, out_point_sec=2.0)
    op2 = AddClipOp(author="user", asset_hash=assets[1].asset_hash,
                    track_id="v1", position_sec=2.0, in_point_sec=0.0, out_point_sec=2.0)
    op3 = AddClipOp(author="user", asset_hash=assets[2].asset_hash,
                    track_id="v1", position_sec=4.0, in_point_sec=0.0, out_point_sec=2.0)
    for op in [op1, op2, op3]:
        graph.append(op)
        project.edit_graph.append(op)

    op_t = AddTransitionOp(author="user", clip_a_id=op1.clip_id, clip_b_id=op2.clip_id,
                           transition_type="luma", duration_sec=1.0)
    graph.append(op_t)
    project.edit_graph.append(op_t)

    # 3. Render
    result = render_project(
        project_id="e2e",
        project_dir=project_dir,
        workdir=tmp_path / "renders",
        mode="proxy",
        profile_name="480p30",
        force=True,
    )
    assert result.ok, f"render failed: {result.error}"
    assert Path(result.output_path).exists()
    assert Path(result.output_path).stat().st_size > 0

    # 4. Verify the cache key is stable across calls
    payload = [op.model_dump(mode="json") for op in project.edit_graph]
    expected_hash = canonical_json_hash(payload)
    assert result.edit_graph_hash == expected_hash

    # 5. Second render hits the cache (output_path points into the cache
    #    dir, so compare file contents rather than paths)
    result2 = render_project(
        project_id="e2e",
        project_dir=project_dir,
        workdir=tmp_path / "renders",
        mode="proxy",
        profile_name="480p30",
        force=False,
    )
    assert result2.ok
    assert result2.cache_hit is True
    assert Path(result2.output_path).exists()
    assert Path(result2.output_path).read_bytes() == Path(result.output_path).read_bytes()
