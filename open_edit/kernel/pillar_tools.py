"""Dispatch functions for the 4 pillar tools.

These functions route through the single canonical table,
``open_edit.agent.tools.TOOL_TABLE``: each routing dict maps a pillar
sub-command (query / operation / generate kind) to one of the 26
table entries, so there is exactly one registry of callable tools.
Pillar names themselves (``query_project``, ``edit_project``) are NOT
in the table — they are dispatched by ``kernel.tool_executor``.

``apply_generated_ops`` is a pillar-only composite (commit a list of op
dicts from generate mode); it is not a callable tool, so it lives here
rather than in TOOL_TABLE.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from open_edit.agent.tools import TOOL_TABLE

# Sub-command → TOOL_TABLE name for the query (read-only) pillar mode.
_QUERY_ROUTING: dict[str, str] = {
    "list_assets": "list_assets",
    "get_pending_notes": "get_pending_notes",
    "get_style_profile": "get_style_profile",
    "analyze_narrative": "analyze_narrative",
    "search_assets": "search_assets",
    "get_transcript_packed": "get_transcript_packed",
    "get_silence_gaps": "get_silence_gaps",
    "get_timeline_view": "get_timeline_view",
    "get_authoring_view": "get_authoring_view",
    "get_graphics_view": "get_graphics_view",
}

# Sub-command → TOOL_TABLE name for the edit pillar mode. Includes the
# 4 re-exported edit tools plus the 7 timeline_ops functions.
_EDIT_ROUTING: dict[str, str] = {
    "add_marker": "add_marker",
    "set_pinned_value": "set_pinned_value",
    "capture_style_hint": "capture_style_hint",
    "import_asset": "import_asset",
    "ingest_local": "ingest_local",
    "add_clip": "add_clip",
    "add_hyperframes_overlay": "add_hyperframes_overlay",
    "trim_clip": "trim_clip",
    "replace_clip_source": "replace_clip_source",
    "change_clip_speed": "change_clip_speed",
    "remove_clip": "remove_clip",
    "set_audio_gain": "set_audio_gain",
    "apply_silence_gaps": "apply_silence_gaps",
    "auto_color_grade": "auto_color_grade",
    "apply_authoring_edit": "apply_authoring_edit",
    "commit_graphics": "commit_graphics",
    "rewrite_graphics_source": "rewrite_graphics_source",
    "retime_asset": "retime_asset",
}

# Generate kind → TOOL_TABLE name for the generate pillar mode.
_GENERATE_ROUTING: dict[str, str] = {
    "sfx": "place_sfx",
    "music": "select_music",
    "visual": "generate_visual_for_segment",
    "silence_cuts": "propose_silence_cuts",
    "remotion": "generate_remotion_composition",
    "init_remotion": "init_remotion_project",
    "write_remotion": "write_remotion_composition",
}


def _with_project_id(params: dict[str, Any], project_path: Path) -> dict[str, Any]:
    """Attach the graph's stable id to project-scoped pillar calls."""
    p = dict(params) if params else {}
    try:
        from open_edit.storage.edit_graph import EditGraphStore
        from open_edit.storage.paths import ProjectPaths

        db_path = ProjectPaths.for_project(project_path).db_path
        if db_path.exists():
            p["project_id"] = EditGraphStore(db_path).project_id
    except Exception:
        # The wrapped tool returns its normal structured error on failure.
        pass
    return p


def dispatch_query(query: str, params: dict[str, Any], project_path: Path) -> dict[str, Any]:
    """Dispatch a query to one of the 6 read-only tools."""
    if query == 'get_tracking_job':
        from open_edit.kernel.tracking_jobs import get_tracking_job
        try:
            return get_tracking_job(project_path, **params)
        except (TypeError, ValueError) as exc:
            return {'status': 'error', 'error': str(exc)}
    if query in ('get_studio', 'get_editing_context'):
        from open_edit.kernel.studio_service import get_editing_context, get_studio
        from open_edit.storage.edit_graph import GraphRevisionConflict
        try:
            return (get_studio if query == 'get_studio' else get_editing_context)(project_path, **params)
        except (TypeError, ValueError, GraphRevisionConflict) as exc:
            return {'status': 'error', 'error': str(exc)}
    if query == 'get_history':
        from open_edit.kernel.edit_graph_service import open_store
        return {'status': 'ok', **open_store(project_path).history()}
    fn = TOOL_TABLE[_QUERY_ROUTING[query]] if query in _QUERY_ROUTING else None
    if fn is None:
        return {"status": "error", "error": f"unknown query: {query!r}"}
    p = _with_project_id(params, project_path)
    return fn(p, str(project_path))


