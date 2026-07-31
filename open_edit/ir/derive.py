"""Timeline derivation: replay the edit graph into a Timeline. Pure functions."""
from __future__ import annotations

from open_edit.ir.apply import apply_operation
from open_edit.ir.apply_common import ApplyError
from open_edit.ir.types import Project, Timeline


def derive_timeline(project: Project, strict: bool = False) -> Timeline:
    """Replay all non-reverted, applied operations in sequence order.

    When ``strict=True``, raise TimelineValidationError if the resulting
    timeline has overlaps or non-positive-duration clips.
    """
    timeline = Timeline()
    if not project.edit_graph:
        return timeline

    op_by_id = {op.edit_id: op for op in project.edit_graph}

    for op in project.edit_graph:
        if op.status != "applied":
            continue

        curr_parent = op.parent_id
        parent_reverted = False
        # ``derive_timeline`` assumes the parent chain is a tree. A tampered DB
        # could introduce a cycle in parent_id references; walking it would
        # hang the process. Track visited edit_ids to detect the cycle and
        # raise instead of looping forever.
        visited_parents: set[str] = set()
        cycle_detected = False
        while curr_parent:
            if curr_parent in visited_parents:
                cycle_detected = True
                break
            visited_parents.add(curr_parent)
            parent_op = op_by_id.get(curr_parent)
            if parent_op is not None and parent_op.status != "applied":
                parent_reverted = True
                break
            curr_parent = parent_op.parent_id if parent_op else None

        if cycle_detected:
            raise ApplyError(
                f"derive_timeline: parent_id cycle detected starting from "
                f"op.edit_id={op.edit_id!r} (parent_id={op.parent_id!r})"
            )
        if parent_reverted:
            continue

        timeline = apply_operation(timeline, op)

    max_end = 0.0
    for track in timeline.tracks:
        for clip in track.clips:
            end = clip.position_sec + (clip.out_point_sec - clip.in_point_sec)
            if end > max_end:
                max_end = end
    for overlay in timeline.overlays:
        end = overlay.position_sec + overlay.duration_sec
        if end > max_end:
            max_end = end
    for composition in timeline.remotion_compositions:
        end = composition.position_sec + composition.duration_sec
        if end > max_end:
            max_end = end
    timeline.duration_sec = max_end
    if strict:
        from open_edit.ir.validate import TimelineValidationError, validate_timeline
        errs = validate_timeline(timeline)
        if errs:
            raise TimelineValidationError("; ".join(errs))
    return timeline
