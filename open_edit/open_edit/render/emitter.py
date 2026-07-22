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


def _format_timecode(seconds: float, fps_num: int, fps_den: int) -> str:
    """Convert seconds to MLT frame count (integer)."""
    return str(int(round(seconds * fps_num / fps_den)))


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
            for effect in clip.effects:
                if effect.effect_type.startswith("transition_"):
                    _emit_transition(entry, effect)
                else:
                    _emit_filter(entry, effect, fps_num, fps_den)
            current_pos = clip.position_sec + clip_dur

        etree.SubElement(multitrack, "track", attrib={
            "producer": f"playlist_{track.track_id}",
        })

    xml_bytes = etree.tostring(
        root, pretty_print=True, xml_declaration=True, encoding="UTF-8",
    )
    return xml_bytes.decode("utf-8")
