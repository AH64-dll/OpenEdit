"""Tests for the list_assets tool (Wave 1.2)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from open_edit.agent.tools.pyagent_list_assets import list_assets


def test_list_assets_returns_empty_for_empty_project() -> None:
    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)
        (workdir / ".open_edit" / "assets").mkdir(parents=True)
        result = list_assets({}, str(workdir))
        assert result == {"assets": []}


def test_list_assets_returns_ingested_assets() -> None:
    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)
        assets_root = workdir / ".open_edit" / "assets"
        assets_root.mkdir(parents=True)

        hash_hex = "a" * 64
        prefix_dir = assets_root / hash_hex[:2]
        prefix_dir.mkdir(exist_ok=True)
        sidecar = {
            "asset_hash": hash_hex,
            "original_path": "/tmp/my_video.mp4",
            "duration_sec": 42.5,
            "type": "video",
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "codec": "h264",
            "has_audio": True,
        }
        (prefix_dir / f"{hash_hex}.meta.json").write_text(json.dumps(sidecar))

        result = list_assets({}, str(workdir))
        assert len(result["assets"]) == 1
        a = result["assets"][0]
        assert a["hash"] == hash_hex
        assert a["filename"] == "my_video.mp4"
        assert a["duration_s"] == 42.5
        assert a["type"] == "video"
        assert a["width"] == 1920
        assert a["height"] == 1080
        assert a["has_audio"] is True


def test_list_assets_skips_invalid_sidecars() -> None:
    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)
        assets_root = workdir / ".open_edit" / "assets" / "ff"
        assets_root.mkdir(parents=True)
        (assets_root / "dead.meta.json").write_text("not-json")
        result = list_assets({}, str(workdir))
        assert result == {"assets": []}


def test_list_assets_no_assets_dir_is_empty() -> None:
    with tempfile.TemporaryDirectory() as td:
        result = list_assets({}, td)
        assert result == {"assets": []}
