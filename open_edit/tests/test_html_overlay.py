"""v1.6: tests for the HTML overlay compositing module.

The module is split into 4 public functions (this file's tests cover
all of them in groups):
  * `generate_composition_html` — pure HTML generation, gotchas, template
  * `render_overlay_layer` + `composite_with_background` — subprocess wrappers
  * `render_composited` — async orchestrator with concurrent bg + overlay
  * `_resolve_hyperframes_bin` — binary resolution (env var > pinned > npx)

Plus 1 exception class: `OverlayRenderError(message, bg_path=None)`.

All subprocess calls in the module are mocked in unit tests; only
test 41 (the integration test, last in the file) actually runs
hyperframes + ffmpeg, and it's skipped if hyperframes is missing.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shlex
import shutil
import sys
from pathlib import Path
from unittest import mock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from open_edit.serve import html_overlay  # noqa: E402
from open_edit.serve import serve_env  # noqa: E402


# ---------------------------------------------------------------------------
# Binary resolution (Task 1 — tests 30, 31, 32 in spec §10)
# ---------------------------------------------------------------------------

def test_resolve_hyperframes_bin_prefers_pinned_binary(tmp_path, monkeypatch, caplog):
    """Pinned `node_modules/.bin/hyperframes` exists → it's returned, no warning."""
    pinned = tmp_path / "node_modules" / ".bin" / "hyperframes"
    pinned.parent.mkdir(parents=True)
    pinned.write_text("#!/bin/sh\necho hyperframes\n")
    pinned.chmod(0o755)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPEN_EDIT_HYPERFRAMES_BIN", raising=False)
    with caplog.at_level(logging.WARNING, logger="open_edit.serve.html_overlay"):
        bin_path = html_overlay._resolve_hyperframes_bin()
    assert bin_path == str(pinned)
    assert not any("hyperframes" in r.message.lower() and "fallback" in r.message.lower()
                   for r in caplog.records)


def test_resolve_hyperframes_bin_falls_back_to_npx_with_warning(tmp_path, monkeypatch, caplog):
    """No pinned binary → bare `npx hyperframes`, WARNING logged with the prescribed message."""
    monkeypatch.chdir(tmp_path)  # no node_modules/.bin
    monkeypatch.delenv("OPEN_EDIT_HYPERFRAMES_BIN", raising=False)
    with caplog.at_level(logging.WARNING, logger="open_edit.serve.html_overlay"):
        bin_path = html_overlay._resolve_hyperframes_bin()
    assert bin_path == "npx hyperframes"
    # Spec §5 mandates the exact WARNING wording.
    assert any(
        "hyperframes pinned binary not found" in r.message
        and "falling back to npx hyperframes" in r.message
        and "version drift risk" in r.message
        for r in caplog.records
    )


def test_resolve_hyperframes_bin_respects_env_var_override(tmp_path, monkeypatch):
    """OPEN_EDIT_HYPERFRAMES_BIN env var wins over the auto-resolution."""
    custom = tmp_path / "my-hf"
    custom.write_text("#!/bin/sh\n")
    custom.chmod(0o755)
    pinned = tmp_path / "node_modules" / ".bin" / "hyperframes"
    pinned.parent.mkdir(parents=True)
    pinned.write_text("#!/bin/sh\n")
    pinned.chmod(0o755)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPEN_EDIT_HYPERFRAMES_BIN", str(custom))
    bin_path = html_overlay._resolve_hyperframes_bin()
    assert bin_path == str(custom)
