"""Pytest configuration for open_edit tests."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def tmp_project_with_assets(tmp_path):
    """A project with one asset pre-ingested, suitable for free-form runs (L9)."""
    from open_edit.ir.types import Project, Asset
    stored = tmp_path / "assets" / "ab" / "abc123" / "clip.mp4"
    stored.parent.mkdir(parents=True)
    stored.write_bytes(b"\x00")
    asset = Asset(
        asset_hash="abc123",
        original_path="/tmp/clip.mp4",
        stored_path=str(stored),
        type="video",
        duration_sec=10.0,
        fps=30.0, width=1920, height=1080, codec="h264", has_audio=True,
    )
    # Create the edit_graph.db so run_free_form's preflight passes.
    (tmp_path / "edit_graph.db").touch()
    return Project(
        name="test", workdir=tmp_path,
        assets={asset.asset_hash: asset},
    )
