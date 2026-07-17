"""phase3_pyagent_core — the Python side of the pyagent pi extension.

Invoked as `python3 -m phase3_pyagent_core <op> --project <path> --catalog <path>
--args-json '<json>'`. Emits a single JSON line on stdout, exits with code
0 (success), 1 (validation error), or 2 (fatal error).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Make Phase 2 importable when this package is installed standalone.
# __main__.py lives at <project>/phase3_pyagent_core/__main__.py, so parents[1]
# is the project root where phase2_project_engine/ sits.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from phase2_project_engine import (  # noqa: E402
    Catalog,
    KdenliveFileBackend,
    ValidationError,
    BackendError,
)


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
    "apply_effect": "apply_effect",
    "add_marker": "add_marker",
    "save": "save",
    # "list_catalog" handled specially (not a backend op).
}

# Ops that mutate the project. The runtime auto-saves after any of these so
# subsequent subprocess calls see the change.
MUTATING_OPS: frozenset[str] = frozenset({
    "import_media", "insert_clip", "append_clip", "move_clip", "trim_clip",
    "delete_clip", "add_transition", "apply_effect", "add_marker", "save",
})


def _emit(response: dict[str, Any]) -> None:
    """Write one JSON line to stdout, exactly one, no trailing whitespace."""
    sys.stdout.write(json.dumps(response, default=_to_jsonable) + "\n")
    sys.stdout.flush()


def _to_jsonable(obj: Any) -> Any:
    """Coerce dataclasses and other Phase 2 return types to JSON-safe dicts."""
    if hasattr(obj, "__dataclass_fields__"):
        from dataclasses import asdict, is_dataclass
        return asdict(obj) if is_dataclass(obj) else obj.__dict__
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    return obj


def run_op(op: str, args: dict, project_path: str, catalog_path: str) -> tuple[int, dict]:
    """Run one backend op. Returns (exit_code, response_dict).

    exit_code: 0 = success, 1 = validation error (LLM self-corrects),
               2 = fatal error (project unreadable, op missing, etc.)
    """
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


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns the process exit code."""
    parser = argparse.ArgumentParser(
        prog="phase3_pyagent_core",
        description="Run one Phase 2 backend op, emit JSON result on stdout.",
    )
    parser.add_argument("op", help="The op name (e.g. 'append_clip')")
    parser.add_argument("--project", required=True, help="Path to the .kdenlive file")
    parser.add_argument("--catalog", required=True, help="Path to the catalog.json")
    parser.add_argument("--args-json", default="{}", help="JSON object of kwargs for the op")
    parsed = parser.parse_args(argv)

    try:
        args = json.loads(parsed.args_json)
    except json.JSONDecodeError as e:
        _emit({"ok": False, "fatal": True, "error": f"invalid --args-json: {e}"})
        return 2

    code, response = run_op(parsed.op, args, parsed.project, parsed.catalog)
    _emit(response)
    return code


if __name__ == "__main__":
    sys.exit(main())
