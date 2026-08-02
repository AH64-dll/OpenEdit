"""Tests for unrestricted ingest_local path access and CAS ingest."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from open_edit.agent.tools.pyagent_ingest_local import ingest_local


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / ".open_edit" / "assets").mkdir(parents=True)
    return root


def test_ingest_local_rejects_relative_path(project: Path) -> None:
    result = ingest_local({"paths": ["relative/clip.mp4"]}, str(project))
    assert result["status"] == "error"
    assert result["count"] == 0
    assert "absolute" in result["errors"][0]["error"]


def test_ingest_local_accepts_any_folder(project: Path, tmp_path: Path) -> None:
    outsider = tmp_path / "outside.mp4"
    outsider.write_bytes(b"not-really-mp4")
    fake_asset = MagicMock(
        asset_hash="outside123",
        duration_sec=1.0,
        type="video",
        has_audio=False,
        alignment=[],
    )
    with patch("open_edit.agent.tools.pyagent_ingest_local.get_asset_store") as gas:
        store = MagicMock()
        store.ingest.return_value = fake_asset
        gas.return_value = store
        result = ingest_local(
            {"paths": [str(outsider)], "transcribe": False}, str(project),
        )
    assert result["status"] == "ok"
    assert result["count"] == 1
    store.ingest.assert_called_once_with(str(outsider.resolve()), transcribe=False)


def test_ingest_local_allows_project_path(project: Path) -> None:
    media = project / "clip.mp4"
    media.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32)
    fake_asset = MagicMock(
        asset_hash="abc123",
        duration_sec=1.5,
        type="video",
        has_audio=True,
        alignment=[],
    )
    with patch("open_edit.agent.tools.pyagent_ingest_local.get_asset_store") as gas:
        store = MagicMock()
        store.ingest.return_value = fake_asset
        gas.return_value = store
        result = ingest_local(
            {"paths": [str(media)], "transcribe": False}, str(project),
        )
    assert result["status"] == "ok"
    assert result["count"] == 1
    assert result["ingested"][0]["hash"] == "abc123"
    store.ingest.assert_called_once_with(str(media.resolve()), transcribe=False)


def test_ingest_local_follows_symlink(project: Path, tmp_path: Path) -> None:
    source_dir = tmp_path / "videos"
    source_dir.mkdir()
    media = source_dir / "talk.mp4"
    media.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32)
    link = project / "linked-talk.mp4"
    try:
        link.symlink_to(media)
    except OSError:
        pytest.skip("symlinks unavailable on this platform")
    fake_asset = MagicMock(
        asset_hash="def456",
        duration_sec=2.0,
        type="video",
        has_audio=True,
        alignment=[1, 2],
    )
    with patch("open_edit.agent.tools.pyagent_ingest_local.get_asset_store") as gas:
        store = MagicMock()
        store.ingest.return_value = fake_asset
        gas.return_value = store
        result = ingest_local({"paths": [str(link)], "transcribe": False}, str(project))
    assert result["status"] == "ok"
    assert result["ingested"][0]["words"] == 2
    store.ingest.assert_called_once_with(str(media.resolve()), transcribe=False)
