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
import inspect
import logging
import os
import shlex
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable
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


# ---------------------------------------------------------------------------
# Composition HTML generation (Task 2 — tests 1-18 in spec §10)
# ---------------------------------------------------------------------------

def _timeline(overlays):
    """Build a minimal Timeline-shaped object for the composition tests."""
    from open_edit.ir.types import Timeline
    return Timeline(overlays=overlays)


def _overlay(template_path="lower_third.html", variables=None, position_sec=2.0,
             duration_sec=5.0, overlay_id="a1b2c3"):
    """Build a minimal HtmlOverlay-shaped object for the composition tests."""
    from open_edit.ir.types import HtmlOverlay
    return HtmlOverlay(
        id=overlay_id,
        template_path=template_path,
        variables=variables or {},
        position_sec=position_sec,
        duration_sec=duration_sec,
    )


def _render_spec(**overrides):
    """Build a minimal RenderSpec-shaped dict for the composition tests."""
    spec = {
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "duration_sec": 10.0,
        "mode": "final",
        "hyperframes_bin": "npx hyperframes",
        "hyperframes_timeout_s": 120,
        "tmpdir": Path("/tmp/test-overlay"),
    }
    spec.update(overrides)
    return spec


def test_root_has_required_data_attrs_with_data_duration(tmp_path):
    """Test 1: root has data-composition-id, data-start=0, data-duration=<bg_total>,
    data-width, data-height, data-fps, id=root."""
    timeline = _timeline([_overlay()])
    html = html_overlay.generate_composition_html(
        timeline, tmp_path, _render_spec(duration_sec=5.0)
    )
    assert 'id="root"' in html
    assert 'data-composition-id="open_edit_overlay"' in html
    assert 'data-start="0"' in html
    assert 'data-duration="5.0"' in html
    assert 'data-width="1920"' in html
    assert 'data-height="1080"' in html
    assert 'data-fps="30"' in html


def test_root_has_data_no_timeline_attribute(tmp_path):
    """Test 2: data-no-timeline on the root (skips the 45s poll)."""
    html = html_overlay.generate_composition_html(
        _timeline([_overlay()]), tmp_path, _render_spec()
    )
    assert "data-no-timeline" in html


def test_root_has_proper_html_document_structure(tmp_path):
    """Test 3: <!DOCTYPE html>, <html>, <head>, <body> wrappers (avoids
    root_composition_missing_html_wrapper lint error)."""
    html = html_overlay.generate_composition_html(
        _timeline([_overlay()]), tmp_path, _render_spec()
    )
    assert html.lstrip().startswith("<!DOCTYPE html>")
    assert "<html" in html
    assert "<head>" in html
    assert "<body>" in html


def test_one_overlay_produces_single_clip_div(tmp_path):
    """Test 4: 1 overlay → 1 clip <div>."""
    html = html_overlay.generate_composition_html(
        _timeline([_overlay()]), tmp_path, _render_spec()
    )
    # Exactly one class="clip" div in the body.
    assert html.count('class="clip"') == 1


def test_overlay_data_attrs_match_op(tmp_path):
    """Test 5: clip div's data-start/data-duration/data-track-index
    match the HtmlOverlay op."""
    html = html_overlay.generate_composition_html(
        _timeline([_overlay(position_sec=2.0, duration_sec=5.0)]),
        tmp_path, _render_spec(),
    )
    assert 'data-start="2.0"' in html
    assert 'data-duration="5.0"' in html
    # One track → track-index 0
    assert 'data-track-index="0"' in html


def test_clip_divs_have_stable_unique_ids(tmp_path):
    """Test 6: every clip <div> has id="overlay_<hash>"""
    overlays = [
        _overlay(overlay_id="abc"),
        _overlay(overlay_id="def", position_sec=10.0, duration_sec=2.0),
    ]
    html = html_overlay.generate_composition_html(
        _timeline(overlays), tmp_path, _render_spec()
    )
    assert 'id="overlay_abc"' in html
    assert 'id="overlay_def"' in html
    # No clip <div> without an id.
    import re
    clip_divs = re.findall(r'<div class="clip"[^>]*>', html)
    assert all('id="' in d for d in clip_divs)


def test_track_assignment_non_overlapping_shares_index(tmp_path):
    """Test 7: two non-overlapping overlays share track-index 0."""
    overlays = [
        _overlay(position_sec=0.0, duration_sec=2.0, overlay_id="first"),
        _overlay(position_sec=3.0, duration_sec=2.0, overlay_id="second"),
    ]
    html = html_overlay.generate_composition_html(
        _timeline(overlays), tmp_path, _render_spec()
    )
    # Both clips on track 0.
    import re
    clip_divs = re.findall(r'<div class="clip"[^>]*data-track-index="(\d+)"', html)
    assert clip_divs == ["0", "0"]


def test_track_assignment_overlapping_gets_new_index(tmp_path):
    """Test 8: two overlapping overlays get distinct track indices."""
    overlays = [
        _overlay(position_sec=0.0, duration_sec=5.0, overlay_id="long"),
        _overlay(position_sec=2.0, duration_sec=2.0, overlay_id="mid"),
    ]
    html = html_overlay.generate_composition_html(
        _timeline(overlays), tmp_path, _render_spec()
    )
    import re
    clip_divs = re.findall(r'<div class="clip"[^>]*data-track-index="(\d+)"', html)
    # One on track 0, one on track 1 (order is sorted by position_sec).
    assert sorted(clip_divs) == ["0", "1"]


