"""Tests for prune_images and _build_tool_result_message base64 dedup."""
from __future__ import annotations

import json

from open_edit.serve.visual_verify import (
    _strip_verification_frames,
    prune_images,
)


def _make_verification_result(frame_count: int = 2) -> dict:
    frames = [
        {"data": f"data:image/jpeg;base64,{'A' * 5000}", "mimeType": "image/jpeg"}
        for _ in range(frame_count)
    ]
    return {
        "status": "ok",
        "output_path": "/tmp/render.mp4",
        "verification": {
            "render_id": "r1",
            "frames": frames,
            "verdict": "looks_good",
            "notes": "all frames OK",
        },
    }


def _make_tool_result_message(verification_result: dict) -> dict:
    from open_edit.serve.visual_verify import _strip_verification_frames as svf
    verification = verification_result.get("verification") or {}
    frames = verification.get("frames") or []
    if frames:
        text_summary = json.dumps(svf(verification_result), default=str)
        blocks = [{"type": "text", "text": text_summary}]
        for frame in frames:
            blocks.append({"type": "image", "data": frame["data"], "mimeType": "image/jpeg"})
    else:
        text_summary = json.dumps(verification_result, default=str)
        blocks = [{"type": "text", "text": text_summary}]
    return {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "tu1", "content": blocks}],
    }


def test_strip_verification_frames_removes_frames():
    result = _make_verification_result(3)
    stripped = _strip_verification_frames(result)
    assert "verification" in stripped
    assert "frames" not in stripped["verification"]
    assert stripped["verification"]["frame_count"] == 3


def test_strip_verification_frames_no_verification():
    result = {"status": "ok", "value": 42}
    assert _strip_verification_frames(result) == result


def test_strip_verification_frames_empty_frames():
    result = {"status": "ok", "verification": {"render_id": "r1", "frames": []}}
    stripped = _strip_verification_frames(result)
    assert "frames" not in stripped["verification"]


def test_prune_images_strips_images_and_base64():
    msg = _make_tool_result_message(_make_verification_result(2))
    history = [msg]
    slimmed = prune_images(history)
    slim_msg = slimmed[0]
    content = slim_msg["content"]
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_result":
            inner = block.get("content", [])
            for b2 in inner:
                assert b2.get("type") != "image", "image block survived pruning"
                if b2.get("type") == "text":
                    assert "AAAA" not in b2["text"], "base64 leaked into text summary"
                    assert '"frame_count": 2' in b2["text"], "frame_count missing"


def test_prune_images_no_frames_unchanged():
    msg = {"role": "user", "content": [{"type": "text", "text": "hello"}]}
    history = [msg]
    slimmed = prune_images(history)
    assert slimmed == history


def test_prune_images_preserves_last_verdict():
    msg = _make_tool_result_message(_make_verification_result(2))
    history = [msg]
    slimmed = prune_images(history, last_verdict=("r2", "bad", True, "needs work"))
    summaries = [m for m in slimmed if "VERDICT" in str(m.get("content", "")).upper()]
    assert len(summaries) >= 1


def test_text_summary_no_base64_after_build():
    result = _make_verification_result(4)
    stripped_text = json.dumps(_strip_verification_frames(result), default=str)
    assert "AAAA" not in stripped_text, "base64 leaked into text summary"
    assert "frame_count" in stripped_text
