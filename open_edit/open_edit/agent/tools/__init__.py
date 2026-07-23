"""New agent tools for Phase 4 Task 7.

This package is the home for the 5 new tools (run_python, get_style_profile,
set_pinned_value, get_pending_notes, add_marker). The 32 repointed wrappers
still live in `phase3_pyagent_core/tools/*.py`; this package is the canonical
home for the new ones.

The runtime's OP_TABLE dispatches by `(module_path, function_name)`, so each
wrapper is exposed by importing its function from this package.

v1.4 P1-1: also re-exports ``search_assets`` and ``import_asset`` so the
pi extension bridge can dispatch them via ``getattr(tools_mod, name)``.

v1.4 final review: the pi bridge advertises 13 tools in
``open_edit.serve.tool_schemas.TOOL_SCHEMAS`` and dispatches every name
via ``getattr(open_edit.agent.tools, name)`` (the virtual
``trigger_render`` is handled separately). Re-export every advertised
tool here so the LLM can actually call it; otherwise the bridge returns
``tool not found in open_edit.agent.tools: '<name>'``.
"""
from open_edit.agent.tools.pyagent_add_marker import add_marker
from open_edit.agent.tools.pyagent_analyze_narrative import analyze_narrative
from open_edit.agent.tools.pyagent_generate_visual_for_segment import (
    generate_visual_for_segment,
)
from open_edit.agent.tools.pyagent_get_pending_notes import get_pending_notes
from open_edit.agent.tools.pyagent_get_style_profile import get_style_profile
from open_edit.agent.tools.pyagent_import_asset import import_asset
from open_edit.agent.tools.pyagent_list_assets import list_assets
from open_edit.agent.tools.pyagent_place_sfx import place_sfx
from open_edit.agent.tools.pyagent_propose_silence_cuts import propose_silence_cuts
from open_edit.agent.tools.pyagent_run_python import run_python, run_script
from open_edit.agent.tools.pyagent_search_assets import search_assets
from open_edit.agent.tools.pyagent_select_music import select_music
from open_edit.agent.tools.pyagent_set_pinned_value import set_pinned_value

__all__ = [
    "add_marker",
    "analyze_narrative",
    "generate_visual_for_segment",
    "get_pending_notes",
    "get_style_profile",
    "import_asset",
    "list_assets",
    "place_sfx",
    "propose_silence_cuts",
    "run_python",
    "run_script",
    "search_assets",
    "select_music",
    "set_pinned_value",
]
