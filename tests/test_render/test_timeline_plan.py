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
        ("review-artifact", "original"),
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


def test_review_artifact_does_not_change_to_source_proxy_semantics(
    tmp_path: Path,
) -> None:
    store, asset, _ = _seed_asset(tmp_path, with_proxy=True)
    timeline, ops = _timeline_for_asset(asset.asset_hash)

    plan = build_render_plan(
        timeline,
        ops,
        store,
        "proxy",
        emission_profile="review-artifact",
        enqueue_missing_proxies=False,
    )

    assert plan.source_media_policy == "original"
    assert plan.asset_paths[asset.asset_hash] == asset.stored_path


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
