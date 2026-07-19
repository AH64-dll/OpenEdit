"""Track-level effect operations: add_effect_to_track, list_track_effects."""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from lxml import etree

from ..errors import NotFoundError, validation_error
from ..io import ProjectTree
from ..tracks import get_tracks, is_audio_track
from ..validators import validate_effect_id


def add_effect_to_track(
    tree: ProjectTree,
    track_index: int,
    effect_id: str,
    params: Mapping[str, object] | None = None,
    *,
    catalog: Sequence[Mapping] | None = None,
) -> dict:
    """Add a Kdenlive effect to a track (not a clip).

    The effect is added as a <filter> child of the track's <tractor>.
    Video effects cannot be added to audio tracks and vice versa.
    """
    if catalog is None:
        catalog = []
    kid = validate_effect_id(effect_id, catalog)
    cat_entry = next(
        (e for e in catalog if e.get("kdenlive_id") == kid), None
    )
    if cat_entry is None:
        raise validation_error(
            f"effect_id_unknown: effect {effect_id!r} is not in the catalog",
        )
    tracks = get_tracks(tree)
    if track_index < 0 or track_index >= len(tracks):
        raise NotFoundError(
            f"track_index_out_of_range: track_index={track_index}, "
            f"track_count={len(tracks)}\n"
            f"fix: call get_timeline_summary to see valid track indices"
        )
    track_tractor = tracks[track_index]
    is_audio = is_audio_track(tree, track_tractor)
    effect_type = cat_entry.get("kdenlive_type", "video")
    if is_audio and effect_type != "audio":
        raise validation_error(
            f"effect_id_must_be_audio: effect {kid!r} is {effect_type!r} but "
            f"track {track_index} is an audio track\n"
            f"fix: pass an audio effect (kdenlive_type='audio'), or call "
            f"add_effect_to_track on a video track"
        )
    if not is_audio and effect_type != "video":
        raise validation_error(
            f"effect_id_must_be_video: effect {kid!r} is {effect_type!r} but "
            f"track {track_index} is a video track\n"
            f"fix: pass a video effect (kdenlive_type='video'), or call "
            f"add_effect_to_track on an audio track"
        )
    # Build the <filter> on the track's tractor (BUG 9 fix: colon, not snake)
    filt = etree.SubElement(track_tractor, "filter")
    mlt = etree.SubElement(filt, "property")
    mlt.set("name", "mlt_service")
    mlt.text = cat_entry.get("mlt_service", kid)
    kdenlive_label = etree.SubElement(filt, "property")
    kdenlive_label.set("name", "kdenlive:id")
    kdenlive_label.text = kid
    # Apply params or defaults
    effective_params: dict[str, object] = dict(params) if params else {}
    if not effective_params:
        for p in cat_entry.get("parameters", []):
            if "default" in p:
                effective_params[p["name"]] = p["default"]
    for k, v in effective_params.items():
        p = etree.SubElement(filt, "property")
        p.set("name", k)
        p.text = str(v)
    filters = list(track_tractor.findall("filter"))
    return {
        "track_index": track_index,
        "effect_index": len(filters) - 1,
        "effect_id": kid,
    }


def list_track_effects(tree: ProjectTree, track_index: int) -> dict:
    """Return the effect stack of `track_index`."""
    tracks = get_tracks(tree)
    if track_index < 0 or track_index >= len(tracks):
        raise NotFoundError(
            f"track_index_out_of_range: track_index={track_index}, "
            f"track_count={len(tracks)}\n"
            f"fix: call get_timeline_summary to see valid track indices"
        )
    track_tractor = tracks[track_index]
    filters = list(track_tractor.findall("filter"))
    effects = []
    for i, filt in enumerate(filters):
        effect_id = ""
        params: dict[str, str] = {}
        enabled = True
        for prop in filt.findall("property"):
            name = prop.get("name", "")
            if name == "kdenlive:id":
                effect_id = prop.text or ""
            elif name == "mlt_service":
                pass  # redundant with kdenlive:id
            elif name == "disable":
                enabled = (prop.text or "0") != "1"
            else:
                params[name] = prop.text or ""
        effects.append({
            "index": i,
            "effect_id": effect_id,
            "enabled": enabled,
            "params": params,
        })
    return {
        "track_index": track_index,
        "effects": effects,
    }


__all__ = ["add_effect_to_track", "list_track_effects"]
