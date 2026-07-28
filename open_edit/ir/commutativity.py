"""Commutativity predicate for reordering operations."""
from __future__ import annotations

from open_edit.ir.types import (
    AddClipOp,
    AddEffectOp,
    AddTransitionOp,
    MoveClipOp,
    OperationUnion,
    RemoveClipOp,
    SetKeyframeOp,
    TrimClipOp,
)


def _refs_clip(op: OperationUnion, clip_id: str) -> bool:
    if isinstance(op, AddClipOp) and op.clip_id == clip_id:
        return True
    if isinstance(op, RemoveClipOp) and op.clip_id == clip_id:
        return True
    if isinstance(op, MoveClipOp) and op.clip_id == clip_id:
        return True
    if isinstance(op, TrimClipOp) and op.clip_id == clip_id:
        return True
    if isinstance(op, AddTransitionOp) and (
        op.clip_a_id == clip_id or op.clip_b_id == clip_id
    ):
        return True
    if isinstance(op, AddEffectOp) and op.target_kind == "clip" and op.target_id == clip_id:
        return True
    return False


def can_swap(op_a: OperationUnion, op_b: OperationUnion) -> bool:
    """Whether two adjacent operations can be safely reordered.

    Conservative: when in doubt, return False.
    """
    if isinstance(op_a, AddClipOp) and isinstance(op_b, AddClipOp):
        return True
    if isinstance(op_a, SetKeyframeOp) and isinstance(op_b, SetKeyframeOp):
        return op_a.effect_id != op_b.effect_id
    if isinstance(op_a, AddEffectOp) and isinstance(op_b, AddEffectOp):
        return op_a.effect_id != op_b.effect_id

    if isinstance(op_a, (RemoveClipOp, MoveClipOp, TrimClipOp)):
        if _refs_clip(op_b, op_a.clip_id):
            return False
    if isinstance(op_b, (RemoveClipOp, MoveClipOp, TrimClipOp)):
        if _refs_clip(op_a, op_b.clip_id):
            return False

    if isinstance(op_a, AddEffectOp) and op_a.target_kind == "clip":
        if _refs_clip(op_b, op_a.target_id) and isinstance(
            op_b, (RemoveClipOp, MoveClipOp, TrimClipOp)
        ):
            return False
    if isinstance(op_b, AddEffectOp) and op_b.target_kind == "clip":
        if _refs_clip(op_a, op_b.target_id) and isinstance(
            op_a, (RemoveClipOp, MoveClipOp, TrimClipOp)
        ):
            return False

    if isinstance(op_a, AddTransitionOp):
        if _refs_clip(op_b, op_a.clip_a_id) or _refs_clip(op_b, op_a.clip_b_id):
            return False
    if isinstance(op_b, AddTransitionOp):
        if _refs_clip(op_a, op_b.clip_a_id) or _refs_clip(op_a, op_b.clip_b_id):
            return False

    return True
