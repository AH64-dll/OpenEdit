"""Conversation JSONL persistence regression tests.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

from open_edit.serve.agent import append_to_conversation, load_conversation


def _project_with_jsonl(tmp_path: Path) -> tuple[Path, str]:
    proj = tmp_path / "testproj"
    proj.mkdir()
    (proj / ".open_edit").mkdir()
    (proj / ".open_edit" / "conversations").mkdir()
    conv_id = "test-conv-001"
    return proj, conv_id


def test_append_and_load_roundtrip(tmp_path):
    proj, conv_id = _project_with_jsonl(tmp_path)
    def fake_resolve(pid):
        return proj if pid == conv_id else None
    with mock.patch("open_edit.serve.agent._resolve_project_path", fake_resolve):
        msg = {"role": "user", "content": "hello"}
        append_to_conversation(conv_id, conv_id, msg)
        loaded = load_conversation(conv_id, conv_id)
    assert len(loaded) == 1
    assert loaded[0]["content"] == "hello"


def test_load_missing_returns_empty(tmp_path):
    proj, conv_id = _project_with_jsonl(tmp_path)
    def fake_resolve(pid):
        return proj if pid == conv_id else None
    with mock.patch("open_edit.serve.agent._resolve_project_path", fake_resolve):
        loaded = load_conversation("missing", "missing")
    assert loaded == []


def test_append_multiple_messages(tmp_path):
    proj, conv_id = _project_with_jsonl(tmp_path)
    def fake_resolve(pid):
        return proj if pid == conv_id else None
    with mock.patch("open_edit.serve.agent._resolve_project_path", fake_resolve):
        for i in range(3):
            append_to_conversation(conv_id, conv_id, {"role": "user", "content": f"msg_{i}"})
        loaded = load_conversation(conv_id, conv_id)
    assert len(loaded) == 3
    assert [m["content"] for m in loaded] == ["msg_0", "msg_1", "msg_2"]


def test_append_mid_turn_survives(tmp_path):
    """Simulate mid-turn crash: save after each tool_result, crash, restart."""
    proj, conv_id = _project_with_jsonl(tmp_path)
    def fake_resolve(pid):
        return proj if pid == conv_id else None
    with mock.patch("open_edit.serve.agent._resolve_project_path", fake_resolve):
        append_to_conversation(conv_id, conv_id, {"role": "user", "content": "tool_result_1"})
        append_to_conversation(conv_id, conv_id, {"role": "user", "content": "tool_result_2"})
        loaded = load_conversation(conv_id, conv_id)
    assert len(loaded) == 2
    assert loaded[1]["content"] == "tool_result_2"


def test_jsonl_is_valid_jsonl(tmp_path):
    """Each line must be valid JSON."""
    proj, conv_id = _project_with_jsonl(tmp_path)
    def fake_resolve(pid):
        return proj if pid == conv_id else None
    with mock.patch("open_edit.serve.agent._resolve_project_path", fake_resolve):
        append_to_conversation(conv_id, conv_id, {"role": "user", "content": "line1"})
        append_to_conversation(conv_id, "assistant-reserved", {"role": "assistant", "content": "line2"})
    f = proj / ".open_edit" / "conversations" / f"{conv_id}.jsonl"
    lines = f.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    for line in lines:
        obj = json.loads(line)
        assert "role" in obj


# ---------------------------------------------------------------------------
# A3-5: durable JSONL must be image-free while live history keeps frames
# ---------------------------------------------------------------------------

def _frame_message(render_id: str, fill: str) -> dict:
    text = json.dumps({
        "status": "ok", "render_id": render_id, "verification": {"frame_count": 2},
    })
    return {
        "role": "user",
        "content": [{
            "type": "tool_result",
            "tool_use_id": f"tu_{render_id}",
            "content": [
                {"type": "text", "text": text},
                {"type": "image", "data": fill * 4096, "mimeType": "image/jpeg"},
                {"type": "image", "data": fill * 4096, "mimeType": "image/jpeg"},
            ],
        }],
    }


def test_append_strips_frames_from_durable_copy_but_keeps_live_history(tmp_path):
    """append_to_conversation writes image-free bytes immediately;
    the caller's in-memory message still carries its frame data."""
    proj, conv_id = _project_with_jsonl(tmp_path)
    def fake_resolve(pid):
        return proj if pid == conv_id else None
    msg = _frame_message("r9", "Z")
    with mock.patch("open_edit.serve.agent._resolve_project_path", fake_resolve):
        append_to_conversation(conv_id, conv_id, msg)
        loaded = load_conversation(conv_id, conv_id)
    # live message untouched
    inner = msg["content"][0]["content"]
    assert [b["type"] for b in inner if isinstance(b, dict)].count("image") == 2

    # durable copy bounded + image-free, summary text intact
    durable = json.loads(loaded[0] and (json.dumps(loaded[0])))
    durable_inner = [b for b in durable["content"][0]["content"] if isinstance(b, dict)]
    assert not any(b.get("type") == "image" for b in durable_inner), "frames must not reach disk"
    assert any(b.get("type") == "image_stripped" for b in durable_inner), "strip marker identifies the frames"
    summary_texts = [b["text"] for b in durable_inner if b.get("type") == "text"]
    assert summary_texts and '"frame_count": 2' in summary_texts[0] and '"render_id": "r9"' in summary_texts[0]

    f = proj / ".open_edit" / "conversations" / f"{conv_id}.jsonl"
    raw = f.read_text()
    assert "Z" * 100 not in raw and '"type": "image"' not in raw, "raw JSONL must carry no frame bytes"
    per_msg_bytes = f.stat().st_size
    assert per_msg_bytes < 1200, f"durable record must be bounded, got {per_msg_bytes}"


