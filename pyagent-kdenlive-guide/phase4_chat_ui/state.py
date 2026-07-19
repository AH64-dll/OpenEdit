"""Project-state snapshot helpers.

Thin wrappers around Phase 3's runtime (`run_op`) that return plain dicts for
the chat UI's project-state panel. Dataclass results from Phase 2/3 are
converted via `dataclasses.asdict` directly (no helper).
"""
from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from phase3_pyagent_core.__main__ import run_op  # noqa: E402

DEFAULT_CATALOG = _REPO_ROOT / "phase1_knowledge_base" / "catalog.json"


def _exists(path: str) -> bool:
    return Path(path).exists()


def get_project_info(project: str, catalog: str | None = None) -> dict | None:
    """Return get_project_info() as a dict, or None if the project is missing."""
    if not _exists(project):
        return None
    _code, resp = run_op("get_project_info", {}, project, catalog or str(DEFAULT_CATALOG))
    if not resp.get("ok") or resp.get("result") is None:
        return None
    return asdict(resp["result"])


def get_timeline_summary(project: str, catalog: str | None = None) -> dict | None:
    if not _exists(project):
        return None
    _code, resp = run_op("get_timeline_summary", {}, project, catalog or str(DEFAULT_CATALOG))
    if not resp.get("ok") or resp.get("result") is None:
        return None
    return asdict(resp["result"])
