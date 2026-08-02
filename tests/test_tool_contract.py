"""Tests for the canonical tool result contract (open_edit/agent/tools/_contract.py).

Shapes: success ``{"status": "ok", ...}``; error ``{"status": "error", "error": str(e)}``;
retry ``{"status": "retry", "error": "..."}``. ``@tool_result`` normalizes exceptions;
``get_asset_or_error`` / ``require_alignment`` produce the canonical asset lookup and
alignment-pending dicts used by every tool wrapper (Tasks 4.2-4.4 migrate tools onto them).
"""
from __future__ import annotations

import json
from pathlib import Path

from open_edit.agent.tools._contract import (
    ToolError,
    ToolRetryableError,
    get_asset_or_error,
    require_alignment,
    tool_result,
)


def test_tool_result_wraps_success():
    @tool_result
    def ok(args, project_path):
        return {"status": "ok", "data": 1}
    assert ok({}, "/tmp") == {"status": "ok", "data": 1}


def test_tool_result_catches_exception():
    @tool_result
    def boom(args, project_path):
        raise ValueError("nope")
    res = boom({}, "/tmp")
    assert res["status"] == "error" and "nope" in res["error"]


def test_tool_result_marks_retryable():
    @tool_result
    def retry(args, project_path):
        raise ToolRetryableError("try later")
    res = retry({}, "/tmp")
    assert res["status"] == "retry" and "try later" in res["error"]


def test_tool_result_logs_exception(caplog):
    @tool_result
    def boom(args, project_path):
        raise ValueError("logged")
    boom({}, "/tmp")
    assert any("logged" in r.message for r in caplog.records)


def test_tool_result_preserves_metadata():
    @tool_result
    def ok(args, project_path):
        """docstring here"""
        return {"status": "ok"}
    assert ok.__name__ == "ok"
    assert ok.__doc__ == "docstring here"


def test_tool_result_plain_tool_error_is_error_status():
    @tool_result
    def boom(args, project_path):
        raise ToolError("plain failure")
    res = boom({}, "/tmp")
    assert res["status"] == "error" and "plain failure" in res["error"]


def _write_asset(tmp_path: Path, asset_hash: str, alignment: list) -> None:
    """Write a CAS file + sidecar so AssetStore.get() returns a full Asset."""
    assets_root = tmp_path / ".open_edit" / "assets" / asset_hash[:2]
    assets_root.mkdir(parents=True)
    sidecar = {
        "asset_hash": asset_hash,
        "original_path": "/tmp/clip.mp4",
        "stored_path": str(assets_root / asset_hash),
        "duration_sec": 42.5,
        "type": "video",
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "codec": "h264",
        "has_audio": True,
        "alignment": alignment,
    }
    (assets_root / asset_hash).write_bytes(b"x")
    (assets_root / f"{asset_hash}.meta.json").write_text(json.dumps(sidecar))


def test_get_asset_or_error_found(tmp_path: Path):
    _write_asset(tmp_path, "abc123", [])
    asset, err = get_asset_or_error(str(tmp_path), "abc123")
    assert asset is not None and asset.asset_hash == "abc123"
    assert err is None


def test_get_asset_or_error_not_found(tmp_path: Path):
    asset, err = get_asset_or_error(str(tmp_path), "nonexistent")
    assert asset is None
    assert err is not None
    assert err["status"] == "error"
    assert "not found" in err["error"]


def test_require_alignment_aligned(tmp_path: Path):
    _write_asset(tmp_path, "abc123", [{"word": "hi", "t_start": 0.0, "t_end": 0.4}])
    asset, err = get_asset_or_error(str(tmp_path), "abc123")
    assert err is None
    assert require_alignment(asset) is None


def test_require_alignment_pending(tmp_path: Path):
    _write_asset(tmp_path, "abc123", [])
    asset, err = get_asset_or_error(str(tmp_path), "abc123")
    assert err is None
    err = require_alignment(asset)
    assert err is not None
    assert err["status"] == "retry"
    assert "alignment" in err["error"]


def test_packaged_skill_matches_canonical_preview_section():
    repo_root = Path(__file__).resolve().parents[1]
    paths = [
        repo_root / "skills" / "open-edit-mcp.md",
        repo_root / "open_edit" / "harness_skills" / "open-edit-mcp.md",
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "`preview-chunks`" in text
        assert "sequential" in text
        assert "same-range" in text
