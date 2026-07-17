"""Project-state snapshot helpers.

Thin wrappers around Phase 3's runtime (`run_op`) that return plain dicts for
the chat UI's project-state panel. Any dataclass result from Phase 2/3 is
converted to a JSON-safe dict.
"""
from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from phase3_pyagent_core.__main__ import run_op  # noqa: E402

DEFAULT_CATALOG = _REPO_ROOT / "phase1_knowledge_base" / "catalog.json"


def _to_dict(obj: Any) -> Any:
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    return obj


def get_project_info(project: str, catalog: str | None = None) -> dict | None:
    """Return get_project_info() as a dict, or None if the project is missing."""
    if not Path(project).exists():
        return None
    code, resp = run_op(
        "get_project_info", {}, project, catalog or str(DEFAULT_CATALOG)
    )
    if not resp.get("ok"):
        return None
    return _to_dict(resp["result"])


def get_timeline_summary(project: str, catalog: str | None = None) -> dict | None:
    if not Path(project).exists():
        return None
    code, resp = run_op(
        "get_timeline_summary", {}, project, catalog or str(DEFAULT_CATALOG)
    )
    if not resp.get("ok"):
        return None
    return _to_dict(resp["result"])
