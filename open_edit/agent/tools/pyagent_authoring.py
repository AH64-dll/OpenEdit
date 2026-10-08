"""Optional Diffusion authoring commands routed through existing MCP pillars."""
from open_edit.agent.tools._contract import tool_result
from open_edit.integrations.diffusion.authoring import (
    apply_authoring_edit as _apply,
)
from open_edit.integrations.diffusion.authoring import (
    get_authoring_view as _get,
)
from open_edit.storage.edit_graph import GraphRevisionConflict


def _check_keys(args, allowed):
    unknown = args.keys() - {*allowed, 'project_id'}
    if unknown:
        raise ValueError(f'Unknown authoring arguments: {sorted(unknown)}')


@tool_result
def get_authoring_view(args: dict, project_path: str) -> dict:
    _check_keys(args, {'include_source'})
    return _get(project_path, include_source=args.get('include_source', False))


@tool_result
def apply_authoring_edit(args: dict, project_path: str) -> dict:
    _check_keys(args, {'expected_revision', 'source', 'edits'})
    try:
        return _apply(project_path, expected_revision=args.get('expected_revision'), source=args.get('source'), edits=args.get('edits'))
    except GraphRevisionConflict as exc:
        return {'status': 'error', 'error_code': 'stale_revision', 'error': str(exc), 'expected_revision': exc.expected, 'graph_revision': exc.actual}


@tool_result
def get_graphics_view(args: dict, project_path: str) -> dict:
    from open_edit.integrations.diffusion.graphics import get_graphics_view as get

    _check_keys(args, {'clip_id', 'include_source'})
    return get(project_path, **{k: v for k, v in args.items() if k != 'project_id'})


@tool_result
def commit_graphics(args: dict, project_path: str) -> dict:
    from open_edit.integrations.diffusion.graphics import commit_graphics as commit

    _check_keys(args, {'job_id', 'expected_revision', 'clip_id', 'track_id', 'position_sec'})
    try:
        return commit(project_path, **{k: v for k, v in args.items() if k != 'project_id'})
    except GraphRevisionConflict as exc:
        return {'status': 'error', 'error_code': 'stale_revision', 'error': str(exc), 'graph_revision': exc.actual}


@tool_result
def rewrite_graphics_source(args: dict, project_path: str) -> dict:
    from open_edit.integrations.diffusion.graphics import rewrite_graphics_source as rewrite

    _check_keys(args, {'source', 'edits', 'expected_revision'})
    return rewrite(project_path, **{k: v for k, v in args.items() if k != 'project_id'})


@tool_result
def retime_asset(args: dict, project_path: str) -> dict:
    from open_edit.integrations.diffusion.timing import bake_timing

    _check_keys(args, {'asset_hash', 'source_in', 'source_out', 'playback_rate', 'segments', 'fps'})
    return bake_timing(project_path, **{k: v for k, v in args.items() if k != 'project_id'})
