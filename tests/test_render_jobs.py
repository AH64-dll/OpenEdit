from __future__ import annotations

import asyncio
import sqlite3
import sys
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


def test_render_job_schema_migrates_old_mode_check_without_losing_params(
    tmp_path: Path,
) -> None:
    (tmp_path / ".open_edit").mkdir(parents=True)
    db_path = RenderJobService.db_path(tmp_path)
    with sqlite3.connect(db_path) as con:
        con.executescript(
            """
            CREATE TABLE render_jobs (
                job_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                mode TEXT NOT NULL CHECK (mode IN ('proxy', 'final', 'overlay')),
                status TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                output_path TEXT,
                error TEXT,
                result_json TEXT,
                qc_report TEXT,
                graph_revision INTEGER,
                edit_graph_hash TEXT,
                params_json TEXT
            );
            INSERT INTO render_jobs (
                job_id, project_id, mode, status, created_at, updated_at,
                output_path, result_json, graph_revision, edit_graph_hash, params_json
            ) VALUES (
                'legacy', 'proj', 'proxy', 'succeeded', 1, 2,
                '/tmp/proxy.mp4', '{"ok":true}', 7, 'old-hash',
                '{"quality":"high","crf":20}'
            );
            """
        )

    service = RenderJobService()
    migrated = service.get(tmp_path, "legacy")
    assert migrated is not None
    assert migrated.params == {"quality": "high", "crf": 20}
    assert migrated.result == {"ok": True}

    with sqlite3.connect(db_path) as con:
        create_sql = con.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='render_jobs'"
        ).fetchone()[0]
    assert "preview-chunks" in create_sql


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
async def test_proxy_cache_hit_persists_skipped_qc_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    (project / ".open_edit").mkdir(parents=True)
    service = RenderJobService()

    async def cached_launch(project_path, job_id, mode):
        return {
            "ok": True,
            "output_path": str(project / "cached.mp4"),
            "mode": mode,
            "cache_hit": True,
            "diagnostics": {"cache": {"hit": True}, "stages": {}},
        }

    service._launch = cached_launch  # type: ignore[method-assign]
    queued = service.enqueue("project-id", project, "proxy")
    completed = await service.wait(project, queued.job_id)

    report = completed.result["qc_report"]
    assert report["passed"] is True
    assert report["policy"] == "skip"
    assert report["complete"] is False
    assert "deliverable_cache_hit" in report["reason"]
    assert report["checks"]
    assert all(check["skipped"] for check in report["checks"])
    assert completed.qc_report == report
    assert completed.result["qc_policy"] == "skip"
    assert completed.result["diagnostics"]["qc_policy"] == "skip"
    assert completed.result["diagnostics"]["qc_report"] == report
    qc_stage = completed.result["diagnostics"]["stages"]["qc"]
    assert qc_stage["status"] == "skipped"
    assert qc_stage["policy"] == "skip"
    assert qc_stage["elapsed_sec"] >= 0

    restored = RenderJobService().get(project, queued.job_id)
    assert restored is not None
    assert restored.qc_report == report


@pytest.mark.asyncio
async def test_final_cache_hit_still_runs_qc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from open_edit.qc.gate import QCReport

    service = RenderJobService()
    called = False
    seen_policy = None

    def fake_qc(*args, **kwargs):
        nonlocal called, seen_policy
        called = True
        seen_policy = kwargs["policy"]
        return QCReport(passed=True, checks=[])

    monkeypatch.setattr("open_edit.qc.gate.run_qc_gate", fake_qc)
    updated = await service._attach_qc(
        {
            "ok": True,
            "output_path": str(tmp_path / "cached.mp4"),
            "mode": "final",
            "cache_hit": True,
            "diagnostics": {"cache": {"hit": True}, "stages": {}},
        },
        tmp_path,
    )

    assert called is True
    assert seen_policy.mode == "full"
    assert updated["qc_report"]["passed"] is True
    assert "skipped" not in updated["qc_report"]
    assert updated["qc_policy"] == "full"
    assert updated["diagnostics"]["stages"]["qc"]["status"] == "completed"


@pytest.mark.asyncio
async def test_proxy_cold_uses_light_qc_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from open_edit.qc.gate import QCReport

    service = RenderJobService()
    seen_policy = None

    def fake_qc(*args, **kwargs):
        nonlocal seen_policy
        seen_policy = kwargs["policy"]
        return QCReport(passed=True, checks=[])

    monkeypatch.setattr("open_edit.qc.gate.run_qc_gate", fake_qc)
    updated = await service._attach_qc(
        {
            "ok": True,
            "output_path": str(tmp_path / "out.mp4"),
            "mode": "proxy",
            "cache_hit": False,
            "diagnostics": {"stages": {}},
        },
        tmp_path,
    )

    assert seen_policy.mode == "light"
    assert updated["qc_policy"] == "light"


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
            params={
                "quality": "high",
                "crf": 20,
                "scale": "640x360",
                "codec": "hevc",
                "force_remotion": True,
                "remotion_uids": ["uid-a", "uid-b"],
            },
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
        assert "--force-remotion" in cmd
        assert cmd.count("--remotion-uid") == 2
        assert "uid-a" in cmd and "uid-b" in cmd
    finally:
        for task in service._tasks.values():
            task.cancel()


