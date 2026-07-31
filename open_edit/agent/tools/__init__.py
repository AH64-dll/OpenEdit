"""Agent tool registry.

This package is the canonical registry of agent tools. It re-exports 19
tool functions (``pyagent_*.py`` modules) so agent hosts and the pi
extension bridge can dispatch them via ``getattr(open_edit.agent.tools,
name)``.

``pyagent_timeline_ops`` is NOT re-exported here: its query/edit/generate
functions are dispatched by ``open_edit.kernel.pillar_tools`` instead.

v1.4 P1-1: also re-exports ``search_assets`` and ``import_asset`` so the
pi extension bridge can dispatch them via ``getattr(tools_mod, name)``.

v1.4 final review: the pi bridge advertises 13 tools in
``open_edit.kernel.tool_schemas.TOOL_SCHEMAS`` and dispatches every name
via ``getattr(open_edit.agent.tools, name)`` (the virtual
``trigger_render`` is handled separately). Re-export every advertised
tool here so the LLM can actually call it; otherwise the bridge returns
``tool not found in open_edit.agent.tools: '<name>'``.
"""
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
]