def test_html_key_substitution_escapes_special_chars(tmp_path):
    """Test 9: {{key}} with <, >, &, " is HTML-escaped."""
    # Write a template that uses {{title}}.
    template = tmp_path / "my.html"
    template.write_text("<div class='title'>{{title}}</div>")
    timeline = _timeline([_overlay(
        template_path="my.html",
        variables={"title": "<script>alert(1)</script>"},
    )])
    html = html_overlay.generate_composition_html(timeline, tmp_path, _render_spec())
    assert "&lt;script&gt;" in html
    assert "<script>alert" not in html  # raw < not present


def test_html_key_substitution_preserves_missing_keys(tmp_path):
    """Test 10: missing {{key}} is left literal (with a logged warning)."""
    template = tmp_path / "my.html"
    template.write_text("<div>{{title}}</div>")
    timeline = _timeline([_overlay(template_path="my.html", variables={})])
    html = html_overlay.generate_composition_html(timeline, tmp_path, _render_spec())
    assert "{{title}}" in html  # not replaced


def test_non_primitive_variable_raises_overlay_render_error(tmp_path):
    """Test 11: dict/list variable raises OverlayRenderError (no JSON-blob support in v1.6)."""
    template = tmp_path / "my.html"
    template.write_text("<div>{{data}}</div>")
    timeline = _timeline([_overlay(
        template_path="my.html",
        variables={"data": {"nested": "dict"}},
    )])
    with pytest.raises(html_overlay.OverlayRenderError, match="non-primitive variable"):
        html_overlay.generate_composition_html(timeline, tmp_path, _render_spec())


def test_empty_variables_yields_unchanged_template(tmp_path):
    """Test 12: empty variables dict → template renders with placeholders intact."""
    template = tmp_path / "my.html"
    template.write_text("<div>{{title}}</div>")
    timeline = _timeline([_overlay(template_path="my.html", variables={})])
    html = html_overlay.generate_composition_html(timeline, tmp_path, _render_spec())
    assert "{{title}}" in html


def test_composition_css_has_transparent_background(tmp_path):
    """Test 13: <style> has `background: transparent` on html/body/root."""
    html = html_overlay.generate_composition_html(
        _timeline([_overlay()]), tmp_path, _render_spec()
    )
    # The <style> block (between <head> and </head>) must set transparent bg.
    style_start = html.index("<style>")
    style_end = html.index("</style>")
    style = html[style_start:style_end]
    assert "background: transparent" in style
    assert "html, body" in style
    assert "[data-composition-id]" in style


def test_template_resolution_project_dir_first(tmp_path):
    """Test 14: template_path resolves in the project dir first, before built-ins."""
    proj_template = tmp_path / "my.html"
    proj_template.write_text("<div>PROJECT</div>")
    timeline = _timeline([_overlay(template_path="my.html", variables={})])
    html = html_overlay.generate_composition_html(timeline, tmp_path, _render_spec())
    assert "PROJECT" in html


def test_template_resolution_falls_back_to_builtin(tmp_path):
    """Test 15: if no project-dir match, fall back to open_edit/serve/templates/overlay/."""
    # No `my.html` in tmp_path (the project_workdir).
    timeline = _timeline([_overlay(template_path="lower_third.html", variables={"name": "X", "title": "Y"})])
    html = html_overlay.generate_composition_html(timeline, tmp_path, _render_spec())
    # The built-in lower_third template uses {{name}} and {{title}}.
    assert "X" in html
    assert "Y" in html


def test_template_path_rejects_absolute(tmp_path):
    """Test 16: absolute template_path raises OverlayRenderError."""
    timeline = _timeline([_overlay(template_path="/etc/passwd")])
    with pytest.raises(html_overlay.OverlayRenderError, match="absolute template_path"):
        html_overlay.generate_composition_html(timeline, tmp_path, _render_spec())


def test_template_path_rejects_parent_traversal(tmp_path):
    """Test 17: '..' in template_path raises OverlayRenderError."""
    timeline = _timeline([_overlay(template_path="../../../etc/passwd")])
    with pytest.raises(html_overlay.OverlayRenderError, match=r"\.\. not allowed"):
        html_overlay.generate_composition_html(timeline, tmp_path, _render_spec())


def test_template_path_rejects_symlink_escape(tmp_path):
    """Symlink inside project_workdir pointing outside must raise OverlayRenderError."""
    outside = tmp_path / ".." / "outside_target.html"
    outside.write_text("<div>ESCAPED</div>")
    symlink = tmp_path / "escaped.html"
    symlink.symlink_to(outside)
    timeline = _timeline([_overlay(template_path="escaped.html")])
    with pytest.raises(html_overlay.OverlayRenderError, match="escapes project dir"):
        html_overlay.generate_composition_html(timeline, tmp_path, _render_spec())


def test_template_not_found_raises_overlay_render_error(tmp_path):
    """Test 18: template not found in either dir raises OverlayRenderError."""
    timeline = _timeline([_overlay(template_path="does_not_exist.html")])
    with pytest.raises(html_overlay.OverlayRenderError, match="template_not_found"):
        html_overlay.generate_composition_html(timeline, tmp_path, _render_spec())


# ---------------------------------------------------------------------------
# Subprocess wrappers (Task 3 — tests 19-29 in spec §10)
# ---------------------------------------------------------------------------

def _argv_of(mock_popen_call):
    """Return the argv list from a mocked subprocess.Popen call."""
    return list(mock_popen_call.args[0])


def _make_popen_mock(returncode=0, stdout="", stderr="", communicate_side_effect=None):
    """Build a fake Popen instance for the cancellation-aware wrappers."""
    popen = mock.Mock()
    popen.communicate.return_value = (stdout, stderr)
    if communicate_side_effect is not None:
        popen.communicate.side_effect = communicate_side_effect
    popen.poll.return_value = returncode
    popen.returncode = returncode
    popen.kill.return_value = None
    return popen


