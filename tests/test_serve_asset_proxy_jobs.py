"""Tests for the durable source-proxy REST surface."""
from __future__ import annotations

import argparse
import hashlib
import time
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from open_edit.cli import cmd_init
from open_edit.ir.types import Asset
from open_edit.render.source_proxy import SourceProxyResult
from open_edit.serve import app as app_mod
from open_edit.serve import projects as projects_mod
from open_edit.storage.assets import AssetStore
from open_edit.agent.tools.pyagent_list_assets import list_assets


def seed_project(tmp_path: Path, monkeypatch) -> tuple[Path, str]:
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    monkeypatch.setenv("OPEN_EDIT_PROJECTS_ROOT", str(projects_root))
    project_path = projects_root / "project"
    project_path.mkdir()
    assert cmd_init(argparse.Namespace(folder=str(project_path))) == 0
    project_id = projects_mod._project_id_from_path(project_path.resolve())
    return project_path, project_id


def seed_asset(project_path: Path) -> str:
    contents = b"high-resolution route asset"
    asset_hash = hashlib.sha256(contents).hexdigest()
    store = AssetStore(project_path / ".open_edit" / "assets")
    cas_path = store._cas_path(asset_hash)
    cas_path.parent.mkdir(parents=True, exist_ok=True)
    cas_path.write_bytes(contents)
    asset = Asset(
        asset_hash=asset_hash,
        original_path=str(project_path / "route-source.mp4"),
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


def test_post_asset_proxy_returns_accepted_job(tmp_path: Path, monkeypatch) -> None:
    project_path, project_id = seed_project(tmp_path, monkeypatch)
    asset_hash = seed_asset(project_path)
    result = SourceProxyResult(
        asset_hash=asset_hash,
        proxy_hash="c" * 64,
        profile="source_proxy_360_v1",
        status="ready",
        output_path="/tmp/proxy",
        elapsed_sec=0.2,
    )

    with (
        mock.patch(
            "open_edit.kernel.asset_proxy_jobs.generate_asset_proxy",
            return_value=result,
        ),
        TestClient(app_mod.app) as client,
    ):
        response = client.post(
            f"/api/projects/{project_id}/assets/{asset_hash}/proxy",
            json={"profile": "source_proxy_360_v1"},
        )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["job_id"]
    assert body["project_id"] == project_id
    assert body["asset_hash"] == asset_hash
    assert body["profile"] == "source_proxy_360_v1"


def test_post_asset_proxy_rejects_malformed_hash(tmp_path: Path, monkeypatch) -> None:
    _project_path, project_id = seed_project(tmp_path, monkeypatch)

    with TestClient(app_mod.app) as client:
        response = client.post(
            f"/api/projects/{project_id}/assets/not-a-hash/proxy",
            json={},
        )

    assert response.status_code == 400


def test_post_asset_proxy_rejects_unknown_profile(tmp_path: Path, monkeypatch) -> None:
    project_path, project_id = seed_project(tmp_path, monkeypatch)
    asset_hash = seed_asset(project_path)

    with TestClient(app_mod.app) as client:
        response = client.post(
            f"/api/projects/{project_id}/assets/{asset_hash}/proxy",
            json={"profile": "arbitrary-ffmpeg"},
        )

    assert response.status_code == 400


def test_get_asset_proxy_job_returns_durable_state(tmp_path: Path, monkeypatch) -> None:
    project_path, project_id = seed_project(tmp_path, monkeypatch)
    asset_hash = seed_asset(project_path)
    result = SourceProxyResult(
        asset_hash=asset_hash,
        proxy_hash="d" * 64,
        profile="source_proxy_360_v1",
        status="ready",
        output_path="/tmp/proxy",
        elapsed_sec=0.2,
    )

    with (
        mock.patch(
            "open_edit.kernel.asset_proxy_jobs.generate_asset_proxy",
            return_value=result,
        ),
        TestClient(app_mod.app) as client,
    ):
        created = client.post(
            f"/api/projects/{project_id}/assets/{asset_hash}/proxy",
            json={},
        )
        assert created.status_code == 202, created.text
        job_id = created.json()["job_id"]

        deadline = time.time() + 5
        while time.time() < deadline:
            response = client.get(
                f"/api/projects/{project_id}/asset_proxy_jobs/{job_id}"
            )
            if response.json()["status"] == "succeeded":
                break
            time.sleep(0.02)

    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"
    assert response.json()["proxy_hash"] == "d" * 64


def test_asset_and_agent_detail_expose_proxy_metadata(
    tmp_path: Path, monkeypatch,
) -> None:
    project_path, project_id = seed_project(tmp_path, monkeypatch)
    asset_hash = seed_asset(project_path)
    store = AssetStore(project_path / ".open_edit" / "assets")
    store.update_proxy_metadata(
        asset_hash,
        proxy_hash="p" * 64,
        profile="source_proxy_360_v1",
        status="ready",
    )

    with TestClient(app_mod.app) as client:
        response = client.get(f"/api/projects/{project_id}")

    assert response.status_code == 200
    asset = response.json()["assets"][0]
    assert asset["proxy_hash"] == "p" * 64
    assert asset["proxy_profile"] == "source_proxy_360_v1"
    assert asset["proxy_status"] == "ready"

    listed = list_assets({"detail": True}, str(project_path))
    detail = listed["assets"][0]
    assert detail["proxy_hash"] == "p" * 64
    assert detail["proxy_profile"] == "source_proxy_360_v1"
    assert detail["proxy_status"] == "ready"
