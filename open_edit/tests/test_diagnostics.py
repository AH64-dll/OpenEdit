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

_REPO_ROOT = Path(__file__).resolve().parents[2]
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
    assert isinstance(diag["config_summary"], dict)
    assert diag["disk_free_bytes"] is None or isinstance(diag["disk_free_bytes"], int)


def test_collect_diagnostics_never_raises_when_detectors_fail(monkeypatch):
    monkeypatch.setattr(diagnostics.shutil, "which", lambda *a, **k: (_ for _ in ()).throw(OSError))
    monkeypatch.setattr(diagnostics.os, "statvfs", lambda *a, **k: (_ for _ in ()).throw(OSError))
    diag = diagnostics.collect_diagnostics()
    assert set(diag) == _EXPECTED_KEYS
    assert diag["disk_free_bytes"] is None


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
