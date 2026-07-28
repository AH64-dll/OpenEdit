from __future__ import annotations

import asyncio

import pytest

from open_edit.serve.render_service import RenderService


@pytest.mark.asyncio
async def test_job_record_survives_a_new_service_instance(tmp_path):
    project = tmp_path / "project with spaces"
    (project / ".open_edit").mkdir(parents=True)
    service = RenderService()

    async def successful_launch(project_path, job_id, mode):
        return {"ok": True, "output_path": str(project / "out.mp4"), "mode": mode}

    service._launch = successful_launch  # type: ignore[method-assign]
    queued = service.enqueue("project-id", project, "proxy")
    completed = await service.wait(project, queued.job_id)

    assert completed.status == "succeeded"
    restored = RenderService().get(project, queued.job_id)
    assert restored is not None
    assert restored.status == "succeeded"
    assert restored.result == completed.result


def test_restart_marks_nonterminal_jobs_orphaned(tmp_path):
    project = tmp_path / "project"
    (project / ".open_edit").mkdir(parents=True)
    service = RenderService()
    with service._connect(project) as con:
        con.execute(
            "INSERT INTO render_jobs (job_id, project_id, mode, status, created_at, updated_at) "
            "VALUES ('interrupted', 'p', 'final', 'running', 1, 1)"
        )

    assert RenderService().recover(project) == 1
    job = service.get(project, "interrupted")
    assert job is not None
    assert job.status == "orphaned"
    assert "restarted" in (job.error or "")


@pytest.mark.asyncio
async def test_same_project_jobs_are_serialized(tmp_path):
    project = tmp_path / "project"
    (project / ".open_edit").mkdir(parents=True)
    service = RenderService(max_concurrency=2)
    running = 0
    maximum = 0

    async def launch(project_path, job_id, mode):
        nonlocal running, maximum
        running += 1
        maximum = max(maximum, running)
        await asyncio.sleep(0.02)
        running -= 1
        return {"ok": True, "output_path": str(project / f"{job_id}.mp4"), "mode": mode}

    service._launch = launch  # type: ignore[method-assign]
    first = service.enqueue("p", project, "proxy")
    second = service.enqueue("p", project, "final")
    await asyncio.gather(service.wait(project, first.job_id), service.wait(project, second.job_id))

    assert maximum == 1


@pytest.mark.asyncio
async def test_global_limit_serializes_different_projects(tmp_path):
    first_project = tmp_path / "first"
    second_project = tmp_path / "second"
    (first_project / ".open_edit").mkdir(parents=True)
    (second_project / ".open_edit").mkdir(parents=True)
    service = RenderService(max_concurrency=1)
    running = 0
    maximum = 0

    async def launch(project_path, job_id, mode):
        nonlocal running, maximum
        running += 1
        maximum = max(maximum, running)
        await asyncio.sleep(0.02)
        running -= 1
        return {"ok": True, "output_path": str(project_path / f"{job_id}.mp4"), "mode": mode}

    service._launch = launch  # type: ignore[method-assign]
    first = service.enqueue("first", first_project, "proxy")
    second = service.enqueue("second", second_project, "final")
    await asyncio.gather(
        service.wait(first_project, first.job_id),
        service.wait(second_project, second.job_id),
    )

    assert maximum == 1
