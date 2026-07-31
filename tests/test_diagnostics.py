"""Tests for ``open_edit.serve.diagnostics``.

The module collects a redacted system-health snapshot and must never
raise, regardless of which optional components (MLT, chromium, the Rust
sandbox) are installed. These tests pin the public contract used by the
future ``/health`` and ``/diagnostics`` routes.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from open_edit.serve import diagnostics  # noqa: E402

_EXPECTED_KEYS = {
    "python_version",
    "sqlite_version",
    "mlt_available",
    "chromium_available",
    "sandbox_backend",
    "sandbox_available",
    "sandbox",
    "disk_free_bytes",
    "config_summary",
}


def test_collect_diagnostics_returns_expected_keys():
    diag = diagnostics.collect_diagnostics()
    assert isinstance(diag, dict)
    assert set(diag) == _EXPECTED_KEYS


def test_collect_diagnostics_types():
    diag = diagnostics.collect_diagnostics()
    assert isinstance(diag["python_version"], str)
    assert isinstance(diag["mlt_available"], bool)
    assert isinstance(diag["chromium_available"], bool)
    assert isinstance(diag["sandbox_available"], bool)
    assert isinstance(diag["sandbox_backend"], str)
    assert isinstance(diag["sandbox"], dict)
    assert isinstance(diag["sandbox"]["backend"], str)
    assert isinstance(diag["sandbox"]["binary_found"], bool)
    assert isinstance(diag["sandbox"]["namespace_capability_hint"], str)
    assert isinstance(diag["config_summary"], dict)
    assert diag["disk_free_bytes"] is None or isinstance(diag["disk_free_bytes"], int)


def test_collect_diagnostics_never_raises_when_detectors_fail(monkeypatch):
    monkeypatch.setattr(diagnostics.shutil, "which", lambda *a, **k: (_ for _ in ()).throw(OSError))
    monkeypatch.setattr(diagnostics.os, "statvfs", lambda *a, **k: (_ for _ in ()).throw(OSError))
    diag = diagnostics.collect_diagnostics()
    assert set(diag) == _EXPECTED_KEYS
    assert diag["disk_free_bytes"] is None


def test_sandbox_diagnostics_are_actionable_and_redacted(monkeypatch):
    from open_edit.agent.sandbox import backends

    monkeypatch.setenv("OPEN_EDIT_SANDBOX_BACKEND", "bwrap")
    monkeypatch.setattr(
        backends,
        "_resolve_sandbox_bin",
        lambda: (_ for _ in ()).throw(FileNotFoundError),
    )
    sandbox = diagnostics.collect_diagnostics()["sandbox"]
    assert sandbox["backend"] == "bwrap"
    assert sandbox["binary_found"] is False
    assert sandbox["namespace_capability_hint"]
    assert "OPEN_EDIT_SANDBOX_BACKEND=dev" in sandbox["remediation"]
    assert "/" not in (sandbox["binary_path"] or "")


def test_bwrap_restricted_has_dev_remediation(monkeypatch):
    from open_edit.agent.sandbox import backends

    monkeypatch.setenv("OPEN_EDIT_SANDBOX_BACKEND", "bwrap")
    monkeypatch.setattr(
        backends, "_resolve_sandbox_bin", lambda: "/private/open-edit-sandbox"
    )
    namespace_file = Path("/proc/sys/kernel/unprivileged_userns_clone")
    monkeypatch.setattr(
        diagnostics.Path, "is_file", lambda self: self == namespace_file
    )
    monkeypatch.setattr(diagnostics.Path, "read_text", lambda self: "0\n")

    sandbox = diagnostics._sandbox_diagnostics()
    assert sandbox["backend"] == "bwrap"
    assert sandbox["binary_found"] is True
    assert sandbox["namespace_capability_hint"] == "restricted"
    assert "OPEN_EDIT_SANDBOX_BACKEND=dev" in sandbox["remediation"]
    assert sandbox["binary_path"] == "open-edit-sandbox"


def test_dev_backend_diagnostics_do_not_require_sandbox_binary(monkeypatch):
    from open_edit.agent.sandbox import backends

    monkeypatch.setenv("OPEN_EDIT_SANDBOX_BACKEND", "  DEV ")
    resolver = mock.Mock(side_effect=AssertionError("dev must not resolve bwrap"))
    monkeypatch.setattr(backends, "_resolve_sandbox_bin", resolver)

    sandbox = diagnostics._sandbox_diagnostics()
    assert sandbox["backend"] == "dev"
    assert sandbox["binary_found"] is False
    assert sandbox["namespace_capability_hint"] == "not_required"
    assert sandbox["remediation"] == ""
    resolver.assert_not_called()


def test_config_summary_has_no_secrets():
    with mock.patch.dict(
        os.environ,
        {"OPEN_EDIT_API_KEY": "sk-secret", "ANTHROPIC_API_KEY": "sk-secret"},
        clear=False,
    ):
        diag = diagnostics.collect_diagnostics()
    flat = repr(diag)
    assert "sk-secret" not in flat


def test_system_healthy_returns_bool():
    assert isinstance(diagnostics.system_healthy(), bool)


def test_system_healthy_true_when_sqlite_ok():
    assert diagnostics.system_healthy() is True


def test_system_healthy_permissive_without_sandbox(monkeypatch):
    monkeypatch.setattr(diagnostics, "_sandbox_available", lambda: False)
    assert diagnostics.system_healthy() is True


def test_get_health_has_status_key():
    health = diagnostics.get_health()
    assert "status" in health
    assert health["status"] in ("ok", "degraded")


def test_get_health_shape():
    health = diagnostics.get_health()
    assert set(health) == {"status", "mlt", "sandbox", "sqlite"}
    assert isinstance(health["mlt"], bool)
    assert isinstance(health["sandbox"], bool)
    assert isinstance(health["sqlite"], bool)
