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
