"""Project-scoped HTTP routes for timeline preview chunks."""
from __future__ import annotations

import argparse
import time
from pathlib import Path
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from open_edit.cli import cmd_init
from open_edit.kernel.render_jobs import RenderJob
from open_edit.render.preview_cache import PreviewChunkCache
from open_edit.render.preview_manifest import (
    PreviewArtifact,
    PreviewChunk,
    PreviewManifest,
    PreviewPlaneState,
)
from open_edit.serve import app as app_mod
from open_edit.serve import projects as projects_mod


@pytest.fixture
def projects_root_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    monkeypatch.setenv("OPEN_EDIT_PROJECTS_ROOT", str(projects_root))
    return projects_root


@pytest.fixture
def seeded_project(projects_root_tmp: Path) -> tuple[Path, str]:
    project_path = projects_root_tmp / "p1"
    project_path.mkdir()
    assert cmd_init(argparse.Namespace(folder=str(project_path))) == 0
    project_id = projects_mod._project_id_from_path(project_path.resolve())
    return project_path, project_id


def _cache(project_path: Path) -> PreviewChunkCache:
    return PreviewChunkCache(
        project_path / ".open_edit" / "preview_chunks",
        max_bytes=1_000_000,
        max_age_sec=None,
        min_free_bytes=0,
    )


def _manifest(project_id: str, artifact: PreviewArtifact) -> PreviewManifest:
    red = PreviewPlaneState(status="red")
    playback = PreviewPlaneState(status="green", current=artifact)
    return PreviewManifest(
        project_id=project_id,
        graph_revision=1,
        edit_graph_hash="graph",
        duration_frames=30,
        duration_sec=1.0,
        fps_num=30,
        fps_den=1,
        chunk_frames=30,
        profile={"fingerprint": "profile"},
        updated_at=time.time(),
        chunks=[
            PreviewChunk(
                chunk_id="000000-000030",
                index=0,
                start_frame=0,
                end_frame=30,
                start_sec=0.0,
                end_sec=1.0,
                status="green",
                video=red,
                audio=red,
                playback=playback,
            )
        ],
    )


def test_get_preview_manifest_returns_empty_contract(seeded_project) -> None:
    _project_path, project_id = seeded_project
    with TestClient(app_mod.app) as client:
        response = client.get(f"/api/projects/{project_id}/preview-chunks")

    assert response.status_code == 200
    body = response.json()
    assert body["manifest"] is None
    assert body["active_job"] is None
    assert body["proxy_fallback"] is None


def test_preview_file_route_streams_indexed_artifact(seeded_project) -> None:
    project_path, project_id = seeded_project
    cache = _cache(project_path)
    source = project_path / "preview-source.mp4"
    source.write_bytes(b"preview bytes")
    artifact = cache.commit_artifact(
        plane="playback",
        key="chunk-0",
        source=source,
        suffix="mp4",
        graph_hash="graph",
    )
    cache.write_manifest(_manifest(project_id, artifact))

    with TestClient(app_mod.app) as client:
        response = client.get(
            f"/api/projects/{project_id}/preview-chunks/files/{artifact.artifact_id}"
        )

    assert response.status_code == 200
    assert response.content == b"preview bytes"
    assert response.headers["content-type"].startswith("video/mp4")
    assert response.headers["accept-ranges"] == "bytes"


def test_preview_file_route_rejects_path_escape(seeded_project) -> None:
    _project_path, project_id = seeded_project
    with TestClient(app_mod.app) as client:
        response = client.get(
            f"/api/projects/{project_id}/preview-chunks/files/..%2Fedit_graph.db"
        )

    assert response.status_code == 404


def test_preview_file_route_is_project_scoped(
    seeded_project, projects_root_tmp: Path
) -> None:
    first_path, first_id = seeded_project
    second_path = projects_root_tmp / "p2"
    second_path.mkdir()
    assert cmd_init(argparse.Namespace(folder=str(second_path))) == 0
    second_id = projects_mod._project_id_from_path(second_path.resolve())

    cache = _cache(second_path)
    source = second_path / "preview-source.mp4"
    source.write_bytes(b"second project")
    artifact = cache.commit_artifact(
        plane="playback",
        key="other-project",
        source=source,
        suffix="mp4",
        graph_hash="graph",
    )
    cache.write_manifest(_manifest(second_id, artifact))

    with TestClient(app_mod.app) as client:
        response = client.get(
            f"/api/projects/{first_id}/preview-chunks/files/{artifact.artifact_id}"
        )

    assert response.status_code == 404
    assert first_path.joinpath(".open_edit", "edit_graph.db").exists()


def test_manifest_adds_urls_and_reports_scoped_jobs(
    seeded_project, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_path, project_id = seeded_project
    cache = _cache(project_path)
    source = project_path / "preview-source.mp4"
    source.write_bytes(b"preview bytes")
    artifact = cache.commit_artifact(
        plane="playback",
        key="url-check",
        source=source,
        suffix="mp4",
        graph_hash="graph",
    )
    cache.write_manifest(_manifest(project_id, artifact))
    proxy = project_path / ".open_edit" / "renders" / "proxy.mp4"
    proxy.parent.mkdir(parents=True, exist_ok=True)
    proxy.write_bytes(b"x" * 10_000)
    now = time.time()
    active = RenderJob(
        job_id="preview-job",
        project_id=project_id,
        mode="preview-chunks",
        status="running",
        created_at=now,
        updated_at=now,
    )
    fallback = RenderJob(
        job_id="proxy-job",
        project_id=project_id,
        mode="proxy",
        status="succeeded",
        created_at=now - 1,
        updated_at=now - 1,
        output_path=str(proxy),
        edit_graph_hash="old-graph",
    )
    with mock.patch.object(
        app_mod.DEFAULT_RENDER_JOB_SERVICE,
        "list_jobs",
        return_value=[active, fallback],
    ), TestClient(app_mod.app) as client:
        response = client.get(f"/api/projects/{project_id}/preview-chunks")

    assert response.status_code == 200
    body = response.json()
    assert body["active_job"]["job_id"] == "preview-job"
    assert body["proxy_fallback"]["job_id"] == "proxy-job"
    assert body["proxy_fallback"]["stale"] is True
    playback = body["manifest"]["chunks"][0]["playback"]["current"]
    assert playback["url"].endswith(f"/preview-chunks/files/{artifact.artifact_id}")


def test_wipe_preview_cache_does_not_delete_edit_graph(seeded_project) -> None:
    project_path, project_id = seeded_project
    cache = _cache(project_path)
    source = project_path / "preview-source.mp4"
    source.write_bytes(b"preview bytes")
    artifact = cache.commit_artifact(
        plane="playback",
        key="wipe-me",
        source=source,
        suffix="mp4",
        graph_hash="graph",
    )
    cache.write_manifest(_manifest(project_id, artifact))

    with TestClient(app_mod.app) as client:
        response = client.delete(f"/api/projects/{project_id}/preview-chunks")

    assert response.status_code == 200
    body = response.json()
    assert body["removed_files"] >= 2
    assert body["removed_bytes"] >= len(b"preview bytes")
    assert project_path.joinpath(".open_edit", "edit_graph.db").exists()
    assert not project_path.joinpath(
        ".open_edit", "preview_chunks", "manifest.json"
    ).exists()
