"""Tests for ``open_edit.serve.pi_bridge``.

The bridge is the Python CLI that the pi extension calls for every
tool invocation. We test it end-to-end against a real project (created
with the real ``open_edit init`` + ``EditGraphStore`` + ``NotesStore``).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

_THIS_DIR = Path(__file__).resolve()
_REPO_ROOT = _THIS_DIR.parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

PYTHON = sys.executable
# The venv's .pth file points at the *main* checkout
# (``/home/ah64/apps/mlt-pipeline/open_edit``), not the worktree. The
# bridge subprocess therefore imports the main repo's ``open_edit``
# package by default. We prepend the worktree's package root to
# ``PYTHONPATH`` for every bridge subprocess so worktree changes (new
# tools, new schemas) are visible to the test.
# ``_REPO_ROOT`` is the parent of the ``open_edit/`` package directory
# (i.e. the dir that contains ``open_edit/__init__.py``).
_WORKTREE_PKG = str(_REPO_ROOT)


def _bridge_env() -> dict:
    env = os.environ.copy()
    pp = env.get("PYTHONPATH", "")
    if _WORKTREE_PKG not in pp.split(os.pathsep):
        env["PYTHONPATH"] = (
            _WORKTREE_PKG + (os.pathsep + pp if pp else "")
        )
    return env


def _run_bridge(*args: str) -> dict:
    """Run the bridge as a subprocess; return the parsed JSON result."""
    out = subprocess.run(
        [PYTHON, "-m", "open_edit.serve.pi_bridge", *args],
        capture_output=True,
        text=True,
        timeout=60,
        env=_bridge_env(),
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
    """--list-tools returns all 13 tool names (10 real + 2 P1-1 + 1 virtual)."""
    res = _run_bridge("--list-tools")
    tools = res.get("tools", [])
    assert "add_marker" in tools
    assert "trigger_render" in tools
    assert "run_python" in tools
    assert "search_assets" in tools
    assert "import_asset" in tools
    assert len(tools) == 13


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


# ---------------------------------------------------------------------------
# v1.4 P1-1: search_assets + import_asset wiring through the bridge.
#
# The bridge must:
# - list both new tool names via ``--list-tools`` (so the TS extension
#   registers them);
# - dispatch search_assets even when ``project_id`` is NOT in args
#   (the tool is project-agnostic — the auto-inject still happens
#   but the tool doesn't use it);
# - dispatch import_asset and write the asset to the project's CAS
#   with the right license/attribution metadata;
# - gracefully degrade when the relevant API key is missing.
# ---------------------------------------------------------------------------

def test_bridge_list_tools_includes_new_tool_names():
    """After the v1.4 P1-1 additions, ``--list-tools`` must include
    ``search_assets`` and ``import_asset`` so the TS extension picks
    them up automatically."""
    res = _run_bridge("--list-tools")
    tools = res.get("tools", [])
    assert "search_assets" in tools
    assert "import_asset" in tools
    # The count grows from 11 (P1-2 baseline) to 13.
    assert len(tools) == 13, tools


def test_bridge_search_assets_missing_key_returns_structured_error(tmp_path):
    """search_assets without the Pexels key must return a structured
    error (not a process crash), so the LLM can read the cause and
    the UI can surface it."""
    # Make sure no key is set in the subprocess env.
    env = _bridge_env()
    for k in ("OPEN_EDIT_PEXELS_API_KEY", "OPEN_EDIT_FREESOUND_API_KEY"):
        env.pop(k, None)
    out = subprocess.run(
        [PYTHON, "-m", "open_edit.serve.pi_bridge",
         "--tool", "search_assets",
         "--project", str(tmp_path),
         "--args", json.dumps({"query": "rain", "kind": "video", "limit": 3})],
        capture_output=True, text=True, timeout=60, env=env,
    )
    assert out.returncode == 0, f"bridge crashed: stderr={out.stderr!r}"
    last = (out.stdout or "").strip().splitlines()[-1] if out.stdout else "{}"
    res = json.loads(last) if last else {}
    assert "error" in res
    assert "OPEN_EDIT_PEXELS_API_KEY" in res["error"]
    assert "results" in res
    assert res["results"] == []


def test_bridge_search_assets_rejects_invalid_kind(tmp_path):
    """A bad ``kind`` is rejected up front, no HTTP call made."""
    res = _run_bridge(
        "--tool", "search_assets",
        "--project", str(tmp_path),
        "--args", json.dumps({"query": "x", "kind": "storyboard", "limit": 1}),
    )
    assert "error" in res
    assert "kind" in res["error"]


def test_bridge_search_assets_rejects_missing_query(tmp_path):
    """Empty ``query`` is rejected up front — don't waste an API call."""
    res = _run_bridge(
        "--tool", "search_assets",
        "--project", str(tmp_path),
        "--args", json.dumps({"query": "", "kind": "video", "limit": 3}),
    )
    assert "error" in res
    assert "query" in res["error"]


