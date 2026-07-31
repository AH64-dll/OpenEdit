"""Agent tool registry.

This package is the canonical registry of agent tools. It re-exports 19
tool functions (``pyagent_*.py`` modules) plus the 7 ``pyagent_timeline_ops``
functions and exposes them all in a single explicit table:

``TOOL_TABLE: dict[str, Callable]`` maps every callable tool name to its
function (26 entries: 19 re-exported + 7 timeline ops). Kernel dispatch
(``open_edit.kernel.tool_executor._run_tool``) and pillar routing
(``open_edit.kernel.pillar_tools``) both consume this one table — there is
no longer any ``getattr(open_edit.agent.tools, name)`` lookup.

Not in TOOL_TABLE (kernel-handled, see ``kernel.tool_executor``):
- ``query_project`` / ``edit_project`` — pillar dispatchers
  (``kernel.pillar_tools.dispatch_query/dispatch_edit/dispatch_generate``);
- ``get_render_job`` / ``cancel_render_job`` — kernel render-service
  branches;
- ``trigger_render`` — virtual tool executed by
  ``kernel.tool_executor.execute_trigger_render``.

v1.4 P1-1: also re-exports ``search_assets`` and ``import_asset`` so the
pi extension bridge can dispatch them.

The pi bridge (``serve/pi_bridge.py``) routes the 4 pillar tools from
``open_edit.kernel.tool_schemas.TOOL_SCHEMAS`` (``query_project``,
``edit_project``, ``run_script``, ``trigger_render``) through
``kernel.tool_executor.execute_tool``, which owns schema validation,
pillar routing, and the ``TOOL_TABLE`` lookup; ``trigger_render`` goes
through the separate server-side ``execute_trigger_render`` path.
Unknown names raise ``ToolNotFound`` ("tool not found in
open_edit.agent.tools: '<name>'"). 3 of the 4 pillar tools are
deliberately NOT re-exported here — only ``run_script`` is (backed by
``pyagent_run_python``).
"""
from typing import Callable

from open_edit.agent.tools.pyagent_add_marker import add_marker
from open_edit.agent.tools.pyagent_analyze_narrative import analyze_narrative
from open_edit.agent.tools.pyagent_generate_remotion_composition import (
    generate_remotion_composition,
)
from open_edit.agent.tools.pyagent_generate_visual_for_segment import (
    generate_visual_for_segment,
)
from open_edit.agent.tools.pyagent_get_pending_notes import get_pending_notes
from open_edit.agent.tools.pyagent_get_style_profile import get_style_profile
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
    apply_silence_gaps,
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
    "add_marker",
    "analyze_narrative",
    "generate_remotion_composition",
    "generate_visual_for_segment",
    "get_pending_notes",
    "get_style_profile",
    "get_transcript_packed",
    "import_asset",
    "ingest_local",
    "init_remotion_project",
    "list_assets",
    "place_sfx",
    "propose_silence_cuts",
    "run_python",
    "run_script",
    "search_assets",
    "select_music",
    "set_pinned_value",
    "write_remotion_composition",
    "add_clip",
    "trim_clip",
    "replace_clip_source",
    "change_clip_speed",
    "remove_clip",
    "set_audio_gain",
    "apply_silence_gaps",
]

TOOL_TABLE: dict[str, Callable] = {
    # 19 re-exported tool functions (pyagent_*.py modules).
    "add_marker": add_marker,
    "analyze_narrative": analyze_narrative,
    "generate_remotion_composition": generate_remotion_composition,
    "generate_visual_for_segment": generate_visual_for_segment,
    "get_pending_notes": get_pending_notes,
    "get_style_profile": get_style_profile,
    "get_transcript_packed": get_transcript_packed,
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
    "trim_clip": trim_clip,
    "replace_clip_source": replace_clip_source,
    "change_clip_speed": change_clip_speed,
    "remove_clip": remove_clip,
    "set_audio_gain": set_audio_gain,
    "apply_silence_gaps": apply_silence_gaps,
}

