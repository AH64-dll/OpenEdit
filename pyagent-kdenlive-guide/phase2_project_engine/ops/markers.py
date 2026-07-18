"""Marker operations: add_marker."""
from __future__ import annotations

from lxml import etree

from ..errors import BackendError
from ..io import ProjectTree, _sec_to_tc
from ..validators import validate_marker_kind, validate_position_sec


_KIND_TO_TYPE = {"marker": "0", "guide": "1", "chapter": "2"}


def add_marker(
    tree: ProjectTree,
    position_sec: float,
    label: str,
    kind: str = "marker",
) -> None:
    """Add a marker/guide/chapter at the given timeline position.

    Markers live inside the main tractor in Kdenlive's file format,
    so the marker is appended to whatever tractor `tree.get_tractor()`
    returns.
    """
    validate_position_sec(position_sec)
    kind = validate_marker_kind(kind)
    tractor = tree.get_tractor()
    if tractor is None:
        raise BackendError("project has no tractor (cannot add markers)")
    m = etree.SubElement(tractor, "marker")
    t = etree.SubElement(m, "property")
    t.set("name", "time")
    t.text = _sec_to_tc(position_sec)
    c = etree.SubElement(m, "property")
    c.set("name", "comment")
    c.text = label
    ty = etree.SubElement(m, "property")
    ty.set("name", "type")
    ty.text = _KIND_TO_TYPE[kind]


__all__ = ["add_marker"]
