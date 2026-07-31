"""Unit tests for phrase-packed transcription formatting, tool handler, and registration."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from open_edit.agent.tools import get_transcript_packed
from open_edit.ir.types import Asset, WordAlignment
from open_edit.kernel.pillar_tools import dispatch_query
from open_edit.kernel.tool_registry import validate_tool_args
from open_edit.storage.assets import AssetStore
from open_edit.storage.transcription import format_timestamp, pack_transcript


def test_format_timestamp():
    assert format_timestamp(0.0) == "00:00.00"
    assert format_timestamp(1.25) == "00:01.25"
    assert format_timestamp(65.5) == "01:05.50"
    assert format_timestamp(3661.2) == "01:01:01.20"


def test_pack_transcript_empty():
    assert pack_transcript([]) == ""


def test_pack_transcript_speakers_and_groups():
    alignments = [
        WordAlignment(word="Hello", t_start=0.0, t_end=0.5, speaker="Speaker 1"),
        WordAlignment(word="world", t_start=0.6, t_end=1.0, speaker="Speaker 1"),
        WordAlignment(word="Welcome", t_start=1.1, t_end=1.5, speaker="Speaker 2"),
        WordAlignment(word="here", t_start=1.6, t_end=2.0, speaker="Speaker 2"),
    ]
    packed = pack_transcript(alignments, pause_threshold_sec=0.5)
    expected_lines = [
        "[00:00.00 - 00:01.00] [Speaker 1] Hello world",
        "[00:01.10 - 00:02.00] [Speaker 2] Welcome here",
    ]
    assert packed == "\n".join(expected_lines)


def test_pack_transcript_silence_gaps():
    alignments = [
        WordAlignment(word="First", t_start=0.0, t_end=0.5, speaker="Speaker 1"),
        WordAlignment(word="phrase", t_start=0.6, t_end=1.0, speaker="Speaker 1"),
        WordAlignment(word="Second", t_start=2.5, t_end=3.0, speaker="Speaker 1"),
        WordAlignment(word="phrase", t_start=3.1, t_end=3.5, speaker="Speaker 1"),
    ]
    # Inter-word gap = 2.5 - 1.0 = 1.5s >= 0.5s
    packed = pack_transcript(alignments, pause_threshold_sec=0.5)
    expected_lines = [
        "[00:00.00 - 00:01.00] [Speaker 1] First phrase",
        "*--- Silence (1.50s) ---*",
        "[00:02.50 - 00:03.50] [Speaker 1] Second phrase",
    ]
    assert packed == "\n".join(expected_lines)


def test_pack_transcript_no_speaker():
    alignments = [
        WordAlignment(word="Testing", t_start=0.0, t_end=0.5),
        WordAlignment(word="unlabeled", t_start=0.6, t_end=1.0),
        WordAlignment(word="speaker", t_start=2.0, t_end=2.5),
    ]
    packed = pack_transcript(alignments, pause_threshold_sec=0.5)
    expected_lines = [
        "[00:00.00 - 00:01.00] Testing unlabeled",
        "*--- Silence (1.00s) ---*",
        "[00:02.00 - 00:02.50] speaker",
    ]
    assert packed == "\n".join(expected_lines)


def test_get_transcript_packed_tool(tmp_path: Path):
    store = AssetStore(tmp_path / ".open_edit" / "assets")
    asset_hash = "1234567890abcdef"
    asset = Asset(
        asset_hash=asset_hash,
        original_path="/path/to/audio.mp3",
        stored_path=str(store._cas_path(asset_hash)),
        type="audio",
        duration_sec=5.0,
        has_audio=True,
        alignment=[
            WordAlignment(word="Testing", t_start=0.0, t_end=0.5, speaker="Speaker 1"),
            WordAlignment(word="tool", t_start=0.6, t_end=1.0, speaker="Speaker 1"),
        ],
    )
    # Persist CAS file and sidecar JSON
    store._cas_path(asset_hash).parent.mkdir(parents=True, exist_ok=True)
    store._cas_path(asset_hash).touch()
    store._sidecar_path(asset_hash).write_text(asset.model_dump_json())

    # Call tool handler directly
    res = get_transcript_packed({"asset_hash": asset_hash}, tmp_path)
    assert res["status"] == "ok"
    assert res["asset_hash"] == asset_hash
    # The tool returns the single packed field (transcript_packed) to avoid
    # 3x transcript token burn in MCP responses.
    assert res["transcript_packed"] == "[00:00.00 - 00:01.00] [Speaker 1] Testing tool"

    # Test missing asset_hash
    err_res = get_transcript_packed({}, tmp_path)
    assert err_res["status"] == "error"

    # Test unknown asset
    nonexistent_res = get_transcript_packed({"asset_hash": "unknown_hash"}, tmp_path)
    assert nonexistent_res["status"] == "error"


def test_tool_registration_and_dispatch(tmp_path: Path):
    # Test tool args validation via Pydantic registry
    validated = validate_tool_args(
        "query_project",
        {"query": "get_transcript_packed", "params": {"asset_hash": "test_hash"}},
    )
    assert validated["query"] == "get_transcript_packed"

    # Set up asset in store
    store = AssetStore(tmp_path / ".open_edit" / "assets")
    asset_hash = "fedcba0987654321"
    asset = Asset(
        asset_hash=asset_hash,
        original_path="/path/to/test.mp3",
        stored_path=str(store._cas_path(asset_hash)),
        type="audio",
        duration_sec=3.0,
        has_audio=True,
        alignment=[
            WordAlignment(word="Dispatched", t_start=0.0, t_end=1.0, speaker="Host"),
        ],
    )
    store._cas_path(asset_hash).parent.mkdir(parents=True, exist_ok=True)
    store._cas_path(asset_hash).touch()
    store._sidecar_path(asset_hash).write_text(asset.model_dump_json())

    # Dispatch via pillar tool dispatcher
    res = dispatch_query("get_transcript_packed", {"asset_hash": asset_hash}, tmp_path)
    assert res["status"] == "ok"
    assert res["transcript_packed"] == "[00:00.00 - 00:01.00] [Host] Dispatched"
