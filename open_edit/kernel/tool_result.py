"""Structured tool-result shapes (spec §4).

Failure shapes have no ``verification`` block, just an ``error`` key.
Hosted in kernel because both the overlay render trigger
(``open_edit.kernel.render_overlay``) and the serve agent
(``serve.visual_verify`` re-exports it) build these results.
"""
from __future__ import annotations

from typing import Any


def build_failure_tool_result(reason: str, render_id: str = "render_unknown", **extra: Any) -> dict:
    """Spec §4 failure shapes: no ``verification`` block, just an ``error`` key."""
    return {
        "error": f"{reason}: {extra.pop('detail', '')}".rstrip(": ").rstrip(),
        "render_id": render_id,
        **extra,
    }
