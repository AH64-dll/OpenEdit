"""Tests for the AssetStore (content-addressed + ffprobe metadata)."""
import shutil
import tempfile
import unittest
from pathlib import Path

from open_edit.storage.assets import AssetStore, _probe_media


TESTDATA = Path(__file__).parent.parent / "testdata" / "raw_videos"


def _ffprobe_available() -> bool:
    return shutil.which("ffprobe") is not None


@unittest.skipUnless(_ffprobe_available(), "ffprobe not installed")
class TestAssetStore(unittest.TestCase):
    """Unit tests for content-addressed AssetStore."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_ingest_returns_asset_with_hash(self) -> None:
        store = AssetStore(self.tmp_path / "assets")
        asset = store.ingest(str(TESTDATA / "clip_a.mp4"))
        self.assertEqual(len(asset.asset_hash), 64)  # SHA-256 hex
        self.assertGreater(asset.duration_sec, 0)

    def test_ingest_stores_file_in_cas_layout(self) -> None:
        assets_dir = self.tmp_path / "assets"
        store = AssetStore(assets_dir)
        asset = store.ingest(str(TESTDATA / "clip_a.mp4"))
        expected = assets_dir / asset.asset_hash[:2] / asset.asset_hash
        self.assertTrue(expected.exists())

    def test_ingest_same_file_twice_returns_same_hash(self) -> None:
        store = AssetStore(self.tmp_path / "assets")
        a1 = store.ingest(str(TESTDATA / "clip_a.mp4"))
        a2 = store.ingest(str(TESTDATA / "clip_a.mp4"))
        self.assertEqual(a1.asset_hash, a2.asset_hash)

    def test_ingest_different_files_return_different_hashes(self) -> None:
        store = AssetStore(self.tmp_path / "assets")
        a1 = store.ingest(str(TESTDATA / "clip_a.mp4"))
        a2 = store.ingest(str(TESTDATA / "clip_b.mp4"))
        self.assertNotEqual(a1.asset_hash, a2.asset_hash)

    def test_ingest_paths_rejects_empty_list(self) -> None:
        store = AssetStore(self.tmp_path / "assets")
        with self.assertRaisesRegex(ValueError, "empty"):
            store.ingest_paths([])

    def test_ingest_rejects_nonexistent_file(self) -> None:
        store = AssetStore(self.tmp_path / "assets")
        with self.assertRaises(FileNotFoundError):
            store.ingest("/nonexistent/path/to/video.mp4")

    def test_get_returns_ingested_asset(self) -> None:
        store = AssetStore(self.tmp_path / "assets")
        asset = store.ingest(str(TESTDATA / "clip_a.mp4"))
        retrieved = store.get(asset.asset_hash)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.asset_hash, asset.asset_hash)

    def test_get_returns_full_metadata_via_sidecar(self) -> None:
        store = AssetStore(self.tmp_path / "assets")
        asset = store.ingest(str(TESTDATA / "clip_a.mp4"))
        retrieved = store.get(asset.asset_hash)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.original_path, asset.original_path)
        self.assertEqual(retrieved.stored_path, asset.stored_path)
        self.assertEqual(retrieved.type, asset.type)
        self.assertAlmostEqual(retrieved.duration_sec, asset.duration_sec, delta=0.1)
        self.assertEqual(retrieved.fps, asset.fps)
        self.assertEqual(retrieved.width, asset.width)
        self.assertEqual(retrieved.height, asset.height)
        self.assertEqual(retrieved.codec, asset.codec)
        self.assertEqual(retrieved.has_audio, asset.has_audio)

    def test_get_falls_back_to_reprobe_when_sidecar_missing(self) -> None:
        store = AssetStore(self.tmp_path / "assets")
        asset = store.ingest(str(TESTDATA / "clip_a.mp4"))
        sidecar = store._sidecar_path(asset.asset_hash)
        sidecar.unlink()
        retrieved = store.get(asset.asset_hash)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.type, asset.type)
        self.assertEqual(retrieved.width, asset.width)
        self.assertEqual(retrieved.height, asset.height)

    def test_get_returns_none_for_unknown_hash(self) -> None:
        store = AssetStore(self.tmp_path / "assets")
        self.assertIsNone(store.get("0" * 64))

    def test_probe_media_extracts_resolution(self) -> None:
        info = _probe_media(str(TESTDATA / "clip_a.mp4"))
        self.assertEqual(info["width"], 320)
        self.assertEqual(info["height"], 240)
        self.assertEqual(info["fps"], 30.0)
        self.assertAlmostEqual(info["duration_sec"], 2.0, delta=0.1)
        self.assertFalse(info["has_audio"])

    def test_probe_media_handles_missing_file(self) -> None:
        with self.assertRaises(FileNotFoundError):
            _probe_media("/nonexistent/file.mp4")


if __name__ == "__main__":
    unittest.main()
