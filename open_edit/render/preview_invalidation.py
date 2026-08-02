"""Frame-aligned geometry helpers for timeline preview chunks.

Chunk boundaries are expressed as integer project frames.  Seconds are only
materialized at the IR boundary because ``Timeline`` and its child models
currently expose seconds as their public representation.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Literal, Sequence

from open_edit.ir.types import (
    Clip,
    HtmlOverlay,
    Operation,
    RemotionComposition,
    Timeline,
    Track,
)
from open_edit.render.preview_manifest import PreviewRange


PreviewPlane = Literal["video", "audio", "both"]


@dataclass(frozen=True)
class ChunkWindow:
    """A core chunk plus the context rendered around it.

    ``start_frame`` and ``end_frame`` are the published core range.  The
    render range may be wider when a caller adds transition/effect context;
    crop counts describe how much of that wider render must be removed before
    publishing the core artifact.
    """

    index: int
    start_frame: int
    end_frame: int
    render_start_frame: int
    render_end_frame: int
    crop_head_frames: int
    crop_tail_frames: int
    # Kept on the geometry object so invalidation can map operation seconds
    # back to frame-aligned windows without changing the public fingerprint
    # interface.
    fps_num: int | None = None
    fps_den: int | None = None


@dataclass(frozen=True)
class ChunkFingerprint:
    """Canonical current keys and dirty state for one preview chunk."""

    video_key: str
    audio_key: str
    composition_uids: tuple[str, ...]
    video_dirty: bool
    audio_dirty: bool
    # These fields are populated by ``compute_chunk_fingerprints`` and let the
    # range selector remain independent of the geometry list.
    start_sec: float | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    end_sec: float | None = field(
        default=None,
        repr=False,
        compare=False,
    )


def make_chunk_windows(
    duration_frames: int,
    fps_num: int,
    fps_den: int,
    chunk_frames: int | None = None,
) -> list[ChunkWindow]:
    """Build half-open, frame-aligned core windows.

    The default chunk size is one project second, rounded in frame space.  A
    window initially renders exactly its core; callers that detect a
    boundary-crossing transition/effect can widen ``render_*`` and recompute
    the crop counts without changing the published core geometry.
    """
    _validate_fps(fps_num, fps_den)
    if duration_frames < 0:
        raise ValueError("duration_frames must be non-negative")

    if chunk_frames is None:
        chunk_frames = max(1, int(round(fps_num / fps_den)))
    if chunk_frames <= 0:
        raise ValueError("chunk_frames must be positive")

    windows: list[ChunkWindow] = []
    for index, start_frame in enumerate(range(0, duration_frames, chunk_frames)):
        end_frame = min(duration_frames, start_frame + chunk_frames)
        windows.append(
            ChunkWindow(
                index=index,
                start_frame=start_frame,
                end_frame=end_frame,
                render_start_frame=start_frame,
                render_end_frame=end_frame,
                crop_head_frames=0,
                crop_tail_frames=0,
                fps_num=fps_num,
                fps_den=fps_den,
            )
        )
    return windows


def slice_timeline(
    timeline: Timeline,
    *,
    render_start_frame: int,
    render_end_frame: int,
    fps_num: int,
    fps_den: int,
    plane: PreviewPlane,
) -> Timeline:
    """Return a local-coordinate timeline for a frame range.

    The render range is half-open.  A crossing clip is retained once and its
    timeline position plus source in/out points are rebased using integer
    frame offsets.  Clip-local effects and track effects are copied unchanged.
    """
    _validate_fps(fps_num, fps_den)
    _validate_frame_range(render_start_frame, render_end_frame)
    if plane not in {"video", "audio", "both"}:
        raise ValueError(f"unsupported preview plane: {plane!r}")

    updated = timeline.model_copy(deep=True)
    updated.tracks = _slice_tracks(
        updated.tracks,
        render_start_frame=render_start_frame,
        render_end_frame=render_end_frame,
        fps_num=fps_num,
        fps_den=fps_den,
        plane=plane,
    )

    if plane == "audio":
        updated.overlays = []
        updated.remotion_compositions = []
    else:
        updated.overlays = _slice_html_overlays(
            updated.overlays,
            render_start_frame=render_start_frame,
            render_end_frame=render_end_frame,
            fps_num=fps_num,
            fps_den=fps_den,
        )
        updated.remotion_compositions = _slice_remotion_compositions(
            updated.remotion_compositions,
            render_start_frame=render_start_frame,
            render_end_frame=render_end_frame,
            fps_num=fps_num,
            fps_den=fps_den,
        )

    updated.duration_sec = _frames_to_seconds(
        render_end_frame - render_start_frame,
        fps_num,
        fps_den,
    )
    return updated


def _slice_tracks(
    tracks: list[Track],
    *,
    render_start_frame: int,
    render_end_frame: int,
    fps_num: int,
    fps_den: int,
    plane: PreviewPlane,
) -> list[Track]:
    selected_kinds = (
        {"video", "audio"}
        if plane == "both"
        else {plane}
    )
    sliced_tracks: list[Track] = []
    for track in tracks:
        if track.kind not in selected_kinds:
            continue
        clips = [
            sliced
            for clip in track.clips
            if (sliced := _slice_clip(
                clip,
                render_start_frame=render_start_frame,
                render_end_frame=render_end_frame,
                fps_num=fps_num,
                fps_den=fps_den,
            )) is not None
        ]
        if clips:
            clips.sort(key=lambda clip: clip.position_sec)
            sliced_tracks.append(track.model_copy(update={"clips": clips}))
    return sliced_tracks


def _slice_clip(
    clip: Clip,
    *,
    render_start_frame: int,
    render_end_frame: int,
    fps_num: int,
    fps_den: int,
) -> Clip | None:
    source_start_frame = _seconds_to_frame(clip.in_point_sec, fps_num, fps_den)
    source_end_frame = _seconds_to_frame(clip.out_point_sec, fps_num, fps_den)
    source_duration = source_end_frame - source_start_frame
    if source_duration <= 0:
        return None

    timeline_start_frame = _seconds_to_frame(
        clip.position_sec,
        fps_num,
        fps_den,
    )
    timeline_end_frame = timeline_start_frame + source_duration
    overlap_start = max(timeline_start_frame, render_start_frame)
    overlap_end = min(timeline_end_frame, render_end_frame)
    if overlap_start >= overlap_end:
        return None

    source_overlap_start = source_start_frame + (
        overlap_start - timeline_start_frame
    )
    source_overlap_end = source_start_frame + (
        overlap_end - timeline_start_frame
    )
    return clip.model_copy(
        update={
            "position_sec": _frames_to_seconds(
                overlap_start - render_start_frame,
                fps_num,
                fps_den,
            ),
            "in_point_sec": _frames_to_seconds(
                source_overlap_start,
                fps_num,
                fps_den,
            ),
            "out_point_sec": _frames_to_seconds(
                source_overlap_end,
                fps_num,
                fps_den,
            ),
        }
    )


def _slice_html_overlays(
    overlays: list[HtmlOverlay],
    *,
    render_start_frame: int,
    render_end_frame: int,
    fps_num: int,
    fps_den: int,
) -> list[HtmlOverlay]:
    sliced: list[HtmlOverlay] = []
    for overlay in overlays:
        overlap = _overlap_interval(
            overlay.position_sec,
            overlay.position_sec + overlay.duration_sec,
            render_start_frame=render_start_frame,
            render_end_frame=render_end_frame,
            fps_num=fps_num,
            fps_den=fps_den,
        )
        if overlap is None:
            continue
        overlap_start, overlap_end = overlap
        sliced.append(
            overlay.model_copy(
                update={
                    "position_sec": _frames_to_seconds(
                        overlap_start - render_start_frame,
                        fps_num,
                        fps_den,
                    ),
                    "duration_sec": _frames_to_seconds(
                        overlap_end - overlap_start,
                        fps_num,
                        fps_den,
                    ),
                }
            )
        )
    return sliced


def _slice_remotion_compositions(
    compositions: list[RemotionComposition],
    *,
    render_start_frame: int,
    render_end_frame: int,
    fps_num: int,
    fps_den: int,
) -> list[RemotionComposition]:
    sliced: list[RemotionComposition] = []
    for composition in compositions:
        overlap = _overlap_interval(
            composition.position_sec,
            composition.position_sec + composition.duration_sec,
            render_start_frame=render_start_frame,
            render_end_frame=render_end_frame,
            fps_num=fps_num,
            fps_den=fps_den,
        )
        if overlap is None:
            continue
        overlap_start, overlap_end = overlap
        sliced.append(
            composition.model_copy(
                update={
                    "position_sec": _frames_to_seconds(
                        overlap_start - render_start_frame,
                        fps_num,
                        fps_den,
                    ),
                    "duration_sec": _frames_to_seconds(
                        overlap_end - overlap_start,
                        fps_num,
                        fps_den,
                    ),
                }
            )
        )
    return sliced


def _overlap_interval(
    start_sec: float,
    end_sec: float,
    *,
    render_start_frame: int,
    render_end_frame: int,
    fps_num: int,
    fps_den: int,
) -> tuple[int, int] | None:
    start_frame = _seconds_to_frame(start_sec, fps_num, fps_den)
    end_frame = _seconds_to_frame(end_sec, fps_num, fps_den)
    overlap_start = max(start_frame, render_start_frame)
    overlap_end = min(end_frame, render_end_frame)
    if overlap_start >= overlap_end:
        return None
    return overlap_start, overlap_end


def _validate_fps(fps_num: int, fps_den: int) -> None:
    if fps_num <= 0 or fps_den <= 0:
        raise ValueError("fps_num and fps_den must be positive")


def _validate_frame_range(start_frame: int, end_frame: int) -> None:
    if start_frame < 0:
        raise ValueError("render_start_frame must be non-negative")
    if end_frame <= start_frame:
        raise ValueError(
            "render_end_frame must be greater than render_start_frame"
        )


def _seconds_to_frame(seconds: float, fps_num: int, fps_den: int) -> int:
    if not math.isfinite(seconds):
        raise ValueError("timeline seconds must be finite")
    return int(round(seconds * fps_num / fps_den))


def _frames_to_seconds(frames: int, fps_num: int, fps_den: int) -> float:
    return frames * fps_den / fps_num


OperationPlane = Literal["video", "audio"]
_AUDIO_ONLY_KINDS = frozenset({"set_audio_gain", "normalize_audio"})
_VIDEO_ONLY_KINDS = frozenset(
    {
        "add_html_overlay",
        "remove_html_overlay",
        "add_remotion_composition",
        "remove_remotion_composition",
    }
)
_FULL_TIMELINE_KINDS = frozenset({"raw_mlt_xml", "free_form_code"})
_CLIP_TARGET_KINDS = frozenset(
    {
        "remove_clip",
        "move_clip",
        "trim_clip",
        "remove_effect",
        "set_effect_param",
        "slip_clip",
        "ripple_delete_clip",
        "change_clip_speed",
        "split_clip",
        "replace_clip_source",
        "set_clip_speed_ramp",
        "set_audio_gain",
    }
)
_TRANSITION_KINDS = frozenset(
    {"add_transition", "remove_transition", "set_transition_property"}
)
_EFFECT_KINDS = frozenset({"add_effect", "remove_effect", "set_effect_param"})
_KNOWN_KINDS = (
    _AUDIO_ONLY_KINDS
    | _VIDEO_ONLY_KINDS
    | _FULL_TIMELINE_KINDS
    | _CLIP_TARGET_KINDS
    | _TRANSITION_KINDS
    | _EFFECT_KINDS
    | {
        "add_clip",
        "set_keyframe",
        "remove_keyframe",
        "group_edits",
        "ungroup_edits",
    }
)
_AUDIO_EFFECT_NAMES = frozenset(
    {
        "audio",
        "audio_fade",
        "audio_gain",
        "compressor",
        "equalizer",
        "limiter",
        "loudness",
        "mute",
        "normalize",
        "pan",
        "volume",
    }
)
_VIDEO_EFFECT_NAMES = frozenset(
    {
        "blur",
        "brightness",
        "chroma",
        "color",
        "composite",
        "contrast",
        "crop",
        "opacity",
        "overlay",
        "saturation",
        "transform",
        "video",
    }
)


def classify_operation_planes(
    op: Operation,
    timeline: Timeline,
) -> frozenset[OperationPlane]:
    """Classify an applied operation into the media planes it can affect.

    Operations with an unresolvable target are deliberately conservative.  A
    missing target can mean the caller supplied the post-edit snapshot, so
    guessing a plane would risk reusing an invalid artifact.
    """

    kind = str(_op_field(op, "kind", ""))
    if kind in _FULL_TIMELINE_KINDS:
        return frozenset({"video", "audio"})
    if kind in _AUDIO_ONLY_KINDS:
        return frozenset({"audio"})
    if kind in _VIDEO_ONLY_KINDS:
        return frozenset({"video"})
    if kind == "add_clip":
        track_kind = _op_field(op, "track_kind", None)
        if track_kind in {"video", "audio"}:
            return frozenset({track_kind})
        track = _find_track(timeline, _op_field(op, "track_id", ""))
        return frozenset({track.kind}) if track is not None else frozenset(
            {"video", "audio"}
        )

    if kind in _TRANSITION_KINDS:
        if kind != "add_transition":
            # The current Timeline IR does not retain transition records, so
            # removal/property edits cannot be narrowed by the snapshot.
            return frozenset({"video"})
        planes: set[OperationPlane] = set()
        for clip_id in (
            _op_field(op, "clip_a_id", ""),
            _op_field(op, "clip_b_id", ""),
        ):
            planes.update(_clip_planes(timeline, clip_id))
        return frozenset(planes or {"video"})

    if kind == "add_effect":
        target_kind = _op_field(op, "target_kind", "")
        target_id = _op_field(op, "target_id", "")
        if target_kind == "clip":
            planes = _clip_planes(timeline, target_id)
            return frozenset(planes or {"video", "audio"})
        if target_kind == "track":
            track = _find_track(timeline, target_id)
            return (
                frozenset({track.kind})
                if track is not None
                else frozenset({"video", "audio"})
            )
        return frozenset({"video", "audio"})

    if kind in {"set_keyframe", "remove_keyframe"}:
        planes = _effect_planes(timeline, _op_field(op, "effect_id", ""))
        return frozenset(planes or {"video", "audio"})

    if kind in _CLIP_TARGET_KINDS:
        clip_id = _op_field(op, "clip_id", "")
        planes: set[OperationPlane] = set()
        planes.update(_clip_planes(timeline, clip_id))
        if kind == "move_clip":
            track = _find_track(timeline, _op_field(op, "new_track_id", ""))
            if track is not None:
                planes.add(track.kind)
        return frozenset(planes or {"video", "audio"})

    if kind in {"group_edits", "ungroup_edits"}:
        return frozenset({"video", "audio"})

    # New operation kinds must never silently reuse either plane.
    return frozenset({"video", "audio"})


def compute_chunk_fingerprints(
    *,
    old_timeline: Timeline | None,
    new_timeline: Timeline,
    old_graph_hash: str | None,
    new_graph_hash: str,
    operations: Sequence[Operation],
    windows: Sequence[ChunkWindow],
    profile_fingerprint: str,
    content_fingerprint: str,
) -> list[ChunkFingerprint]:
    """Compute per-plane keys and conservative dirty flags.

    Keys intentionally omit the whole edit-graph hash.  The graph hash is a
    snapshot identity and a fallback signal; putting it into both plane keys
    would make an audio-only edit flush video chunks.  The sliced timeline,
    profile/content identity, core geometry, plane, and localized operation
    semantics are the actual cache identity.
    """

    if not windows:
        return []

    old_missing = old_timeline is None or old_graph_hash is None
    operations = tuple(operations)
    operation_info = [
        (
            op,
            _operation_planes(op, old_timeline, new_timeline),
            _operation_intervals(op, old_timeline, new_timeline),
        )
        for op in operations
    ]
    has_unknown_operation = any(
        str(_op_field(op, "kind", "")) not in _KNOWN_KINDS
        for op in operations
    )
    full_graph_fallback = (
        has_unknown_operation
        or (old_graph_hash != new_graph_hash and not operations)
    )

    fingerprints: list[ChunkFingerprint] = []
    for window in windows:
        video_key = _chunk_plane_key(
            new_timeline,
            window=window,
            plane="video",
            profile_fingerprint=profile_fingerprint,
            content_fingerprint=content_fingerprint,
            operation_markers=_localized_operation_markers(
                operation_info,
                plane="video",
                window=window,
            ),
        )
        audio_key = _chunk_plane_key(
            new_timeline,
            window=window,
            plane="audio",
            profile_fingerprint=profile_fingerprint,
            content_fingerprint=content_fingerprint,
            operation_markers=_localized_operation_markers(
                operation_info,
                plane="audio",
                window=window,
            ),
        )

        old_video_key = None
        old_audio_key = None
        if old_timeline is not None:
            old_video_key = _chunk_plane_key(
                old_timeline,
                window=window,
                plane="video",
                profile_fingerprint=profile_fingerprint,
                content_fingerprint=content_fingerprint,
                operation_markers=(),
            )
            old_audio_key = _chunk_plane_key(
                old_timeline,
                window=window,
                plane="audio",
                profile_fingerprint=profile_fingerprint,
                content_fingerprint=content_fingerprint,
                operation_markers=(),
            )

        video_dirty = old_missing or old_video_key != video_key
        audio_dirty = old_missing or old_audio_key != audio_key
        if full_graph_fallback:
            video_dirty = True
            audio_dirty = True
        else:
            for op, planes, intervals in operation_info:
                del op
                for plane in planes:
                    if not _operation_overlaps_window(intervals, window):
                        continue
                    if plane == "video":
                        video_dirty = True
                    else:
                        audio_dirty = True

        start_sec, end_sec = _window_seconds(window)
        compositions = _overlapping_composition_uids(new_timeline, window)
        fingerprints.append(
            ChunkFingerprint(
                video_key=video_key,
                audio_key=audio_key,
                composition_uids=compositions,
                video_dirty=video_dirty,
                audio_dirty=audio_dirty,
                start_sec=start_sec,
                end_sec=end_sec,
            )
        )
    return fingerprints


def select_dirty_windows(
    fingerprints: Sequence[ChunkFingerprint],
    requested_ranges: Sequence[PreviewRange],
    *,
    background: bool,
) -> list[int]:
    """Return dirty chunk indexes, prioritizing an interactive playhead range."""

    dirty = {
        index
        for index, fingerprint in enumerate(fingerprints)
        if fingerprint.video_dirty or fingerprint.audio_dirty
    }
    if not dirty:
        return []
    if background or not requested_ranges:
        return sorted(dirty)

    first_range = requested_ranges[0]
    matching = {
        index
        for index in dirty
        if any(
            _ranges_overlap(
                fingerprint.start_sec,
                fingerprint.end_sec,
                requested.start_sec,
                requested.end_sec,
            )
            for requested in requested_ranges
            for fingerprint in (fingerprints[index],)
        )
    }

    # A manually constructed fingerprint may not carry geometry metadata.  It
    # is safer to render all dirty work than to silently drop a requested miss.
    if not any(
        fingerprint.start_sec is not None and fingerprint.end_sec is not None
        for fingerprint in fingerprints
    ):
        return sorted(dirty)
    if not matching:
        return []

    selected = set(matching)
    for index in matching:
        for neighbor in (index - 1, index + 1):
            if neighbor in dirty:
                selected.add(neighbor)

    def priority(index: int) -> tuple[int, float, int]:
        fingerprint = fingerprints[index]
        distance = _range_distance(
            fingerprint.start_sec,
            fingerprint.end_sec,
            first_range.start_sec,
            first_range.end_sec,
        )
        overlaps = _ranges_overlap(
            fingerprint.start_sec,
            fingerprint.end_sec,
            first_range.start_sec,
            first_range.end_sec,
        )
        return (0 if overlaps else 1), distance, index

    return sorted(selected, key=priority)


def _chunk_plane_key(
    timeline: Timeline,
    *,
    window: ChunkWindow,
    plane: OperationPlane,
    profile_fingerprint: str,
    content_fingerprint: str,
    operation_markers: Sequence[dict[str, Any]],
) -> str:
    sliced = slice_timeline(
        timeline,
        render_start_frame=window.render_start_frame,
        render_end_frame=window.render_end_frame,
        fps_num=window.fps_num or 1,
        fps_den=window.fps_den or 1,
        plane=plane,
    )
    payload = {
        "plane": plane,
        "core_range": [window.start_frame, window.end_frame],
        "render_range": [window.render_start_frame, window.render_end_frame],
        "profile": profile_fingerprint,
        "content": content_fingerprint,
        "timeline": _key_timeline_value(sliced, plane),
        "operations": list(operation_markers),
    }
    return _stable_hash(payload)


def _operation_planes(
    op: Operation,
    old_timeline: Timeline | None,
    new_timeline: Timeline,
) -> frozenset[OperationPlane]:
    candidates: list[frozenset[OperationPlane]] = []
    for timeline in (old_timeline, new_timeline):
        if timeline is not None:
            candidates.append(classify_operation_planes(op, timeline))
    if not candidates:
        return frozenset({"video", "audio"})

    # A removed target is absent from the new snapshot and therefore looks
    # unknown there.  Preserve the plane resolved from the old snapshot while
    # still unioning genuinely resolvable plane changes (for example a move
    # from an audio track to a video track).
    specific = [candidate for candidate in candidates if len(candidate) < 2]
    if specific:
        return frozenset().union(*specific)
    return frozenset({"video", "audio"})


def _localized_operation_markers(
    operation_info: Sequence[
        tuple[Operation, frozenset[OperationPlane], list[tuple[float, float]] | None]
    ],
    *,
    plane: OperationPlane,
    window: ChunkWindow,
) -> tuple[dict[str, Any], ...]:
    markers: list[dict[str, Any]] = []
    for op, planes, intervals in operation_info:
        if plane not in planes or not _operation_overlaps_window(intervals, window):
            continue
        markers.append(_operation_marker(op))
    markers.sort(key=lambda marker: json.dumps(marker, sort_keys=True))
    return tuple(markers)


def _operation_marker(op: Operation) -> dict[str, Any]:
    data = _json_value(op)
    if not isinstance(data, dict):
        return {"kind": str(_op_field(op, "kind", "")), "value": data}
    # Identity/audit fields do not change rendered media.  The semantic IDs
    # that target clips/effects/compositions remain in the marker.
    for field in (
        "author",
        "edit_id",
        "originating_note_id",
        "parent_id",
        "status",
        "timestamp",
    ):
        data.pop(field, None)
    return data


def _operation_intervals(
    op: Operation,
    old_timeline: Timeline | None,
    new_timeline: Timeline,
) -> list[tuple[float, float]] | None:
    """Return affected project-second intervals, or None for full timeline."""

    kind = str(_op_field(op, "kind", ""))
    if kind in _FULL_TIMELINE_KINDS or kind in {
        "group_edits",
        "ungroup_edits",
        "remove_transition",
        "set_transition_property",
        "remove_html_overlay",
    }:
        return None
    if kind == "add_clip":
        clip = _find_clip(new_timeline, _op_field(op, "clip_id", ""))
        if clip is not None:
            return [_clip_interval(clip)]
        out_point = _op_field(op, "out_point_sec", None)
        if out_point is None:
            return None
        return [
            (
                float(_op_field(op, "position_sec", 0.0)),
                float(_op_field(op, "position_sec", 0.0))
                + max(
                    0.0,
                    float(out_point) - float(_op_field(op, "in_point_sec", 0.0)),
                ),
            )
        ]
    if kind in _CLIP_TARGET_KINDS:
        clip_id = _op_field(op, "clip_id", "")
        intervals = _clip_intervals(old_timeline, new_timeline, clip_id)
        return intervals or None
    if kind == "add_effect":
        target_kind = _op_field(op, "target_kind", "")
        target_id = _op_field(op, "target_id", "")
        if target_kind == "clip":
            return _clip_intervals(old_timeline, new_timeline, target_id) or None
        if target_kind == "track":
            intervals = _track_intervals(old_timeline, new_timeline, target_id)
            return intervals or None
        return None
    if kind in {"set_keyframe", "remove_keyframe"}:
        intervals = _effect_intervals(
            old_timeline,
            new_timeline,
            _op_field(op, "effect_id", ""),
        )
        return intervals or None
    if kind == "add_transition":
        intervals: list[tuple[float, float]] = []
        for clip_id in (
            _op_field(op, "clip_a_id", ""),
            _op_field(op, "clip_b_id", ""),
        ):
            intervals.extend(_clip_intervals(old_timeline, new_timeline, clip_id))
        return intervals or None
    if kind == "set_audio_gain":
        return _clip_intervals(
            old_timeline,
            new_timeline,
            _op_field(op, "clip_id", ""),
        ) or None
    if kind == "normalize_audio":
        target_kind = _op_field(op, "target_kind", "")
        target_id = _op_field(op, "target_id", "")
        if target_kind == "clip":
            return _clip_intervals(old_timeline, new_timeline, target_id) or None
        if target_kind == "track":
            return _track_intervals(old_timeline, new_timeline, target_id) or None
        return None
    if kind == "add_html_overlay":
        start = float(_op_field(op, "position_sec", 0.0))
        return [
            (start, start + max(0.0, float(_op_field(op, "duration_sec", 0.0))))
        ]
    if kind == "add_remotion_composition":
        start = float(_op_field(op, "position_sec", 0.0))
        return [
            (start, start + max(0.0, float(_op_field(op, "duration_sec", 0.0))))
        ]
    if kind == "remove_remotion_composition":
        composition_id = _op_field(op, "composition_uid", "")
        intervals: list[tuple[float, float]] = []
        for timeline in (old_timeline, new_timeline):
            if timeline is None:
                continue
            for composition in timeline.remotion_compositions:
                if composition.composition_uid == composition_id:
                    intervals.append(_composition_interval(composition))
        return intervals or None
    if kind in _KNOWN_KINDS:
        return None
    return None


def _operation_overlaps_window(
    intervals: list[tuple[float, float]] | None,
    window: ChunkWindow,
) -> bool:
    if intervals is None:
        return True
    start_sec, end_sec = _window_seconds(window)
    return any(
        _ranges_overlap(start_sec, end_sec, start, end)
        for start, end in intervals
    )


def _window_seconds(window: ChunkWindow) -> tuple[float, float]:
    if (
        window.fps_num is not None
        and window.fps_den is not None
        and window.fps_num > 0
        and window.fps_den > 0
    ):
        return (
            window.render_start_frame * window.fps_den / window.fps_num,
            window.render_end_frame * window.fps_den / window.fps_num,
        )
    # Chunk windows are one project second by default.  This fallback keeps
    # manually-created windows useful and remains conservative for custom
    # geometry because key comparison still catches timeline changes.
    return float(window.index), float(window.index + 1)


def _overlapping_composition_uids(
    timeline: Timeline,
    window: ChunkWindow,
) -> tuple[str, ...]:
    start_sec, end_sec = _window_seconds(window)
    return tuple(
        composition.composition_uid
        for composition in timeline.remotion_compositions
        if _ranges_overlap(
            start_sec,
            end_sec,
            composition.position_sec,
            composition.position_sec + composition.duration_sec,
        )
    )


def _ranges_overlap(
    left_start: float | None,
    left_end: float | None,
    right_start: float,
    right_end: float,
) -> bool:
    if left_start is None or left_end is None:
        return False
    return left_start < right_end and right_start < left_end


def _range_distance(
    start: float | None,
    end: float | None,
    requested_start: float,
    requested_end: float,
) -> float:
    if start is None or end is None:
        return math.inf
    if _ranges_overlap(start, end, requested_start, requested_end):
        return 0.0
    if end <= requested_start:
        return requested_start - end
    return start - requested_end


def _find_clip(timeline: Timeline, clip_id: str) -> Clip | None:
    for track in timeline.tracks:
        for clip in track.clips:
            if clip.clip_id == clip_id:
                return clip
    return None


def _clip_planes(timeline: Timeline, clip_id: str) -> set[OperationPlane]:
    return {
        clip.track_kind
        for track in timeline.tracks
        for clip in track.clips
        if clip.clip_id == clip_id
    }


def _find_track(timeline: Timeline, track_id: str) -> Track | None:
    return next(
        (track for track in timeline.tracks if track.track_id == track_id),
        None,
    )


def _clip_interval(clip: Clip) -> tuple[float, float]:
    start = float(clip.position_sec)
    end = start + max(0.0, float(clip.out_point_sec) - float(clip.in_point_sec))
    return start, end


def _composition_interval(
    composition: RemotionComposition,
) -> tuple[float, float]:
    start = float(composition.position_sec)
    return start, start + max(0.0, float(composition.duration_sec))


def _clip_intervals(
    old_timeline: Timeline | None,
    new_timeline: Timeline,
    clip_id: str,
) -> list[tuple[float, float]]:
    intervals: list[tuple[float, float]] = []
    for timeline in (old_timeline, new_timeline):
        if timeline is None:
            continue
        clip = _find_clip(timeline, clip_id)
        if clip is not None:
            intervals.append(_clip_interval(clip))
    return intervals


def _track_intervals(
    old_timeline: Timeline | None,
    new_timeline: Timeline,
    track_id: str,
) -> list[tuple[float, float]]:
    intervals: list[tuple[float, float]] = []
    for timeline in (old_timeline, new_timeline):
        if timeline is None:
            continue
        track = _find_track(timeline, track_id)
        if track is not None:
            intervals.extend(_clip_interval(clip) for clip in track.clips)
    return intervals


def _effect_intervals(
    old_timeline: Timeline | None,
    new_timeline: Timeline,
    effect_id: str,
) -> list[tuple[float, float]]:
    intervals: list[tuple[float, float]] = []
    for timeline in (old_timeline, new_timeline):
        if timeline is None:
            continue
        for track in timeline.tracks:
            if any(effect.effect_id == effect_id for effect in track.effects):
                intervals.extend(_clip_interval(clip) for clip in track.clips)
            for clip in track.clips:
                if any(effect.effect_id == effect_id for effect in clip.effects):
                    intervals.append(_clip_interval(clip))
    return intervals


def _effect_planes(timeline: Timeline, effect_id: str) -> set[OperationPlane]:
    planes: set[OperationPlane] = set()
    for track in timeline.tracks:
        if any(effect.effect_id == effect_id for effect in track.effects):
            planes.add(track.kind)
        for clip in track.clips:
            if any(effect.effect_id == effect_id for effect in clip.effects):
                planes.add(clip.track_kind)
    return planes


def _op_field(op: Operation | dict[str, Any], name: str, default: Any) -> Any:
    if isinstance(op, dict):
        return op.get(name, default)
    return getattr(op, name, default)


def _json_value(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _key_timeline_value(timeline: Timeline, plane: OperationPlane) -> Any:
    """Dump a plane slice while dropping effects owned by the other plane."""

    data = _json_value(timeline)
    if not isinstance(data, dict):
        return data
    for track in data.get("tracks", []):
        if not isinstance(track, dict):
            continue
        track["effects"] = [
            effect
            for effect in track.get("effects", [])
            if _effect_in_plane(effect, plane)
        ]
        for clip in track.get("clips", []):
            if isinstance(clip, dict):
                clip["effects"] = [
                    effect
                    for effect in clip.get("effects", [])
                    if _effect_in_plane(effect, plane)
                ]
    return data


def _effect_in_plane(effect: Any, plane: OperationPlane) -> bool:
    if not isinstance(effect, dict):
        return True
    effect_type = str(effect.get("effect_type", "")).strip().lower()
    params = effect.get("params")
    if not isinstance(params, dict):
        params = {}
    is_audio = (
        effect_type in _AUDIO_EFFECT_NAMES
        or effect_type.startswith("audio_")
        or bool(params.get("normalize"))
        or "gain_db" in params
    )
    is_video = (
        effect_type in _VIDEO_EFFECT_NAMES
        or effect_type.startswith("video_")
        or effect_type.startswith("compositor")
    )
    if plane == "video":
        return not is_audio
    return not is_video


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(
        _json_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
