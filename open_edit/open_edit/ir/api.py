"""In-process IR API for free-form Python code (sandbox side).

Phase 0+1 ships a stub. The full implementation in Phase 3/4 will:
- Accept a workdir, an EditGraphStore, and a buffer
- Expose add_clip, trim_clip, move_clip, remove_clip, add_transition,
  add_effect, set_keyframe, set_audio_gain, normalize_audio as methods
- Each method appends a structured op to the buffer
- The buffer is returned to apply.py which appends to the edit graph
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from open_edit.ir.types import OperationUnion


class IR:
    """Stub IR API. Real implementation in Phase 3/4."""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "open_edit.ir.api.IR is a Phase 0+1 stub. "
            "Full implementation comes in Phase 3 (sandbox) + Phase 4 (agent loop)."
        )
