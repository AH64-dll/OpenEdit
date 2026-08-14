"""Tests for the local Open Edit MCP adapters and project binding."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from open_edit.mcp.adapters import (
    HELPER_TOOL_NAMES,
    dispatch_mcp_tool,
    mcp_tool_schemas,
    result_to_json,
)
from open_edit.mcp.context import ProjectPathError, resolve_project_path
from open_edit.storage.edit_graph import EditGraphStore


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / ".open_edit").mkdir(parents=True)
    EditGraphStore(root / ".open_edit" / "edit_graph.db")
    return root


def test_resolve_project_path_requires_marker(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ProjectPathError, match="missing .open_edit"):
        resolve_project_path(empty)


def test_resolve_project_path_from_env(project: Path) -> None:
    resolved = resolve_project_path(None, env={"OPEN_EDIT_PROJECT": str(project)})
    assert resolved == project.resolve()


def test_resolve_project_path_missing() -> None:
    with pytest.raises(ProjectPathError, match="required"):
        resolve_project_path(None, env={})


def test_mcp_tool_schemas_include_pillars_and_helpers() -> None:
    names = {s["name"] for s in mcp_tool_schemas()}
    assert {
        "query_project",
        "edit_project",
        "run_script",
        "trigger_render",
        "get_render_job",
        "cancel_render_job",
    } <= names
    assert HELPER_TOOL_NAMES <= names
    # project_path must not appear in LLM-visible schemas
    for schema in mcp_tool_schemas():
        props = (schema.get("input_schema") or {}).get("properties") or {}
        assert "project_path" not in props


def test_result_to_json_stable() -> None:
    assert '"ok": true' in result_to_json({"ok": True, "a": 1})


@pytest.mark.asyncio
async def test_dispatch_query_injects_project_path(project: Path) -> None:
    seen: dict[str, Any] = {}

    def fake_execute(name, args, project_path, command_id=None):
        seen["name"] = name
        seen["args"] = args
        seen["project_path"] = project_path
        return {"ok": True, "assets": []}

    with patch("open_edit.mcp.adapters.execute_tool", side_effect=fake_execute):
        result = await dispatch_mcp_tool(
            "query_project",
            {"query": "list_assets", "params": {}},
            project,
        )
    assert result["ok"] is True
    assert seen["name"] == "query_project"
    assert seen["project_path"] == project
    assert "project_path" not in seen["args"]


@pytest.mark.asyncio
async def test_dispatch_invalid_query_args(project: Path) -> None:
    result = await dispatch_mcp_tool(
        "query_project",
        {"query": "not_a_real_query"},
        project,
    )
    assert result.get("ok") is False or "error" in result


@pytest.mark.asyncio
async def test_dispatch_unknown_tool(project: Path) -> None:
    result = await dispatch_mcp_tool("nope", {}, project)
    assert result["ok"] is False
    assert result["error_code"] == "unknown_tool"


@pytest.mark.asyncio
async def test_get_render_job_wrapper(project: Path) -> None:
    @dataclass(frozen=True)
    class FakeJob:
        job_id: str
        project_id: str
        mode: str
        status: str
        created_at: float
        updated_at: float
        output_path: str | None = None
        error: str | None = None
        result: dict | None = None
        graph_revision: int | None = None
        edit_graph_hash: str | None = None

    fake = FakeJob("abc", "proj", "proxy", "succeeded", 1.0, 2.0)
    mock_svc = MagicMock()
    mock_svc.get.return_value = fake

    with patch("open_edit.kernel.render_jobs.DEFAULT_RENDER_JOB_SERVICE", mock_svc):
        result = await dispatch_mcp_tool(
            "get_render_job", {"job_id": "abc"}, project,
        )
    assert result["ok"] is True
    assert result["job_id"] == "abc"
    mock_svc.get.assert_called_once_with(project, "abc")


@pytest.mark.asyncio
async def test_get_render_job_missing_id(project: Path) -> None:
    result = await dispatch_mcp_tool("get_render_job", {}, project)
    assert result["ok"] is False
    assert "job_id" in result.get("expected_keys", [])


@pytest.mark.asyncio
async def test_cancel_render_job_wrapper(project: Path) -> None:
    @dataclass(frozen=True)
    class FakeJob:
        job_id: str
        project_id: str
        mode: str
        status: str
        created_at: float
        updated_at: float
        output_path: str | None = None
        error: str | None = None
        result: dict | None = None
        graph_revision: int | None = None
        edit_graph_hash: str | None = None

    fake = FakeJob("xyz", "proj", "proxy", "cancelled", 1.0, 2.0)
    mock_svc = MagicMock()
    mock_svc.cancel = AsyncMock(return_value=fake)

    with patch("open_edit.kernel.render_jobs.DEFAULT_RENDER_JOB_SERVICE", mock_svc):
        result = await dispatch_mcp_tool(
            "cancel_render_job", {"job_id": "xyz"}, project,
        )
    assert result["ok"] is True
    assert result["status"] == "cancelled"
    mock_svc.cancel.assert_awaited_once_with(project, "xyz")


@pytest.mark.asyncio
async def test_trigger_render_routes_to_executor(project: Path) -> None:
    async def fake_render(args, project_path, command_id=None):
        assert project_path == project
        assert args.get("mode") == "proxy"
        return {"ok": True, "output_path": "/tmp/out.mp4", "render_id": "r1"}

    with patch(
        "open_edit.mcp.adapters.execute_trigger_render",
        side_effect=fake_render,
    ):
        result = await dispatch_mcp_tool(
            "trigger_render", {"mode": "proxy"}, project,
        )
    assert result["ok"] is True
    assert result["render_id"] == "r1"


def test_build_server_lists_tools(project: Path) -> None:
    mcp = pytest.importorskip("mcp")
    mcp_file = (getattr(mcp, "__file__", "") or "").replace("\\", "/")
    if mcp_file.endswith("open_edit/mcp/__init__.py") or "/open_edit/mcp/" in mcp_file:
        pytest.skip("MCP SDK shadowed by open_edit.mcp; fix editable install root")
    from open_edit.mcp.server import build_server

    server = build_server(project)
    assert server.name == "open-edit"
    assert server.instructions
    assert "query_project" in server.instructions


def test_harness_skills_loadable() -> None:
    from open_edit.mcp.skills import (
        load_skill,
        mcp_instructions,
        resource_uri,
        skills_dir,
        stem_from_uri,
    )

    root = skills_dir()
    assert root is not None
    playbook = load_skill("open-edit-mcp")
    assert "trigger_render" in playbook
    assert "silence_cuts" in playbook
    native = load_skill("hyperframes_native")
    assert "HTML/CSS/JavaScript" in native
    ref = load_skill("open-edit-mcp-reference")
    assert "add_clip" in ref
    assert "query_project" in mcp_instructions()
    assert "get_pending_notes" in mcp_instructions()
    assert "Skill: review-notes" in mcp_instructions()
    assert stem_from_uri(resource_uri("open-edit-mcp")) == "open-edit-mcp"
    assert load_skill("review-notes")
    assert "track_kind" in load_skill("review-notes")


def test_mcp_playbook_distinguishes_proxy_and_preview_chunks() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    text = (repo_root / "skills" / "open-edit-mcp.md").read_text(
        encoding="utf-8",
    )
    assert "`preview-chunks`" in text
    assert "whole-file" in text
    assert "audio" in text and "independent" in text
    assert "live MLT" in text and "M4" in text


def test_qc_skill_copies_document_render_policy() -> None:
    """Canonical and packaged QC guidance must expose the same policy."""
    repo_root = Path(__file__).resolve().parents[1]
    canonical_skill = (repo_root / "skills" / "qc-standards.md").read_text(
        encoding="utf-8",
    )
    harness_skill = (
        repo_root / "open_edit" / "harness_skills" / "qc-standards.md"
    ).read_text(encoding="utf-8")

    required_terms = (
        "mode=proxy",
        "source proxy",
        "preview chunks",
        "qc_report",
        "complete",
        "final export",
    )
    for term in required_terms:
        assert term in canonical_skill
        assert term in harness_skill
    assert canonical_skill == harness_skill


def test_packaged_harness_skills_match_repo() -> None:
    """Wheel-bundled copies must stay in sync with repo skills/."""
    from pathlib import Path

    # Flat layout: tests/ sits at the repo root next to open_edit/.
    pkg_root = Path(__file__).resolve().parents[1]
    repo_root = Path(__file__).resolve().parents[1]
    packaged = pkg_root / "open_edit" / "harness_skills"
    repo_skills = repo_root / "skills"
    for name in (
        "open-edit-mcp.md",
        "open-edit-mcp-reference.md",
        "style-memory.md",
        "tool_surface.md",
        "edit-planning.md",
        "hyperframes_native.md",
        "remotion_motion.md",
    ):
        pkg_file = packaged / name
        repo_file = repo_skills / name
        if not (pkg_file.is_file() and repo_file.is_file()):
            pytest.skip(f"missing {name} in repo or package")
        assert pkg_file.read_text(encoding="utf-8") == repo_file.read_text(
            encoding="utf-8"
        ), f"{name} drifted between skills/ and open_edit/harness_skills/"
