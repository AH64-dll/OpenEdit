"""Remotion composition renderer for Open Edit.

Materializes React Remotion compositions to media files that are then
ingested into the CAS and treated as normal MLT clips. Never shell-
interpolates props: they are always written to a JSON file.
"""
from __future__ import annotations

from open_edit.render.remotion.renderer import (
    RemotionRenderResult,
    RemotionRunner,
    render_composition,
    remotion_profile_for_mode,
)
from open_edit.render.remotion.safety import (
    REMOTION_VERSION,
    RemotionRenderError,
    composition_cache_key,
    composition_source_bundle,
    resolve_remotion_root,
    validate_entry_point,
)

__all__ = [
    "REMOTION_VERSION",
    "RemotionRenderError",
    "RemotionRenderResult",
    "RemotionRunner",
    "composition_cache_key",
    "composition_source_bundle",
    "render_composition",
    "remotion_profile_for_mode",
    "resolve_remotion_root",
    "validate_entry_point",
]
