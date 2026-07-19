"""Effect operations: apply_effect, remove_effect.

BUG 5 fix: when `params` is None or empty, the catalog's
parameter `default` values are read and used as the params.

BUG 9 fix: the effect label property is `kdenlive:id` (with a
colon), NOT `kdenlive_id` (snake). The snake form is what the old
backend wrote; the colon form is what Kdenlive looks for when
re-opening a project to identify an effect filter.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from lxml import etree

from ..errors import CatalogError, NotFoundError
from ..io import ProjectTree
from ..tracks import find_clip_entry
from ..validators import validate_effect_id, validate_effect_params


def apply_effect(
    tree: ProjectTree,
    clip_id: str,
    effect_id: str,
    params: Mapping[str, object] | None = None,
    *,
    catalog: Sequence[Mapping] | None = None,
) -> str:
    """Apply an effect to a clip. Returns the canonical effect id.

    If `params` is None or empty, the catalog's parameter defaults
    are read and used (BUG 5 fix). The effect label is written as
    `kdenlive:id` (colon), not `kdenlive_id` (BUG 9 fix).
    """
    if catalog is None:
        catalog = []
    kid = validate_effect_id(effect_id, catalog)
    cat_entry = next(
        (e for e in catalog if e.get("kdenlive_id") == kid), None
    )
    if cat_entry is None:
        raise CatalogError(
            f"effect '{kid}' is in the catalog id-index but missing its entry"
        )
    entry, _ = find_clip_entry(tree, clip_id)
    filt = etree.SubElement(entry, "filter")
    mlt = etree.SubElement(filt, "property")
    mlt.set("name", "mlt_service")
    mlt.text = cat_entry.get("mlt_service", kid)
    # BUG 9 fix: use `kdenlive:id` (colon) so Kdenlive recognizes
    # this as a known effect when re-opening the project.
    kdenlive_label = etree.SubElement(filt, "property")
    kdenlive_label.set("name", "kdenlive:id")
    kdenlive_label.text = kid
    # BUG 5 fix: if no params were given, fall back to the
    # catalog's parameter defaults.
    effective_params: dict[str, object] = dict(params) if params else {}
    if not effective_params:
        for p in cat_entry.get("parameters", []):
            if "default" in p:
                effective_params[p["name"]] = p["default"]
    validated = validate_effect_params(cat_entry, effective_params)
    for k, v in validated.items():
        p = etree.SubElement(filt, "property")
        p.set("name", k)
        p.text = v
    return kid


def remove_effect(tree: ProjectTree, clip_id: str, effect_index: int) -> dict:
    """Remove the effect at `effect_index` from the clip's filter list.

    The clip's filter list is the chain of `<filter>` children of the
    clip's `<entry>` element (the same place `apply_effect` writes).
    Order is preserved; the entry at `effect_index` (0-based) is
    dropped. `effect_index` out of range raises NotFoundError with
    `effect_index_out_of_range` in the message.
    """
    from .clips_edit import _find_entry_for_clip
    track, entry, ti = _find_entry_for_clip(tree, clip_id)
    filters = list(entry.findall("filter"))
    if effect_index < 0 or effect_index >= len(filters):
        raise NotFoundError(
            f"effect_index_out_of_range: effect_index={effect_index}, "
            f"effect_count={len(filters)}\n"
            f"fix: call get_timeline_summary to see valid indices"
        )
    removed = filters[effect_index]
    removed_id = removed.get("id") or ""
    # Read the kdenlive:id from inside the filter (it's a child property,
    # not an attribute) so the caller can see what was removed.
    for prop in removed.findall("property"):
        if prop.get("name") == "kdenlive:id" and prop.text:
            removed_id = prop.text
            break
    entry.remove(removed)
    return {
        "clip_id": clip_id,
        "removed_effect_index": effect_index,
        "removed_effect_id": removed_id,
        "remaining_effect_count": len(filters) - 1,
    }


__all__ = ["apply_effect", "remove_effect"]
