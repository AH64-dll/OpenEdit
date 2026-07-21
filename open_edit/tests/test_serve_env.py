"""Tests for ``open_edit.serve.serve_env``.

The module exposes typed config dictionaries for the visual-verification
stage (``get_visual_verify_config``) and the v1.6 HTML-overlay stage
(``get_overlay_config``). Both functions must return real Python types
(not raw env strings) so the rest of the server can treat them as the
canonical source of truth.

These tests pin:

* Default values for every key in each config.
* Environment overrides for the typed-int / typed-bool / typed-str fields.
* The ``hyperframes_bin`` / ``overlay_tmpdir`` "unset" contract: the
  consumer uses ``or`` short-circuiting, so both keys must be ``None``
  (not an empty string) when their env var is unset — otherwise a
  caller can accidentally treat ``""`` as a real path and pass it to
  ``subprocess.run``.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from open_edit.serve import serve_env  # noqa: E402


# ---------------------------------------------------------------------------
# get_overlay_config
# ---------------------------------------------------------------------------

def test_overlay_config_hyperframes_bin_unset_is_none():
    """OPEN_EDIT_HYPERFRAMES_BIN unset → ``hyperframes_bin`` is ``None``.

    Sentinel fix: the previous implementation returned ``""`` here,
    forcing the consumer to use ``or`` to short-circuit. Returning
    ``None`` matches the sibling field ``overlay_tmpdir`` and makes
    the "unset" state unambiguous.
    """
    with mock.patch.dict(os.environ, {}, clear=True):
        cfg = serve_env.get_overlay_config()
    assert cfg["hyperframes_bin"] is None


def test_overlay_config_hyperframes_bin_set_is_returned():
    """OPEN_EDIT_HYPERFRAMES_BIN=/foo/bar → returned verbatim."""
    with mock.patch.dict(os.environ, {"OPEN_EDIT_HYPERFRAMES_BIN": "/foo/bar"}, clear=True):
        cfg = serve_env.get_overlay_config()
    assert cfg["hyperframes_bin"] == "/foo/bar"


def test_overlay_config_overlay_tmpdir_unset_is_none():
    """OPEN_EDIT_OVERLAY_TMPDIR unset → ``overlay_tmpdir`` is ``None``."""
    with mock.patch.dict(os.environ, {}, clear=True):
        cfg = serve_env.get_overlay_config()
    assert cfg["overlay_tmpdir"] is None


def test_overlay_config_overlay_tmpdir_set_is_resolved_path():
    """OPEN_EDIT_OVERLAY_TMPDIR=/tmp/x → Path('/tmp/x').resolve()."""
    with mock.patch.dict(os.environ, {"OPEN_EDIT_OVERLAY_TMPDIR": "/tmp/foo"}, clear=True):
        cfg = serve_env.get_overlay_config()
    assert isinstance(cfg["overlay_tmpdir"], Path)
    assert str(cfg["overlay_tmpdir"]) == str(Path("/tmp/foo").resolve())


def test_overlay_config_hyperframes_timeout_s_default():
    """OPEN_EDIT_HYPERFRAMES_TIMEOUT_SECONDS defaults to 120 (int)."""
    with mock.patch.dict(os.environ, {}, clear=True):
        cfg = serve_env.get_overlay_config()
    assert cfg["hyperframes_timeout_s"] == 120
    assert isinstance(cfg["hyperframes_timeout_s"], int)


def test_overlay_config_hyperframes_timeout_s_override():
    """OPEN_EDIT_HYPERFRAMES_TIMEOUT_SECONDS=300 → 300."""
    with mock.patch.dict(
        os.environ,
        {"OPEN_EDIT_HYPERFRAMES_TIMEOUT_SECONDS": "300"},
        clear=True,
    ):
        cfg = serve_env.get_overlay_config()
    assert cfg["hyperframes_timeout_s"] == 300


# ---------------------------------------------------------------------------
# Consumer: pi_bridge._build_render_spec still resolves hyperframes_bin
# even when the config returns ``None`` for the unset case.
# ---------------------------------------------------------------------------

def test_build_render_spec_resolves_hyperframes_bin_when_unset(tmp_path, monkeypatch):
    """When ``hyperframes_bin`` is ``None`` (env unset), the consumer
    falls back to ``html_overlay._resolve_hyperframes_bin()`` via the
    ``or`` short-circuit. We mock the resolver to a known string and
    verify the render spec picks it up.
    """
    from open_edit.serve import pi_bridge
    from open_edit.serve import html_overlay

    # Create a real (empty) project so _read_mlt_profile has something to read.
    project = tmp_path / "p1"
    project.mkdir()
    (project / ".open_edit").mkdir()
    monkeypatch.setattr(html_overlay, "_resolve_hyperframes_bin", lambda: "/resolved/hf")
    # Force the config to return None for hyperframes_bin by clearing the env.
    monkeypatch.delenv("OPEN_EDIT_HYPERFRAMES_BIN", raising=False)
    spec = pi_bridge._build_render_spec(project, "proxy", 120)
    assert spec["hyperframes_bin"] == "/resolved/hf"


def test_build_render_spec_uses_env_value_when_set(tmp_path, monkeypatch):
    """When the env var is set, ``hyperframes_bin`` is the env value
    (no fallback to the resolver)."""
    from open_edit.serve import pi_bridge
    from open_edit.serve import html_overlay

    project = tmp_path / "p1"
    project.mkdir()
    (project / ".open_edit").mkdir()

    def _must_not_call():
        raise AssertionError("resolver should not be called when env is set")

    monkeypatch.setattr(html_overlay, "_resolve_hyperframes_bin", _must_not_call)
    monkeypatch.setenv("OPEN_EDIT_HYPERFRAMES_BIN", "/env/hf")
    spec = pi_bridge._build_render_spec(project, "proxy", 120)
    assert spec["hyperframes_bin"] == "/env/hf"