def test_bridge_search_assets_dispatches_with_mocked_http(
    tmp_path, monkeypatch,
):
    """End-to-end through the bridge, with the HTTP layer mocked. The
    tool must return a normalised list shape that the TS extension /
    frontend can render.

    We can't monkeypatch the subprocess (the bridge is a separate
    process), so this test calls the tool directly through the
    module-level function (which is what the bridge does). The bridge
    subprocess tests above pin the bridge plumbing; the unit tests in
    ``test_pyagent_search_assets.py`` pin the dispatch shape; this
    test pins the full path through ``open_edit.agent.tools`` so any
    future refactor that breaks the public API gets caught.
    """
    from open_edit.agent.tools import pyagent_search_assets
    fake = {
        "videos": [
            {
                "id": 1,
                "url": "https://pexels.com/video/1/",
                "duration": 5,
                "image": "https://i.pexels.com/1.jpg",
                "video_files": [
                    {
                        "id": 10, "quality": "hd",
                        "file_type": "video/mp4",
                        "link": "https://v.pexels.com/1-hd.mp4",
                    },
                ],
            },
        ],
    }
    monkeypatch.setattr(
        pyagent_search_assets, "_http_get_json", lambda *a, **kw: fake,
    )
    monkeypatch.setattr(
        pyagent_search_assets, "_pexels_api_key", lambda: "test-key",
    )
    res = pyagent_search_assets.search_assets(
        {"query": "ocean", "kind": "video", "limit": 3}, str(tmp_path),
    )
    assert "error" not in res, res
    assert res["source"] == "pexels"
    assert len(res["results"]) == 1
    r0 = res["results"][0]
    assert r0["kind"] == "video"
    assert r0["preview_url"].endswith("1-hd.mp4")


def test_bridge_import_asset_rejects_non_https_url(tmp_path):
    """The import tool requires HTTPS."""
    res = _run_bridge(
        "--tool", "import_asset",
        "--project", str(tmp_path),
        "--args", json.dumps({"source_url": "http://example.com/x.mp4"}),
    )
    assert "error" in res
    assert "https" in res["error"].lower()


def test_bridge_import_asset_requires_result_id_or_source_url(tmp_path):
    """If neither is provided, the tool must reject up front."""
    res = _run_bridge(
        "--tool", "import_asset",
        "--project", str(tmp_path),
        "--args", json.dumps({}),
    )
    assert "error" in res
    assert "result_id" in res["error"] or "source_url" in res["error"]


def test_bridge_import_asset_download_failure_returns_error(tmp_path, monkeypatch):
    """A 404 during the download is surfaced as a structured error."""
    if not shutil.which("open_edit"):
        pytest.skip("open_edit CLI not on PATH; cannot bootstrap project")
    project_path = tmp_path / "myproj"
    _bootstrap_project(project_path)

    from open_edit.agent.tools import pyagent_import_asset
    monkeypatch.setattr(
        pyagent_import_asset, "_http_download",
        mock.MagicMock(side_effect=RuntimeError("upstream 404: not found")),
    )
    res = _run_bridge(
        "--tool", "import_asset",
        "--project", str(project_path),
        "--args", json.dumps({"source_url": "https://example.com/missing.mp4"}),
    )
    assert "error" in res
    assert "404" in res["error"] or "not found" in res["error"].lower()


# ---------------------------------------------------------------------------
# v1.4 final-review fix: every tool advertised in TOOL_SCHEMAS must be
# dispatchable via the bridge.
#
# The bridge looks tools up with ``getattr(tools_mod, name)`` on
# ``open_edit.agent.tools``. If a tool name is in TOOL_SCHEMAS (i.e. the
# LLM sees it as callable) but is NOT re-exported from
# ``open_edit.agent.tools.__init__``, the LLM call yields
# ``tool not found in open_edit.agent.tools: '<name>'``. This test loops
# over every schema name (skipping the server-side virtual
# ``trigger_render``) and asserts the bridge can resolve it.
# ---------------------------------------------------------------------------

