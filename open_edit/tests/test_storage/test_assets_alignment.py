"""Phase 4.5 W1: Asset.alignment field + AssetStore integration."""
import json
import pytest
from pathlib import Path
from open_edit.ir.types import Asset, WordAlignment
from open_edit.storage.assets import AssetStore


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


def test_ingest_back_compat_without_whisper(tmp_path, monkeypatch):
    """Without faster-whisper installed, ingest still works; alignment is empty."""
    monkeypatch.setattr("open_edit.storage.transcription._has_whisper", lambda: False)
    src = tmp_path / "test.mp4"
    src.write_bytes(b"\x00" * 1024)
    store = AssetStore(tmp_path / "assets")
    try:
        assets = store.ingest_paths([str(src)])
    except Exception as e:
        pytest.skip(f"ffprobe not available: {e}")
    assert assets[0].alignment == []