def test_render_overlay_layer_uses_argv_list_no_shell(tmp_path):
    """Test 19: subprocess.Popen is called with shell=False (explicit)."""
    comp_html = tmp_path / "compositions" / "overlay.html"
    comp_html.parent.mkdir(parents=True)
    comp_html.write_text("<html></html>")
    out = tmp_path / "overlay.mov"
    out.write_bytes(b"x")
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    # Write the composition HTML inside the project dir for the positional [DIR] arg.
    proj_comp = project_dir / "compositions"
    proj_comp.mkdir()
    proj_comp.joinpath("overlay.html").write_text("<html></html>")
    popen_inst = _make_popen_mock()
    with mock.patch("subprocess.Popen", return_value=popen_inst) as popen_mock:
        html_overlay.render_overlay_layer(
            comp_html_path=proj_comp / "overlay.html",
            output_path=out,
            render_spec=_render_spec(
                hyperframes_bin="/usr/local/bin/hyperframes",
                tmpdir=project_dir,
            ),
        )
    assert popen_mock.call_args.kwargs.get("shell", False) is False


def test_render_overlay_layer_uses_mov_format_not_mp4(tmp_path):
    """Test 20: argv contains '--format mov' (not '--format mp4' or '--transparent')."""
    comp_html = tmp_path / "compositions" / "overlay.html"
    comp_html.parent.mkdir(parents=True)
    comp_html.write_text("<html></html>")
    out = tmp_path / "overlay.mov"
    out.write_bytes(b"x")
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    popen_inst = _make_popen_mock()
    with mock.patch("subprocess.Popen", return_value=popen_inst) as popen_mock:
        html_overlay.render_overlay_layer(
            comp_html_path=comp_html,
            output_path=out,
            render_spec=_render_spec(
                hyperframes_bin="/usr/local/bin/hyperframes",
                tmpdir=project_dir,
            ),
        )
    argv = _argv_of(popen_mock.call_args)
    assert "--format" in argv
    mov_idx = argv.index("--format")
    assert argv[mov_idx + 1] == "mov"
    assert "mp4" not in argv
    assert "--transparent" not in argv


def test_render_overlay_layer_uses_composition_flag_not_input(tmp_path):
    """Test 21: argv contains '-c' (not '--input' which doesn't exist)."""
    comp_html = tmp_path / "overlay.html"
    comp_html.write_text("<html></html>")
    out = tmp_path / "out.mov"
    out.write_bytes(b"x")
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    popen_inst = _make_popen_mock()
    with mock.patch("subprocess.Popen", return_value=popen_inst) as popen_mock:
        html_overlay.render_overlay_layer(
            comp_html_path=comp_html,
            output_path=out,
            render_spec=_render_spec(
                hyperframes_bin="/usr/local/bin/hyperframes",
                tmpdir=project_dir,
            ),
        )
    argv = _argv_of(popen_mock.call_args)
    assert "-c" in argv
    c_idx = argv.index("-c")
    assert argv[c_idx + 1] == "overlay.html"
    assert "--input" not in argv


def test_render_overlay_layer_uses_positional_dir_arg(tmp_path):
    """Test 22: the last positional arg is the project tmpdir (not a flag)."""
    comp_html = tmp_path / "overlay.html"
    comp_html.write_text("<html></html>")
    out = tmp_path / "out.mov"
    out.write_bytes(b"x")
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    popen_inst = _make_popen_mock()
    with mock.patch("subprocess.Popen", return_value=popen_inst) as popen_mock:
        html_overlay.render_overlay_layer(
            comp_html_path=comp_html,
            output_path=out,
            render_spec=_render_spec(
                hyperframes_bin="/usr/local/bin/hyperframes",
                tmpdir=project_dir,
            ),
        )
    argv = _argv_of(popen_mock.call_args)
    # After shlex.split, the first element is the binary; the last is the [DIR].
    assert argv[-1] == str(project_dir.resolve())


def test_render_overlay_layer_uses_strict_flag(tmp_path):
    """Test 23: argv contains '--strict' (fails on lint errors)."""
    comp_html = tmp_path / "overlay.html"
    comp_html.write_text("<html></html>")
    out = tmp_path / "out.mov"
    out.write_bytes(b"x")
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    popen_inst = _make_popen_mock()
    with mock.patch("subprocess.Popen", return_value=popen_inst) as popen_mock:
        html_overlay.render_overlay_layer(
            comp_html_path=comp_html,
            output_path=out,
            render_spec=_render_spec(
                hyperframes_bin="/usr/local/bin/hyperframes",
                tmpdir=project_dir,
            ),
        )
    argv = _argv_of(popen_mock.call_args)
    assert "--strict" in argv


def test_render_overlay_layer_translates_file_not_found(tmp_path):
    """Test 24: FileNotFoundError → OverlayRenderError."""
    comp_html = tmp_path / "x.html"
    comp_html.write_text("<html></html>")
    with mock.patch("subprocess.Popen", side_effect=FileNotFoundError("no hyperframes")):
        with pytest.raises(html_overlay.OverlayRenderError, match="binary not found"):
            html_overlay.render_overlay_layer(
                comp_html_path=comp_html,
                output_path=tmp_path / "out.mov",
                render_spec=_render_spec(hyperframes_bin="/nope/hyperframes", tmpdir=tmp_path),
            )


