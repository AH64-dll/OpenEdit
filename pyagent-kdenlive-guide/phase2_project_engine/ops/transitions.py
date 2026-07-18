"""Transition operations: add_transition.

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

from ..errors import BackendError, ValidationError, validation_error
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
    # BUG 2 fix: use BOTH a.out and b.in for the boundary
    # so the transition covers the cut symmetrically even when
    # a and b are not exactly adjacent.
    a_out = _tc_to_sec(a.get("out", "00:00:00.000"))
    b_in = _tc_to_sec(b.get("in", "00:00:00.000"))
    cut = (a_out + b_in) / 2.0
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


__all__ = ["add_transition"]
