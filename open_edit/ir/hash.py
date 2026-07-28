"""Canonical hashing of an edit graph for timeline snapshot caching."""
from __future__ import annotations

import hashlib
import json


def compute_edit_graph_hash(ops: list) -> str:
    """Return a stable sha256 hex digest for a list of operations.

    The hash is order-independent (ops are sorted by a stable key) and
    excludes the auto-assigned ``sequence_num``. Any change to an op's
    payload or status yields a different digest.
    """
    ordered = sorted(
        ops,
        key=lambda op: (getattr(op, "sequence_num", 0), getattr(op, "edit_id", "")),
    )
    parts: list[str] = []
    for op in ordered:
        data = op.model_dump(mode="json")
        data.pop("sequence_num", None)
        parts.append(json.dumps(data, sort_keys=True, separators=(",", ":")))
    return hashlib.sha256("".join(parts).encode()).hexdigest()
