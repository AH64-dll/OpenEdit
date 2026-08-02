"""Tests for per-asset source-proxy generation."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from open_edit.render import source_proxy
from open_edit.render.source_proxy import (
    DEFAULT_SOURCE_PROXY_PROFILE,
    SourceProxyProfile,
    generate_asset_proxy,
)
from open_edit.storage.assets import AssetStore


pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg and ffprobe are required",
)


def _run_ffmpeg(*args: str) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args],
        capture_output=True,
        text=True,
        check=True,
    )


def make_video_fixture(path: Path, *, width: int, height: int, duration: float = 1.0) -> Path:
    _run_ffmpeg(
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size={width}x{height}:rate=24:duration={duration}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(path),
    )
    return path


def make_audio_fixture(path: Path, *, duration: float = 1.0) -> Path:
    _run_ffmpeg(
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:duration={duration}",
        "-c:a",
        "pcm_s16le",
        str(path),
    )
    return path


def make_image_fixture(path: Path, *, width: int, height: int) -> Path:
    _run_ffmpeg(
        "-f",
        "lavfi",
        "-i",
        f"color=c=blue:s={width}x{height}:d=1",
        "-frames:v",
        "1",
        str(path),
    )
    return path


def fail_if_called(*args, **kwargs):
    raise AssertionError("ffmpeg should not run for a reusable source proxy")


def test_source_proxy_profile_fingerprint_is_stable() -> None:
    profile = SourceProxyProfile(
        name="custom",
        height=240,
        vcodec="libx264",
        crf=30,
        preset="fast",
        acodec="aac",
        audio_bitrate="64k",
        version=2,
    )

    assert profile.fingerprint() == (
        "custom:v2:h240:libx264:crf=30:preset=fast:aac:64k"
    )


def test_asset_proxy_fields_round_trip_through_sidecar(tmp_path: Path) -> None:
    store = AssetStore(tmp_path / ".open_edit" / "assets")
    source = make_video_fixture(tmp_path / "source.mp4", width=1920, height=1080)
    asset = store.ingest(str(source), transcribe=False)

    updated = store.update_proxy_metadata(
        asset.asset_hash,
        proxy_hash="b" * 64,
        profile="source_proxy_360_v1",
        status="ready",
    )
    loaded = store.get(asset.asset_hash)

    assert loaded is not None
    assert loaded.proxy_hash == "b" * 64
    assert loaded.proxy_profile == "source_proxy_360_v1"
    assert loaded.proxy_status == "ready"
    assert updated.proxy_updated_at


def test_generate_asset_proxy_writes_low_res_hash_and_links_source(
    tmp_path: Path,
) -> None:
    source = make_video_fixture(tmp_path / "source.mp4", width=1920, height=1080)
    store = AssetStore(tmp_path / ".open_edit" / "assets")
    asset = store.ingest(str(source), transcribe=False)

    result = generate_asset_proxy(tmp_path, asset.asset_hash)

    assert result.status == "ready"
    assert result.proxy_hash is not None
    assert store.path(result.proxy_hash) is not None
    linked = store.get(asset.asset_hash)
    assert linked is not None
    assert linked.proxy_hash == result.proxy_hash
    assert linked.proxy_profile == DEFAULT_SOURCE_PROXY_PROFILE.name

    proxy_asset = store.get(result.proxy_hash)
    assert proxy_asset is not None
    assert proxy_asset.height <= 360
    assert proxy_asset.duration_sec == pytest.approx(asset.duration_sec, abs=0.2)
    assert store._sidecar_path(result.proxy_hash).exists() is False


def test_generate_asset_proxy_reuses_matching_ready_proxy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = make_video_fixture(tmp_path / "source.mp4", width=1920, height=1080)
    store = AssetStore(tmp_path / ".open_edit" / "assets")
    asset = store.ingest(str(source), transcribe=False)
    first = generate_asset_proxy(tmp_path, asset.asset_hash)

    monkeypatch.setattr(source_proxy.subprocess, "run", fail_if_called)
    second = generate_asset_proxy(tmp_path, asset.asset_hash)

    assert second.status == "ready"
    assert second.proxy_hash == first.proxy_hash


def test_source_proxy_does_not_proxy_audio_or_alpha_sources(tmp_path: Path) -> None:
    audio = make_audio_fixture(tmp_path / "voice.wav")
    store = AssetStore(tmp_path / ".open_edit" / "assets")
    asset = store.ingest(str(audio), transcribe=False)

    result = generate_asset_proxy(tmp_path, asset.asset_hash)

    assert result.status == "not_needed"
    assert result.proxy_hash is None
    loaded = store.get(asset.asset_hash)
    assert loaded is not None
    assert loaded.proxy_status == "not_needed"


def test_source_proxy_does_not_proxy_small_video(tmp_path: Path) -> None:
    source = make_video_fixture(tmp_path / "small.mp4", width=320, height=240)
    store = AssetStore(tmp_path / ".open_edit" / "assets")
    asset = store.ingest(str(source), transcribe=False)

    result = generate_asset_proxy(tmp_path, asset.asset_hash)

    assert result.status == "not_needed"
    assert result.proxy_hash is None
    loaded = store.get(asset.asset_hash)
    assert loaded is not None
    assert loaded.proxy_status == "not_needed"


def test_source_proxy_does_not_proxy_images(tmp_path: Path) -> None:
    source = make_image_fixture(tmp_path / "still.png", width=1920, height=1080)
    store = AssetStore(tmp_path / ".open_edit" / "assets")
    asset = store.ingest(str(source), transcribe=False)

    result = generate_asset_proxy(tmp_path, asset.asset_hash)

    assert asset.type == "image"
    assert result.status == "not_needed"
    assert result.proxy_hash is None


def test_source_proxy_failure_keeps_original_and_records_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = make_video_fixture(tmp_path / "source.mp4", width=1920, height=1080)
    store = AssetStore(tmp_path / ".open_edit" / "assets")
    asset = store.ingest(str(source), transcribe=False)
    monkeypatch.setattr(
        source_proxy.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args, 1, stdout="", stderr="encoder failed",
        ),
    )

    result = generate_asset_proxy(tmp_path, asset.asset_hash)

    assert result.status == "failed"
    assert result.proxy_hash is None
    linked = store.get(asset.asset_hash)
    assert linked is not None
    assert linked.proxy_status == "failed"
    assert "encoder failed" in linked.proxy_error
    assert store.path(asset.asset_hash) is not None


def test_source_proxy_missing_asset_returns_structured_failure(tmp_path: Path) -> None:
    result = generate_asset_proxy(tmp_path, "a" * 64)

    assert result.status == "failed"
    assert result.proxy_hash is None
    assert result.output_path is None
    assert result.error
