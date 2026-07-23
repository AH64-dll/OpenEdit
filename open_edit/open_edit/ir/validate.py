"""Validation of operations against a project's current state.

Returns a list of error messages (empty list = valid). Each error
includes a `fix:` line per the spec.
"""
from __future__ import annotations

from pathlib import Path
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
    Timeline,
    TrimClipOp,
)

if TYPE_CHECKING:
    from open_edit.ir.catalog.loader import EffectCatalog


_DEFAULT_CATALOG: Optional["EffectCatalog"] = None


def _get_default_catalog() -> "EffectCatalog":
    """Load the bundled effect catalog once, on first use, and cache it."""
    global _DEFAULT_CATALOG
    if _DEFAULT_CATALOG is None:
        from open_edit.ir.catalog.loader import EffectCatalog
        catalog_dir = Path(__file__).parent / "catalog"
        _DEFAULT_CATALOG = EffectCatalog(catalog_dir)
    return _DEFAULT_CATALOG


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
    """Validate an operation against the project. Returns a list of errors.

    The default catalog is loaded from the bundled effects directory on
    first use. Tests can pass an explicit ``catalog=`` to isolate from the
    real catalog. Spec §6.1.1 requires the unknown-effect-type check to
    be unconditional, so the catalog is always applied when one is
    available.
    """
    if catalog is None:
        catalog = _get_default_catalog()
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
        if catalog is not None:
            spec = catalog.get(op.effect_type)
            if spec is not None and op.target_kind not in spec.target_kind:
                allowed = ", ".join(spec.target_kind)
                errors.append(
                    f"AddEffectOp: effect '{op.effect_type}' cannot be "
                    f"applied to {op.target_kind}; it supports: {allowed}. "
                    f"fix: change target_kind to one of: {allowed}."
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


class OpValidationError(ValueError):
    """Raised by EditGraphStore.append when an op fails validation."""


class TimelineValidationError(ValueError):
    """Raised by derive_timeline(strict=True) when the timeline is broken."""


def validate_timeline(timeline: Timeline) -> list[str]:
    """Return timeline-level errors (empty list = valid).

    Detects overlapping clips on the same track and non-positive clip
    durations. Transitions do not create overlaps in the derived timeline
    (they trim clip boundaries to meet at the cut), so a plain interval
    check is correct.
    """
    errors: list[str] = []
    eps = 1e-6
    for track in timeline.tracks:
        clips = sorted(track.clips, key=lambda c: c.position_sec)
        for prev, cur in zip(clips, clips[1:]):
            prev_end = prev.position_sec + (prev.out_point_sec - prev.in_point_sec)
            if prev_end > cur.position_sec + eps:
                errors.append(
                    f"Overlap on track {track.track_id}: clip {prev.clip_id!r} "
                    f"spans [{prev.position_sec:.3f}, {prev_end:.3f}] but clip "
                    f"{cur.clip_id!r} starts at {cur.position_sec:.3f}."
                )
        for c in track.clips:
            dur = c.out_point_sec - c.in_point_sec
            if dur <= 0:
                errors.append(
                    f"Clip {c.clip_id!r} has non-positive duration ({dur:.3f}s)."
                )
    return errors


def validate_op_for_append(op: OperationUnion, store) -> list[str]:
    """Validate one op against the store's current project state.

    Builds a lightweight Project from the store (current ops + assets) and
    delegates to :func:`validate_op`. ``store`` is duck-typed (must expose
    ``load_all()``, ``db_path``, ``project_id``). No runtime import of
    EditGraphStore here to avoid a circular import.
    """
    from open_edit.storage.assets import AssetStore

    ops = store.load_all()
    assets: dict = {}
    db_parent = store.db_path.parent
    direct = db_parent / "assets"
    assets_dir = direct if direct.is_dir() else db_parent / ".open_edit" / "assets"
    if assets_dir.is_dir():
        astore = AssetStore(assets_dir)
        for o in ops:
            if isinstance(o, AddClipOp) and o.asset_hash not in assets:
                a = astore.get(o.asset_hash)
                if a is not None:
                    assets[o.asset_hash] = a
    project = Project(
        project_id=store.project_id,
        name=db_parent.name,
        workdir=db_parent,
        assets=assets,
        edit_graph=ops,
    )
    return validate_op(op, project)
