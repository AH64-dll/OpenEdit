"""Phase 4.5 W1: Asset.alignment field + AssetStore integration."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from open_edit.ir.types import Asset, WordAlignment
from open_edit.storage.assets import AssetStore, _probe_media


class TestAssetsAlignment(unittest.TestCase):
    """Unit tests for Asset alignment fields and AssetStore integration."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_word_alignment_pydantic(self) -> None:
        wa = WordAlignment(word="hello", t_start=0.0, t_end=0.5, confidence=0.99)
        self.assertEqual(wa.word, "hello")
        self.assertEqual(wa.t_start, 0.0)

    def test_asset_default_alignment_empty(self) -> None:
        asset = Asset(
            asset_hash="abc",
            original_path="/tmp/x.mp4",
            stored_path="/tmp/x",
            type="video",
            duration_sec=10.0,
            fps=30.0, width=1920, height=1080, codec="h264", has_audio=True,
        )
        self.assertEqual(asset.alignment, [])

    def test_asset_with_alignment(self) -> None:
        asset = Asset(
            asset_hash="abc",
            original_path="/tmp/x.mp4",
            stored_path="/tmp/x",
            type="video",
            duration_sec=10.0,
            fps=30.0, width=1920, height=1080, codec="h264", has_audio=True,
            alignment=[
                WordAlignment(word="hello", t_start=0.0, t_end=0.5, confidence=0.99),
            ],
        )
        self.assertEqual(len(asset.alignment), 1)

    def test_asset_alignment_sidecar_json_roundtrip(self) -> None:
        asset = Asset(
            asset_hash="abc",
            original_path="/tmp/x.mp4",
            stored_path="/tmp/x",
            type="video",
            duration_sec=10.0,
            fps=30.0, width=1920, height=1080, codec="h264", has_audio=True,
            alignment=[
                WordAlignment(word="hello", t_start=0.0, t_end=0.5, confidence=0.99),
                WordAlignment(word="world", t_start=0.5, t_end=1.0, confidence=0.98),
            ],
        )
        raw = asset.model_dump_json()
        round_tripped = Asset.model_validate_json(raw)
        self.assertEqual(round_tripped, asset)
        self.assertEqual(len(round_tripped.alignment), 2)
        self.assertEqual(round_tripped.alignment[1].word, "world")

    @patch("open_edit.storage.transcription._has_whisper", lambda: False)
    @patch(
        "open_edit.storage.assets._probe_media",
        lambda p: {
            "duration_sec": 10.0, "fps": 30.0, "width": 1920, "height": 1080,
            "codec": "h264", "has_audio": True, "type": "video",
        },
    )
    def test_ingest_back_compat_without_whisper(self) -> None:
        src = self.tmp_path / "test.mp4"
        src.write_bytes(b"\x00" * 1024)
        store = AssetStore(self.tmp_path / "assets")
        assets = store.ingest_paths([str(src)])
        self.assertEqual(assets[0].alignment, [])

    def test_ingest_image_skips_transcription(self) -> None:
        transcribe_mock_called = []

        def fake_transcribe(src, model_size="base"):
            transcribe_mock_called.append(str(src))
            return []

        with patch(
            "open_edit.storage.assets._probe_media",
            lambda p: {
                "duration_sec": 0.0, "fps": None, "width": 1920, "height": 1080,
                "codec": "png", "has_audio": False, "type": "image",
            },
        ), patch("open_edit.storage.assets.transcribe", fake_transcribe):
            src = self.tmp_path / "test.png"
            src.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 1024)
            store = AssetStore(self.tmp_path / "assets")
            assets = store.ingest_paths([str(src)])

            self.assertEqual(assets[0].type, "image")
            self.assertEqual(assets[0].alignment, [])
            self.assertEqual(
                transcribe_mock_called, [],
                f"transcribe() must not be called for image assets, got calls: {transcribe_mock_called}"
            )


if __name__ == "__main__":
    unittest.main()
