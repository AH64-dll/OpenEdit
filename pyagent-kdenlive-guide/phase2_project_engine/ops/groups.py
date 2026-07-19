"""Group operations: create/dissolve/list clip groups using Kdenlive's
real groups format.

Storage: `kdenlive:sequenceproperties.groups` on the tractor, a
JSON-encoded string containing a JSON array of root group objects.
Each group is `{type: "Normal", pyagent:name: <name>, children: [...]}`.
Each leaf is `{type: "Leaf", leaf: "clip", data: "<track>:<pos>:-1"}`.

pyagent only creates `Normal` groups (Kdenlive manages `AVSplit` and
`Selection` itself). No runtime IDs are minted; `group_name` (enforced
unique) is the handle for ungroup/list.
"""
from __future__ import annotations

import json

from lxml import etree

from ..errors import NotFoundError, validation_error
from ..io import ProjectTree
_GROUPS_PROPERTY = "kdenlive:sequenceproperties.groups"


def _load_groups(tree: ProjectTree) -> list[dict]:
    """Load the existing groups array from the tractor, or [] if empty."""
    tractor = tree.get_tractor()
    if tractor is None:
        return []
    prop = tractor.find(f"property[@name='{_GROUPS_PROPERTY}']")
    if prop is None or not prop.text:
        return []
    return json.loads(prop.text)


def _save_groups(tree: ProjectTree, groups: list[dict]) -> None:
    """Save the groups array back to the tractor's property."""
    tractor = tree.get_tractor()
    if tractor is None:
        return
    prop = tractor.find(f"property[@name='{_GROUPS_PROPERTY}']")
    if prop is None:
        prop = etree.SubElement(tractor, "property")
        prop.set("name", _GROUPS_PROPERTY)
    prop.text = json.dumps(groups)


def _clip_position(tree: ProjectTree, clip_id: str) -> tuple[int, int, int]:
    """Return (track_pos, timeline_pos_ms, sublayer=-1) for a given clip_id.

    Walks each tractor -> multitrack -> track -> resolved playlist -> entries.
    `timeline_pos_ms` is the clip's start position in MILLISECONDS (int), matching
    the unit Kdenlive writes to its groups JSON. See citation below.
    `sublayer` is always -1 for clips (matches Kdenlive's Leaf format).

    Position unit: Kdenlive's groupsmodel.cpp::toJson(int gid) writes the
    leaf `data` as `f"{track}:{pos}:{sublayer}"` where `pos` comes from
    `TimelineItemModel::getItemPosition(gid)` (clip start position, in ms).
    See https://github.com/KDE/kdenlive/blob/master/src/timeline2/model/groupsmodel.cpp
    (toJson(int gid) method, ~line 720, and fromJson Leaf branch ~line 770
    which resolves (trackId, pos) -> clip_id via getClipByStartPosition).
    Our position is in ms to match Kdenlive's encoding.
    """
    from ..tracks import get_tracks, get_video_playlist
    from ._helpers import entry_start_sec
    for ti, track in enumerate(get_tracks(tree)):
        pl = get_video_playlist(tree, track)
        if pl is None:
            continue
        for entry in pl.iter("entry"):
            kid_prop = entry.find("property[@name='kdenlive:id']")
            if kid_prop is not None and kid_prop.text == clip_id:
                pos_sec = entry_start_sec(pl, entry)
                return (ti, int(pos_sec * 1000), -1)
    raise NotFoundError(
        f"clip_not_found: clip_id={clip_id!r}\n"
        f"fix: call get_timeline_summary and re-pick"
    )


