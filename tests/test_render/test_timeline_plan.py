"""Tests for explicit source-media selection during render planning."""
from __future__ import annotations

from pathlib import Path

import pytest

from open_edit.ir.types import AddClipOp, Asset, Clip, Timeline, Track
from open_edit.render.timeline_plan import (
    build_render_plan,
    source_media_policy_for,
)
from open_edit.storage.assets import AssetStore


SOURCE_PROXY_PROFILE = "source_proxy_360_v1"


def _seed_asset(
    tmp_path: Path,
    *,
    with_proxy: bool,
) -> tuple[AssetStore, Asset, Path | None]:
    store = AssetStore(tmp_path / ".open_edit" / "assets")
    asset_hash = "a" * 64
    source_path = store._cas_path(asset_hash)
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"canonical source")

    proxy_hash = "b" * 64
    proxy_path = store._cas_path(proxy_hash)
    if with_proxy:
        proxy_path.parent.mkdir(parents=True, exist_ok=True)
        proxy_path.write_bytes(b"derived source proxy")

    asset = Asset(
        asset_hash=asset_hash,
        original_path=str(tmp_path / "source.mp4"),
        stored_path=str(source_path),
        type="video",
        duration_sec=1.0,
        fps=30.0,
        width=1920,
        height=1080,
        proxy_hash=proxy_hash if with_proxy else None,
        proxy_profile=SOURCE_PROXY_PROFILE if with_proxy else None,
        proxy_status="ready" if with_proxy else "none",
    )
    store._sidecar_path(asset_hash).write_text(asset.model_dump_json())
    return store, asset, proxy_path if with_proxy else None


def _timeline_for_asset(asset_hash: str) -> tuple[Timeline, list[AddClipOp]]:
    op = AddClipOp(
        author="user",
        asset_hash=asset_hash,
        track_id="v1",
        position_sec=0.0,
        in_point_sec=0.0,
        out_point_sec=1.0,
    )
    timeline = Timeline(
        duration_sec=1.0,
        tracks=[
            Track(
                track_id="v1",
                kind="video",
                clips=[
                    Clip(
                        clip_id=op.clip_id,
                        asset_hash=asset_hash,
                        track_id="v1",
                        track_kind="video",
                        position_sec=0.0,
                        in_point_sec=0.0,
                        out_point_sec=1.0,
                    )
                ],
            )
        ],
    )
    return timeline, [op]


@pytest.mark.parametrize(
    ("emission_profile", "policy"),
    [
        ("final", "original"),
        ("review-artifact", "proxy"),
        ("proxy-edit", "proxy"),
        ("preview-chunk", "proxy"),
    ],
)
def test_source_media_policy_is_explicit(
    emission_profile: str,
    policy: str,
) -> None:
    assert source_media_policy_for(emission_profile) == policy


def test_preview_chunk_uses_ready_source_proxy(tmp_path: Path) -> None:
    store, asset, proxy_path = _seed_asset(tmp_path, with_proxy=True)
    timeline, ops = _timeline_for_asset(asset.asset_hash)

    plan = build_render_plan(
        timeline,
        ops,
        store,
        "proxy",
        emission_profile="preview-chunk",
        enqueue_missing_proxies=False,
    )

    assert plan.source_media_policy == "proxy"
    assert plan.source_proxy_hits[asset.asset_hash] == asset.proxy_hash
    assert plan.asset_paths[asset.asset_hash] == str(proxy_path)


def test_final_plan_uses_original_even_when_proxy_is_ready(tmp_path: Path) -> None:
    store, asset, proxy_path = _seed_asset(tmp_path, with_proxy=True)
    timeline, ops = _timeline_for_asset(asset.asset_hash)

    plan = build_render_plan(
        timeline,
        ops,
        store,
        "final",
        emission_profile="final",
        enqueue_missing_proxies=False,
    )

    assert plan.source_media_policy == "original"
    assert plan.asset_paths[asset.asset_hash] == asset.stored_path
    assert str(proxy_path) not in plan.asset_paths.values()


def test_review_artifact_uses_ready_source_proxy(tmp_path: Path) -> None:
    store, asset, proxy_path = _seed_asset(tmp_path, with_proxy=True)
    timeline, ops = _timeline_for_asset(asset.asset_hash)

    plan = build_render_plan(
        timeline,
        ops,
        store,
        "proxy",
        emission_profile="review-artifact",
        enqueue_missing_proxies=False,
    )

    assert plan.source_media_policy == "proxy"
    assert plan.source_proxy_hits[asset.asset_hash] == asset.proxy_hash
    assert plan.asset_paths[asset.asset_hash] == str(proxy_path)
    assert plan.asset_paths[asset.asset_hash] != asset.stored_path