def dispatch_edit(operation: str, params: dict[str, Any], project_path: Path) -> dict[str, Any]:
    """Dispatch an edit operation to the corresponding tool."""
    if operation in ('start_tracking', 'cancel_tracking', 'apply_tracking_job', 'edit_object_track'):
        from open_edit.kernel.object_tracking import edit_object_track
        from open_edit.kernel.tracking_jobs import (
            apply_tracking_job,
            cancel_tracking,
            start_tracking,
        )
        from open_edit.storage.edit_graph import GraphRevisionConflict
        try:
            values = {k: v for k, v in params.items() if k != 'author'}
            functions = {'start_tracking': start_tracking, 'cancel_tracking': cancel_tracking,
                         'apply_tracking_job': apply_tracking_job, 'edit_object_track': edit_object_track}
            if operation != 'cancel_tracking':
                values['author'] = 'ai'
            return functions[operation](project_path, **values)
        except (TypeError, ValueError, GraphRevisionConflict) as exc:
            return {'status': 'error', 'error': str(exc)}
    if operation == 'revert_request':
        from open_edit.kernel.request_history import revert_request
        from open_edit.storage.edit_graph import GraphRevisionConflict
        try:
            return {'status': 'ok', **revert_request(project_path, **params)}
        except (TypeError, ValueError, GraphRevisionConflict) as exc:
            return {'status': 'error', 'error': str(exc)}
    if operation in ('apply_studio_changes', 'apply_graphics_edits'):
        from open_edit.kernel.studio_service import apply_graphics_edits, commit_studio
        from open_edit.storage.edit_graph import GraphRevisionConflict
        try:
            # The caller cannot disguise an AI write as a manual action.
            values = {k: v for k, v in params.items() if k != 'author'}
            allowed = ({'expected_revision', 'changes', 'ops', 'request_id', 'label'} if operation == 'apply_studio_changes'
                       else {'expected_revision', 'document_id', 'edits', 'request_id', 'label'})
            if values.keys() - allowed:
                raise ValueError('Unsupported studio change parameters')
            fn = commit_studio if operation == 'apply_studio_changes' else apply_graphics_edits
            return fn(project_path, **values, author='ai')
        except (TypeError, ValueError, GraphRevisionConflict) as exc:
            return {'status': 'error', 'error': str(exc)}
    if operation in ('undo', 'redo'):
        from open_edit.kernel.edit_graph_service import open_store
        from open_edit.storage.edit_graph import GraphRevisionConflict
        revision = params.get('expected_revision')
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            return {'status': 'error', 'error': 'expected_revision must be a nonnegative integer'}
        try:
            return {'status': 'ok', **open_store(project_path).history_step(operation, revision)}
        except (ValueError, GraphRevisionConflict) as exc:
            return {'status': 'error', 'error': str(exc)}
    if operation == "apply_generated_ops":
        return _apply_generated_ops(dict(params) if params else {}, project_path)
    fn = TOOL_TABLE[_EDIT_ROUTING[operation]] if operation in _EDIT_ROUTING else None
    if fn is None:
        return {"status": "error", "error": f"unknown operation: {operation!r}"}
    p = _with_project_id(params, project_path)
    return fn(p, str(project_path))


def _apply_generated_ops(params: dict[str, Any], project_path: Path) -> dict[str, Any]:
    """Commit a list of op dicts generated by the generate mode.

    Accepts the shapes the generate tools actually return: full IR op
    model dumps (``kind``-discriminated, e.g. ``AddEffectOp.model_dump()``
    from ``place_sfx`` / ``select_music``, ``AddClipOp.model_dump()`` from
    ``generate_visual_for_segment``). Each op is validated against the
    project's edit graph (reference integrity) and appended atomically.

    The legacy ``{"type": "add_marker", "params": {...}}`` shape is also
    accepted for back-compat.
    """
    add_marker = TOOL_TABLE["add_marker"]

    ops = params.get("ops", [])
    if not isinstance(ops, list):
        return {"status": "error", "error": "apply_generated_ops: ops must be a list"}
    if any(not isinstance(op, dict) for op in ops):
        return {"status": "error", "error": "apply_generated_ops: every op must be an object"}
    legacy = [op for op in ops if "type" in op and "kind" not in op]
    if legacy:
        if len(ops) != 1 or legacy[0].get("type") != "add_marker":
            return {"status": "error", "error": "legacy markers must be applied individually"}
        result = add_marker(_with_project_id(legacy[0].get("params", {}), project_path), str(project_path))
        return {"status": result.get("status", "error"), "results": [result]}
    from pydantic import TypeAdapter

    from open_edit.ir.types import OperationUnion
    from open_edit.storage.edit_graph import EditGraphStore
    from open_edit.storage.paths import ProjectPaths

    db = ProjectPaths.for_project(project_path).db_path
    if not db.exists():
        return {"status": "error", "error": "edit graph not found"}
    try:
        adapter = TypeAdapter(OperationUnion)
        models = [adapter.validate_python(op) for op in ops]
        sequences = EditGraphStore(db).append_many(models)
    except Exception as exc:
        return {"status": "error", "error": f"apply_generated_ops: {exc}"}
    return {
        "status": "ok",
        "results": [
            {"status": "ok", "kind": model.kind, "edit_id": model.edit_id, "sequence_num": seq}
            for model, seq in zip(models, sequences, strict=True)
        ],
    }


def dispatch_generate(kind: str, params: dict[str, Any], project_path: Path) -> dict[str, Any]:
    """Generate creative suggestions (SFX, music, visuals, Remotion, silence cuts)."""
    fn = TOOL_TABLE[_GENERATE_ROUTING[kind]] if kind in _GENERATE_ROUTING else None
    if fn is None:
        return {"status": "error", "error": f"unknown generate kind: {kind!r}"}
    p = _with_project_id(dict(params) if params else {}, project_path)
    return fn(p, str(project_path))
