"""Transition operations: add_transition, remove_transition.

BUG 2 fix: transition timing uses BOTH a.out and b.in (the
boundary), not just a.out.

BUG 3 fix: cross-track transitions raise a ValidationError with
a `fix:` line that names the source track, so the caller knows
where to move the second clip.

BUG 10 fix: the transition is written to the tractor that OWNS
the playlist where the clips live (tracks[track_a]), not into
get_tractor() (which is the main sequence tractor).
"""
from __future__ import annotations

from lxml import etree

from ..errors import BackendError, NotFoundError, ValidationError, validation_error
from ..io import ProjectTree, _sec_to_tc, _tc_to_sec
from ..tracks import find_clip_entry, get_tracks, next_kdenlive_id
from ..validators import validate_transition_kind


def add_transition(
    tree: ProjectTree,
    *,
    clip_a_id: str,
    clip_b_id: str,
    kind: str = "dissolve",
    duration_sec: float = 1.0,
    catalog: list[dict] | None = None,
) -> str:
    """Add a same-track transition between two adjacent clips.

    Cross-track transitions are not supported in v1; raises
    ValidationError with a `fix:` hint naming the source track.

    Returns the kdenlive:id of the new transition.
    """
    if catalog is None:
        catalog = []
    kid = validate_transition_kind(kind, catalog)
    a, track_a = find_clip_entry(tree, clip_a_id)
    b, track_b = find_clip_entry(tree, clip_b_id)
    if track_a != track_b:
        raise validation_error(
            f"clips {clip_a_id} and {clip_b_id} are on different tracks; "
            f"transitions are per-track in v1",
            f"fix: call move_clip to put both clips on track {track_a}, "
            f"then add_transition",
        )
    tracks = get_tracks(tree)
    # BUG 10 fix: insert the transition into the tractor that
    # owns the playlist where the clips live (tracks[track_a]),
    # NOT into get_tractor() (the main sequence tractor).
    tractor = tracks[track_a]
    tr = etree.Element("transition")
    # BUG 2 fix: the cut point is the END of clip A on the timeline
    # (== the start of clip B on the timeline), i.e. a_out. Do NOT
    # average a_out with b's *source* in-point (which is 0 for a clip
    # that starts at its own head) — that produced a midpoint like 4.0
    # for two clips meeting at 8.0. Center the transition of
    # `duration_sec` on a_out so it straddles the real cut.
    a_out = _tc_to_sec(a.get("out", "00:00:00.000"))
    cut = a_out
    tr.set("in", _sec_to_tc(cut - duration_sec / 2.0))
    tr.set("out", _sec_to_tc(cut + duration_sec / 2.0))
    # Same-track transition: a_track == b_track == track_a.
    for name, val in (("a_track", str(track_a)), ("b_track", str(track_a))):
        p = etree.SubElement(tr, "property")
        p.set("name", name)
        p.text = val
    # Resolve the catalog entry for mlt_service.
    cat_entry = next(
        (e for e in catalog if e.get("kdenlive_id") == kid), {}
    )
    mlt = etree.SubElement(tr, "property")
    mlt.set("name", "mlt_service")
    mlt.text = cat_entry.get("mlt_service", kid)
    # Insert in the tractor AFTER the last <track> (Kdenlive's
    # convention; melt accepts the order loosely but this is
    # the order a real Kdenlive save produces).
    last_track_idx = -1
    for i, c in enumerate(tractor):
        if c.tag == "track":
            last_track_idx = i
    tractor.insert(last_track_idx + 1, tr)
    kid2 = next_kdenlive_id(tree)
    new_id = etree.SubElement(tr, "property")
    new_id.set("name", "kdenlive:id")
    new_id.text = kid2
    return kid2


