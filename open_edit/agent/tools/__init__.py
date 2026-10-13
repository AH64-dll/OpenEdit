"""Editing tools loaded on first use; optional engines do not slow startup."""
from collections.abc import Callable
from functools import cache
from importlib import import_module

# Compatibility names remain available for stored projects and existing clients.
_IMPLEMENTATIONS = {'add_clip': ('open_edit.agent.tools.pyagent_timeline_ops', 'add_clip'),
 'add_hyperframes_overlay': ('open_edit.agent.tools.pyagent_timeline_ops',
                             'add_hyperframes_overlay'),
 'add_marker': ('open_edit.agent.tools.pyagent_add_marker', 'add_marker'),
 'analyze_narrative': ('open_edit.agent.tools.pyagent_analyze_narrative', 'analyze_narrative'),
 'apply_authoring_edit': ('open_edit.agent.tools.pyagent_authoring', 'apply_authoring_edit'),
 'apply_silence_gaps': ('open_edit.agent.tools.pyagent_timeline_ops', 'apply_silence_gaps'),
 'auto_color_grade': ('open_edit.agent.tools.pyagent_timeline_ops', 'auto_color_grade'),
 'capture_style_hint': ('open_edit.agent.tools.pyagent_capture_style_hint', 'capture_style_hint'),
 'change_clip_speed': ('open_edit.agent.tools.pyagent_timeline_ops', 'change_clip_speed'),
 'commit_graphics': ('open_edit.agent.tools.pyagent_authoring', 'commit_graphics'),
 'generate_remotion_composition': ('open_edit.agent.tools.pyagent_generate_remotion_composition',
                                   'generate_remotion_composition'),
 'generate_visual_for_segment': ('open_edit.agent.tools.pyagent_generate_visual_for_segment',
                                 'generate_visual_for_segment'),
 'get_authoring_view': ('open_edit.agent.tools.pyagent_authoring', 'get_authoring_view'),
 'get_graphics_view': ('open_edit.agent.tools.pyagent_authoring', 'get_graphics_view'),
 'get_pending_notes': ('open_edit.agent.tools.pyagent_get_pending_notes', 'get_pending_notes'),
 'get_silence_gaps': ('open_edit.agent.tools.pyagent_get_silence_gaps', 'get_silence_gaps'),
 'get_style_profile': ('open_edit.agent.tools.pyagent_get_style_profile', 'get_style_profile'),
 'get_timeline_view': ('open_edit.agent.tools.pyagent_get_timeline_view', 'get_timeline_view'),
 'get_transcript_packed': ('open_edit.agent.tools.pyagent_get_transcript_packed',
                           'get_transcript_packed'),
 'import_asset': ('open_edit.agent.tools.pyagent_import_asset', 'import_asset'),
 'ingest_local': ('open_edit.agent.tools.pyagent_ingest_local', 'ingest_local'),
 'init_remotion_project': ('open_edit.agent.tools.pyagent_init_remotion_project',
                           'init_remotion_project'),
 'list_assets': ('open_edit.agent.tools.pyagent_list_assets', 'list_assets'),
 'place_sfx': ('open_edit.agent.tools.pyagent_place_sfx', 'place_sfx'),
 'propose_silence_cuts': ('open_edit.agent.tools.pyagent_propose_silence_cuts',
                          'propose_silence_cuts'),
 'remove_clip': ('open_edit.agent.tools.pyagent_timeline_ops', 'remove_clip'),
 'replace_clip_source': ('open_edit.agent.tools.pyagent_timeline_ops', 'replace_clip_source'),
 'retime_asset': ('open_edit.agent.tools.pyagent_authoring', 'retime_asset'),
 'rewrite_graphics_source': ('open_edit.agent.tools.pyagent_authoring', 'rewrite_graphics_source'),
 'run_python': ('open_edit.agent.tools.pyagent_run_python', 'run_python'),
 'run_script': ('open_edit.agent.tools.pyagent_run_python', 'run_script'),
 'search_assets': ('open_edit.agent.tools.pyagent_search_assets', 'search_assets'),
 'select_music': ('open_edit.agent.tools.pyagent_select_music', 'select_music'),
 'set_audio_gain': ('open_edit.agent.tools.pyagent_timeline_ops', 'set_audio_gain'),
 'set_pinned_value': ('open_edit.agent.tools.pyagent_set_pinned_value', 'set_pinned_value'),
 'trim_clip': ('open_edit.agent.tools.pyagent_timeline_ops', 'trim_clip'),
 'write_remotion_composition': ('open_edit.agent.tools.pyagent_write_remotion_composition',
                                'write_remotion_composition')}
__all__ = list(_IMPLEMENTATIONS)


@cache
def __getattr__(name: str) -> Callable:
    if name not in _IMPLEMENTATIONS:
        raise AttributeError(name)
    module, attribute = _IMPLEMENTATIONS[name]
    return getattr(import_module(module), attribute)


def _lazy_tool(name: str) -> Callable:
    def invoke(*args, **kwargs):
        return __getattr__(name)(*args, **kwargs)
    invoke.__name__ = name
    return invoke


TOOL_TABLE = {name: _lazy_tool(name) for name in _IMPLEMENTATIONS}
