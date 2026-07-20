"""Phase 4.5 W1: Asset.alignment field + AssetStore integration."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch

from open_edit.ir.types import Asset, WordAlignment
from open_edit.storage.assets import AssetStore, _probe_media


def test_word_alignment_pydantic():
    wa = WordAlignment(word="hello", t_start=0.0, t_end=0.5, confidence=0.99)
    assert wa.word == "hello"
    assert wa.t_start == 0.0


def test_asset_default_alignment_empty():
    asset = Asset(
        asset_hash="abc",
        original_path="/tmp/x.mp4",
        stored_path="/tmp/x",
        type="video",
        duration_sec=10.0,
        fps=30.0, width=1920, height=1080, codec="h264", has_audio=True,
    )
    assert asset.alignment == []


def test_asset_with_alignment():
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
    assert len(asset.alignment) == 1


def test_asset_alignment_sidecar_json_roundtrip():
    """Constructed Asset with alignment survives a JSON dump/load cycle (M3)."""
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
    assert round_tripped == asset
    assert len(round_tripped.alignment) == 2
    assert round_tripped.alignment[1].word == "world"


def test_ingest_back_compat_without_whisper(tmp_path, monkeypatch):
    """Without faster-whisper installed, ingest still works; alignment is empty.

    M4: mock _probe_media directly so the test does not depend on ffprobe.
    """
    monkeypatch.setattr("open_edit.storage.transcription._has_whisper", lambda: False)
    monkeypatch.setattr(
        "open_edit.storage.assets._probe_media",
        lambda p: {
            "duration_sec": 10.0, "fps": 30.0, "width": 1920, "height": 1080,
            "codec": "h264", "has_audio": True, "type": "video",
        },
    )
    src = tmp_path / "test.mp4"
    src.write_bytes(b"\x00" * 1024)
    store = AssetStore(tmp_path / "assets")
    assets = store.ingest_paths([str(src)])
    assert assets[0].alignment == []


def test_ingest_image_skips_transcription(tmp_path, monkeypatch):
    """Regression (I1): ingesting an image asset must not call transcribe().

    faster-whisper cannot transcribe image files; without the has_audio gate
    the call would raise and the whole batch would die.
    """
    monkeypatch.setattr(
        "open_edit.storage.assets._probe_media",
        lambda p: {
            "duration_sec": 0.0, "fps": None, "width": 1920, "height": 1080,
            "codec": "png", "has_audio": False, "type": "image",
        },
    )
    transcribe_mock_called = []

    def fake_transcribe(src, model_size="base"):
        transcribe_mock_called.append(str(src))
        return []

    monkeypatch.setattr("open_edit.storage.assets.transcribe", fake_transcribe)

    src = tmp_path / "test.png"
    src.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 1024)
    store = AssetStore(tmp_path / "assets")
    assets = store.ingest_paths([str(src)])

    assert assets[0].type == "image"
    assert assets[0].alignment == []
    assert transcribe_mock_called == [], (
        f"transcribe() must not be called for image assets, got calls: {transcribe_mock_called}"
    )
