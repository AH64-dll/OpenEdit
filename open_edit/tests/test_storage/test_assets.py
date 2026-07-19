"""Tests for the AssetStore (content-addressed + ffprobe metadata)."""
import shutil
from pathlib import Path

import pytest

from open_edit.storage.assets import AssetStore, _probe_media


TESTDATA = Path(__file__).parent.parent / "testdata" / "raw_videos"


def _ffprobe_available() -> bool:
    return shutil.which("ffprobe") is not None


pytestmark = pytest.mark.skipif(
    not _ffprobe_available(), reason="ffprobe not installed"
)


def test_ingest_returns_asset_with_hash(tmp_path: Path) -> None:
    store = AssetStore(tmp_path / "assets")
    asset = store.ingest(str(TESTDATA / "clip_a.mp4"))
    assert len(asset.asset_hash) == 64  # SHA-256 hex
    assert asset.duration_sec > 0


def test_ingest_stores_file_in_cas_layout(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets"
    store = AssetStore(assets_dir)
    asset = store.ingest(str(TESTDATA / "clip_a.mp4"))
    expected = assets_dir / asset.asset_hash[:2] / asset.asset_hash
    assert expected.exists()


def test_ingest_same_file_twice_returns_same_hash(tmp_path: Path) -> None:
    store = AssetStore(tmp_path / "assets")
    a1 = store.ingest(str(TESTDATA / "clip_a.mp4"))
    a2 = store.ingest(str(TESTDATA / "clip_a.mp4"))
    assert a1.asset_hash == a2.asset_hash


def test_ingest_different_files_return_different_hashes(tmp_path: Path) -> None:
    store = AssetStore(tmp_path / "assets")
    a1 = store.ingest(str(TESTDATA / "clip_a.mp4"))
    a2 = store.ingest(str(TESTDATA / "clip_b.mp4"))
    assert a1.asset_hash != a2.asset_hash


def test_ingest_paths_rejects_empty_list(tmp_path: Path) -> None:
    """Bug B regression: empty paths list rejected with fix: line."""
    store = AssetStore(tmp_path / "assets")
    with pytest.raises(ValueError, match="empty"):
        store.ingest_paths([])


def test_ingest_rejects_nonexistent_file(tmp_path: Path) -> None:
    store = AssetStore(tmp_path / "assets")
    with pytest.raises(FileNotFoundError):
        store.ingest("/nonexistent/path/to/video.mp4")


def test_get_returns_ingested_asset(tmp_path: Path) -> None:
    store = AssetStore(tmp_path / "assets")
    asset = store.ingest(str(TESTDATA / "clip_a.mp4"))
    retrieved = store.get(asset.asset_hash)
    assert retrieved is not None
    assert retrieved.asset_hash == asset.asset_hash


def test_get_returns_full_metadata_via_sidecar(tmp_path: Path) -> None:
    """Bug-hunt finding: get() must return the full Asset metadata that was
    captured at ingest time, not the placeholder empty/default values
    that the old code returned. The sidecar JSON persists the asset."""
    store = AssetStore(tmp_path / "assets")
    asset = store.ingest(str(TESTDATA / "clip_a.mp4"))
    retrieved = store.get(asset.asset_hash)
    assert retrieved is not None
    # All fields must round-trip through the sidecar.
    assert retrieved.original_path == asset.original_path
    assert retrieved.stored_path == asset.stored_path
    assert retrieved.type == asset.type
    assert retrieved.duration_sec == pytest.approx(asset.duration_sec, abs=0.1)
    assert retrieved.fps == asset.fps
    assert retrieved.width == asset.width
    assert retrieved.height == asset.height
    assert retrieved.codec == asset.codec
    assert retrieved.has_audio == asset.has_audio


def test_get_falls_back_to_reprobe_when_sidecar_missing(tmp_path: Path) -> None:
    """If the sidecar has been deleted but the CAS file remains, get() must
    re-probe the file to recover the metadata instead of returning
    placeholder values."""
    store = AssetStore(tmp_path / "assets")
    asset = store.ingest(str(TESTDATA / "clip_a.mp4"))
    sidecar = store._sidecar_path(asset.asset_hash)
    sidecar.unlink()
    retrieved = store.get(asset.asset_hash)
    assert retrieved is not None
    assert retrieved.type == asset.type
    assert retrieved.width == asset.width
    assert retrieved.height == asset.height


def test_get_returns_none_for_unknown_hash(tmp_path: Path) -> None:
    store = AssetStore(tmp_path / "assets")
    assert store.get("0" * 64) is None


def test_probe_media_extracts_resolution() -> None:
    info = _probe_media(str(TESTDATA / "clip_a.mp4"))
    assert info["width"] == 320
    assert info["height"] == 240
    assert info["fps"] == 30.0
    assert info["duration_sec"] == pytest.approx(2.0, abs=0.1)
    assert info["has_audio"] is False


def test_probe_media_handles_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        _probe_media("/nonexistent/file.mp4")
