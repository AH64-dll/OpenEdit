"""Tests for durable host-side source-proxy jobs."""
from __future__ import annotations

import asyncio
import hashlib
import threading
from pathlib import Path
from unittest import mock

import pytest

from open_edit.kernel.asset_proxy_jobs import AssetProxyJobService
from open_edit.render.source_proxy import SourceProxyResult
from open_edit.storage.assets import AssetStore
from open_edit.ir.types import Asset


def seed_high_res_asset(project_path: Path) -> str:
    contents = b"high-resolution source asset"
    asset_hash = hashlib.sha256(contents).hexdigest()
    store = AssetStore(project_path / ".open_edit" / "assets")
    cas_path = store._cas_path(asset_hash)
    cas_path.parent.mkdir(parents=True, exist_ok=True)
    cas_path.write_bytes(contents)
    asset = Asset(
        asset_hash=asset_hash,
        original_path=str(project_path / "source.mp4"),
        stored_path=str(cas_path),
        type="video",
        duration_sec=10.0,
        fps=30.0,
        width=1920,
        height=1080,
        codec="h264",
    )
    store._sidecar_path(asset_hash).write_text(asset.model_dump_json(indent=2))
    return asset_hash


def proxy_result(asset_hash: str, proxy_hash: str = "c" * 64) -> SourceProxyResult:
    return SourceProxyResult(
        asset_hash=asset_hash,
        proxy_hash=proxy_hash,
        profile="source_proxy_360_v1",
        status="ready",
        output_path="/tmp/proxy",
        elapsed_sec=0.2,
    )


@pytest.mark.asyncio
async def test_proxy_job_persists_runs_and_can_be_reloaded(tmp_path: Path) -> None:
    service = AssetProxyJobService(max_concurrency=1)
    asset_hash = seed_high_res_asset(tmp_path)

    with mock.patch(
        "open_edit.kernel.asset_proxy_jobs.generate_asset_proxy",
        return_value=proxy_result(asset_hash),
    ):
        job = service.enqueue("project", tmp_path, asset_hash)
        finished = await service.wait(tmp_path, job.job_id)

    assert finished.status == "succeeded"
    assert finished.proxy_hash == "c" * 64
    restored = AssetProxyJobService().get(tmp_path, job.job_id)
    assert restored is not None
    assert restored.status == "succeeded"
    assert restored.proxy_hash == finished.proxy_hash


@pytest.mark.asyncio
async def test_proxy_job_coalesces_same_asset_and_profile(tmp_path: Path) -> None:
    service = AssetProxyJobService(max_concurrency=1)
    asset_hash = seed_high_res_asset(tmp_path)
    release = threading.Event()

    def generate(*args, **kwargs):
        assert release.wait(5)
        return proxy_result(asset_hash)

    with mock.patch(
        "open_edit.kernel.asset_proxy_jobs.generate_asset_proxy",
        side_effect=generate,
    ):
        first = service.enqueue("project", tmp_path, asset_hash)
        second = service.enqueue("project", tmp_path, asset_hash)
        assert second.job_id == first.job_id
        release.set()
        assert (await service.wait(tmp_path, first.job_id)).status == "succeeded"


def test_proxy_job_recovery_marks_interrupted_rows_orphaned(tmp_path: Path) -> None:
    service = AssetProxyJobService()
    with service._connect(tmp_path) as con:
        con.execute(
            "INSERT INTO asset_proxy_jobs "
            "(job_id, project_id, asset_hash, profile, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("interrupted", "project", "d" * 64, "source_proxy_360_v1", "running", 1, 1),
        )

    assert service.recover(tmp_path) == 1
    assert service.list_jobs(tmp_path)[0].status == "orphaned"


@pytest.mark.asyncio
async def test_failed_proxy_job_records_generator_error(tmp_path: Path) -> None:
    service = AssetProxyJobService()
    asset_hash = seed_high_res_asset(tmp_path)

    with mock.patch(
        "open_edit.kernel.asset_proxy_jobs.generate_asset_proxy",
        side_effect=RuntimeError("encoder exploded"),
    ):
        job = service.enqueue("project", tmp_path, asset_hash)
        finished = await service.wait(tmp_path, job.job_id)

    assert finished.status == "failed"
    assert "encoder exploded" in (finished.error or "")


@pytest.mark.asyncio
async def test_missing_proxy_cas_allows_new_attempt(tmp_path: Path) -> None:
    service = AssetProxyJobService()
    asset_hash = seed_high_res_asset(tmp_path)
    first_result = proxy_result(asset_hash, "e" * 64)
    second_result = proxy_result(asset_hash, "f" * 64)

    with mock.patch(
        "open_edit.kernel.asset_proxy_jobs.generate_asset_proxy",
        side_effect=[first_result, second_result],
    ):
        first = service.enqueue("project", tmp_path, asset_hash)
        assert (await service.wait(tmp_path, first.job_id)).status == "succeeded"
        second = service.enqueue("project", tmp_path, asset_hash)
        assert second.job_id != first.job_id
        assert (await service.wait(tmp_path, second.job_id)).proxy_hash == "f" * 64
