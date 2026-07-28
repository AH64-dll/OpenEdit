"""Pytest configuration for open_edit tests."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def tmp_notes_db(tmp_path):
    """An isolated notes database file under a fresh tmp dir."""
    from open_edit.storage.notes import NotesStore
    return NotesStore(tmp_path / "notes.db")


@pytest.fixture
def tmp_project_with_assets(tmp_path):
    """A project with one asset pre-ingested, suitable for free-form runs (L9).

    Seeds on-disk state (CAS asset + edit graph entry) so run_free_form can
    discover the asset via _load_assets_via_store. Returns a Project without
    the misleading in-memory assets/edit_graph dicts: the sandbox always loads
    from disk, so in-memory state would diverge from reality.
    """
    from open_edit.ir.types import AddClipOp, Asset, Project
    from open_edit.storage.assets import AssetStore
    from open_edit.storage.edit_graph import EditGraphStore

    # AssetStore CAS layout: <assets_dir>/<hash[:2]>/<hash> (bare) with a
    # sibling <hash>.meta.json sidecar. The sidecar lets AssetStore.get()
    # return full metadata without invoking ffprobe on the 1-byte placeholder.
    asset = Asset(
        asset_hash="abc123",
        original_path="/tmp/clip.mp4",
        stored_path="",
        type="video",
        duration_sec=10.0,
        fps=30.0, width=1920, height=1080, codec="h264", has_audio=True,
    )
    asset_store = AssetStore(tmp_path / "assets")
    cas_file = asset_store._cas_path(asset.asset_hash)
    cas_file.parent.mkdir(parents=True, exist_ok=True)
    cas_file.write_bytes(b"\x00")
    asset.stored_path = str(cas_file)
    sidecar = asset_store._sidecar_path(asset.asset_hash)
    sidecar.write_text(asset.model_dump_json(indent=2))

    # Seed the edit graph with an AddClipOp so _load_assets_via_store
    # discovers the asset hash (it scans prior AddClipOps, not the fs).
    graph = EditGraphStore(tmp_path / "edit_graph.db")
    seed_op = AddClipOp(
        author="user",
        asset_hash=asset.asset_hash,
        track_id="video_main",
        position_sec=0.0,
        in_point_sec=0.0,
        out_point_sec=asset.duration_sec,
    )
    graph.append(seed_op)

    return Project(name="test", workdir=tmp_path)