@pytest.mark.asyncio
async def test_preview_launch_uses_durable_job_id_without_shell_params(
    tmp_path: Path,
) -> None:
    service = RenderJobService()
    (tmp_path / ".open_edit").mkdir(parents=True)
    with service._connect(tmp_path) as con:
        con.execute(
            "INSERT INTO render_jobs "
            "(job_id, project_id, mode, status, created_at, updated_at, params_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "preview-job", "proj", "preview-chunks", "queued", 1.0, 1.0,
                '{"media":"audio","ranges":[{"end_sec":4,"start_sec":2}]}',
            ),
        )

    captured: dict = {}

    class FakeProcess:
        pid = 123
        returncode = 0

        async def communicate(self):
            return (
                b'{"ok": true, "mode": "preview-chunks", '
                b'"output_path": "/tmp/manifest.json"}',
                b"",
            )

    async def fake_exec(*args, **kwargs):
        captured["cmd"] = list(args)
        return FakeProcess()

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    try:
        result = await service._launch(tmp_path, "preview-job", "preview-chunks")
    finally:
        monkeypatch.undo()

    assert result["mode"] == "preview-chunks"
    assert captured["cmd"] == [
        sys.executable, "-m", "open_edit.cli", "preview-chunks",
        "--job-id", "preview-job", "--json",
    ]


@pytest.mark.asyncio
async def test_preview_chunks_job_persists_exact_params_and_skips_qc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RenderJobService()
    launched = tmp_path / ".open_edit" / "preview_chunks" / "manifest.json"
    qc_called = False

    async def preview_launch(project_path, job_id, mode):
        assert mode == "preview-chunks"
        return {
            "ok": True,
            "mode": mode,
            "output_path": str(launched),
            "manifest_path": str(launched),
            "green_chunks": 1,
        }

    async def fail_if_qc(*args, **kwargs):
        nonlocal qc_called
        qc_called = True
        raise AssertionError("preview chunks must not run whole-file QC")

    monkeypatch.setattr(service, "_launch", preview_launch)
    monkeypatch.setattr(service, "_attach_qc", fail_if_qc)
    params = {
        "ranges": [{"start_sec": 0.0, "end_sec": 1.0}],
        "media": "both",
    }

    job = service.enqueue("proj", tmp_path, "preview-chunks", params=params)
    assert job.mode == "preview-chunks"
    assert job.params == params
    completed = await service.wait(tmp_path, job.job_id)

    assert completed.status == "succeeded"
    assert completed.output_path == str(launched)
    assert completed.result["mode"] == "preview-chunks"
    assert completed.result["green_chunks"] == 1
    assert qc_called is False


@pytest.mark.asyncio
async def test_preview_chunks_coalescing_requires_exact_params(tmp_path: Path) -> None:
    service = RenderJobService()
    release = asyncio.Event()

    async def preview_launch(project_path, job_id, mode):
        await release.wait()
        return {
            "ok": True,
            "mode": mode,
            "output_path": str(tmp_path / "manifest.json"),
        }

    service._launch = preview_launch  # type: ignore[method-assign]
    first_params = {
        "ranges": [{"start_sec": 0.0, "end_sec": 1.0}],
        "media": "video",
    }
    second_params = {
        "ranges": [{"start_sec": 1.0, "end_sec": 2.0}],
        "media": "video",
    }
    try:
        first = service.enqueue("proj", tmp_path, "preview-chunks", params=first_params)
        same = service.enqueue("proj", tmp_path, "preview-chunks", params=first_params)
        different = service.enqueue("proj", tmp_path, "preview-chunks", params=second_params)

        assert same.job_id == first.job_id
        assert different.job_id != first.job_id
    finally:
        release.set()
        for task in service._tasks.values():
            task.cancel()


@pytest.mark.asyncio
async def test_qc_stage_timing_is_attached_to_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from open_edit.qc.gate import QCReport

    service = RenderJobService()

    def fake_qc(*args, **kwargs):
        return QCReport(passed=True, checks=[])

    monkeypatch.setattr("open_edit.qc.gate.run_qc_gate", fake_qc)
    result = {
        "ok": True,
        "output_path": str(tmp_path / "out.mp4"),
        "mode": "proxy",
        "duration_sec": 1.0,
        "diagnostics": {"stages": {}},
    }

    updated = await service._attach_qc(result, tmp_path)

    assert updated["qc_report"]["passed"] is True
    assert updated["qc_report"]["checks"] == []
    assert updated["diagnostics"]["stages"]["qc"]["status"] == "completed"
    assert updated["diagnostics"]["stages"]["qc"]["elapsed_sec"] >= 0
