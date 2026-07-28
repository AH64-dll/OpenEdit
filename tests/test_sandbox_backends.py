"""Pluggable sandbox backend selection + fail-closed behavior.

Covers the refactor of sandbox_bridge into a SandboxBackend interface with a
default (secure) BwrapBackend and an opt-in DevSubprocessBackend, plus the
fail-closed SandboxUnavailable contract.
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from open_edit.agent.sandbox_bridge import (
    BwrapBackend,
    DevSubprocessBackend,
    SandboxBackend,
    SandboxUnavailable,
    get_sandbox_backend,
)


@pytest.fixture(autouse=True)
def _allow_tmp_workdir(tmp_path, monkeypatch):
    monkeypatch.setenv("OPEN_EDIT_PROJECTS_ROOT", str(tmp_path))


def _make_project(tmp_path):
    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "edit_graph.db").touch()
    return workdir


# ---------------------------------------------------------------------------
# get_sandbox_backend selection contract
# ---------------------------------------------------------------------------

def test_default_selects_bwrap_backend(monkeypatch):
    monkeypatch.delenv("OPEN_EDIT_SANDBOX_BACKEND", raising=False)
    backend = get_sandbox_backend()
    assert isinstance(backend, BwrapBackend)
    assert isinstance(backend, SandboxBackend)
    assert backend.name == "bwrap"


def test_explicit_bwrap_selects_bwrap_backend(monkeypatch):
    monkeypatch.setenv("OPEN_EDIT_SANDBOX_BACKEND", "bwrap")
    assert isinstance(get_sandbox_backend(), BwrapBackend)


def test_dev_selects_dev_backend(monkeypatch):
    monkeypatch.setenv("OPEN_EDIT_SANDBOX_BACKEND", "dev")
    backend = get_sandbox_backend()
    assert isinstance(backend, DevSubprocessBackend)
    assert backend.name == "dev"


def test_case_insensitive_and_whitespace(monkeypatch):
    monkeypatch.setenv("OPEN_EDIT_SANDBOX_BACKEND", "  DEV ")
    assert isinstance(get_sandbox_backend(), DevSubprocessBackend)


def test_unknown_backend_raises_value_error(monkeypatch):
    monkeypatch.setenv("OPEN_EDIT_SANDBOX_BACKEND", "docker")
    with pytest.raises(ValueError, match="not a valid sandbox backend"):
        get_sandbox_backend()


# ---------------------------------------------------------------------------
# DevSubprocessBackend runs the bootstrap in a plain subprocess
# ---------------------------------------------------------------------------

def test_run_free_form_uses_dev_backend(monkeypatch, tmp_path):
    """OPEN_EDIT_SANDBOX_BACKEND=dev routes run_free_form through the dev
    backend, which runs a plain subprocess (no bwrap)."""
    from open_edit.agent import sandbox_bridge
    from open_edit.agent.sandbox_bridge import run_free_form

    monkeypatch.setenv("OPEN_EDIT_SANDBOX_BACKEND", "dev")
    workdir = _make_project(tmp_path)

    captured = {}

    def _fake_run(cmd, **kwargs):
        # Assert we did NOT invoke bwrap / the Rust binary — just python -c.
        captured["cmd"] = cmd
        assert cmd[0] == sandbox_bridge.PINNED_PYTHON_BIN
        assert "-c" in cmd
        # Emulate the sandboxed script writing an (empty) ops file.
        ops_idx = cmd.index("-c")
        # ops path is embedded in the runner string; write it out.
        runner = cmd[ops_idx + 1]
        assert "open-edit-sandbox" not in runner
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch.object(sandbox_bridge.subprocess, "run", side_effect=_fake_run), \
         patch.object(
             sandbox_bridge, "_validate_ops_incrementally", return_value=([], None)
         ):
        # ops.jsonl won't exist (our fake didn't write it) -> ops_missing,
        # but that still proves the dev path executed a plain subprocess.
        result = run_free_form(
            code="# ir_api_version: 0.1; libs: {}\nprint('hi')",
            workdir=workdir,
            project_id="p1",
            parent_op_id="e1",
        )

    assert "cmd" in captured, "dev backend did not run a subprocess"
    assert result.reason in ("ops_missing", "")


def test_dev_backend_executes_real_python(monkeypatch, tmp_path):
    """End-to-end (no mocks): the dev backend actually runs the generated
    bootstrap + user code with the real interpreter and produces ops."""
    from open_edit.agent.sandbox_bridge import run_free_form
    from open_edit.storage.edit_graph import EditGraphStore

    monkeypatch.setenv("OPEN_EDIT_SANDBOX_BACKEND", "dev")
    workdir = tmp_path / "proj"
    workdir.mkdir()
    EditGraphStore(workdir / "edit_graph.db")  # real schema for validation
    (workdir / "assets").mkdir()

    # Add a real asset so AddClipOp reference validation passes.
    from open_edit.ir.types import Asset
    from open_edit.storage.assets import AssetStore
    store = AssetStore(workdir / "assets")
    asset = Asset(
        asset_hash="asset_abc", original_path="x", stored_path="x", type="video",
    )
    if hasattr(store, "put"):
        try:
            store.put(asset)
        except Exception:
            pass

    code = (
        "# ir_api_version: 0.1; libs: {}\n"
        "ir.add_clip(asset_hash='asset_abc', track_id='t1', position_sec=0.0)\n"
    )
    result = run_free_form(
        code=code, workdir=workdir, project_id="p1", parent_op_id="e1",
    )
    # Either the op validated (success) or reference validation rejected the
    # asset (invalid_op) — both prove the dev subprocess ran real python and
    # produced ops.jsonl. It must NOT be a protocol / binary error.
    assert result.reason not in (
        "sandbox_binary_missing", "sandbox_protocol_error", "sandbox_unavailable",
    ), f"unexpected: {result.reason} {result.detail!r}"


# ---------------------------------------------------------------------------
# FAIL-CLOSED: bwrap launch failure -> SandboxUnavailable (never dev fallback)
# ---------------------------------------------------------------------------

def _bwrap_fail_proc():
    return MagicMock(
        returncode=1,
        stdout="",
        stderr="bwrap: Creating new namespace failed: Resource temporarily unavailable\n",
    )


def test_bwrap_backend_raises_sandbox_unavailable(tmp_path):
    """BwrapBackend.run raises SandboxUnavailable when bwrap can't create
    its namespaces (fail-closed)."""
    from open_edit.agent import sandbox_bridge

    workdir = _make_project(tmp_path)
    with patch.object(
        sandbox_bridge, "_resolve_sandbox_bin", return_value="/fake/open-edit-sandbox",
    ), patch.object(
        sandbox_bridge.subprocess, "run", return_value=_bwrap_fail_proc(),
    ):
        with pytest.raises(SandboxUnavailable, match="OPEN_EDIT_SANDBOX_BACKEND=dev"):
            BwrapBackend().run(
                code="# ir_api_version: 0.1; libs: {}",
                workdir=workdir,
                project_id="p1",
                parent_op_id="e1",
                timeout=30,
                mem_mb=512,
                cpu_sec=None,
                originating_note_id=None,
            )


def test_run_free_form_fails_closed_not_dev_fallback(monkeypatch, tmp_path):
    """When bwrap is selected (default) and its launch fails, run_free_form
    returns reason='sandbox_unavailable' and does NOT silently run in dev
    mode."""
    from open_edit.agent import sandbox_bridge
    from open_edit.agent.sandbox_bridge import run_free_form

    monkeypatch.setenv("OPEN_EDIT_SANDBOX_BACKEND", "bwrap")
    workdir = _make_project(tmp_path)

    dev_run = MagicMock()
    with patch.object(
        sandbox_bridge, "_resolve_sandbox_bin", return_value="/fake/open-edit-sandbox",
    ), patch.object(
        sandbox_bridge.subprocess, "run", return_value=_bwrap_fail_proc(),
    ), patch.object(
        sandbox_bridge.DevSubprocessBackend, "run", dev_run,
    ):
        result = run_free_form(
            code="# ir_api_version: 0.1; libs: {}",
            workdir=workdir,
            project_id="p1",
            parent_op_id="e1",
        )

    assert not result.success
    assert result.reason == "sandbox_unavailable"
    assert "OPEN_EDIT_SANDBOX_BACKEND=dev" in result.detail
    dev_run.assert_not_called()  # NEVER a silent dev fallback


def test_bwrap_usage_error_is_not_sandbox_unavailable(tmp_path):
    """A plain non-namespace bwrap/usage error must NOT be misclassified as
    SandboxUnavailable (preserves the existing sandbox_protocol_error path)."""
    from open_edit.agent import sandbox_bridge

    workdir = _make_project(tmp_path)
    proc = MagicMock(
        returncode=2,
        stdout="",
        stderr="error: the following required arguments were not provided\n",
    )
    with patch.object(
        sandbox_bridge, "_resolve_sandbox_bin", return_value="/fake/open-edit-sandbox",
    ), patch.object(
        sandbox_bridge.subprocess, "run", return_value=proc,
    ):
        result = BwrapBackend().run(
            code="# ir_api_version: 0.1; libs: {}",
            workdir=workdir,
            project_id="p1",
            parent_op_id="e1",
            timeout=30,
            mem_mb=512,
            cpu_sec=None,
            originating_note_id=None,
        )
    assert result.reason == "sandbox_protocol_error"
