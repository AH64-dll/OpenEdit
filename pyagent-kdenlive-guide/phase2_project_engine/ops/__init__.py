"""phase2_project_engine.ops — per-domain editor operations.

One module per concern; each function takes a ProjectTree plus
its kwargs and returns the new state. The old monolithic
`KdenliveFileBackend` class (Task 1.8) is being deleted; this
package is the new home for the operations it used to provide.
"""
from __future__ import annotations

from .bin import import_media
from .clips import (
    append_clip,
    delete_clip,
    insert_clip,
    move_clip,
    trim_clip,
)
from .effects import apply_effect
from .markers import add_marker
from .transitions import add_transition


__all__ = [
    "import_media",
    "insert_clip",
    "append_clip",
    "move_clip",
    "trim_clip",
    "delete_clip",
    "add_transition",
    "apply_effect",
    "add_marker",
]
