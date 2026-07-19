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


def get_effect_param(
    tree: ProjectTree,
    clip_id: str,
    effect_index: int,
    param_name: str,
    *,
    catalog: Sequence[Mapping] | None = None,
) -> dict:
    """Return the current value of `param_name` on effect `effect_index` of `clip_id`.

    For keyframable params, also returns the parsed list of keyframes and
    the on-disk format ("animated", "keyframe", "simplekeyframe", etc.).
    """
    from .clips_edit import _find_entry_for_clip
    from .._keyframes import is_keyframable_param, parse_animation_string

    if catalog is None:
        catalog = []
    track, entry, _ti = _find_entry_for_clip(tree, clip_id)
    filters = list(entry.findall("filter"))
    if effect_index < 0 or effect_index >= len(filters):
        raise NotFoundError(
            f"effect_index_out_of_range: effect_index={effect_index}, "
            f"effect_count={len(filters)}\n"
            f"fix: call get_timeline_summary to see valid indices"
        )
    filt = filters[effect_index]
    # Resolve effect_id from the kdenlive:id (colon) property
    effect_id = ""
    for prop in filt.findall("property"):
        if prop.get("name") == "kdenlive:id" and prop.text:
            effect_id = prop.text
            break
    # Find the requested param's value
    value = None
    for prop in filt.findall("property"):
        if prop.get("name") == param_name:
            value = prop.text or ""
            break
    if value is None:
        raise NotFoundError(
            f"param_not_found: effect '{effect_id}' (index {effect_index}) on "
            f"clip '{clip_id}' has no parameter named '{param_name}'\n"
            f"fix: call list_catalog to see valid parameter names for {effect_id}"
        )
    kf_status = is_keyframable_param(catalog, effect_id, param_name)
    is_kf = kf_status is True
    is_simplekf = kf_status == "simplekeyframe"
    if is_kf:
        kfs = parse_animation_string(value)
        keyframes = [{"frame": k.frame, "value": k.value, "type": k.type}
                     for k in kfs]
    elif is_simplekf:
        keyframes = []  # mlt_geometry not yet supported
    else:
        keyframes = None
    # Format string for the response
    fmt = ""
    if is_kf:
        # Look up the exact type= from catalog to report
        for entry_cat in catalog:
            if entry_cat.get("kdenlive_id") == effect_id:
                for p in entry_cat.get("parameters", []):
                    if p.get("name") == param_name:
                        fmt = p.get("type", "")
                        break
                break
    return {
        "clip_id": clip_id,
        "effect_index": effect_index,
        "effect_id": effect_id,
        "param_name": param_name,
        "value": value,
        "is_keyframable": is_kf,
        "format": fmt,
        "keyframes": keyframes,
    }


def set_effect_param(
    tree: ProjectTree,
    clip_id: str,
    effect_index: int,
    param_name: str,
    value: str,
    *,
    catalog: Sequence[Mapping] | None = None,
) -> dict:
    """Set `param_name` on effect `effect_index` of `clip_id` to a static `value`.

    WARNING: if the param is keyframable, this REPLACES the entire
    animation string with the static value. The response includes
    `is_keyframable` and `previous_value` so the caller can detect
    the case and decide to use set_keyframe instead.
    """
    from .clips_edit import _find_entry_for_clip
    from .._keyframes import is_keyframable_param, coerce_param_value
    from ..errors import validation_error

    if catalog is None:
        catalog = []
    track, entry, _ti = _find_entry_for_clip(tree, clip_id)
    filters = list(entry.findall("filter"))
    if effect_index < 0 or effect_index >= len(filters):
        raise NotFoundError(
            f"effect_index_out_of_range: effect_index={effect_index}, "
            f"effect_count={len(filters)}\n"
            f"fix: call get_timeline_summary to see valid indices"
        )
    filt = filters[effect_index]
    effect_id = ""
    for prop in filt.findall("property"):
        if prop.get("name") == "kdenlive:id" and prop.text:
            effect_id = prop.text
            break
    # Find current value
    current_value = None
    for prop in filt.findall("property"):
        if prop.get("name") == param_name:
            current_value = prop.text or ""
            break
    if current_value is None:
        raise NotFoundError(
            f"param_not_found: effect '{effect_id}' (index {effect_index}) on "
            f"clip '{clip_id}' has no parameter named '{param_name}'\n"
            f"fix: call list_catalog to see valid parameter names for {effect_id}"
        )
    # Coerce the new value to the catalog's type (if specified)
    cat_entry = None
    for e in catalog:
        if e.get("kdenlive_id") == effect_id:
            cat_entry = e
            break
    cat_param = None
    if cat_entry:
        for p in cat_entry.get("parameters", []):
            if p.get("name") == param_name:
                cat_param = p
                break
    if cat_param is not None:
        param_type = cat_param.get("type", "constant")
        try:
            coerced = coerce_param_value(param_type, value)
        except ValueError as e:
            raise validation_error(
                f"value_type_mismatch: cannot coerce {value!r} to "
                f"param type {param_type!r} for {effect_id}.{param_name}: {e}\n"
                f"fix: pass a value that parses as {param_type}",
            )
    else:
        coerced = str(value)
    # Find or create the property element and update its text
    found_prop = None
    for prop in filt.findall("property"):
        if prop.get("name") == param_name:
            found_prop = prop
            break
    if found_prop is not None:
        found_prop.text = coerced
    else:
        p = etree.SubElement(filt, "property")
        p.set("name", param_name)
        p.text = coerced
    kf_status = is_keyframable_param(catalog, effect_id, param_name)
    return {
        "clip_id": clip_id,
        "effect_index": effect_index,
        "param_name": param_name,
        "previous_value": current_value,
        "new_value": coerced,
        "is_keyframable": kf_status is True,
    }


__all__ = ["apply_effect", "get_effect_param", "remove_effect", "set_effect_param"]
