"""Token counting and sliding-window history truncation for context budget management."""
from __future__ import annotations

import os
from typing import Any


def _has_tool_result(content: Any) -> bool:
    """True if a message ``content`` carries a ``tool_result`` block.

    tool_result blocks live inside user-role messages and must stay distinct
    from plain user text for the Anthropic tool_use/tool_result pairing.
    """
    if not isinstance(content, list):
        return False
    return any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content)


def compact_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not history:
        return history

    out: list[dict[str, Any]] = []
    for msg in history:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "assistant" and isinstance(content, list):
            has_text = any(
                isinstance(b, dict) and b.get("type") == "text"
                for b in content
            )
            if not has_text:
                continue

        if role == "user" and out and out[-1].get("role") == "user":
            prev = out[-1]
            prev_content = prev.get("content", "")
            # Never merge a tool_result message into a neighbouring user
            # message -- that would corrupt the tool_use/tool_result pairing
            # the Anthropic API relies on.
            if _has_tool_result(prev_content) or _has_tool_result(content):
                out.append(msg)
                continue
            if isinstance(prev_content, str) and isinstance(content, str):
                prev["content"] = prev_content + "\n" + content
            elif isinstance(prev_content, list) and isinstance(content, list):
                prev["content"] = prev_content + content
            elif isinstance(prev_content, str):
                prev["content"] = [{"type": "text", "text": prev_content}] + (content if isinstance(content, list) else [{"type": "text", "text": content}])
            else:
                prev["content"] = (prev_content if isinstance(prev_content, list) else [{"type": "text", "text": str(prev_content)}]) + (content if isinstance(content, list) else [{"type": "text", "text": str(content)}])
            continue

        out.append(msg)

    return out


def count_tokens(text: str) -> int:
    """Approximate token count (1 token ≈ 4 chars for English text)."""
    return max(1, len(text) // 4)


def count_tokens_message(msg: dict[str, Any]) -> int:
    """Count tokens in a single conversation message (role + content)."""
    total = count_tokens(msg.get("role", ""))
    content = msg.get("content", "")
    if isinstance(content, str):
        total += count_tokens(content)
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                total += count_tokens(str(block.get("text", "")))
                if block.get("type") == "tool_result":
                    inner = block.get("content")
                    if isinstance(inner, str):
                        total += count_tokens(inner)
                    elif isinstance(inner, list):
                        for b2 in inner:
                            if isinstance(b2, dict):
                                total += count_tokens(str(b2.get("text", "")))
    return total


def count_tokens_history(history: list[dict[str, Any]]) -> int:
    """Count tokens in full conversation history."""
    return sum(count_tokens_message(m) for m in history)


class ContextBudget:
    """Sliding-window context budget manager."""

    def __init__(
        self,
        max_tokens: int = 0,
        reserve_tokens: int = 4000,
    ):
        if max_tokens == 0:
            max_tokens = int(os.environ.get("OPEN_EDIT_CONTEXT_MAX_TOKENS", "32000"))
        self.max_tokens = max_tokens
        self.reserve_tokens = reserve_tokens

    def truncate(self, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Apply sliding-window truncation.

        Always keeps the first user message. Removes earlier turns when
        the total exceeds budget, replacing them with a placeholder.
        """
        budget = self.max_tokens - self.reserve_tokens
        if budget <= 0:
            return history

        total = count_tokens_history(history)
        if total <= budget:
            return history

        keep: list[dict[str, Any]] = []
        if history:
            keep.append(history[0])

        kept_tokens = count_tokens_message(history[0]) if history else 0
        for msg in reversed(history[1:]):
            msg_tokens = count_tokens_message(msg)
            if kept_tokens + msg_tokens > budget:
                break
            keep.insert(1, msg)
            kept_tokens += msg_tokens

        removed = len(history) - len(keep)
        if removed > 0:
            placeholder: dict[str, Any] = {
                "role": "user",
                "content": f"[{removed} earlier messages truncated]",
            }
            keep.insert(1, placeholder)

        return keep

    def summarize_tool_result(self, result: dict[str, Any], max_chars: int = 1000) -> dict[str, Any]:
        """Truncate oversized string fields and limit list lengths in a tool result."""
        truncated = False
        out = dict(result)

        for field in ("stdout", "stderr", "error"):
            if isinstance(out.get(field), str) and len(out[field]) > max_chars:
                out[field] = out[field][:max_chars] + "... [truncated]"
                truncated = True

        for field in list(out.keys()):
            if isinstance(out[field], list) and len(out[field]) > 20:
                out[field] = out[field][:20] + [f"... [{len(out[field]) - 20} more items]"]
                truncated = True

        if truncated:
            out["_truncated"] = True

        return out