def test_review_artifact_missing_proxy_falls_back_and_queues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset_proxy_jobs = pytest.importorskip("open_edit.kernel.asset_proxy_jobs")
    store, asset, _ = _seed_asset(tmp_path, with_proxy=False)
    timeline, ops = _timeline_for_asset(asset.asset_hash)
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(
        asset_proxy_jobs.DEFAULT_ASSET_PROXY_JOB_SERVICE,
        "enqueue",
        lambda project_id, project_path, asset_hash, profile: (
            calls.append((asset_hash, profile.name)) or object()
        ),
    )

    plan = build_render_plan(
        timeline,
        ops,
        store,
        "proxy",
        emission_profile="review-artifact",
        enqueue_missing_proxies=True,
    )

    # Safety: a missing proxy must never block the preview. The plan falls
    # back to canonical bytes and queues generation for the next render.
    assert plan.source_media_policy == "proxy"
    assert plan.source_proxy_fallbacks[asset.asset_hash] == "queued"
    assert plan.asset_paths[asset.asset_hash] == asset.stored_path
    assert calls == [(asset.asset_hash, SOURCE_PROXY_PROFILE)]


def test_missing_preview_proxy_falls_back_and_queues_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset_proxy_jobs = pytest.importorskip("open_edit.kernel.asset_proxy_jobs")
    store, asset, _ = _seed_asset(tmp_path, with_proxy=False)
    timeline, ops = _timeline_for_asset(asset.asset_hash)
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(
        asset_proxy_jobs.DEFAULT_ASSET_PROXY_JOB_SERVICE,
        "enqueue",
        lambda project_id, project_path, asset_hash, profile: (
            calls.append((asset_hash, profile.name)) or object()
        ),
    )

    plan = build_render_plan(
        timeline,
        ops,
        store,
        "proxy",
        emission_profile="proxy-edit",
        enqueue_missing_proxies=True,
    )

    assert plan.source_proxy_fallbacks[asset.asset_hash] == "queued"
    assert plan.asset_paths[asset.asset_hash] == asset.stored_path
    assert calls == [(asset.asset_hash, SOURCE_PROXY_PROFILE)]


def test_cuda_fastpath_command_builds_with_proxy_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CUDA fast path consumes asset_paths, so a resolved 360p proxy
    (full-length, offsets preserved) flows straight into the ffmpeg command:
    ``-i <proxy>`` + ``-ss`` trim + ``scale_cuda=640:360`` (identity/upscale
    for a 360p source proxy rendered at the 640x360 review-artifact size)."""
    from open_edit.render import cuda_fastpath
    from open_edit.render.cuda_fastpath import build_cuda_fastpath_command
    from open_edit.render.encoder import EncoderSpec
    from open_edit.render.profiles import RenderProfile

    proxy_file = (
        Path(__file__).resolve().parents[1] / "testdata" / "raw_videos" / "clip_a.mp4"
    )
    if not proxy_file.is_file():
        pytest.skip("clip_a.mp4 missing")

    monkeypatch.setattr(cuda_fastpath, "_cuda_probe", lambda: True)

    # Sliced timeline: clip covers the whole (trimmed) duration, so the
    # in-point trim is expressed with -ss and the proxy's full-length
    # offsets hold.
    timeline = Timeline(
        duration_sec=1.0,
        tracks=[
            Track(
                track_id="v1",
                kind="video",
                clips=[
                    Clip(
                        clip_id="c1",
                        asset_hash="h1",
                        track_id="v1",
                        track_kind="video",
                        position_sec=0.0,
                        in_point_sec=0.5,
                        out_point_sec=1.5,
                    )
                ],
            )
        ],
    )
    profile = RenderProfile(
        name="fast_proxy",
        width=640,
        height=360,
        frame_rate_num=30,
        frame_rate_den=1,
        scale=None,
    )
    cmd = build_cuda_fastpath_command(
        timeline,
        {"h1": str(proxy_file)},
        tmp_path / "out.mp4",
        profile,
        EncoderSpec("h264_nvenc", (), ()),
    )
    assert cmd is not None
    assert str(proxy_file) in cmd
    assert "-ss" in cmd and "0.500000" in cmd
    assert any("scale_cuda=640:360" in part for part in cmd)
