"""Bin operations: import_media."""
from __future__ import annotations

from collections.abc import Sequence

from lxml import etree

from ..errors import BackendError
from ..io import ProjectTree
from ..validators import validate_source_path


def import_media(tree: ProjectTree, paths: Sequence[str]) -> list[str]:
    """Add media files to the project bin.

    Producers are added as children of the <mlt> root (NOT inside the
    main_bin playlist) — that's what Kdenlive's actual file format
    requires. They must also be inserted BEFORE any <playlist>,
    <tractor>, <transition>, or <filter> element so producers are
    defined before they are referenced.

    Returns the kdenlive:id of each imported producer (the value
    callers will pass as `source_id` to insert_clip/append_clip).
    """
    new_ids: list[str] = []
    for p in paths:
        abs_path = validate_source_path(p)
        # CRITICAL: producers must be children of the MLT root, not the
        # main_bin playlist. If they go inside main_bin, MLT silently
        # drops them (Property without a parent warnings) and the
        # timeline shows empty. Also, they must be defined BEFORE any
        # playlist/tractor references them. So we insert them before the
        # first playlist or tractor element.
        insert_idx = 0
        for idx, child in enumerate(tree.root):
            if child.tag in ("playlist", "tractor", "transition", "filter"):
                insert_idx = idx
                break
        else:
            insert_idx = len(tree.root)
        producer = etree.Element("producer")
        tree.root.insert(insert_idx, producer)
        producer.set("id", f"producer_{len(tree.root) - 1}")
        resource = etree.SubElement(producer, "property")
        resource.set("name", "resource")
        resource.text = str(abs_path)
        tree.ensure_kdenlive_properties_on_producer(producer, str(abs_path))
        # The new producer's kdenlive:id is what callers will use to
        # reference it as a `source_id` in insert_clip/append_clip.
        kid = next(
            (
                pp.text
                for pp in producer.iter("property")
                if pp.get("name") == "kdenlive:id"
            ),
            None,
        )
        if kid is None:
            raise BackendError(
                f"internal error: imported {abs_path} has no kdenlive:id"
            )
        new_ids.append(kid)
    return new_ids


__all__ = ["import_media"]