def test_compact_jsonl_strips_legacy_embedded_frames(tmp_path):
    """Legacy JSONL written before image-free appends still gets its base64
    stripped by compaction (no per-append scanning needed)."""
    from open_edit.serve.agent.history_store import _compact_jsonl
    proj, conv_id = _project_with_jsonl(tmp_path)
    legacy = _frame_message("legacy", "Y")
    f = proj / ".open_edit" / "conversations" / f"{conv_id}.jsonl"
    f.write_text(json.dumps(legacy, sort_keys=True) + "\n", encoding="utf-8")
    assert "Y" * 100 in f.read_text(), "sanity: legacy file carried frames"
    with mock.patch("open_edit.serve.agent._resolve_project_path", lambda pid: proj):
        _compact_jsonl(f)
    raw = f.read_text()
    assert "Y" * 100 not in raw, "legacy base64 must be stripped on compaction"
    loaded = [json.loads(line) for line in raw.splitlines() if line.strip()]
    inner = [b for b in loaded[0]["content"][0]["content"] if isinstance(b, dict)]
    assert not any(b.get("type") == "image" for b in inner)
    assert any(b.get("type") == "text" and '"render_id": "legacy"' in b.get("text", "") for b in inner), \
        "summary provenance must survive the legacy strip"


def test_no_sidecar_or_scan_per_append(tmp_path):
    """Repeated appends add exactly one bounded line each — no cache or extra
    files were introduced by the image-free append strategy."""
    proj, conv_id = _project_with_jsonl(tmp_path)
    def fake_resolve(pid):
        return proj if pid == conv_id else None
    with mock.patch("open_edit.serve.agent._resolve_project_path", fake_resolve):
        for i in range(4):
            append_to_conversation(conv_id, conv_id, _frame_message(f"r{i}", "W"))
        conv_dir = proj / ".open_edit" / "conversations"
        files = sorted(p.name for p in conv_dir.iterdir())
        assert files == [f"{conv_id}.jsonl"], f"no sidecars expected, found {files}"
        sizes = [len(line) for line in (conv_dir / f"{conv_id}.jsonl").read_text().splitlines()]
        assert len(sizes) == 4 and all(s < 1200 for s in sizes), f"bounded per-line sizes: {sizes}"
