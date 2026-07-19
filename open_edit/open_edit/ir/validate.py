"""Validation of operations against a project's current state.

Returns a list of error messages (empty list = valid). Each error
includes a `fix:` line per the spec.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from open_edit.ir.types import (
    AddClipOp,
    AddEffectOp,
    AddTransitionOp,
    MoveClipOp,
    OperationUnion,
    Project,
    RemoveClipOp,
    SetAudioGainOp,
    SetKeyframeOp,
    TrimClipOp,
)

if TYPE_CHECKING:
    from open_edit.ir.catalog.loader import EffectCatalog


def _known_clip_ids(project: Project) -> set[str]:
    known: set[str] = set()
    for op in project.edit_graph:
        if isinstance(op, AddClipOp) and op.status == "applied":
            known.add(op.clip_id)
        elif isinstance(op, RemoveClipOp) and op.status == "applied":
            known.discard(op.clip_id)
    return known


def _known_effect_ids(project: Project) -> set[str]:
    return {
        op.effect_id
        for op in project.edit_graph
        if isinstance(op, AddEffectOp) and op.status == "applied"
    }


def validate_op(
    op: OperationUnion,
    project: Project,
    catalog: Optional["EffectCatalog"] = None,
) -> list[str]:
    """Validate an operation against the project. Returns a list of errors."""
    errors: list[str] = []

    if op.status != "applied":
        return errors

    if isinstance(op, AddClipOp):
        if op.asset_hash not in project.assets:
            errors.append(
                f"Unknown asset_hash '{op.asset_hash}'. "
                f"fix: import the asset first via AssetStore.ingest()."
            )
        if op.position_sec < 0:
            errors.append(
                f"position_sec must be >= 0; got {op.position_sec}. "
                f"fix: use a non-negative position."
            )
        if op.in_point_sec < 0:
            errors.append(
                f"in_point_sec must be >= 0; got {op.in_point_sec}. "
                f"fix: use a non-negative in-point."
            )
        if op.out_point_sec is not None and op.out_point_sec <= op.in_point_sec:
            errors.append(
                f"out_point_sec ({op.out_point_sec}) must be greater than "
                f"in_point_sec ({op.in_point_sec}). "
                f"fix: set out_point_sec > in_point_sec, or leave as None."
            )

    elif isinstance(op, RemoveClipOp):
        pass  # no-op if unknown

    elif isinstance(op, MoveClipOp):
        if op.clip_id not in _known_clip_ids(project):
            errors.append(
                f"MoveClipOp: clip_id '{op.clip_id}' not found in project. "
                f"fix: ensure the clip was added before moving it."
            )

    elif isinstance(op, TrimClipOp):
        if op.clip_id not in _known_clip_ids(project):
            errors.append(
                f"TrimClipOp: clip_id '{op.clip_id}' not found in project. "
                f"fix: ensure the clip was added before trimming it."
            )
        if op.new_in_point_sec >= op.new_out_point_sec:
            errors.append(
                f"new_in_point_sec ({op.new_in_point_sec}) must be less than "
                f"new_out_point_sec ({op.new_out_point_sec}). "
                f"fix: ensure in < out."
            )

    elif isinstance(op, AddTransitionOp):
        if op.clip_a_id not in _known_clip_ids(project):
            errors.append(
                f"AddTransitionOp: clip_a_id '{op.clip_a_id}' not found. "
                f"fix: ensure clip_a is added before the transition."
            )
        if op.clip_b_id not in _known_clip_ids(project):
            errors.append(
                f"AddTransitionOp: clip_b_id '{op.clip_b_id}' not found. "
                f"fix: ensure clip_b is added before the transition."
            )
        if op.duration_sec <= 0:
            errors.append(
                f"duration_sec must be > 0; got {op.duration_sec}. "
                f"fix: set a positive duration."
            )

    elif isinstance(op, AddEffectOp):
        if catalog is not None and not catalog.is_known(op.effect_type):
            known = ", ".join(sorted(catalog.known_names()))
            errors.append(
                f"AddEffectOp: effect_type '{op.effect_type}' is not in the catalog. "
                f"fix: use one of: {known}."
            )
        if op.target_kind == "clip" and op.target_id not in _known_clip_ids(project):
            errors.append(
                f"AddEffectOp: target clip '{op.target_id}' not found. "
                f"fix: add the clip before applying the effect."
            )

    elif isinstance(op, SetKeyframeOp):
        if op.effect_id not in _known_effect_ids(project):
            errors.append(
                f"SetKeyframeOp: effect_id '{op.effect_id}' not found. "
                f"fix: add the effect before setting keyframes."
            )

    elif isinstance(op, SetAudioGainOp):
        if op.clip_id not in _known_clip_ids(project):
            errors.append(
                f"SetAudioGainOp: clip_id '{op.clip_id}' not found. "
                f"fix: add the audio clip before setting gain."
            )

    return errors