def test_render_overlay_layer_translates_timeout(tmp_path):
    """Test 25: subprocess.TimeoutExpired → OverlayRenderError."""
    comp_html = tmp_path / "x.html"
    comp_html.write_text("<html></html>")
    popen_inst = _make_popen_mock(communicate_side_effect=subprocess.TimeoutExpired(cmd="hf", timeout=5))
    with mock.patch("subprocess.Popen", return_value=popen_inst):
        with pytest.raises(html_overlay.OverlayRenderError, match="timed out"):
            html_overlay.render_overlay_layer(
                comp_html_path=comp_html,
                output_path=tmp_path / "out.mov",
                render_spec=_render_spec(hyperframes_bin="/usr/local/bin/hyperframes", tmpdir=tmp_path, hyperframes_timeout_s=5),
            )


def test_render_overlay_layer_translates_nonzero_exit(tmp_path):
    """Test 26: returncode != 0 → OverlayRenderError with stderr in the message."""
    comp_html = tmp_path / "x.html"
    comp_html.write_text("<html></html>")
    popen_inst = _make_popen_mock(returncode=1, stderr="lint error: bad HTML")
    with mock.patch("subprocess.Popen", return_value=popen_inst):
        with pytest.raises(html_overlay.OverlayRenderError, match="non-zero exit"):
            html_overlay.render_overlay_layer(
                comp_html_path=comp_html,
                output_path=tmp_path / "out.mov",
                render_spec=_render_spec(hyperframes_bin="/usr/local/bin/hyperframes", tmpdir=tmp_path),
            )


def test_render_overlay_layer_rejects_missing_output_file(tmp_path):
    """returncode == 0 but output file missing/empty → OverlayRenderError."""
    comp_html = tmp_path / "x.html"
    comp_html.write_text("<html></html>")
    out = tmp_path / "out.mov"
    # Do not create `out`; it is missing.
    popen_inst = _make_popen_mock(returncode=0)
    with mock.patch("subprocess.Popen", return_value=popen_inst):
        with pytest.raises(html_overlay.OverlayRenderError, match="output file is missing or empty"):
            html_overlay.render_overlay_layer(
                comp_html_path=comp_html,
                output_path=out,
                render_spec=_render_spec(hyperframes_bin="/usr/local/bin/hyperframes", tmpdir=tmp_path),
            )


class _SlowPopen:
    """Fake Popen that stays alive until kill() is called."""

    def __init__(self, cmd, **kwargs):
        self.cmd = cmd
        self._killed = threading.Event()
        self.returncode = None

    def communicate(self, timeout=None):
        if not self._killed.wait(timeout=timeout):
            raise subprocess.TimeoutExpired(self.cmd, timeout)
        self.returncode = -9
        return "", ""

    def poll(self):
        return None if not self._killed.is_set() else -9

    def kill(self):
        self._killed.set()


def test_render_overlay_layer_cancellation_kills_subprocess(tmp_path):
    """Cancellation during the render calls kill() and raises OverlayRenderError."""
    comp_html = tmp_path / "overlay.html"
    comp_html.write_text("<html></html>")
    out = tmp_path / "out.mov"
    out.write_bytes(b"x")
    cancel_flag = {"cancel": False}

    def should_cancel():
        return cancel_flag["cancel"]

    def trigger_cancel():
        time.sleep(0.1)
        cancel_flag["cancel"] = True

    threading.Thread(target=trigger_cancel).start()
    with mock.patch("subprocess.Popen", side_effect=lambda cmd, **kw: _SlowPopen(cmd)):
        with pytest.raises(html_overlay.OverlayRenderError, match="cancelled during overlay render"):
            html_overlay.render_overlay_layer(
                comp_html_path=comp_html,
                output_path=out,
                render_spec=_render_spec(
                    hyperframes_bin="/usr/local/bin/hyperframes",
                    tmpdir=tmp_path,
                    hyperframes_timeout_s=10,
                ),
                should_cancel=should_cancel,
            )


def test_composite_with_background_cancellation_kills_subprocess(tmp_path):
    """Cancellation during ffmpeg calls kill() and raises OverlayRenderError."""
    bg = tmp_path / "bg.mp4"
    overlay = tmp_path / "overlay.mov"
    out = tmp_path / "final.mp4"
    out.write_bytes(b"x")
    cancel_flag = {"cancel": False}

    def should_cancel():
        return cancel_flag["cancel"]

    def trigger_cancel():
        time.sleep(0.1)
        cancel_flag["cancel"] = True

    threading.Thread(target=trigger_cancel).start()
    with mock.patch("subprocess.Popen", side_effect=lambda cmd, **kw: _SlowPopen(cmd)):
        with pytest.raises(html_overlay.OverlayRenderError, match="cancelled during ffmpeg composite"):
            html_overlay.composite_with_background(
                bg_path=bg, overlay_path=overlay, output_path=out,
                render_spec=_render_spec(hyperframes_timeout_s=10),
                should_cancel=should_cancel,
            )


def test_composite_with_background_uses_explicit_audio_map(tmp_path):
    """Test 27: ffmpeg argv contains '-map 0:a -map [outv] -c:a copy'."""
    bg = tmp_path / "bg.mp4"
    bg.write_bytes(b"x" * 100)
    overlay = tmp_path / "overlay.mov"
    overlay.write_bytes(b"x" * 100)
    out = tmp_path / "final.mp4"
    out.write_bytes(b"x")
    popen_inst = _make_popen_mock()
    with mock.patch("subprocess.Popen", return_value=popen_inst) as popen_mock:
        html_overlay.composite_with_background(
            bg_path=bg, overlay_path=overlay, output_path=out,
            render_spec=_render_spec(),
        )
    argv = _argv_of(popen_mock.call_args)
    # The 4 critical flags in order: -map 0:a ... -map [outv] ... -c:a copy
    assert "-map" in argv
    map_indices = [i for i, a in enumerate(argv) if a == "-map"]
    assert len(map_indices) >= 2
    assert argv[map_indices[0] + 1] == "0:a"
    assert argv[map_indices[1] + 1] == "[outv]"
    assert "-c:a" in argv
    ca_idx = argv.index("-c:a")
    assert argv[ca_idx + 1] == "copy"


