"""Pure dispatch layer between the LLM tool-calls and the Phase 2 backend.

This module is intentionally CLI-free. It is invoked by the thin
`__main__.py` shell and by tests. Responsibilities:

- Map op names to backend methods (the OP_TABLE).
- Handle the special `list_catalog` op (not a backend method).
- Catch all backend errors and return them as `(code, response_dict)`
  tuples. Codes: 0 = success, 1 = validation error, 2 = fatal.
- Auto-save after any mutating op so subsequent subprocess calls see
  the change.

No I/O, no argparse, no `sys.exit`. The CLI wraps this.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from phase2_project_engine import (
    Catalog,
    KdenliveFileBackend,
    ValidationError,
    BackendError,
)


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
    list. This is what keeps the 19-tool surface in one place.
    """
    from .tools import all_tools
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


# Op name (as called from TS) -> backend method name.
# Filled in incrementally as each backend op is wired up.
OP_TABLE: dict[str, str] = {
    "get_project_info": "get_project_info",
    "get_timeline_summary": "get_timeline_summary",
    "import_media": "import_media",
    "insert_clip": "insert_clip",
    "append_clip": "append_clip",
    "move_clip": "move_clip",
    "trim_clip": "trim_clip",
    "delete_clip": "delete_clip",
    "add_transition": "add_transition",
    "remove_transition": "remove_transition",
    "apply_effect": "apply_effect",
    "remove_effect": "remove_effect",
    "add_marker": "add_marker",
    "slip_clip": "slip_clip",
    "ripple_delete_clip": "ripple_delete_clip",
    "change_clip_speed": "change_clip_speed",
    "split_clip": "split_clip",
    "replace_clip_source": "replace_clip_source",
    "save": "save",
    # "list_catalog" handled specially (not a backend op).
}

# Ops that mutate the project. The runtime auto-saves after any of these so
# subsequent subprocess calls see the change.
MUTATING_OPS: frozenset[str] = frozenset({
    "import_media", "insert_clip", "append_clip", "move_clip", "trim_clip",
    "delete_clip", "add_transition", "remove_transition", "apply_effect", "remove_effect", "add_marker",
    "slip_clip", "ripple_delete_clip", "change_clip_speed", "split_clip",
    "replace_clip_source", "save",
})

_ALLOWED_CATALOG_KINDS = ("effects", "transitions", "generators")


def _run_list_catalog(args: dict, catalog_path: str) -> tuple[int, dict]:
    try:
        cat = Catalog.from_json(catalog_path)
    except Exception as e:  # noqa: BLE001
        return 2, {"ok": False, "fatal": True, "error": f"BackendError: catalog unreadable: {e}"}

    kind = args.get("kind", "effects")
    if kind not in _ALLOWED_CATALOG_KINDS:
        return 1, {
            "ok": False,
            "error": (
                f"invalid kind: {kind!r}\n"
                f"fix: use one of {_ALLOWED_CATALOG_KINDS}"
            ),
        }

    # The catalog object has a by_id mapping; iterate it filtered by `kind`.
    # (The schema of the catalog is in phase1_knowledge_base/catalog.json;
    # each top-level key corresponds to a kind.)
    raw = json.loads(Path(catalog_path).read_text())
    items = raw.get(kind, [])
    if "filter" in args and args["filter"]:
        needle = str(args["filter"]).lower()
        items = [e for e in items if needle in e.get("name", "").lower()]
    # Project to a small dict per entry. The actual catalog schema (see
    # phase1_knowledge_base/catalog.json) uses `kdenlive_id` and `mlt_service`,
    # not `id` and `tag`. Project both so the LLM has what it needs.
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


def _to_jsonable(obj: Any) -> Any:
    """Coerce dataclasses and other Phase 2 return types to JSON-safe dicts."""
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


def run_op(op: str, args: dict, project_path: str, catalog_path: str) -> tuple[int, dict]:
    """Run one backend op. Returns (exit_code, response_dict).

    exit_code: 0 = success, 1 = validation error (LLM self-corrects),
               2 = fatal error (project unreadable, op missing, etc.)
    """
    if op == "list_catalog":
        return _run_list_catalog(args, catalog_path)

    if op not in OP_TABLE:
        return 2, {"ok": False, "fatal": True, "error": f"unknown op: {op!r}"}

    if not Path(project_path).exists():
        return 2, {
            "ok": False,
            "fatal": True,
            "error": f"BackendError: project file not found at {project_path}",
        }

    try:
        backend = KdenliveFileBackend(
            project_path=project_path,
            catalog=Catalog.from_json(catalog_path),
        )
        method = getattr(backend, OP_TABLE[op])
        result = method(**args)
        # Auto-save after any mutating op so subsequent subprocess calls
        # see the change. The `save` op is a no-op (already saved). Read-only
        # ops do not save (they do not mutate).
        if op in MUTATING_OPS or op == "save":
            backend.save()
        return 0, {"ok": True, "result": result}
    except ValidationError as e:
        return 1, {"ok": False, "error": str(e)}
    except BackendError as e:
        return 2, {"ok": False, "fatal": True, "error": f"BackendError: {e}"}
    except Exception as e:  # noqa: BLE001 — last-resort guard
        return 2, {"ok": False, "fatal": True, "error": f"Unexpected: {type(e).__name__}: {e}"}