def test_bridge_can_dispatch_every_advertised_tool():
    """Regression for the pre-existing 5-tool bridge gap.

    For every tool name in TOOL_SCHEMAS (except the server-side virtual
    ``trigger_render``), ``getattr(open_edit.agent.tools, name)`` must
    return a callable. This is the exact lookup the bridge does in
    ``_run_agent_tool`` (``pi_bridge.py``); a missing re-export would
    make the LLM see ``tool not found`` for that tool.
    """
    from open_edit.serve.tool_schemas import TOOL_SCHEMAS
    import open_edit.agent.tools as tools_mod

    missing: list[str] = []
    for schema in TOOL_SCHEMAS:
        name = schema["name"]
        if name == "trigger_render":
            # Server-side virtual tool — handled specially by
            # _run_agent_tool / _run_trigger_render, not via getattr.
            continue
        fn = getattr(tools_mod, name, None)
        if fn is None or not callable(fn):
            missing.append(name)

    assert missing == [], (
        f"bridge advertises {len(TOOL_SCHEMAS)} tools in TOOL_SCHEMAS but "
        f"the following are not re-exported from open_edit.agent.tools "
        f"(would yield 'tool not found' at dispatch time): {missing!r}. "
        f"Fix: add `from open_edit.agent.tools.pyagent_<name> import <name>` "
        f"to open_edit/agent/tools/__init__.py."
    )


# ---------------------------------------------------------------------------
# v1.5: structured trigger_render result shapes
# ---------------------------------------------------------------------------

def test_run_trigger_render_returns_structured_dict(tmp_path):
    """Happy path returns {output_path, mode, duration_s, render_id}."""
    from open_edit.serve import pi_bridge
    renders = tmp_path / ".open_edit" / "renders"
    renders.mkdir(parents=True, exist_ok=True)
    fake = renders / "project_aaa.mp4"
    fake.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    proc = mock.Mock(returncode=0, stdout=f"{fake}\n", stderr="")
    with mock.patch("subprocess.run", return_value=proc), \
         mock.patch("open_edit.serve.pi_bridge._probe_duration", return_value=10.5):
        out = pi_bridge._run_trigger_render({}, tmp_path)
    assert out["output_path"] == str(fake)
    assert out["mode"] == "proxy"
    assert out["duration_s"] == 10.5
    assert out["render_id"].startswith("render_")


def test_run_trigger_render_returns_render_failed_on_nonzero_exit(tmp_path):
    """Subprocess returns exit 1 → ``error: render_failed: ...``."""
    from open_edit.serve import pi_bridge
    proc = mock.Mock(returncode=1, stdout="", stderr="ffmpeg crashed")
    with mock.patch("subprocess.run", return_value=proc):
        out = pi_bridge._run_trigger_render({}, tmp_path)
    assert "error" in out
    assert "render_failed" in out["error"]
    assert "render_id" in out


def test_run_trigger_render_returns_render_invalid_on_empty_mp4(tmp_path):
    """Output file is 0 bytes → ``error: render_invalid``."""
    from open_edit.serve import pi_bridge
    renders = tmp_path / ".open_edit" / "renders"
    renders.mkdir(parents=True, exist_ok=True)
    (renders / "empty.mp4").write_bytes(b"")
    proc = mock.Mock(returncode=0, stdout="empty.mp4\n", stderr="")
    with mock.patch("subprocess.run", return_value=proc):
        out = pi_bridge._run_trigger_render({}, tmp_path)
    assert "error" in out
    assert "render_invalid" in out["error"] or "empty_render" in out["error"]


def test_run_trigger_render_returns_no_video_stream(tmp_path):
    """ffprobe finds no video stream → ``error: no_video_stream``."""
    from open_edit.serve import pi_bridge
    renders = tmp_path / ".open_edit" / "renders"
    renders.mkdir(parents=True, exist_ok=True)
    (renders / "x.mp4").write_bytes(b"\x00" * 100)
    proc = mock.Mock(returncode=0, stdout="x.mp4\n", stderr="")
    with mock.patch("subprocess.run", return_value=proc), \
         mock.patch("open_edit.serve.pi_bridge._probe_duration",
                    side_effect=RuntimeError("no video stream")):
        out = pi_bridge._run_trigger_render({}, tmp_path)
    assert "error" in out
    assert "no_video_stream" in out["error"]