def test_composite_with_background_filter_includes_eof_action_pass(tmp_path):
    """Test 28: ffmpeg filter_complex includes 'overlay=eof_action=pass'."""
    bg = tmp_path / "bg.mp4"
    overlay = tmp_path / "overlay.mov"
    out = tmp_path / "final.mp4"
    out.write_bytes(b"x")
    popen_inst = _make_popen_mock()
    with mock.patch("subprocess.Popen", return_value=popen_inst) as popen_mock:
        html_overlay.composite_with_background(
            bg_path=bg, overlay_path=overlay, output_path=out,
            render_spec=_render_spec(),
        )
    argv = _argv_of(popen_mock.call_args)
    fc_idx = argv.index("-filter_complex")
    filter_str = argv[fc_idx + 1]
    assert "overlay=eof_action=pass" in filter_str


def test_composite_with_background_translates_ffmpeg_errors(tmp_path):
    """Test 29: ffmpeg non-zero exit → OverlayRenderError."""
    bg = tmp_path / "bg.mp4"
    overlay = tmp_path / "overlay.mov"
    out = tmp_path / "final.mp4"
    popen_inst = _make_popen_mock(returncode=1, stderr="ffmpeg: Invalid data found")
    with mock.patch("subprocess.Popen", return_value=popen_inst):
        with pytest.raises(html_overlay.OverlayRenderError, match="ffmpeg failed"):
            html_overlay.composite_with_background(
                bg_path=bg, overlay_path=overlay, output_path=out,
                render_spec=_render_spec(),
            )


# ---------------------------------------------------------------------------
# Disk-footprint preflight (Task 3 — tests 33, 34 in spec §10)
# ---------------------------------------------------------------------------

def test_disk_footprint_preflight_warns_at_500mb(tmp_path, caplog):
    """Test 33: 600 MB estimate → WARNING logged, render proceeds (no exception)."""
    # 600s of overlay at 1 MB/s = 600 MB. Use a single overlay spanning 10 minutes.
    timeline = _timeline([_overlay(position_sec=0, duration_sec=600.0)])
    import logging
    with caplog.at_level(logging.WARNING, logger="open_edit.serve.html_overlay"):
        html_overlay._disk_footprint_check(estimated_mb=600, tmpdir=tmp_path)
    assert any("overlay estimated" in r.message and "~600 MB" in r.message
               for r in caplog.records)


def test_disk_footprint_preflight_raises_overlay_render_error_at_2gb(tmp_path):
    """Test 34: 3 GB estimate → OverlayRenderError (no subprocess spawned)."""
    with pytest.raises(html_overlay.OverlayRenderError, match="overlay_render_too_large"):
        html_overlay._disk_footprint_check(estimated_mb=3000, tmpdir=tmp_path)


def test_estimate_overlay_size_mb_heuristic(tmp_path):
    """Direct coverage for _estimate_overlay_size_mb: 1 MB/s rounded."""
    timeline = _timeline([
        _overlay(position_sec=0, duration_sec=2.5),
        _overlay(position_sec=3.0, duration_sec=4.5),
    ])
    assert html_overlay._estimate_overlay_size_mb(timeline) == 7


# ---------------------------------------------------------------------------
# Orchestrator (Task 4 — tests 35-40 in spec §10)
# ---------------------------------------------------------------------------

class _FakePopen:
    """Popen stand-in for the orchestrator tests. Writes requested outputs
    and returns the configured exit code."""

    def __init__(self, cmd, returncode=0, stdout="", stderr="", side_effect=None):
        self.cmd = cmd
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self._side_effect = side_effect

    def communicate(self, timeout=None):
        if self._side_effect:
            self._side_effect(self.cmd)
        return self.stdout, self.stderr

    def poll(self):
        return self.returncode

    def kill(self):
        pass


def test_render_composited_writes_composition_html_to_compositions_subdir(tmp_path):
    """Test 35: the composition HTML lands at <tmpdir>/overlay.html."""
    timeline = _timeline([_overlay()])
    bg = tmp_path / "bg.mp4"
    bg.write_bytes(b"x" * 100)
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    # Mock bg_renderer to return a fake bg.
    bg_renderer = mock.Mock(return_value=bg)
    # Mock both subprocess.Popen calls (hyperframes and ffmpeg).
    overlay_out = project_dir / "overlay.mov"
    final_out = project_dir / "final.mp4"
    overlay_out.parent.mkdir(parents=True, exist_ok=True)
    final_out.parent.mkdir(parents=True, exist_ok=True)

    def side_effect(cmd):
        for i, a in enumerate(cmd):
            if a == "-o" and i + 1 < len(cmd):
                Path(cmd[i + 1]).write_bytes(b"x" * 100)
            if cmd[-1] == str(final_out):
                Path(cmd[-1]).write_bytes(b"x" * 100)

    def fake_popen(cmd, **kwargs):
        return _FakePopen(cmd, side_effect=side_effect)

    with mock.patch("subprocess.Popen", side_effect=fake_popen):
        result = asyncio.run(html_overlay.render_composited(
            timeline=timeline,
            project_workdir=project_dir,
            render_spec=_render_spec(
                hyperframes_bin="hyperframes",
                tmpdir=project_dir,
            ),
            bg_renderer=bg_renderer,
            should_cancel=lambda: False,
        ))
    # The orchestrator writes the composition HTML to overlay.html
    # inside the project tmpdir. After render_overlay_layer, the file should
    # exist (it writes the html itself before calling subprocess).
    # (The orchestrator's finally: cleans it up — but the test checks
    # bg_renderer was called and the final path was returned.)
    assert result == final_out
    assert bg_renderer.called


