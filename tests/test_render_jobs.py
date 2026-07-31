from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from open_edit.kernel.render_jobs import RenderJobService


@pytest.mark.asyncio
async def test_job_record_survives_a_new_service_instance(tmp_path):
    project = tmp_path / "project with spaces"
    (project / ".open_edit").mkdir(parents=True)
    service = RenderJobService()

    async def successful_launch(project_path, job_id, mode):
        return {"ok": True, "output_path": str(project / "out.mp4"), "mode": mode}

    service._launch = successful_launch  # type: ignore[method-assign]
    queued = service.enqueue("project-id", project, "proxy")
    completed = await service.wait(project, queued.job_id)

    assert completed.status == "succeeded"
    restored = RenderJobService().get(project, queued.job_id)
    assert restored is not None
    assert restored.status == "succeeded"
    assert restored.result == completed.result


def test_restart_marks_nonterminal_jobs_orphaned(tmp_path):
    project = tmp_path / "project"
    (project / ".open_edit").mkdir(parents=True)
    service = RenderJobService()
    with service._connect(project) as con:
        con.execute(
            "INSERT INTO render_jobs (job_id, project_id, mode, status, created_at, updated_at) "
            "VALUES ('interrupted', 'p', 'final', 'running', 1, 1)"
        )

    assert RenderJobService().recover(project) == 1
    job = service.get(project, "interrupted")
    assert job is not None
    assert job.status == "orphaned"
    assert "restarted" in (job.error or "")


@pytest.mark.asyncio
async def test_successful_render_attaches_qc_report(tmp_path):
    """After a successful render the QC gate runs and its report attaches
    to the job result and the qc_report column (missing output file →
    a failed proxy_render report, not an exception)."""
    project = tmp_path / "project"
    (project / ".open_edit").mkdir(parents=True)
    service = RenderJobService()

    async def successful_launch(project_path, job_id, mode):
        return {"ok": True, "output_path": str(project / "out.mp4"), "mode": mode}

    service._launch = successful_launch  # type: ignore[method-assign]
    queued = service.enqueue("project-id", project, "proxy")
    completed = await service.wait(project, queued.job_id)

    assert completed.status == "succeeded"
    qc_report = (completed.result or {}).get("qc_report")
    assert isinstance(qc_report, dict)
    assert qc_report["passed"] is False
    names = {c["name"] for c in qc_report["checks"]}
    assert "proxy_render" in names
    assert "streams" in names
    assert "frozen_frames" in names

    restored = RenderJobService().get(project, queued.job_id)
    assert restored is not None
    assert restored.qc_report == qc_report


@pytest.mark.asyncio
async def test_same_project_jobs_are_serialized(tmp_path):
    project = tmp_path / "project"
    (project / ".open_edit").mkdir(parents=True)
    service = RenderJobService(max_concurrency=2)
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
    service = RenderJobService(max_concurrency=1)
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


@pytest.mark.asyncio
async def test_enqueue_persists_params(tmp_path: Path) -> None:
    from open_edit.kernel.render_jobs import RenderJobService
    from open_edit.storage.edit_graph import EditGraphStore
    db = tmp_path / ".open_edit"
    db.mkdir(parents=True)
    EditGraphStore(db / "edit_graph.db")
    service = RenderJobService()
    try:
        job = service.enqueue(
            "proj", tmp_path, "final",
            params={"profile": "1080p30", "quality": "high", "crf": 20},
        )
        persisted = service.get(tmp_path, job.job_id)
        assert persisted is not None
        assert persisted.params == {"profile": "1080p30", "quality": "high", "crf": 20}
    finally:
        for task in service._tasks.values():
            task.cancel()


@pytest.mark.asyncio
async def test_launch_command_includes_params(tmp_path: Path) -> None:
    from open_edit.kernel.render_jobs import RenderJobService
    from open_edit.storage.edit_graph import EditGraphStore
    db = tmp_path / ".open_edit"
    db.mkdir(parents=True)
    EditGraphStore(db / "edit_graph.db")
    service = RenderJobService()
    try:
        job = service.enqueue(
            "proj", tmp_path, "final",
            params={"quality": "high", "crf": 20, "scale": "640x360", "codec": "hevc"},
        )
        # _launch builds the command before any subprocess runs; we only
        # assert the command shape via a spy on create_subprocess_exec.
        captured: dict = {}

        async def fake_exec(*args, **kwargs):
            captured["cmd"] = list(args)
            import asyncio as aio
            proc = aio.subprocess.Process(
                transport=None, protocol=None, loop=aio.get_running_loop(),
            )
            proc.returncode = 0
            return proc

        original = asyncio.create_subprocess_exec
        asyncio.create_subprocess_exec = fake_exec
        try:
            await service._launch(tmp_path, job.job_id, "final")
        except Exception:
            pass
        finally:
            asyncio.create_subprocess_exec = original
        cmd = captured.get("cmd", [])
        assert "--quality" in cmd and "high" in cmd
        assert "--crf" in cmd and "20" in cmd
        assert "--scale" in cmd and "640x360" in cmd
        assert "--codec" in cmd and "hevc" in cmd
    finally:
        for task in service._tasks.values():
            task.cancel()
