"""Pytest configuration for open_edit tests."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def tmp_project_with_assets(tmp_path):
    """A project with one asset pre-ingested, suitable for free-form runs (L9)."""
    from open_edit.ir.types import AddClipOp, Asset, Project
    from open_edit.storage.edit_graph import EditGraphStore
    # CAS layout is <assets_dir>/<hash[:2]>/<hash> (bare file, no extension).
    # Place a dummy byte at that path and a sidecar JSON so AssetStore.get()
    # returns the asset without needing ffprobe on a 1-byte placeholder.
    cas_file = tmp_path / "assets" / "ab" / "abc123"
    cas_file.parent.mkdir(parents=True)
    cas_file.write_bytes(b"\x00")
    asset = Asset(
        asset_hash="abc123",
        original_path="/tmp/clip.mp4",
        stored_path=str(cas_file),
        type="video",
        duration_sec=10.0,
        fps=30.0, width=1920, height=1080, codec="h264", has_audio=True,
    )
    sidecar = cas_file.parent / "abc123.meta.json"
    sidecar.write_text(asset.model_dump_json(indent=2))
    # Seed edit_graph.db with an AddClipOp so _load_assets_via_store discovers
    # the asset hash (it scans prior AddClipOps, not the filesystem).
    store = EditGraphStore(tmp_path / "edit_graph.db")
    seed_op = AddClipOp(
        author="user", asset_hash=asset.asset_hash,
        track_id="video_main", position_sec=0.0,
        in_point_sec=0.0, out_point_sec=10.0,
    )
    store.append(seed_op)
    return Project(
        name="test", workdir=tmp_path,
        assets={asset.asset_hash: asset},
        edit_graph=[seed_op],
    )
