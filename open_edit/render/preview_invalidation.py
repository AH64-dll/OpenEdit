"""Frame-aligned geometry helpers for timeline preview chunks.

Chunk boundaries are expressed as integer project frames.  Seconds are only
materialized at the IR boundary because ``Timeline`` and its child models
currently expose seconds as their public representation.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from open_edit.ir.types import Clip, HtmlOverlay, RemotionComposition, Timeline, Track


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
