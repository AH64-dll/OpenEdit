"""Emit clean MLT XML from a Timeline state.

No Kdenlive namespaces. The IR (edit graph) is the source of truth; the
MLT XML is a render target.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field
from lxml import etree

from open_edit.ir.types import Effect, Timeline


class EmitterConfig(BaseModel):
    """Configuration for MLT XML emission."""

    profile: dict = Field(default_factory=lambda: {
        "width": 1920, "height": 1080,
        "frame_rate_num": 30, "frame_rate_den": 1,
    })
    project_meta: dict = Field(default_factory=dict)
    enable_audio_micro_fades: bool = True
    micro_fade_duration_sec: float = 0.030


def _format_timecode(seconds: float, fps_num: int, fps_den: int) -> str:
    """Convert seconds to MLT frame count (integer)."""
    return str(int(round(seconds * fps_num / fps_den)))


def _emit_audio_micro_fade(
    parent: etree._Element,
    clip_id: str,
    clip_dur_sec: float,
    fps_num: int,
    fps_den: int,
    micro_fade_dur_sec: float = 0.030,
) -> None:
    """Inject 30ms audio micro-fade-in and fade-out filter into clip entry.

    Resolves keyframe collisions cleanly so short clips (<60ms) and 1-frame clips
    are never muted and always contain peak volume (1.0).
    """
    fade_dur = micro_fade_dur_sec
    if clip_dur_sec < 0.060:
        fade_dur = clip_dur_sec / 2.0

    clip_end_frame = int(round(clip_dur_sec * fps_num / fps_den))

    if clip_end_frame == 0:
        # 1-frame clip: preserve full volume 1.0 (not muted)
        deduped = [(0, 1.0)]
    else:
        fade_in_end_frame = int(round(fade_dur * fps_num / fps_den))
        fade_out_start_frame = int(round((clip_dur_sec - fade_dur) * fps_num / fps_den))

        if fade_in_end_frame == 0:
            fade_in_end_frame = 1
        if fade_out_start_frame == 0:
            fade_out_start_frame = 1

        fade_in_end_frame = min(fade_in_end_frame, clip_end_frame)
        fade_out_start_frame = min(fade_out_start_frame, clip_end_frame)

        kf_dict: dict[int, float] = {}

        # 1. Start frame (0) is 0.0 for multi-frame clips
        kf_dict[0] = 0.0

        # 2. Fade peak frames set to 1.0 (peak volume takes priority)
        kf_dict[fade_in_end_frame] = 1.0
        kf_dict[fade_out_start_frame] = 1.0

        # 3. Clip end frame set to 0.0 ONLY if it occurs strictly after start (0) AND after all fade peak frames
        max_peak_frame = max(fade_in_end_frame, fade_out_start_frame)
        if clip_end_frame > 0 and clip_end_frame > max_peak_frame:
            kf_dict[clip_end_frame] = 0.0

        deduped = [(f, kf_dict[f]) for f in sorted(kf_dict.keys())]

    filter_el = etree.SubElement(parent, "filter", attrib={
        "id": f"microfade_{clip_id}",
        "service": "volume",
    })
    for frame, val in deduped:
        etree.SubElement(filter_el, "kf", attrib={
            "frame": str(frame),
            "value": str(val),
            "interp": "linear",
        })


def _emit_filter(
    parent: etree._Element,
    effect: Effect,
    fps_num: int,
    fps_den: int,
) -> None:
    """Emit a regular Effect as an MLT <filter> element."""
    filter_el = etree.SubElement(parent, "filter", attrib={
        "id": effect.effect_id,
        "service": effect.effect_type,
    })
    for key, value in effect.params.items():
        if key == "service":
            continue
        prop = etree.SubElement(filter_el, "property", attrib={"name": key})
        if isinstance(value, bool):
            prop.text = "1" if value else "0"
        else:
            prop.text = str(value)
    for param, kfs in effect.keyframes.items():
        for time_sec, value, interp in kfs:
            etree.SubElement(filter_el, "kf", attrib={
                "frame": _format_timecode(time_sec, fps_num, fps_den),
                "value": str(value),
                "interp": interp,
            })


def _emit_transition(
    parent: etree._Element,
    effect: Effect,
) -> None:
    """Emit a transition Effect (effect_type starts with 'transition_') as an MLT <transition> element."""
    service_name = effect.effect_type[len("transition_"):]
    trans = etree.SubElement(parent, "transition", attrib={
        "id": effect.effect_id,
        "service": service_name,
    })
    for key, value in effect.params.items():
        if key == "service":
            continue
        prop = etree.SubElement(trans, "property", attrib={"name": key})
        if isinstance(value, bool):
            prop.text = "1" if value else "0"
        else:
            prop.text = str(value)


def emit_timeline(
    timeline: Timeline,
    config: Optional[EmitterConfig] = None,
    asset_paths: Optional[dict[str, str]] = None,
) -> str:
    """Emit a Timeline as MLT XML.

    Pure function. Returns a complete MLT document string.

    The optional ``asset_paths`` parameter maps asset_hash -> filesystem
    path. When a clip's asset_hash is in this map, the corresponding
    producer's ``resource`` attribute uses the resolved path; otherwise it
    falls back to the asset_hash itself (so the orchestrator can do a
    later pass to substitute real paths).
    """
    if config is None:
        config = EmitterConfig()
    if asset_paths is None:
        asset_paths = {}

    fps_num = config.profile.get("frame_rate_num", 30)
    fps_den = config.profile.get("frame_rate_den", 1)
    width = config.profile.get("width", 1920)
    height = config.profile.get("height", 1080)

    root = etree.Element(
        "mlt",
        attrib={
            "LC_NUMERIC": "C",
            "version": "7.22.0",
        },
    )

    etree.SubElement(root, "profile", attrib={
        "width": str(width),
        "height": str(height),
        "frame_rate_num": str(fps_num),
        "frame_rate_den": str(fps_den),
        "progressive": "1",
        "sample_aspect_num": "1",
        "sample_aspect_den": "1",
        "display_aspect_num": str(width),
        "display_aspect_den": str(height),
        "colorspace": "709",
    })

    used_hashes: set[str] = set()
    for track in timeline.tracks:
        for clip in track.clips:
            used_hashes.add(clip.asset_hash)

    for asset_hash in sorted(used_hashes):
        resource = asset_paths.get(asset_hash, asset_hash)
        etree.SubElement(root, "producer", attrib={
            "id": f"producer_{asset_hash}",
            "resource": resource,
        })

    tractor = etree.SubElement(root, "tractor", attrib={
        "id": "tractor0",
        "out": _format_timecode(timeline.duration_sec, fps_num, fps_den),
    })

    multitrack = etree.SubElement(tractor, "multitrack")

    for track in timeline.tracks:
        playlist = etree.SubElement(root, "playlist", attrib={
            "id": f"playlist_{track.track_id}",
        })

        current_pos: float = 0.0
        for clip in track.clips:
            if clip.position_sec > current_pos:
                blank_dur = clip.position_sec - current_pos
                etree.SubElement(playlist, "blank", attrib={
                    "length": _format_timecode(blank_dur, fps_num, fps_den),
                })
            clip_dur = clip.out_point_sec - clip.in_point_sec
            entry = etree.SubElement(playlist, "entry", attrib={
                "producer": f"producer_{clip.asset_hash}",
                "in": _format_timecode(clip.in_point_sec, fps_num, fps_den),
                "out": _format_timecode(clip.out_point_sec, fps_num, fps_den),
            })
            if config.enable_audio_micro_fades:
                _emit_audio_micro_fade(
                    entry,
                    clip.clip_id,
                    clip_dur,
                    fps_num,
                    fps_den,
                    config.micro_fade_duration_sec,
                )
            for effect in clip.effects:
                if effect.effect_type.startswith("transition_"):
                    _emit_transition(entry, effect)
                else:
                    _emit_filter(entry, effect, fps_num, fps_den)
            current_pos = clip.position_sec + clip_dur

        for effect in track.effects:
            if effect.effect_type.startswith("transition_"):
                _emit_transition(playlist, effect)
            else:
                _emit_filter(playlist, effect, fps_num, fps_den)

        etree.SubElement(multitrack, "track", attrib={
            "producer": f"playlist_{track.track_id}",
        })

    # Composite higher video tracks over lower ones. Without this, melt's
    # multitrack can render blank/silent when more than one video track exists
    # (e.g. Remotion graphics on video_graphics over v1 talk footage).
    video_track_indices = [
        i for i, track in enumerate(timeline.tracks) if track.kind == "video"
    ]
    for upper in video_track_indices[1:]:
        lower = video_track_indices[0]
        trans = etree.SubElement(tractor, "transition", attrib={
            "id": f"composite_{lower}_{upper}",
            "service": "composite",
        })
        for name, value in (
            ("a_track", str(lower)),
            ("b_track", str(upper)),
            ("progressive", "1"),
            ("operator", "over"),
        ):
            prop = etree.SubElement(trans, "property", attrib={"name": name})
            prop.text = value

    xml_bytes = etree.tostring(
        root, pretty_print=True, xml_declaration=True, encoding="UTF-8",
    )
    return xml_bytes.decode("utf-8")