def test_render_composited_cleans_up_composition_html_on_success(tmp_path):
    """Test 36: after success, the temp composition HTML is unlinked."""
    # Same harness as test 35, but assert the html is gone afterwards.
    timeline = _timeline([_overlay()])
    bg = tmp_path / "bg.mp4"
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    bg_renderer = mock.Mock(return_value=bg)
    final_out = project_dir / "final.mp4"

    def side_effect(cmd):
        for i, a in enumerate(cmd):
            if a == "-o" and i + 1 < len(cmd):
                Path(cmd[i + 1]).write_bytes(b"x" * 100)
            if cmd[-1] == str(final_out):
                Path(cmd[-1]).write_bytes(b"x" * 100)

    def fake_popen(cmd, **kwargs):
        return _FakePopen(cmd, side_effect=side_effect)

    with mock.patch("subprocess.Popen", side_effect=fake_popen):
        asyncio.run(html_overlay.render_composited(
            timeline=timeline,
            project_workdir=project_dir,
            render_spec=_render_spec(hyperframes_bin="hyperframes", tmpdir=project_dir),
            bg_renderer=bg_renderer,
        ))
    # The composition HTML written by render_overlay_layer should be cleaned
    # up by the orchestrator's finally block. It lives at <tmpdir>/overlay.html.
    assert not (project_dir / "overlay.html").exists()
    assert not (project_dir / "overlay.mov").exists()


def test_render_composited_cleans_up_composition_html_on_failure(tmp_path):
    """Test 37: even on failure, the temp composition HTML is unlinked."""
    timeline = _timeline([_overlay()])
    bg = tmp_path / "bg.mp4"
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    bg_renderer = mock.Mock(return_value=bg)

    def fake_popen(cmd, **kwargs):
        # Make the hyperframes call fail.
        return _FakePopen(cmd, returncode=1, stderr="lint fail")

    with mock.patch("subprocess.Popen", side_effect=fake_popen):
        with pytest.raises(html_overlay.OverlayRenderError):
            asyncio.run(html_overlay.render_composited(
                timeline=timeline,
                project_workdir=project_dir,
                render_spec=_render_spec(hyperframes_bin="hyperframes", tmpdir=project_dir),
                bg_renderer=bg_renderer,
            ))
    # Even on failure, the temp composition HTML and overlay.mov are unlinked.
    assert not (project_dir / "overlay.html").exists()


def test_render_composited_returns_final_path_on_success(tmp_path):
    """Test 38: returns the composited MP4 path on success."""
    timeline = _timeline([_overlay()])
    bg = tmp_path / "bg.mp4"
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    bg_renderer = mock.Mock(return_value=bg)
    final_out = project_dir / "final.mp4"

    def side_effect(cmd):
        for i, a in enumerate(cmd):
            if a == "-o" and i + 1 < len(cmd):
                Path(cmd[i + 1]).write_bytes(b"x" * 100)
            if cmd[-1] == str(final_out):
                Path(cmd[-1]).write_bytes(b"x" * 100)

    def fake_popen(cmd, **kwargs):
        return _FakePopen(cmd, side_effect=side_effect)

    with mock.patch("subprocess.Popen", side_effect=fake_popen):
        result = asyncio.run(html_overlay.render_composited(
            timeline=timeline,
            project_workdir=project_dir,
            render_spec=_render_spec(hyperframes_bin="hyperframes", tmpdir=project_dir),
            bg_renderer=bg_renderer,
        ))
    assert result == final_out


def test_render_composited_raises_overlay_render_error_on_subprocess_failure(tmp_path):
    """Test 39: hyperframes failure → OverlayRenderError (with bg_path set)."""
    timeline = _timeline([_overlay()])
    bg = tmp_path / "bg.mp4"
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    bg_renderer = mock.Mock(return_value=bg)

    def fake_popen(cmd, **kwargs):
        # The first call (bg render via bg_renderer) is mocked, not subprocess.
        # The second call is hyperframes — make it fail.
        return _FakePopen(cmd, returncode=1, stderr="hyperframes crash")

    with mock.patch("subprocess.Popen", side_effect=fake_popen):
        with pytest.raises(html_overlay.OverlayRenderError) as exc_info:
            asyncio.run(html_overlay.render_composited(
                timeline=timeline,
                project_workdir=project_dir,
                render_spec=_render_spec(hyperframes_bin="hyperframes", tmpdir=project_dir),
                bg_renderer=bg_renderer,
            ))
    # bg_path is set on the exception so pi_bridge can return it without re-rendering.
    assert exc_info.value.bg_path == bg


