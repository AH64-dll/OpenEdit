"""Pure dispatch layer between the LLM tool-calls and Open Edit's IR.

This module is intentionally CLI-free. It is invoked by the thin
`__main__.py` shell and by tests. Responsibilities:

- Map op names to wrapper functions (the OP_TABLE).
- Dynamically import each wrapper module and call its function.
- Catch all errors and return them as `(code, response_dict)`
  tuples. Codes: 0 = success, 1 = validation error, 2 = fatal.
- Handle the special `list_catalog` op (not a wrapper).

Phase 4 Task 7: repointed from KdenliveFileBackend.* to open_edit.ir.api.*.
Names + JSON schemas of the 32 wrappers are unchanged; only their
bodies and the dispatch table changed.
"""
from __future__ import annotations

import importlib
import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Callable

from .tools import all_tools


def list_tools() -> list[dict]:
    """Return every tool's metadata as a JSON-serializable list of dicts.

    Each entry:
        name             "pyagent_xxx" (the pi-registered name)
        label            short human label
        description      full description (sent to the LLM)
        op               backend op name, or "" for tools that call
                         Phase 6 directly (render_qc tools)
        is_mutating      True if the op edits the project on disk
        parameters_schema  properties object only (NOT a full JSON
                           Schema document — that distinction is
                           critical, see the comment in tools/project.py)
        required         list of required parameter names; empty list
                           means every parameter is optional

    Consumed by `extension.ts` via a one-liner that imports this
    function and JSON-dumps the result. The TS side never hard-codes
    a tool's name, label, description, or schema; it iterates this
    list. This is what keeps the tool surface in one place.
    """
    return [
        {
            "name": t.name,
            "label": t.label,
            "description": t.description,
            "op": t.op,
            "is_mutating": t.is_mutating,
            "parameters_schema": t.parameters_schema,
            "required": list(t.required),
        }
        for t in all_tools()
    ]


# Op name (as called from TS) -> (module_path, function_name) pair.
# The dispatcher imports the module, then calls function(args, project_path).
# Each wrapper function returns a dict that becomes the runtime's `result`.
OP_TABLE: dict[str, tuple[str, str]] = {
    # --- Read-back tools (32 repointed wrappers) ---
    "pyagent_get_project_info": (
        "phase3_pyagent_core.tools.project", "get_project_info",
    ),
    "pyagent_get_timeline_summary": (
        "phase3_pyagent_core.tools.project", "get_timeline_summary",
    ),
    "pyagent_list_groups": (
        "phase3_pyagent_core.tools.groups", "list_groups",
    ),
    "pyagent_list_track_effects": (
        "phase3_pyagent_core.tools.track_effects", "list_track_effects",
    ),
    "pyagent_list_keyframes": (
        "phase3_pyagent_core.tools.keyframes", "list_keyframes",
    ),
    "pyagent_get_effect_param": (
        "phase3_pyagent_core.tools.effects", "get_effect_param",
    ),
    "pyagent_save_project": (
        "phase3_pyagent_core.tools.markers", "save_project",
    ),
    # --- Bin ---
    "pyagent_import_media": (
        "phase3_pyagent_core.tools.bin", "import_media",
    ),
    # --- Clips (5) ---
    "pyagent_insert_clip": (
        "phase3_pyagent_core.tools.clips", "insert_clip",
    ),
    "pyagent_append_clip": (
        "phase3_pyagent_core.tools.clips", "append_clip",
    ),
    "pyagent_move_clip": (
        "phase3_pyagent_core.tools.clips", "move_clip",
    ),
    "pyagent_trim_clip": (
        "phase3_pyagent_core.tools.clips", "trim_clip",
    ),
    "pyagent_delete_clip": (
        "phase3_pyagent_core.tools.clips", "delete_clip",
    ),
    # --- Clips edit (6) ---
    "pyagent_slip_clip": (
        "phase3_pyagent_core.tools.clips_edit", "slip_clip",
    ),
    "pyagent_ripple_delete_clip": (
        "phase3_pyagent_core.tools.clips_edit", "ripple_delete_clip",
    ),
    "pyagent_change_clip_speed": (
        "phase3_pyagent_core.tools.clips_edit", "change_clip_speed",
    ),
    "pyagent_split_clip": (
        "phase3_pyagent_core.tools.clips_edit", "split_clip",
    ),
    "pyagent_replace_clip_source": (
        "phase3_pyagent_core.tools.clips_edit", "replace_clip_source",
    ),
    "pyagent_set_clip_speed_ramp": (
        "phase3_pyagent_core.tools.clips_edit", "set_clip_speed_ramp",
    ),
    # --- Transitions (3) ---
    "pyagent_add_transition": (
        "phase3_pyagent_core.tools.transitions", "add_transition",
    ),
    "pyagent_remove_transition": (
        "phase3_pyagent_core.tools.transitions", "remove_transition",
    ),
    "pyagent_set_transition_property": (
        "phase3_pyagent_core.tools.transitions", "set_transition_property",
    ),
    # --- Effects (4) ---
    "pyagent_apply_effect": (
        "phase3_pyagent_core.tools.effects", "apply_effect",
    ),
    "pyagent_remove_effect": (
        "phase3_pyagent_core.tools.effects", "remove_effect",
    ),
    "pyagent_set_effect_param": (
        "phase3_pyagent_core.tools.effects", "set_effect_param",
    ),
    # --- Keyframes (3) ---
    "pyagent_set_keyframe": (
        "phase3_pyagent_core.tools.keyframes", "set_keyframe",
    ),
    "pyagent_remove_keyframe": (
        "phase3_pyagent_core.tools.keyframes", "remove_keyframe",
    ),
    # --- Track effects (2) ---
    "pyagent_add_effect_to_track": (
        "phase3_pyagent_core.tools.track_effects", "add_effect_to_track",
    ),
    # --- Groups (2 mutating) ---
    "pyagent_group_clips": (
        "phase3_pyagent_core.tools.groups", "group_clips",
    ),
    "pyagent_ungroup_clips": (
        "phase3_pyagent_core.tools.groups", "ungroup_clips",
    ),
    # --- Markers (special: writes to NotesStore) ---
    "pyagent_add_marker": (
        "open_edit.agent.tools.pyagent_add_marker", "add_marker",
    ),
    # --- 5 NEW tools (Phase 4 Task 7) ---
    "pyagent_run_python": (
        "open_edit.agent.tools.pyagent_run_python", "run_python",
    ),
    "pyagent_get_style_profile": (
        "open_edit.agent.tools.pyagent_get_style_profile", "get_style_profile",
    ),
    "pyagent_set_pinned_value": (
        "open_edit.agent.tools.pyagent_set_pinned_value", "set_pinned_value",
    ),
    "pyagent_get_pending_notes": (
        "open_edit.agent.tools.pyagent_get_pending_notes", "get_pending_notes",
    ),
    # `list_catalog` is handled specially (not in OP_TABLE).
}


