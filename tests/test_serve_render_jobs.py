"""Tests for the durable render-job lifecycle (v1.7+).

Background: the legacy in-memory registry (``_RENDER_JOBS`` with
``_prune_render_jobs``/``_register_job``/``_run_render_job`` in
``open_edit.serve.app``) was deleted. Render jobs are now persisted by
``open_edit.kernel.render_service.RenderService``
(``DEFAULT_RENDER_SERVICE``) into each project's
``.open_edit/render_jobs.db``.

These tests drive the HTTP trigger route once (request → 202 + job row
in the DB) and otherwise assert the lifecycle contract (created →
running → completed) through the RenderService API, which is the
canonical path both the REST layer and the agent tools share. The old
pruning tests are gone with the code: the durable DB is append-only by
design, so there is no TTL pruning to test; the old "bounded size"
property is covered by the service's queued/running coalescing.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path
from unittest import mock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from open_edit.cli import cmd_init  # noqa: E402
from open_edit.kernel.render_service import DEFAULT_RENDER_SERVICE  # noqa: E402
from open_edit.serve import app as app_mod  # noqa: E402
from open_edit.serve import projects as projects_mod  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def projects_root_tmp(tmp_path, monkeypatch):
    """Point OPEN_EDIT_PROJECTS_ROOT at a fresh empty dir."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    monkeypatch.setenv("OPEN_EDIT_PROJECTS_ROOT", str(projects_dir))
    return projects_dir


@pytest.fixture
def seeded_project(projects_root_tmp):
    """A real, fully-initialised project under projects_root_tmp.

    Returns (project_path, project_id).
    """
    proj = projects_root_tmp / "p1"
    proj.mkdir()
    cmd_init(argparse.Namespace(folder=str(proj)))
    project_id = projects_mod._project_id_from_path(proj.resolve())
    return proj, project_id


# ---------------------------------------------------------------------------
# HTTP route: POST /api/projects/{id}/render
# ---------------------------------------------------------------------------

def test_render_route_202_and_persists_job_row(seeded_project):
    """The trigger route accepts the request (202) and persists a job
    row in the durable DB, which then runs to completion. This is the
    single end-to-end route exercise; the render itself is faked so the
    test does not need a real melt invocation."""
    from fastapi.testclient import TestClient

    proj, project_id = seeded_project
    fake = proj / ".open_edit" / "renders" / "project_fake.mp4"

    async def fake_launch(project_path, job_id, mode):
        return {"ok": True, "output_path": str(fake), "mode": mode}

    with mock.patch(
        "open_edit.kernel.render_service.DEFAULT_RENDER_SERVICE._launch", fake_launch
    ):
        with TestClient(app_mod.app) as client:
            r = client.post(
                f"/api/projects/{project_id}/render", json={"mode": "proxy"}
            )
            assert r.status_code == 202, r.text
            body = r.json()
            assert body["job_id"]
            assert body["project_id"] == project_id
            assert body["mode"] == "proxy"
            assert body["status"] == "queued"
            assert isinstance(body["created_at"], float)

            job = DEFAULT_RENDER_SERVICE.get(proj, body["job_id"])
            assert job is not None, "route must persist a render_jobs row"

            deadline = time.time() + 5
            while time.time() < deadline:
                job = DEFAULT_RENDER_SERVICE.get(proj, body["job_id"])
                if job.status in ("succeeded", "failed"):
                    break
                time.sleep(0.02)
            assert job.status == "succeeded", f"expected terminal job, got {job!r}"
            assert job.output_path == str(fake)


def test_render_route_rejects_invalid_mode(seeded_project):
    """Non-``proxy|final|overlay`` modes are rejected with 400 before
    anything is enqueued."""
    from fastapi.testclient import TestClient

    proj, project_id = seeded_project
    with TestClient(app_mod.app) as client:
        r = client.post(
            f"/api/projects/{project_id}/render", json={"mode": "4k_master"}
        )
    assert r.status_code == 400
    assert DEFAULT_RENDER_SERVICE.list_jobs(proj) == []


# ---------------------------------------------------------------------------
# Lifecycle: created (queued) → running → succeeded
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_render_job_has_created_at_field(tmp_path):
    """Every enqueued job carries a ``created_at`` timestamp (float)."""
    job = DEFAULT_RENDER_SERVICE.enqueue("proj", tmp_path, "proxy")
    assert isinstance(job.created_at, float)
    assert job.status == "queued"
    assert job.job_id


@pytest.mark.asyncio
async def test_render_job_lifecycle_queued_running_succeeded(tmp_path):
    """A job transitions queued → running → succeeded and records the
    render output path — the same lifecycle the old in-memory registry
    asserted, now at the DB level through RenderService."""
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_launch(project_path, job_id, mode):
        started.set()
        await release.wait()
        return {"ok": True, "output_path": str(tmp_path / "out.mp4"), "mode": mode}

    with mock.patch(
        "open_edit.kernel.render_service.DEFAULT_RENDER_SERVICE._launch", fake_launch
    ):
        try:
            job = DEFAULT_RENDER_SERVICE.enqueue("proj", tmp_path, "proxy")
            assert job.status == "queued"

            await asyncio.wait_for(started.wait(), timeout=5)
            running = DEFAULT_RENDER_SERVICE.get(tmp_path, job.job_id)
            assert running is not None
            assert running.status == "running"

            release.set()
            final = await DEFAULT_RENDER_SERVICE.wait(tmp_path, job.job_id)
            assert final.status == "succeeded"
            assert final.output_path == str(tmp_path / "out.mp4")
            assert final.updated_at >= final.created_at
        finally:
            release.set()


@pytest.mark.asyncio
async def test_render_job_failure_records_error(tmp_path):
    """A failing render lands in a terminal ``failed`` state with the
    error recorded — the durable equivalent of the old ``failed``
    status handling."""
    async def fake_launch(project_path, job_id, mode):
        raise RuntimeError("melt exploded")

    with mock.patch(
        "open_edit.kernel.render_service.DEFAULT_RENDER_SERVICE._launch", fake_launch
    ):
        job = DEFAULT_RENDER_SERVICE.enqueue("proj", tmp_path, "proxy")
        final = await DEFAULT_RENDER_SERVICE.wait(tmp_path, job.job_id)
        assert final.status == "failed"
        assert "melt exploded" in (final.error or "")


@pytest.mark.asyncio
async def test_enqueue_coalesces_duplicate_jobs(tmp_path):
    """Repeated enqueues of the same graph+mode while one is in flight
    reuse the queued/running job instead of piling up rows — the
    durable replacement for the old bounded-size guarantee."""
    release = asyncio.Event()

    async def fake_launch(project_path, job_id, mode):
        await release.wait()
        return {"ok": True, "output_path": str(tmp_path / "out.mp4"), "mode": mode}

    with mock.patch(
        "open_edit.kernel.render_service.DEFAULT_RENDER_SERVICE._launch", fake_launch
    ):
        try:
            first = DEFAULT_RENDER_SERVICE.enqueue("proj", tmp_path, "proxy")
            for _ in range(4):
                dup = DEFAULT_RENDER_SERVICE.enqueue("proj", tmp_path, "proxy")
                assert dup.job_id == first.job_id

            active = [
                j for j in DEFAULT_RENDER_SERVICE.list_jobs(tmp_path)
                if j.status in ("queued", "running")
            ]
            assert len(active) == 1, "duplicate enqueues must coalesce"

            release.set()
            final = await DEFAULT_RENDER_SERVICE.wait(tmp_path, first.job_id)
            assert final.status == "succeeded"
        finally:
            release.set()