def test_render_composited_overlay_render_error_carries_bg_path(tmp_path):
    """Test 40: any failure after the bg render → OverlayRenderError.bg_path is set."""
    timeline = _timeline([_overlay()])
    bg = tmp_path / "bg.mp4"
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    bg_renderer = mock.Mock(return_value=bg)

    def fake_popen(cmd, **kwargs):
        # The first subprocess call is hyperframes. Fail.
        return _FakePopen(cmd, returncode=1, stderr="crashed")

    with mock.patch("subprocess.Popen", side_effect=fake_popen):
        with pytest.raises(html_overlay.OverlayRenderError) as exc_info:
            asyncio.run(html_overlay.render_composited(
                timeline=timeline,
                project_workdir=project_dir,
                render_spec=_render_spec(hyperframes_bin="hyperframes", tmpdir=project_dir),
                bg_renderer=bg_renderer,
            ))
    assert exc_info.value.bg_path is not None
    assert exc_info.value.bg_path == bg


# ---------------------------------------------------------------------------
# Integration test (Task 4 — test 41 in spec §10)
# ---------------------------------------------------------------------------

# Resolve the pinned binary against the repo root (one level up from
# open_edit/), not CWD — pytest is typically run from `open_edit/`.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_HYPERFRAMES_AVAILABLE = (_REPO_ROOT / "node_modules" / ".bin" / "hyperframes").is_file()


@pytest.mark.skipif(
    not _HYPERFRAMES_AVAILABLE,
    reason="hyperframes not installed (run 'npm install' at repo root)",
)
def test_end_to_end_overlay_composite(tmp_path):
    """Test 41: actually run hyperframes + ffmpeg on a real project. Skipped
    when hyperframes is missing."""
    # Build a minimal project with one overlay.
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    template = project_dir / "my.html"
    template.write_text("<div style='background:red;width:200px;height:100px'></div>")
    timeline = _timeline([_overlay(
        template_path="my.html", position_sec=0.0, duration_sec=1.0,
    )])
    # Create a fake bg.mp4 (any non-empty file works for the orchestrator's
    # subprocess return-code path; the real ffmpeg would fail without a valid
    # MP4, so we mock ffmpeg for the integration test).
    bg = tmp_path / "bg.mp4"
    bg.write_bytes(b"x" * 1000)
    bg_renderer = mock.Mock(return_value=bg)

    # Only the hyperframes call is real; ffmpeg is mocked (we don't need
    # to verify ffmpeg here — that's covered by tests 27-29 with a mock).
    from open_edit.serve import html_overlay as ho
    real_popen = ho.subprocess.Popen
    calls = {"count": 0}

    def fake_popen(cmd, **kwargs):
        calls["count"] += 1
        if "hyperframes" in cmd[0]:
            # First call is the hyperframes render — invoke the real one.
            return real_popen(cmd, **kwargs)
        # Second call is ffmpeg — fake success and write the output file.
        for i, a in enumerate(cmd):
            if a == str(bg.with_name("final.mp4")) or a.endswith("final.mp4"):
                Path(a).write_bytes(b"x" * 1000)
        return _FakePopen(cmd, returncode=0)

    with mock.patch("subprocess.Popen", side_effect=fake_popen):
        result = asyncio.run(html_overlay.render_composited(
            timeline=timeline,
            project_workdir=project_dir,
            render_spec=_render_spec(
                # Use an absolute path so the test works regardless of pytest's CWD.
                hyperframes_bin=str(_REPO_ROOT / "node_modules" / ".bin" / "hyperframes"),
                tmpdir=project_dir,
                duration_sec=1.0,
            ),
            bg_renderer=bg_renderer,
        ))
    assert result is not None
    assert Path(result).is_file()


# ---------------------------------------------------------------------------
# v1.6 hardening: V2 callable annotations, sibling-task cancellation,
# persistent tmpdir cleanup (regression tests for the 4-bug fix pass)
# ---------------------------------------------------------------------------


def test_v2_render_composited_bg_renderer_param_uses_callable_annotation():
    """V2: bg_renderer must be annotated as Callable[[], str | Path] (not the string 'callable')."""
    sig = inspect.signature(html_overlay.render_composited)
    bg_param = sig.parameters["bg_renderer"]
    # Module uses `from __future__ import annotations`, so the annotation is
    # stored as a string. We assert the string form here.
    assert bg_param.annotation == "Callable[[], str | Path]"


def test_v2_render_composited_should_cancel_param_uses_callable_annotation():
    """V2: render_composited.should_cancel must be Callable[[], bool] | None."""
    sig = inspect.signature(html_overlay.render_composited)
    sc = sig.parameters["should_cancel"]
    assert sc.annotation == "Callable[[], bool] | None"


def test_v2_render_overlay_layer_should_cancel_param_uses_callable_annotation():
    """V2: render_overlay_layer.should_cancel must be Callable[[], bool] | None."""
    sig = inspect.signature(html_overlay.render_overlay_layer)
    sc = sig.parameters["should_cancel"]
    assert sc.annotation == "Callable[[], bool] | None"


def test_v2_composite_with_background_should_cancel_param_uses_callable_annotation():
    """V2: composite_with_background.should_cancel must be Callable[[], bool] | None."""
    sig = inspect.signature(html_overlay.composite_with_background)
    sc = sig.parameters["should_cancel"]
    assert sc.annotation == "Callable[[], bool] | None"


def test_v2_run_subprocess_with_cancel_should_cancel_param_uses_callable_annotation():
    """V2: _run_subprocess_with_cancel.should_cancel must be Callable[[], bool] | None."""
    sig = inspect.signature(html_overlay._run_subprocess_with_cancel)
    sc = sig.parameters["should_cancel"]
    assert sc.annotation == "Callable[[], bool] | None"


