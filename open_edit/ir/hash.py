"""Canonical hashing of an edit graph for timeline snapshot caching."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def compute_edit_graph_hash(ops: list) -> str:
    """Return a stable sha256 hex digest for a list of operations.

    Accepts op objects or their ``model_dump(mode="json")`` dict forms and
    digests both identically. The hash is ORDER-SENSITIVE: ops are sorted
    by their ``sequence_num`` (populated by ``EditGraphStore.load_all``);
    ops without a sequence fall back to their position in the list, and
    equal sequence numbers tie-break on ``edit_id``. The sequence is part
    of the digested payload (``sequence_num:edit_id:op_json``), so any
    reorder of the graph changes the digest. Any change to an op's payload
    or status also yields a different digest.
    """
    def _field(op: Any, name: str, default: Any) -> Any:
        if isinstance(op, dict):
            return op.get(name, default)
        return getattr(op, name, default)

    keyed: list[tuple[int, Any]] = []
    for index, op in enumerate(ops):
        seq = _field(op, "sequence_num", None)
        if seq is None:
            seq = index
        else:
            try:
                seq = int(seq)
            except (TypeError, ValueError):
                seq = index
        keyed.append((seq, op))

    keyed.sort(key=lambda item: (item[0], _field(item[1], "edit_id", "")))

    parts: list[str] = []
    for seq, op in keyed:
        data = op.model_dump(mode="json") if hasattr(op, "model_dump") else dict(op)
        data.pop("sequence_num", None)
        edit_id = data.get("edit_id", "")
        parts.append(f"{seq}:{edit_id}:{json.dumps(data, sort_keys=True, separators=(",", ":"))}")
    return hashlib.sha256("".join(parts).encode()).hexdigest()
