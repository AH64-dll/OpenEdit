"""Shared helpers for the operation apply modules.

``ApplyError`` is raised when an op cannot be applied to the timeline
(strict mode). ``_get_or_create_track``, ``_find_clip`` and ``_make_clip``
are used by the dispatch in :mod:`open_edit.ir.apply` and by the handler
modules (:mod:`open_edit.ir.apply_clips`, :mod:`open_edit.ir.apply_effects`,
:mod:`open_edit.ir.apply_audio`).
"""
from __future__ import annotations

from open_edit.ir.types import AddClipOp, Clip, Timeline, Track


class ApplyError(Exception):
    """Raised when an op cannot be applied to the timeline."""


def _get_or_create_track(timeline: Timeline, track_id: str, kind: str) -> Track:
    for track in timeline.tracks:
        if track.track_id == track_id:
            return track
    new_track = Track(track_id=track_id, kind=kind)
    timeline.tracks.append(new_track)
    return new_track


def _find_clip(timeline: Timeline, clip_id: str):
    for track in timeline.tracks:
        for i, clip in enumerate(track.clips):
            if clip.clip_id == clip_id:
                return track, clip, i
    return None, None, None


def _make_clip(op: AddClipOp, out_point_sec: float) -> Clip:
    return Clip(
        clip_id=op.clip_id,
        asset_hash=op.asset_hash,
        track_id=op.track_id,
        track_kind=op.track_kind,
        position_sec=op.position_sec,
        in_point_sec=op.in_point_sec,
        out_point_sec=out_point_sec,
        effects=[],
    )