def _resolve_clip_id_at(tree: ProjectTree, track_pos: int, timeline_pos_ms: int) -> list[str]:
    """Resolve (track_pos, timeline_pos_in_ms) -> current clip_id. Returns 0 or 1 id."""
    from ..tracks import get_tracks, get_video_playlist
    from ._helpers import entry_start_sec
    tracks = get_tracks(tree)
    if track_pos < 0 or track_pos >= len(tracks):
        return []
    pl = get_video_playlist(tree, tracks[track_pos])
    if pl is None:
        return []
    for entry in pl.iter("entry"):
        pos_sec = entry_start_sec(pl, entry)
        if int(pos_sec * 1000) == timeline_pos_ms:
            kid_prop = entry.find("property[@name='kdenlive:id']")
            if kid_prop is not None and kid_prop.text:
                return [kid_prop.text]
            return []
    return []


# --- Public ops ------------------------------------------------------------

def group_clips(tree: ProjectTree, clip_ids: list[str], group_name: str) -> dict:
    """Create a Normal group containing the given clip_ids.

    Each clip_id is resolved to (track_pos, timeline_pos_ms, -1) and stored
    as a Leaf child. group_name must be unique across all Normal groups in
    the project (duplicate -> ValidationError before any mutation).
    """
    if not clip_ids:
        raise validation_error(
            "empty_clip_list: clip_ids is empty",
            "pass at least one clip_id",
        )
    if not group_name:
        raise validation_error(
            "group_name_invalid: group_name is empty",
            "pass a non-empty group_name",
        )
    groups = _load_groups(tree)
    # Duplicate name check (before any mutation)
    for g in groups:
        if g.get("type") == "Normal" and g.get("pyagent:name") == group_name:
            raise validation_error(
                f"duplicate_group_name: group_name={group_name!r} already exists",
                "use a unique group_name; call list_groups to see existing names",
            )
    # Resolve each clip_id to (track, pos_ms, -1)
    leaves = []
    for cid in clip_ids:
        track_pos, timeline_pos_ms, sublayer = _clip_position(tree, cid)
        leaves.append({
            "type": "Leaf",
            "leaf": "clip",
            "data": f"{track_pos}:{timeline_pos_ms}:{sublayer}",
        })
    new_group = {
        "type": "Normal",
        "pyagent:name": group_name,
        "children": leaves,
    }
    groups.append(new_group)
    _save_groups(tree, groups)
    return {"group_name": group_name, "clip_ids": list(clip_ids)}


def ungroup_clips(tree: ProjectTree, group_name: str) -> dict:
    """Dissolve a group by name. AVSplit / other non-Normal groups are preserved."""
    groups = _load_groups(tree)
    new_groups = []
    dissolved_clip_ids: list[str] = []
    found = False
    for g in groups:
        if g.get("type") == "Normal" and g.get("pyagent:name") == group_name:
            found = True
            for child in g.get("children", []):
                if child.get("type") == "Leaf" and child.get("leaf") == "clip":
                    parts = child["data"].split(":")
                    track_pos = int(parts[0])
                    pos_ms = int(parts[1])
                    dissolved_clip_ids.extend(
                        _resolve_clip_id_at(tree, track_pos, pos_ms)
                    )
        else:
            new_groups.append(g)
    if not found:
        raise NotFoundError(
            f"group_not_found: group_name={group_name!r}\n"
            f"fix: call list_groups to see existing groups"
        )
    _save_groups(tree, new_groups)
    return {"dissolved_group_name": group_name, "affected_clip_ids": dissolved_clip_ids}


def list_groups(tree: ProjectTree) -> dict:
    """Return all Normal groups in the project. AVSplit groups are skipped
    (Kdenlive manages them; pyagent never creates or dissolves them)."""
    groups = _load_groups(tree)
    result = []
    for g in groups:
        if g.get("type") != "Normal":
            continue
        clip_ids: list[str] = []
        for child in g.get("children", []):
            if child.get("type") == "Leaf" and child.get("leaf") == "clip":
                parts = child["data"].split(":")
                track_pos = int(parts[0])
                pos_ms = int(parts[1])
                clip_ids.extend(_resolve_clip_id_at(tree, track_pos, pos_ms))
        result.append({
            "group_name": g.get("pyagent:name", ""),
            "clip_ids": clip_ids,
        })
    return {"groups": result}


__all__ = ["group_clips", "ungroup_clips", "list_groups"]
