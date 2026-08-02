"""Remotion composition renderer for Open Edit.

Materializes React Remotion compositions to media files that are then
ingested into the CAS and treated as normal MLT clips. Never shell-
interpolates props: they are always written to a JSON file.
"""
from __future__ import annotations

from open_edit.render.remotion.renderer import (
    ALPHA_POLICY_VERSION,
    RemotionRenderResult,
    RemotionRunner,
    probe_alpha_capability,
    render_composition,
    remotion_profile_for_mode,
    resolve_alpha_mode,
)
from open_edit.render.remotion.safety import (
    REMOTION_VERSION,
    RemotionRenderError,
    composition_cache_key,
    composition_source_bundle,
    referenced_file_fingerprints,
    render_reference_fingerprint,
    resolve_remotion_root,
    stage_referenced_assets,
    validate_entry_point,
)

__all__ = [
    "REMOTION_VERSION",
    "ALPHA_POLICY_VERSION",
    "RemotionRenderError",
    "RemotionRenderResult",
    "RemotionRunner",
    "composition_cache_key",
    "composition_source_bundle",
    "referenced_file_fingerprints",
    "render_reference_fingerprint",
    "probe_alpha_capability",
    "render_composition",
    "remotion_profile_for_mode",
    "resolve_alpha_mode",
    "resolve_remotion_root",
    "stage_referenced_assets",
    "validate_entry_point",
]
