"""Shared editing tool registry.

TOOL_TABLE explicitly maps supported names to implementations. MCP pillar
routing and the optional built-in agent both dispatch through the kernel.
query_project, edit_project, trigger_render and render-job helpers are handled
by the kernel; run_script aliases the subprocess run_python implementation.
"""
from collections.abc import Callable

from open_edit.agent.tools.pyagent_add_marker import add_marker
from open_edit.agent.tools.pyagent_analyze_narrative import analyze_narrative
from open_edit.agent.tools.pyagent_authoring import apply_authoring_edit, get_authoring_view
from open_edit.agent.tools.pyagent_capture_style_hint import capture_style_hint
from open_edit.agent.tools.pyagent_generate_remotion_composition import (
    generate_remotion_composition,
)
from open_edit.agent.tools.pyagent_generate_visual_for_segment import (
    generate_visual_for_segment,
)
from open_edit.agent.tools.pyagent_get_pending_notes import get_pending_notes
from open_edit.agent.tools.pyagent_get_silence_gaps import get_silence_gaps
from open_edit.agent.tools.pyagent_get_style_profile import get_style_profile
from open_edit.agent.tools.pyagent_get_timeline_view import get_timeline_view
from open_edit.agent.tools.pyagent_get_transcript_packed import get_transcript_packed
from open_edit.agent.tools.pyagent_import_asset import import_asset
from open_edit.agent.tools.pyagent_ingest_local import ingest_local
from open_edit.agent.tools.pyagent_init_remotion_project import init_remotion_project
from open_edit.agent.tools.pyagent_list_assets import list_assets
from open_edit.agent.tools.pyagent_place_sfx import place_sfx
from open_edit.agent.tools.pyagent_propose_silence_cuts import propose_silence_cuts
from open_edit.agent.tools.pyagent_run_python import run_python, run_script
from open_edit.agent.tools.pyagent_search_assets import search_assets
from open_edit.agent.tools.pyagent_select_music import select_music
from open_edit.agent.tools.pyagent_set_pinned_value import set_pinned_value
from open_edit.agent.tools.pyagent_timeline_ops import (
    add_clip,
    add_hyperframes_overlay,
    apply_silence_gaps,
    auto_color_grade,
    change_clip_speed,
    remove_clip,
    replace_clip_source,
    set_audio_gain,
    trim_clip,
)
from open_edit.agent.tools.pyagent_write_remotion_composition import (
    write_remotion_composition,
)

__all__ = [
    "add_clip",
    "add_hyperframes_overlay",
    "add_marker",
    "analyze_narrative",
    "apply_authoring_edit",
    "apply_silence_gaps",
    "auto_color_grade",
    "capture_style_hint",
    "change_clip_speed",
    "generate_remotion_composition",
    "generate_visual_for_segment",
    "get_authoring_view",
    "get_pending_notes",
    "get_silence_gaps",
    "get_style_profile",
    "get_timeline_view",
    "get_transcript_packed",
    "import_asset",
    "ingest_local",
    "init_remotion_project",
    "list_assets",
    "place_sfx",
    "propose_silence_cuts",
    "remove_clip",
    "replace_clip_source",
    "run_python",
    "run_script",
    "search_assets",
    "select_music",
    "set_audio_gain",
    "set_pinned_value",
    "trim_clip",
    "write_remotion_composition",
]

TOOL_TABLE: dict[str, Callable] = {
    "apply_authoring_edit": apply_authoring_edit,
    "get_authoring_view": get_authoring_view,
    # 20 re-exported tool functions (pyagent_*.py modules).
    "add_marker": add_marker,
    "analyze_narrative": analyze_narrative,
    "capture_style_hint": capture_style_hint,
    "generate_remotion_composition": generate_remotion_composition,
    "generate_visual_for_segment": generate_visual_for_segment,
    "get_pending_notes": get_pending_notes,
    "get_silence_gaps": get_silence_gaps,
    "get_style_profile": get_style_profile,
    "get_transcript_packed": get_transcript_packed,
    "get_timeline_view": get_timeline_view,
    "import_asset": import_asset,
    "ingest_local": ingest_local,
    "init_remotion_project": init_remotion_project,
    "list_assets": list_assets,
    "place_sfx": place_sfx,
    "propose_silence_cuts": propose_silence_cuts,
    "run_python": run_python,
    "run_script": run_script,
    "search_assets": search_assets,
    "select_music": select_music,
    "set_pinned_value": set_pinned_value,
    "write_remotion_composition": write_remotion_composition,
    # pyagent_timeline_ops family (7 everyday clip ops).
    "add_clip": add_clip,
    "add_hyperframes_overlay": add_hyperframes_overlay,
    "trim_clip": trim_clip,
    "replace_clip_source": replace_clip_source,
    "change_clip_speed": change_clip_speed,
    "remove_clip": remove_clip,
    "set_audio_gain": set_audio_gain,
    "apply_silence_gaps": apply_silence_gaps,
    "auto_color_grade": auto_color_grade,
}

