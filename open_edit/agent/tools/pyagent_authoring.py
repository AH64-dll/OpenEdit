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
