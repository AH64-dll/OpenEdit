"""Tests for the ContextBudget module."""
from __future__ import annotations

from open_edit.serve.context_budget import (
    ContextBudget,
    compact_history,
    count_tokens,
    count_tokens_history,
    count_tokens_message,
)


def test_count_tokens_basic():
    assert count_tokens("hello world") == 2
    assert count_tokens("") == 1
    assert count_tokens("a" * 100) == 25


def test_count_tokens_message():
    msg = {"role": "user", "content": "hello world"}
    assert count_tokens_message(msg) > 0


def test_count_tokens_history():
    hist = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "second"},
    ]
    assert count_tokens_history(hist) > 0


def test_truncate_keeps_first_and_last():
    budget = ContextBudget(max_tokens=50, reserve_tokens=10)
    hist = [
        {"role": "user", "content": "first message"},
        {"role": "assistant", "content": "middle 1"},
        {"role": "user", "content": "middle 2"},
        {"role": "assistant", "content": "last message"},
    ]
    result = budget.truncate(hist)
    assert result[0] == hist[0]
    total_tokens = count_tokens_history(result)
    assert total_tokens <= budget.max_tokens - budget.reserve_tokens


def test_truncate_inserts_placeholder():
    budget = ContextBudget(max_tokens=30, reserve_tokens=5)
    hist = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "X" * 200},
        {"role": "user", "content": "last"},
    ]
    result = budget.truncate(hist)
    placeholders = [m for m in result if "truncated" in str(m.get("content", ""))]
    assert len(placeholders) >= 1


def test_truncate_within_budget_unchanged():
    budget = ContextBudget(max_tokens=100000, reserve_tokens=1000)
    hist = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    result = budget.truncate(hist)
    assert result == hist


def test_compact_history_merges_plain_user_messages():
    hist = [
        {"role": "user", "content": "one"},
        {"role": "user", "content": "two"},
    ]
    out = compact_history(hist)
    assert len(out) == 1
    assert out[0]["content"] == "one\ntwo"


def test_compact_history_keeps_tool_result_separate_from_following_text():
    # Bug 3 regression: a tool_result user-message must not be merged with a
    # following plain user text message (would corrupt tool_use/tool_result
    # pairing).
    hist = [
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "result"}]},
        {"role": "user", "content": "please continue"},
    ]
    out = compact_history(hist)
    assert len(out) == 2
    assert out[0]["content"][0]["type"] == "tool_result"
    assert out[1]["content"] == "please continue"


def test_compact_history_keeps_tool_result_separate_from_preceding_text():
    hist = [
        {"role": "user", "content": "question"},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "r"}]},
        {"role": "user", "content": "follow-up"},
    ]
    out = compact_history(hist)
    assert len(out) == 3
    assert out[1]["content"][0]["type"] == "tool_result"
    assert out[2]["content"] == "follow-up"


# ---------------------------------------------------------------------------
# A3-1: pending verification frames must survive ContextBudget.truncate
# even when a later, smaller non-verification exchange exists.
# ---------------------------------------------------------------------------

def _frame_tool_result_message(rid: str, tu: str, fill: str = "Q") -> dict:
    import json
    return {"role": "user", "content": [{
        "type": "tool_result",
        "tool_use_id": tu,
        "content": [
            {"type": "text", "text": json.dumps({
                "status": "ok", "render_id": rid, "verification": {"frame_count": 3},
            })},
            {"type": "image", "data": fill * 4096, "mimeType": "image/jpeg"},
        ],
    }]}


def _frame_history() -> list[dict]:
    import json
    hist = [
        {"role": "user", "content": "first request"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "trigger_render", "input": {}}]},
        _frame_tool_result_message("r1", "t1"),
        ["x0", "x1", "x2"],
        {"role": "assistant", "content": [{"type": "tool_use", "id": "q1", "name": "get_history", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "q1", "content": json.dumps({"ok": True})}]},
    ]
    # flatten the three small middle exchanges
    middle: list[dict] = []
    for rid in hist[3]:
        middle.extend([
            {"role": "assistant", "content": [{"type": "tool_use", "id": rid, "name": "list_assets", "input": {}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": rid, "content": json.dumps({"ok": True})}]},
        ])
    return hist[:3] + middle + hist[4:]


def test_truncate_pins_oversized_frame_exchange_before_later_small_exchange():
    """The whole frame-bearing exchange survives a tight budget even though a
    later non-verification exchange exists (pre-fix: it was evicted first)."""
    budget = ContextBudget(max_tokens=400, reserve_tokens=50)
    hist = _frame_history()
    out = budget.truncate(hist)

    def _tool_use_ids(msgs):
        return [b.get("id") for m in msgs for b in (m.get("content") if isinstance(m.get("content"), list) else [])
                if isinstance(b, dict) and b.get("type") == "tool_use"]

    ids = _tool_use_ids(out)
    assert "t1" in ids, f"pinned frame exchange evicted: {ids}"
    frames_kept = any(
        isinstance(x, dict) and x.get("type") == "image"
        for m in out
        for b in (m.get("content") if isinstance(m.get("content"), list) else [])
        if isinstance(b, dict) and b.get("type") == "tool_result" and isinstance(b.get("content"), list)
        for x in b["content"]
    )
    assert frames_kept, "frame image evicted while its exchange was pinned"
    assert _tool_use_ids(out) == [i for i in _tool_use_ids(hist) if i in _tool_use_ids(out)], \
        "preserved exchanges must keep their original order"


def test_truncate_ordering_keeps_marker_before_pinned_exchange():
    """The truncation marker separates the opening request from the retained
    exchanges; the pinned exchange is never split or reordered."""
    budget = ContextBudget(max_tokens=400, reserve_tokens=50)
    out = budget.truncate(_frame_history())
    assert out[0] == {"role": "user", "content": "first request"}
    flattened = __import__("json").dumps(out, default=str)
    marker_pos = flattened.find("earlier messages truncated")
    t1_pos = flattened.find('"t1"')
    assert marker_pos != -1 and t1_pos != -1 and marker_pos < t1_pos


def test_truncate_without_frames_evicts_oversize_by_age():
    """Without a frame summary the old eviction behavior still applies:
    middle exchanges drop, the newest stays."""
    import json
    budget = ContextBudget(max_tokens=400, reserve_tokens=50)
    hist = [
        {"role": "user", "content": "first request"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "old", "name": "list_assets", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "old", "content": json.dumps({"ok": "Q" * 6000})}]},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "new", "name": "list_assets", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "new", "content": json.dumps({"ok": True})}]},
    ]
    out = budget.truncate(hist)
    ids = [b.get("id") for m in out for b in (m.get("content") if isinstance(m.get("content"), list) else [])
           if isinstance(b, dict) and b.get("type") == "tool_use"]
    assert "old" not in ids
    assert "new" in ids
