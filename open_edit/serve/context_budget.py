"""Bound model context while retaining complete tool-call exchanges."""
from __future__ import annotations

import json
import os
from copy import deepcopy
from typing import Any

_IMAGE_TOKENS = 1_024


def _has_tool_result(content: Any) -> bool:
    return isinstance(content, list) and any(
        isinstance(block, dict) and block.get("type") == "tool_result"
        for block in content
    )


def compact_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge plain user messages without mutating persisted conversation data.

    Tool-only assistant messages are essential: dropping them leaves orphaned
    results and makes subsequent function-calling requests invalid.
    """
    out: list[dict[str, Any]] = []
    for original in history:
        msg = deepcopy(original)
        content = msg.get("content", "")
        if msg.get("role") == "user" and out and out[-1].get("role") == "user":
            previous = out[-1].get("content", "")
            if not _has_tool_result(previous) and not _has_tool_result(content):
                if isinstance(previous, str) and isinstance(content, str):
                    out[-1]["content"] = previous + "\n" + content
                else:
                    def blocks(value: Any) -> list:
                        return value if isinstance(value, list) else [{"type": "text", "text": str(value)}]
                    out[-1]["content"] = blocks(previous) + blocks(content)
                continue
        out.append(msg)
    return out


def count_tokens(text: str) -> int:
    """Conservative byte-based estimate; accounts for non-English text too."""
    return max(1, len(text.encode("utf-8")) // 4)


def _count_value(value: Any) -> int:
    if isinstance(value, dict):
        if value.get("type") in {"image", "image_url"}:
            # Base64 is transport encoding, not text supplied to the model.
            return _IMAGE_TOKENS
        return sum(count_tokens(str(key)) + _count_value(item) for key, item in value.items())
    if isinstance(value, list):
        return sum(_count_value(item) for item in value)
    return count_tokens(value if isinstance(value, str) else json.dumps(value, default=str))


def count_tokens_message(msg: dict[str, Any]) -> int:
    """Include tool inputs, results, images and per-message framing."""
    return 4 + _count_value(msg)


def count_tokens_history(history: list[dict[str, Any]]) -> int:
    return sum(count_tokens_message(msg) for msg in history)


def _exchange_groups(history: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Keep each assistant tool call together with all of its results."""
    groups: list[list[dict[str, Any]]] = []
    pending: set[str] = set()
    for msg in history:
        content = msg.get("content")
        results = set()
        calls = set()
        if isinstance(content, list):
            calls = {b.get("id") for b in content if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("id")}
            results = {b.get("tool_use_id") for b in content if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id")}
        if msg.get("role") == "tool":
            results.add(msg.get("tool_call_id"))
        calls.update(call["id"] for call in (msg.get("tool_calls") or []) if isinstance(call, dict) and call.get("id"))
        if pending.intersection(results):
            groups[-1].append(msg)
            pending.difference_update(results)
        else:
            groups.append([msg])
            pending = set()
        pending.update(calls)
    return groups


class ContextBudget:
    """Sliding context window that never splits a tool-call exchange."""

    def __init__(self, max_tokens: int = 0, reserve_tokens: int = 4000):
        if max_tokens == 0:
            try:
                max_tokens = int(os.environ.get("OPEN_EDIT_CONTEXT_MAX_TOKENS", "32000"))
            except ValueError:
                max_tokens = 32000
        if max_tokens <= 0 or reserve_tokens < 0 or reserve_tokens >= max_tokens:
            raise ValueError("context limit must exceed a nonnegative token reserve")
        self.max_tokens = max_tokens
        self.reserve_tokens = reserve_tokens

    def pin_required_exchanges(
        self,
        history: list[dict[str, Any]],
        groups: list[list[dict[str, Any]]],
    ) -> set[int]:
        """Indexes in ``groups`` that must survive truncation as whole units.

        A frame-bearing ``tool_result`` whose canonical summary names
        ``render_id`` pins its whole exchange (assistant ``tool_use`` +
        result). These are verification frames; without the pin a later
        smaller exchange would push an oversized frame exchange out of the
        window and amputate the model's only view of the rendered video.

        Message order is never reordered here — pinned groups preserve
        their original position in ``truncate``.
        """
        from .visual_verify import _summary_render_id_from_tool_result

        message_index_to_group: list[int] = []
        for gi, group in enumerate(groups):
            message_index_to_group.extend([gi] * len(group))

        pinned: set[int] = set()
        for i, msg in enumerate(history):
            if msg.get("role") != "user":
                continue
            for block in msg.get("content", []) if isinstance(msg.get("content"), list) else []:
                if (
                    isinstance(block, dict)
                    and block.get("type") == "tool_result"
                    and isinstance(block.get("content"), list)
                    and _summary_render_id_from_tool_result(block) is not None
                ):
                    gi = message_index_to_group[i]
                    pinned.add(gi)
        return pinned

    def truncate(self, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Retain the opening request, current request and complete exchanges.

        An indivisible newest exchange or user request may exceed the configured
        estimate. Preserve it rather than silently losing the current task or
        corrupting tool arguments; tool results should be capped beforehand.

        Exchanges marked required by :func:`pin_required_exchanges` are kept
        whole even when a later non-verification exchange exists — pinned
        tool results (e.g. pending verification frames) must reach the model.
        """
        budget = self.max_tokens - self.reserve_tokens
        if count_tokens_history(history) <= budget:
            return history
        groups = _exchange_groups(history)
        pinned = self.pin_required_exchanges(history, groups)
        if not groups:
            return []
        current = next((i for i in range(len(groups) - 1, -1, -1) if any(
            msg.get("role") == "user" and not _has_tool_result(msg.get("content"))
            for msg in groups[i]
        )), 0)
        required = {0, current, len(groups) - 1} | pinned
        used = sum(count_tokens_history(groups[i]) for i in required)
        marker = {"role": "user", "content": f"[{len(history)} earlier messages truncated]"}
        overhead = count_tokens_message(marker)
        for i in range(len(groups) - 2, 0, -1):
            if i in required:
                continue
            cost = count_tokens_history(groups[i])
            if used + cost + overhead > budget:
                break
            required.add(i)
            used += cost
        selected = [msg for i, group in enumerate(groups) if i in required for msg in group]
        removed = len(history) - len(selected)
        if removed:
            marker["content"] = f"[{removed} earlier messages truncated]"
            return [*groups[0], marker, *selected[len(groups[0]):]]
        return selected
