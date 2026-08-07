
"""Durable asset-proxy queue runner (drain) and CLI command."""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from unittest import mock

import pytest

from open_edit.cli import cmd_asset_proxy
from open_edit.kernel.asset_proxy_jobs import AssetProxyJobService
from open_edit.render.source_proxy import SourceProxyResult
from open_edit.storage.assets import AssetStore
from open_edit.ir.types import Asset


def seed_high_res_asset(project_path: Path) -> str:
    contents = b"high-resolution source asset for drain"
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
        encoder="h264_nvenc",
    )


def _insert_job(
    service: AssetProxyJobService,
    project_path: Path,
    asset_hash: str,
    status: str,
    job_id: str,
) -> None:
    with service._connect(project_path) as con:
        con.execute(
            "INSERT INTO asset_proxy_jobs "
            "(job_id, project_id, asset_hash, profile, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (job_id, "project", asset_hash, "source_proxy_360_v1", status, 1, 1),
        )


@pytest.mark.asyncio
async def test_drain_runs_persisted_queued_jobs(tmp_path: Path) -> None:
    service = AssetProxyJobService(max_concurrency=2)
    asset_hash = seed_high_res_asset(tmp_path)
    _insert_job(service, tmp_path, asset_hash, "queued", "q1")

    with mock.patch(
        "open_edit.kernel.asset_proxy_jobs.generate_asset_proxy",
        return_value=proxy_result(asset_hash),
    ):
        stats = service.drain(tmp_path)
        job = await service.wait(tmp_path, "q1")

    assert stats["started"] == 1
    assert stats["recovered"] == 0
    assert job.status == "succeeded"


@pytest.mark.asyncio
async def test_drain_recovers_running_and_orphaned_rows(tmp_path: Path) -> None:
    service = AssetProxyJobService(max_concurrency=2)
    asset_hash = seed_high_res_asset(tmp_path)
    _insert_job(service, tmp_path, asset_hash, "running", "r1")
    _insert_job(service, tmp_path, asset_hash, "orphaned", "o1")

    with mock.patch(
        "open_edit.kernel.asset_proxy_jobs.generate_asset_proxy",
        return_value=proxy_result(asset_hash),
    ):
        stats = service.drain(tmp_path)
        r1 = await service.wait(tmp_path, "r1")
        o1 = await service.wait(tmp_path, "o1")

    assert stats["started"] == 2
    assert stats["recovered"] == 2
    assert r1.status == "succeeded"
    assert o1.status == "succeeded"


@pytest.mark.asyncio
async def test_drain_does_not_double_run_live_futures(tmp_path: Path) -> None:
    service = AssetProxyJobService(max_concurrency=1)
    asset_hash = seed_high_res_asset(tmp_path)
    calls: list[str] = []

    def generate(*args, **kwargs):
        calls.append(args[1])
        return proxy_result(asset_hash)

    with mock.patch(
        "open_edit.kernel.asset_proxy_jobs.generate_asset_proxy",
        side_effect=generate,
    ):
        job = service.enqueue("project", tmp_path, asset_hash)
        stats = service.drain(tmp_path)  # row already has a live future
        finished = await service.wait(tmp_path, job.job_id)

    assert stats["started"] == 0
    assert stats["already_running"] == 1
    assert finished.status == "succeeded"
    assert len(calls) == 1


def test_drain_without_db_creates_nothing(tmp_path: Path) -> None:
    service = AssetProxyJobService()
    assert service.drain(tmp_path) == {"recovered": 0, "started": 0, "already_running": 0}
    assert not service.db_path(tmp_path).exists()


@pytest.mark.asyncio
async def test_cli_asset_proxy_drains_and_reports(tmp_path: Path, capsys) -> None:
    service = AssetProxyJobService()
    asset_hash = seed_high_res_asset(tmp_path)
    _insert_job(service, tmp_path, asset_hash, "queued", "cli1")

    class Args:
        project = str(tmp_path)
        wait = True
        timeout = 30
        json = True

    with mock.patch(
        "open_edit.kernel.asset_proxy_jobs.generate_asset_proxy",
        return_value=proxy_result(asset_hash),
    ):
        rc = cmd_asset_proxy(Args())

    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["ok"] is True
    assert out["drain"]["started"] == 1
    assert out["jobs"]["succeeded"] == 1