def remove_transition(tree: ProjectTree, transition_id: str) -> dict:
    """Remove a transition by its kdenlive:id.

    The kdenlive:id lives in a child <property name="kdenlive:id">
    element (the same shape as every other kdenlive:id in the tree);
    it is NOT an attribute on the <transition> element. We must
    descend into the property children to find the target.

    On a successful match we also scan every <entry> for any
    <property name="kdenlive:transition"> whose text equals
    ``transition_id`` and record the bounded entry's own
    kdenlive:id into ``affected_clip_ids``. The current schema
    does not store per-entry transition references on clips
    produced by this codebase, so in practice this list is
    always empty; the field is reserved for future use when
    bounded-entry clearing is implemented. The clip entries
    themselves are not modified by this op.

    Args:
        tree: The open project tree.
        transition_id: The kdenlive:id of the transition to remove.

    Returns:
        A dict with:
          - ``transition_id``: the id that was removed.
          - ``affected_clip_ids``: list of clip ids that were
            bounded by this transition (currently always empty;
            see note above).

    Raises:
        NotFoundError: if no transition with the given id exists.
            The error message includes a ``fix:`` line instructing
            the caller to call ``get_timeline_summary`` and re-pick.
    """
    target = None
    affected_clip_ids: list[str] = []
    for t in tree.root.iter("transition"):
        kid_prop = t.find("property[@name='kdenlive:id']")
        if kid_prop is not None and kid_prop.text == transition_id:
            target = t
            for entry in tree.root.iter("entry"):
                tref = entry.find("property[@name='kdenlive:transition']")
                if tref is not None and tref.text == transition_id:
                    kid = entry.find("property[@name='kdenlive:id']")
                    if kid is not None and kid.text:
                        affected_clip_ids.append(kid.text)
            break
    if target is None:
        raise NotFoundError(
            f"transition_not_found: transition_id={transition_id!r}\n"
            f"fix: call get_timeline_summary and re-pick"
        )
    target.getparent().remove(target)
    return {
        "transition_id": transition_id,
        "affected_clip_ids": affected_clip_ids,
    }


__all__ = ["add_transition", "remove_transition", "set_transition_property"]


_RESERVED_PROP_NAMES = frozenset({"mlt_service", "id", "_childid", "kdenlive:id"})


def set_transition_property(
    tree: ProjectTree,
    transition_id: str,
    prop_name: str,
    value: str,
) -> dict:
    """Set any one property on a transition service.

    Reserved names (mlt_service, id, _childid, kdenlive:id) are rejected.
    All other prop names are accepted; integer coercion is applied
    for a_track/b_track and timecode validation for in/out.
    """
    if prop_name in _RESERVED_PROP_NAMES or prop_name.startswith("_"):
        raise validation_error(
            f"prop_not_allowed: prop_name={prop_name!r} is reserved\n"
            f"fix: pass a transition-specific property (e.g. 'in', 'out', "
            f"'a_track', 'b_track', 'geometry')",
        )
    # Find the transition by its kdenlive:id (stored in a child
    # <property name="kdenlive:id">, NOT an attribute).
    transition = None
    for t in tree.root.iter("transition"):
        kid_prop = t.find("property[@name='kdenlive:id']")
        if kid_prop is not None and kid_prop.text == transition_id:
            transition = t
            break
    if transition is None:
        raise NotFoundError(
            f"transition_not_found: no transition with id={transition_id!r}\n"
            f"fix: call get_timeline_summary to see valid transition ids"
        )
    # Find the existing prop (or none, if it's a new transition param).
    previous_value = None
    target_prop = None
    is_attribute = prop_name in ("in", "out")
    if is_attribute:
        # `in`/`out` are attributes on the <transition> element (the
        # same way add_transition sets them), not <property> children.
        previous_value = transition.get(prop_name)
    else:
        for prop in transition.findall("property"):
            if prop.get("name") == prop_name:
                target_prop = prop
                previous_value = prop.text
                break
    # Coerce the value: timing/track props as timecode/integer.
    if prop_name in ("a_track", "b_track"):
        try:
            coerced = str(int(value))
        except (TypeError, ValueError):
            raise validation_error(
                f"value_type_mismatch: a_track/b_track requires an integer, "
                f"got {value!r}\n"
                f"fix: pass an integer track index as a string",
            )
    elif prop_name in ("in", "out"):
        try:
            _tc_to_sec(value)
            coerced = value
        except (TypeError, ValueError):
            raise validation_error(
                f"value_type_mismatch: {prop_name} requires a timecode, "
                f"got {value!r}\n"
                f"fix: pass a timecode like '00:00:00.500'",
            )
    else:
        coerced = str(value)
    if is_attribute:
        transition.set(prop_name, coerced)
    elif target_prop is not None:
        target_prop.text = coerced
    else:
        p = etree.SubElement(transition, "property")
        p.set("name", prop_name)
        p.text = coerced
    return {
        "transition_id": transition_id,
        "prop_name": prop_name,
        "previous_value": previous_value,
        "new_value": coerced,
    }
