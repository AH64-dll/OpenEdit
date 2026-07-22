"""Builds the prior_state block for the system prompt.

Per phase4-design-revised.md section 3.2 (T2) and audit M4.
"""
from __future__ import annotations

import json
from typing import Optional

from open_edit.style.retrieve import get_slice
from open_edit.storage.config import get_profile_path


def build_prior_state(
    project_id: str,
    expected_op_type: Optional[str] = None,
    creativity_level: str = "balanced",
    workdir: Optional[str] = None,
) -> str:
    parts = []

    # 1. Creativity directive (≤50 tokens)
    parts.append(f"creativity_level: {creativity_level}")

    # 2. Style slice (≤250 tokens)
    if expected_op_type:
        slice_data = get_slice(expected_op_type)
        if slice_data:
            parts.append(f"<style_slice>\n{_format_slice(slice_data)}\n</style_slice>")

    # 3. Pin overrides
    profile = _load_profile()
    pinned = profile.get("pinned", {})
    if pinned:
        pinned_lines = "\n".join(f"{k}: {v} [pinned]" for k, v in pinned.items())
        parts.append(f"<pinned>\n{pinned_lines}\n</pinned>")

    # 4. Latest 3 ops (≤150 tokens)
    if workdir:
        from open_edit.agent.tools._helpers import _db_path
        from open_edit.storage.edit_graph import EditGraphStore
        db_path = _db_path(workdir)
        if not db_path.exists():
            recent = []
        else:
            store = EditGraphStore(db_path)
            recent = store.load_all()[-3:]
        if recent:
            ops_lines = "\n".join(
                f"- {op.kind} ({op.author}) at {op.timestamp[:19]}"
                for op in recent
            )
            parts.append(f"<latest_ops>\n{ops_lines}\n</latest_ops>")

    # 5. Pending notes summary (≤150 tokens)
    # Per phase4-design-revised.md §3.2 + audit M4: the agent needs to
    # know what's queued so it can reason about over-commit risk before
    # it's asked to "process" the notes via commit_feedback.
    if workdir:
        from open_edit.agent.tools._helpers import _notes_db_path
        from open_edit.storage.notes import NotesStore
        notes_db = _notes_db_path(workdir)
        if notes_db.exists():
            store = NotesStore(notes_db)
            pending = store.list_pending(project_id)
            summary_lines = [f"{len(pending)} pending notes"]
            for n in pending[:3]:
                anchor = n.anchor
                if anchor.anchor_type == "timestamp":
                    anchor_text = f"[{anchor.t_start:.1f}s]"
                elif anchor.anchor_type == "region":
                    anchor_text = f"[{anchor.t_start:.1f}s region]"
                else:
                    anchor_text = "[op]"
                summary_lines.append(f"- {anchor_text} {n.text[:50]}")
            parts.append(
                "<pending_notes_summary>\n"
                + "\n".join(summary_lines)
                + "\n</pending_notes_summary>"
            )
        else:
            parts.append("<pending_notes_summary>0 pending notes</pending_notes_summary>")
    else:
        parts.append("<pending_notes_summary>0 pending notes</pending_notes_summary>")

    inner = "\n".join(parts)
    return f"<prior_state>\n{inner}\n</prior_state>"


def _load_profile() -> dict:
    return json.loads(get_profile_path().read_text())


def _format_slice(slice_data: dict) -> str:
    return json.dumps(slice_data, indent=2)
