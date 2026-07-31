"""Canonical hashing of an edit graph for timeline snapshot caching."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def compute_edit_graph_hash(ops: list) -> str:
    """Return a stable sha256 hex digest for a list of operations.

    Accepts op objects or their ``model_dump(mode="json")`` dict forms and
    digests both identically. The hash is order-independent (ops are sorted
    by a stable key) and excludes the auto-assigned ``sequence_num``. Any
    change to an op's payload or status yields a different digest.
    """
    def _field(op: Any, name: str, default: Any) -> Any:
        if isinstance(op, dict):
            return op.get(name, default)
        return getattr(op, name, default)

    ordered = sorted(
        ops,
        key=lambda op: (_field(op, "sequence_num", 0), _field(op, "edit_id", "")),
    )
    parts: list[str] = []
    for op in ordered:
        data = op.model_dump(mode="json") if hasattr(op, "model_dump") else dict(op)
        data.pop("sequence_num", None)
        parts.append(json.dumps(data, sort_keys=True, separators=(",", ":")))
    return hashlib.sha256("".join(parts).encode()).hexdigest()