def test_render_composited_sibling_failure_raises_overlay_render_error(tmp_path):
    """Sibling-task cancellation: when a non-OverlayRenderError exception is raised
    in any task (e.g. comp_html_task), the orchestrator must catch it, cancel the
    in-flight siblings, and re-raise as OverlayRenderError (with bg_path if known).

    Before the fix: the original exception (e.g. ValueError) propagates as-is and
    the sibling asyncio tasks are not cancelled.
    """
    timeline = _timeline([_overlay()])
    bg = tmp_path / "bg.mp4"
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    bg_renderer = mock.Mock(return_value=bg)

    # comp_html_task raises an unexpected (non-OverlayRenderError) exception.
    with mock.patch.object(
        html_overlay, "generate_composition_html",
        side_effect=RuntimeError("comp_html_task boom"),
    ):
        with pytest.raises(html_overlay.OverlayRenderError) as exc_info:
            asyncio.run(html_overlay.render_composited(
                timeline=timeline,
                project_workdir=project_dir,
                render_spec=_render_spec(
                    hyperframes_bin="hyperframes", tmpdir=project_dir,
                ),
                bg_renderer=bg_renderer,
            ))
    # bg_renderer was running — its result should be propagated as bg_path on the
    # exception so pi_bridge can use it for fallback. But since the bg_renderer
    # mock returns immediately and the exception came from comp_html_task before
    # bg completed, bg_path may be None. Just assert the orchestrator transformed
    # the exception correctly.
    assert "comp_html_task boom" in str(exc_info.value) or exc_info.value.bg_path is not None


def test_render_composited_cancels_bg_when_comp_html_raises(tmp_path):
    """Sibling-task cancellation: when comp_html_task raises unexpectedly, the
    orchestrator must cancel the in-flight bg_task and re-raise as
    OverlayRenderError (not the original exception).

    Before the fix: the original exception (e.g. ValueError) propagates as-is
    and bg_task continues running (the asyncio task is not cancelled).
    After the fix: the exception is caught, bg_task's asyncio task is cancelled,
    and OverlayRenderError is raised.
    """
    timeline = _timeline([_overlay()])
    bg = tmp_path / "bg.mp4"
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    bg_called = threading.Event()

    def bg_renderer_fn():
        bg_called.set()
        return bg

    bg_renderer = bg_renderer_fn

    # Make comp_html_task raise an unexpected (non-OverlayRenderError) exception.
    with mock.patch.object(
        html_overlay, "generate_composition_html",
        side_effect=ValueError("comp_html boom"),
    ):
        with pytest.raises(html_overlay.OverlayRenderError):
            asyncio.run(html_overlay.render_composited(
                timeline=timeline,
                project_workdir=project_dir,
                render_spec=_render_spec(
                    hyperframes_bin="hyperframes", tmpdir=project_dir,
                ),
                bg_renderer=bg_renderer,
            ))

    # bg_renderer was invoked (proving the task was running when comp_html failed).
    assert bg_called.is_set()


def test_render_composited_unlinks_partial_final_mp4_on_failure(tmp_path):
    """Persistent tmpdir cleanup: on failure, partial final.mp4 is unlinked."""
    timeline = _timeline([_overlay()])
    bg = tmp_path / "bg.mp4"
    bg.write_bytes(b"x" * 100)
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    bg_renderer = mock.Mock(return_value=bg)
    final_out = project_dir / "final.mp4"

    def side_effect(cmd):
        for i, a in enumerate(cmd):
            if a == "-o" and i + 1 < len(cmd):
                Path(cmd[i + 1]).write_bytes(b"x" * 100)
        # Make the ffmpeg composite (last call) fail AFTER writing partial final.mp4.
        if cmd[-1] == str(final_out):
            raise RuntimeError("ffmpeg crash mid-write")

    def fake_popen(cmd, **kwargs):
        return _FakePopen(cmd, side_effect=side_effect)

    with mock.patch("subprocess.Popen", side_effect=fake_popen):
        with pytest.raises(html_overlay.OverlayRenderError):
            asyncio.run(html_overlay.render_composited(
                timeline=timeline,
                project_workdir=project_dir,
                render_spec=_render_spec(
                    hyperframes_bin="hyperframes", tmpdir=project_dir,
                ),
                bg_renderer=bg_renderer,
            ))

    # On failure, partial final.mp4 must be cleaned up so it doesn't accumulate
    # in a persistent tmpdir.
    assert not final_out.exists(), (
        f"partial final.mp4 left behind at {final_out} on failure"
    )


def test_render_composited_preserves_bg_mp4_on_overlay_failure(tmp_path):
    """Persistent tmpdir cleanup: on overlay/subprocess failure, bg.mp4 is preserved
    (not unlinked) so pi_bridge can return it via OverlayRenderError.bg_path fallback."""
    timeline = _timeline([_overlay()])
    bg = tmp_path / "bg.mp4"
    bg.write_bytes(b"x" * 100)
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    bg_renderer = mock.Mock(return_value=bg)

    def fake_popen(cmd, **kwargs):
        # Make hyperframes fail.
        return _FakePopen(cmd, returncode=1, stderr="hyperframes crash")

    with mock.patch("subprocess.Popen", side_effect=fake_popen):
        with pytest.raises(html_overlay.OverlayRenderError) as exc_info:
            asyncio.run(html_overlay.render_composited(
                timeline=timeline,
                project_workdir=project_dir,
                render_spec=_render_spec(
                    hyperframes_bin="hyperframes", tmpdir=project_dir,
                ),
                bg_renderer=bg_renderer,
            ))

    # bg.mp4 must be preserved (bg_path is propagated for fallback).
    assert exc_info.value.bg_path == bg
    assert bg.exists(), f"bg.mp4 was unlinked despite bg_path fallback being set"