_WRAPPER_CACHE: dict[str, Callable] = {}


def _resolve_wrapper(op: str) -> Callable:
    """Return the wrapper function for `op`, importing its module on first use."""
    if op in _WRAPPER_CACHE:
        return _WRAPPER_CACHE[op]
    if op not in OP_TABLE:
        raise KeyError(op)
    module_path, func_name = OP_TABLE[op]
    module = importlib.import_module(module_path)
    func = getattr(module, func_name)
    _WRAPPER_CACHE[op] = func
    return func


def _to_jsonable(obj: Any) -> Any:
    """Coerce dataclasses and other return types to JSON-safe dicts."""
    if is_dataclass(obj):
        return asdict(obj)
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    return obj


def emit(response: dict[str, Any]) -> None:
    """Write one JSON line to stdout, exactly one, no trailing whitespace."""
    sys.stdout.write(json.dumps(response, default=_to_jsonable) + "\n")
    sys.stdout.flush()


def _run_list_catalog(args: dict, project_path: str, catalog_path: str) -> tuple[int, dict]:
    """Look up effects/transitions/generators from the catalog JSON.

    Per phase1 design, the catalog is a JSON file in phase1_knowledge_base/.
    """
    catalog_json = Path(catalog_path)
    if not catalog_json.exists():
        return 2, {
            "ok": False, "fatal": True,
            "error": f"BackendError: catalog file not found at {catalog_path}",
        }
    try:
        raw = json.loads(catalog_json.read_text())
    except Exception as e:  # noqa: BLE001
        return 2, {"ok": False, "fatal": True, "error": f"BackendError: catalog unreadable: {e}"}

    kind = args.get("kind", "effects")
    if kind not in ("effects", "transitions", "generators"):
        return 1, {
            "ok": False,
            "error": f"invalid kind: {kind!r}",
        }
    items = raw.get(kind, [])
    if "filter" in args and args["filter"]:
        needle = str(args["filter"]).lower()
        items = [e for e in items if needle in e.get("name", "").lower()]
    return 0, {
        "ok": True,
        "result": [
            {
                "kdenlive_id": e.get("kdenlive_id"),
                "name": e.get("name"),
                "mlt_service": e.get("mlt_service"),
                "description": (e.get("description", "") or "").strip(),
            }
            for e in items
        ],
    }


def run_op(op: str, args: dict, project_path: str, catalog_path: str) -> tuple[int, dict]:
    """Run one wrapper function. Returns (exit_code, response_dict).

    exit_code: 0 = success, 1 = validation error (LLM self-corrects),
               2 = fatal error (project unreadable, op missing, etc.)
    """
    if op == "list_catalog" or op == "pyagent_list_catalog":
        return _run_list_catalog(args, project_path, catalog_path)

    if op not in OP_TABLE:
        return 2, {"ok": False, "fatal": True, "error": f"unknown op: {op!r}"}

    project = Path(project_path)
    if not project.exists():
        return 2, {
            "ok": False, "fatal": True,
            "error": f"BackendError: project path not found at {project_path}",
        }

    try:
        func = _resolve_wrapper(op)
    except KeyError:
        return 2, {"ok": False, "fatal": True, "error": f"unknown op: {op!r}"}
    except ImportError as e:
        return 2, {
            "ok": False, "fatal": True,
            "error": f"BackendError: wrapper module import failed: {e}",
        }

    try:
        result = func(args, project_path)
    except ValueError as e:
        return 1, {"ok": False, "error": str(e)}
    except KeyError as e:
        return 1, {"ok": False, "error": f"missing required arg: {e}"}
    except Exception as e:  # noqa: BLE001
        return 2, {
            "ok": False, "fatal": True,
            "error": f"BackendError: {type(e).__name__}: {e}",
        }

    if not isinstance(result, dict):
        result = {"result": result}
    return 0, {"ok": True, "result": result.get("result", result)}
