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
from .clips_edit import (
    change_clip_speed,
    replace_clip_source,
    ripple_delete_clip,
    slip_clip,
    split_clip,
)
from .effects import apply_effect, remove_effect
from .groups import group_clips, list_groups, ungroup_clips
from .markers import add_marker
from .transitions import add_transition, remove_transition


__all__ = [
    "import_media",
    "insert_clip",
    "append_clip",
    "move_clip",
    "trim_clip",
    "delete_clip",
    "slip_clip",
    "ripple_delete_clip",
    "change_clip_speed",
    "split_clip",
    "replace_clip_source",
    "add_transition",
    "remove_transition",
    "apply_effect",
    "remove_effect",
    "add_marker",
    "group_clips",
    "ungroup_clips",
    "list_groups",
]
