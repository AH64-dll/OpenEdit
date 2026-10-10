from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from open_edit.agent.tools.pyagent_timeline_ops import add_hyperframes_overlay
from open_edit.ir.types import HtmlOverlay, Timeline
from open_edit.render.hyperframes import materialize_hyperframes_overlays


@pytest.fixture(autouse=True)
def _stub_engine_identity(monkeypatch):
    # Cache tests mock the renderer and must not require an installed engine.
    monkeypatch.setattr("open_edit.render.hyperframes._hyperframes_bin", lambda: "test-hyperframes")


def _timeline(template: str) -> Timeline:
    return Timeline(
        overlays=[
            HtmlOverlay(
                overlay_id="overlay-1",
                template_path=template,
                variables={"title": "Hello"},
                position_sec=1.0,
                duration_sec=2.0,
            )
        ],
        duration_sec=4.0,
    )


def test_native_materializer_reuses_content_addressed_output(tmp_path: Path) -> None:
    (tmp_path / ".open_edit").mkdir()
    (tmp_path / "title.html").write_text(
        '<div id="title">{{title}}</div>', encoding="utf-8"
    )

    def fake_render(_composition: Path, output: Path, _spec: dict) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"hyperframes-output")

    with patch(
        "open_edit.render.hyperframes.render_overlay_layer",
        side_effect=fake_render,
    ) as render:
        first = materialize_hyperframes_overlays(
            _timeline("title.html"), tmp_path, width=640, height=360, fps=30
        )
        second = materialize_hyperframes_overlays(
            _timeline("title.html"), tmp_path, width=640, height=360, fps=30
        )

    assert first is not None and first.cache_hit is False
    assert second is not None and second.cache_hit is True
    assert second.output_path == first.output_path
    assert render.call_count == 1


def test_native_materializer_changes_key_when_template_changes(tmp_path: Path) -> None:
    (tmp_path / ".open_edit").mkdir()
    template = tmp_path / "title.html"
    template.write_text('<div id="title">one</div>', encoding="utf-8")

    def fake_render(_composition: Path, output: Path, _spec: dict) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"x")

    with patch(
        "open_edit.render.hyperframes.render_overlay_layer",
        side_effect=fake_render,
    ) as render:
        first = materialize_hyperframes_overlays(
            _timeline("title.html"), tmp_path, width=320, height=180, fps=30
        )
        template.write_text('<div id="title">two</div>', encoding="utf-8")
        second = materialize_hyperframes_overlays(
            _timeline("title.html"), tmp_path, width=320, height=180, fps=30
        )

    assert first is not None and second is not None
    assert first.content_hash != second.content_hash
    assert render.call_count == 2


def test_hyperframes_tool_rejects_template_escape(tmp_path: Path) -> None:
    (tmp_path / ".open_edit").mkdir()
    result = add_hyperframes_overlay(
        {
            "template_path": "../outside.html",
            "position_sec": 0,
            "duration_sec": 1,
        },
        str(tmp_path),
    )
    assert result["status"] == "error"
    assert "inside project" in result["error"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell stub")
def test_overlay_returns_compact_hyperframes_lint(tmp_path: Path, monkeypatch) -> None:
    report = {"ok": False, "errorCount": 1, "warningCount": 0, "findings": [{
        "code": "media_missing_data_start", "severity": "error", "message": "no data-start",
        "fixHint": "Add data-start", "elementId": "a-roll", "snippet": "<video ...>", "file": "/x/index.html"}],
        "_meta": {"version": "0.7.65"}}
    stub = tmp_path / "hyperframes"
    stub.write_text(f"#!/bin/sh\ncat <<'JSON'\n{json.dumps(report)}\nJSON\n", encoding="utf-8")
    stub.chmod(0o755)
    monkeypatch.setenv("OPEN_EDIT_HYPERFRAMES_BIN", str(stub))
    (tmp_path / ".open_edit").mkdir()
    (tmp_path / "title.html").write_text("<div>title</div>", encoding="utf-8")
    with patch("open_edit.agent.tools.pyagent_timeline_ops.make_ir"):
        result = add_hyperframes_overlay(
            {"template_path": "title.html", "position_sec": 0, "duration_sec": 1}, str(tmp_path))
    assert result["lint"] == {"status": "issues", "errors": 1, "warnings": 0, "findings": [{
        "severity": "error", "code": "media_missing_data_start", "message": "no data-start",
        "fixHint": "Add data-start", "elementId": "a-roll"}]}
    assert "fixHint" in result["next"]


def test_lint_reports_unavailable_engine(tmp_path: Path, monkeypatch) -> None:
    from open_edit.render import html_overlay

    def missing() -> str:
        raise html_overlay.OverlayRenderError("HyperFrames binary not found")

    monkeypatch.setattr(html_overlay, "_resolve_hyperframes_bin", missing)
    (tmp_path / "t.html").write_text("<div/>", encoding="utf-8")
    assert html_overlay.lint_composition(tmp_path / "t.html")["status"] == "unavailable"
