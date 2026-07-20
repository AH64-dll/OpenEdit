"""Tests for ``open_edit.serve.pi_bridge``.

The bridge is the Python CLI that the pi extension calls for every
tool invocation. We test it end-to-end against a real project (created
with the real ``open_edit init`` + ``EditGraphStore`` + ``NotesStore``).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_THIS_DIR = Path(__file__).resolve()
_REPO_ROOT = _THIS_DIR.parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

PYTHON = sys.executable


def _run_bridge(*args: str) -> dict:
    """Run the bridge as a subprocess; return the parsed JSON result."""
    out = subprocess.run(
        [PYTHON, "-m", "open_edit.serve.pi_bridge", *args],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert out.returncode == 0, f"bridge crashed: stderr={out.stderr!r}"
    last = (out.stdout or "").strip().splitlines()[-1] if out.stdout else "{}"
    return json.loads(last) if last else {}


def _bootstrap_project(project_path: Path) -> None:
    """Create a real Open Edit project at ``project_path``."""
    project_path.mkdir(parents=True, exist_ok=True)
    # The easiest way: run `open_edit init` via subprocess.
    init = subprocess.run(
        ["open_edit", "init", str(project_path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if init.returncode != 0:
        # CLI may not be on PATH; fall back to direct storage setup.
        from open_edit.storage.edit_graph import EditGraphStore
        EditGraphStore(project_path / ".open_edit" / "edit_graph.db")


# ---------------------------------------------------------------------------

def test_bridge_list_tools():
    """--list-tools returns all 11 tool names."""
    res = _run_bridge("--list-tools")
    tools = res.get("tools", [])
    assert "add_marker" in tools
    assert "trigger_render" in tools
    assert "run_python" in tools
    assert len(tools) == 11


def test_bridge_invalid_args_returns_error():
    """Invalid JSON in --args → structured error (not a process crash)."""
    res = _run_bridge("--tool", "add_marker", "--project", "/tmp", "--args", "not-json")
    assert "error" in res
    assert "invalid --args JSON" in res["error"]


def test_bridge_unknown_tool_returns_error():
    """Unknown tool → structured error."""
    res = _run_bridge("--tool", "no_such_tool", "--project", "/tmp", "--args", "{}")
    assert "error" in res
    assert "no_such_tool" in res["error"]


def test_bridge_bad_project_returns_error(tmp_path):
    """Nonexistent project path → structured error."""
    res = _run_bridge(
        "--tool", "add_marker",
        "--project", str(tmp_path / "does-not-exist"),
        "--args", "{}",
    )
    assert "error" in res
    assert "project" in res["error"].lower()


def test_bridge_add_marker_round_trip(tmp_path):
    """Full add_marker + get_pending_notes roundtrip on a real project."""
    if not shutil.which("open_edit"):
        pytest.skip("open_edit CLI not on PATH; cannot bootstrap project")
    project_path = tmp_path / "myproj"
    _bootstrap_project(project_path)

    # Add a marker
    res_add = _run_bridge(
        "--tool", "add_marker",
        "--project", str(project_path),
        "--args", json.dumps({"t_start": 1.0, "t_end": 2.0, "text": "first"}),
    )
    assert res_add.get("status") == "ok"
    assert "note_id" in res_add

    # Read it back
    res_get = _run_bridge(
        "--tool", "get_pending_notes",
        "--project", str(project_path),
        "--args", "{}",
    )
    notes = res_get.get("notes", [])
    assert len(notes) == 1
    n = notes[0]
    assert n["text"] == "first"
    assert n["anchor"]["t_start"] == 1.0
    assert n["anchor"]["t_end"] == 2.0
    assert n["source"] == "agent"
    assert n["status"] == "pending"


def test_bridge_add_marker_without_project_id_in_args(tmp_path):
    """The bridge auto-injects project_id (from EditGraphStore) when
    the caller didn't provide it. This is the key compatibility fix
    for the pi extension."""
    if not shutil.which("open_edit"):
        pytest.skip("open_edit CLI not on PATH; cannot bootstrap project")
    project_path = tmp_path / "myproj"
    _bootstrap_project(project_path)

    # Note: no project_id in args — the bridge must inject it.
    res = _run_bridge(
        "--tool", "add_marker",
        "--project", str(project_path),
        "--args", json.dumps({"t_start": 5.0, "text": "injected-pid"}),
    )
    assert res.get("status") == "ok", res
    assert "note_id" in res
