"""Server-side tool-execution idempotency (Phase 1: data integrity).

A re-delivered tool call (network retry / WS reconnect) carries the same
LLM ``tool_use_id``. ``execute_tool`` dedupes on that ``command_id`` so a
previously successful call is short-circuited to its cached result rather
than re-applied.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from open_edit.serve.tool_executor import ToolNotFound, execute_tool  # noqa: E402
from open_edit.storage.edit_graph import EditGraphStore  # noqa: E402


@pytest.fixture
def project_path(tmp_path: Path) -> Path:
    EditGraphStore(tmp_path / ".open_edit" / "edit_graph.db")
    return tmp_path


def test_same_command_id_is_deduped(project_path: Path) -> None:
    r1 = execute_tool(
        "query_project", {"query": "list_assets", "params": {}},
        project_path, command_id="cmd-1",
    )
    r2 = execute_tool(
        "query_project", {"query": "list_assets", "params": {}},
        project_path, command_id="cmd-1",
    )
    assert r2 == r1

    store = EditGraphStore(project_path / ".open_edit" / "edit_graph.db")
    assert store.command_exists("cmd-1") is True
    assert store.get_command_status("cmd-1") == "done"


def test_different_command_id_not_falsely_deduped(project_path: Path) -> None:
    r1 = execute_tool(
        "query_project", {"query": "list_assets", "params": {}},
        project_path, command_id="cmd-1",
    )
    r2 = execute_tool(
        "query_project", {"query": "list_assets", "params": {}},
        project_path, command_id="cmd-2",
    )
    assert r1 == r2

    store = EditGraphStore(project_path / ".open_edit" / "edit_graph.db")
    assert store.command_exists("cmd-2") is True
    assert store.get_command_status("cmd-2") == "done"


def test_no_command_id_is_backward_compatible(project_path: Path) -> None:
    result = execute_tool(
        "query_project", {"query": "list_assets", "params": {}}, project_path,
    )
    assert result == {"assets": []}


def test_raising_tool_records_no_done_command(project_path: Path) -> None:
    with pytest.raises(ToolNotFound):
        execute_tool("no_such_tool", {}, project_path, command_id="cmd-bad")

    store = EditGraphStore(project_path / ".open_edit" / "edit_graph.db")
    assert store.get_command_status("cmd-bad") != "done"
