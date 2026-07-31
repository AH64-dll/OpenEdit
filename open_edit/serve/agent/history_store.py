"""Conversation persistence for the agent loop.

The conversation history is persisted as JSONL at
``<project>/.open_edit/conversations/<conv_id>.jsonl`` (one JSON message
per line).
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from open_edit.serve import agent as _agent_pkg

from .. import projects as projects_mod
from .. import visual_verify

_append_counters: dict[str, int] = {}
_COMPACTION_INTERVAL = 50


def _conversations_dir(project_path: Path) -> Path:
    d = project_path / ".open_edit" / "conversations"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _resolve_project_path(project_id: str) -> Path | None:
    """Resolve a project_id to a Path. Returns None if not found."""
    # Re-use the registry's resolver (private but stable).
    return projects_mod._resolve_project_by_id(project_id)


def load_conversation(project_id: str, conv_id: str) -> list[dict[str, Any]]:
    """Load a conversation from disk. Returns ``[]`` if it doesn't exist."""
    # Look the resolver up through the package namespace: tests patch
    # ``open_edit.serve.agent._resolve_project_path`` and expect
    # conversation persistence to observe the patch.
    path = _agent_pkg._resolve_project_path(project_id)
    if path is None:
        return []
    f = _conversations_dir(path) / f"{conv_id}.jsonl"
    if not f.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def append_to_conversation(project_id: str, conv_id: str, message: dict[str, Any]) -> None:
    """Append one message to the conversation JSONL file."""
    path = _agent_pkg._resolve_project_path(project_id)
    if path is None:
        return
    f = _conversations_dir(path) / f"{conv_id}.jsonl"
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(message, sort_keys=True, default=str) + "\n")

    key = f"{project_id}:{conv_id}"
    count = _append_counters.get(key, 0) + 1
    _append_counters[key] = count
    if count % _COMPACTION_INTERVAL == 0:
        _compact_jsonl(f)


def _compact_jsonl(path: Path) -> None:
    from ..context_budget import compact_history as _compact_history
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if not lines:
            return
        messages = []
        for line in lines:
            line = line.strip()
            if line:
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        if not messages:
            return
        compacted = _compact_history(messages)
        tmp = path.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for msg in compacted:
                fh.write(json.dumps(msg, sort_keys=True, default=str) + "\n")
        tmp.replace(path)
    except OSError:
        pass


def new_conversation_id() -> str:
    return uuid.uuid4().hex
def _build_tool_result_message(
    tu_id: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Build the ``tool_result`` message for the conversation history.

    When the result carries verification frames, the content is a list
    of content blocks (text summary + image blocks) so the LLM can
    actually see the frames.

    The text summary uses ``_strip_verification_frames`` to remove
    embedded base64 data — frame data is already in the separate
    ``type: "image"`` blocks.
    """
    from ..visual_verify import _strip_verification_frames

    verification = result.get("verification") or {}
    frames = verification.get("frames") or []
    if frames:
        text_summary = json.dumps(_strip_verification_frames(result), default=str)
        blocks: list[dict[str, Any]] = [{"type": "text", "text": text_summary}]
        for frame in frames:
            blocks.append({
                "type": "image",
                "data": frame["data"],
                "mimeType": frame.get("mimeType", "image/jpeg"),
            })
        content: Any = blocks
    else:
        content = json.dumps(result, default=str)
    return {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": tu_id,
                "content": content,
            }
        ],
    }


def _make_slim_history(
    history: list[dict[str, Any]],
    pending: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Build the slim LLM-facing view of ``history``."""
    from ..context_budget import ContextBudget, compact_history

    budget = ContextBudget()

    slimmed = compact_history(list(history))

    if pending is None:
        slimmed = visual_verify.prune_images(slimmed)
    else:
        slimmed = visual_verify.prune_images(
            slimmed,
            last_verdict=(
                pending["render_id"],
                pending.get("verdict", "unknown"),
                pending.get("supports_images", False),
                pending.get("notes", ""),
            ),
        )

    slimmed = budget.truncate(slimmed)

    for msg in slimmed:
        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    inner = block.get("content")
                    if isinstance(inner, str) and len(inner) > 2000:
                        try:
                            parsed = json.loads(inner)
                            block["content"] = json.dumps(budget.summarize_tool_result(parsed), default=str)
                        except (json.JSONDecodeError, TypeError):
                            pass

    return slimmed
