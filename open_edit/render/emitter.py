"""Emit clean MLT XML from a Timeline state.

No Kdenlive namespaces. The IR (edit graph) is the source of truth; the
MLT XML is a render target.
"""
from __future__ import annotations

import math

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


def _amp_to_db(amplitude: float) -> float:
    """Convert a linear amplitude (0..1) to dBFS for MLT volume ``level``.

    MLT's volume filter interprets ``level`` in dBFS (0 dB = unity). A value
    of 0.0 amplitude maps to -80 dB (below 16-bit quantization noise) rather
    than 0 dB, which would have been a no-op.
    """
    if amplitude <= 0.0:
        return -80.0
    return 20.0 * math.log10(amplitude)


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
        "mlt_service": "volume",
    })
    # MLT >= 7.22 volume "level" is in dBFS (0 dB = unity) and keyframes are
    # serialized as an animated property string "frame=value; ..." (the legacy
    # <kf> element is not parsed by producer_xml and amplitude 0..1 values are
    # interpreted as dB, silently rendering the fade a no-op).
    level_parts = [
        f"{frame}={_amp_to_db(val):.1f}" for frame, val in deduped
    ]
    etree.SubElement(
        filter_el, "property", attrib={"name": "level"}
    ).text = ";".join(level_parts)


def _emit_filter(
    parent: etree._Element,
    effect: Effect,
    fps_num: int,
    fps_den: int,
) -> None:
    """Emit a regular Effect as an MLT <filter> element."""
    mlt_service = _mlt_service_name(effect.effect_type)
    filter_el = etree.SubElement(parent, "filter", attrib={
        "id": effect.effect_id,
        "service": mlt_service,
        "mlt_service": mlt_service,
    })
    prop_names = _catalog_property_names(effect.effect_type)
    for key, value in effect.params.items():
        if key == "service":
            continue
        prop = etree.SubElement(filter_el, "property", attrib={"name": prop_names.get(key, key)})
        if isinstance(value, bool):
            prop.text = "1" if value else "0"
        else:
            prop.text = str(value)
    for param, kfs in effect.keyframes.items():
        prop = etree.SubElement(
            filter_el, "property", attrib={"name": prop_names.get(param, param)}
        )
        parts: list[str] = []
        for time_sec, value, interp in kfs:
            marker = "!" if interp == "discrete" else ("~" if interp == "smooth" else "")
            parts.append(
                f"{marker}{_format_timecode(time_sec, fps_num, fps_den)}={value}"
            )
        prop.text = ";".join(parts)


def _catalog_spec(effect_type: str):
    """Load the catalog spec for an effect type, or None."""
    try:
        from open_edit.ir.catalog.loader import EffectCatalog
        from pathlib import Path

        catalog = EffectCatalog(Path(__file__).resolve().parent.parent / "ir" / "catalog")
        return catalog.get(effect_type)
    except Exception:
        return None


def _mlt_service_name(effect_type: str) -> str:
    """Resolve the MLT filter/transition service for an effect type.

    The catalog YAML declares the real MLT service (e.g. catalog effect
    ``contrast`` -> MLT service ``avfilter.eq``). Effect types without a
    catalog entry (e.g. raw ``transition_*`` or legacy effects) pass through
    unchanged.
    """
    spec = _catalog_spec(effect_type)
    if spec is not None and spec.mlt_service:
        return spec.mlt_service
    return effect_type


def _catalog_property_names(effect_type: str) -> dict[str, str]:
    """Map agent-facing effect param names to MLT filter property names.

    The YAML catalog (``ir/catalog/effects/*.yaml``) may declare an optional
    ``property`` per param (e.g. brightness ``value`` -> MLT ``level``).
    Unknown effect types and params pass through unchanged.
    """
    spec = _catalog_spec(effect_type)
    if spec is None:
        return {}
    out: dict[str, str] = {}
    for name, param in spec.params.items():
        out[name] = param.property or name
    return out


def _emit_transition(
    parent: etree._Element,
    effect: Effect,
) -> None:
    """Emit a transition Effect (effect_type starts with 'transition_') as an MLT <transition> element."""
    service_name = effect.effect_type[len("transition_"):]
    trans = etree.SubElement(parent, "transition", attrib={
        "id": effect.effect_id,
        "service": service_name,
        "mlt_service": service_name,
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
    *,
    hwaccel: bool = False,
) -> str:
    """Emit a Timeline as MLT XML.

    Pure function. Returns a complete MLT document string.

    The timeline is emitted in its supplied coordinate system.  A preview
    range should therefore be passed in after ``slice_timeline`` has rebased
    it to local frame zero; this function does not restore a project offset.

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
            # Must name the tractor: with multiple playlists, an absent
            # producer attribute makes melt pick the LAST playlist (an audio
            # track) as main_bin, rendering a white/static video.
            "producer": "tractor0",
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
        producer = etree.SubElement(root, "producer", attrib={
            "id": f"producer_{asset_hash}",
            "resource": resource,
        })
        if hwaccel:
            etree.SubElement(producer, "property", attrib={"name": "hwaccel"}).text = "cuda"
            etree.SubElement(producer, "property", attrib={"name": "hwaccel_device"}).text = "0"

    playlist_track_ids: list[str] = []
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

        if current_pos < timeline.duration_sec:
            trailing = timeline.duration_sec - current_pos
            etree.SubElement(playlist, "blank", attrib={
                "length": _format_timecode(trailing, fps_num, fps_den),
            })

        for effect in track.effects:
            if effect.effect_type.startswith("transition_"):
                _emit_transition(playlist, effect)
            else:
                _emit_filter(playlist, effect, fps_num, fps_den)

        playlist_track_ids.append(track.track_id)

    # The tractor must come AFTER the playlists: MLT's XML parser resolves
    # <track producer="..."> references at parse time, so a tractor emitted
    # first silently gets unresolved (empty) tracks.
    tractor = etree.SubElement(root, "tractor", attrib={
        "id": "tractor0",
        "out": _format_timecode(timeline.duration_sec, fps_num, fps_den),
    })

    multitrack = etree.SubElement(tractor, "multitrack")
    for track_id in playlist_track_ids:
        etree.SubElement(multitrack, "track", attrib={
            "producer": f"playlist_{track_id}",
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
