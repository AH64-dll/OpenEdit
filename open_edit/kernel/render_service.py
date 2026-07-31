"""Durable render scheduling and subprocess lifecycle management.

The service is deliberately independent of FastAPI.  Both HTTP handlers and
agent tools can enqueue the same persisted job, inspect it after a restart,
and share a single process-group cancellation policy.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import signal
import sqlite3
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

JobStatus = Literal[
    "queued", "running", "cancelling", "cancelled", "succeeded", "failed", "orphaned",
]
_TERMINAL = frozenset({"cancelled", "succeeded", "failed", "orphaned"})


@dataclass(frozen=True)
class RenderJob:
    job_id: str
    project_id: str
    mode: str
    status: JobStatus
    created_at: float
    updated_at: float
    output_path: str | None = None
    error: str | None = None
    result: dict | None = None
    qc_report: dict | None = None
    graph_revision: int | None = None
    edit_graph_hash: str | None = None


class RenderEnqueueError(ValueError):
    """Raised when a render cannot be accepted (invalid/stale graph)."""


_SCHEMA = """
CREATE TABLE IF NOT EXISTS render_jobs (
    job_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('proxy', 'final', 'overlay')),
    status TEXT NOT NULL CHECK (status IN
      ('queued', 'running', 'cancelling', 'cancelled', 'succeeded', 'failed', 'orphaned')),
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    output_path TEXT,
    error TEXT,
    result_json TEXT,
    qc_report TEXT,
    graph_revision INTEGER,
    edit_graph_hash TEXT
);
CREATE INDEX IF NOT EXISTS idx_render_jobs_project_created
    ON render_jobs(project_id, created_at DESC);
"""


class RenderService:
    """Persist render jobs under each project and execute them centrally.

    A RenderService instance may schedule multiple projects, but only one
    render is active per project.  The global semaphore bounds the remaining
    cross-project concurrency.  Running processes themselves remain in memory
    because a PID cannot safely survive a server restart; recovery marks those
    durable records as ``orphaned``.
    """

    def __init__(self, *, max_concurrency: int | None = None, timeout_s: float | None = None,
                 cancel_grace_s: float = 5.0) -> None:
        configured = max_concurrency or int(os.environ.get("OPEN_EDIT_RENDER_CONCURRENCY", "1"))
        self._semaphore = asyncio.Semaphore(max(1, configured))
        # Final 1080p + overlay burn for ~30 min timelines needs far more than
        # 30 minutes wall clock; align with serve RENDER_TIMEOUT_S (4h).
        if timeout_s is None:
            env_t = os.environ.get("OPEN_EDIT_RENDER_TIMEOUT_S")
            timeout_s = float(env_t) if env_t and env_t.strip() else 14400.0
        self.timeout_s = float(timeout_s)
        self.cancel_grace_s = cancel_grace_s
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._project_locks: dict[str, asyncio.Lock] = {}
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._job_encoder: dict[str, str] = {}

    @staticmethod
    def db_path(project_path: Path) -> Path:
        return project_path / ".open_edit" / "render_jobs.db"

    def _connect(self, project_path: Path) -> sqlite3.Connection:
        path = self.db_path(project_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(path)
        con.execute("PRAGMA journal_mode=WAL")
        self._ensure_schema(con)
        return con

    @staticmethod
    def _ensure_schema(con: sqlite3.Connection) -> None:
        con.executescript(_SCHEMA)
        cols = {row[1] for row in con.execute("PRAGMA table_info(render_jobs)")}
        if "graph_revision" not in cols:
            con.execute("ALTER TABLE render_jobs ADD COLUMN graph_revision INTEGER")
        if "edit_graph_hash" not in cols:
            con.execute("ALTER TABLE render_jobs ADD COLUMN edit_graph_hash TEXT")
        if "qc_report" not in cols:
            con.execute("ALTER TABLE render_jobs ADD COLUMN qc_report TEXT")
        # Older installs rejected overlay in the CHECK constraint. Rebuild once.
        create_sql = con.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='render_jobs'"
        ).fetchone()
        if create_sql and create_sql[0] and "overlay" not in create_sql[0]:
            con.execute("ALTER TABLE render_jobs RENAME TO render_jobs_legacy")
            con.executescript(_SCHEMA)
            legacy_cols = {row[1] for row in con.execute("PRAGMA table_info(render_jobs_legacy)")}
            graph_rev = "graph_revision" if "graph_revision" in legacy_cols else "NULL"
            graph_hash = "edit_graph_hash" if "edit_graph_hash" in legacy_cols else "NULL"
            qc_report = "qc_report" if "qc_report" in legacy_cols else "NULL"
            con.execute(
                "INSERT INTO render_jobs ("
                "job_id, project_id, mode, status, created_at, updated_at, "
                "output_path, error, result_json, qc_report, graph_revision, edit_graph_hash"
                ") SELECT job_id, project_id, mode, status, created_at, updated_at, "
                f"output_path, error, result_json, {qc_report}, {graph_rev}, {graph_hash} "
                "FROM render_jobs_legacy"
            )
            con.execute("DROP TABLE render_jobs_legacy")

    @staticmethod
    def _row(row: sqlite3.Row) -> RenderJob:
        keys = set(row.keys())
        return RenderJob(
            job_id=row["job_id"], project_id=row["project_id"], mode=row["mode"],
            status=row["status"], created_at=row["created_at"], updated_at=row["updated_at"],
            output_path=row["output_path"], error=row["error"],
            result=json.loads(row["result_json"]) if row["result_json"] else None,
            qc_report=json.loads(row["qc_report"]) if "qc_report" in keys and row["qc_report"] else None,
            graph_revision=row["graph_revision"] if "graph_revision" in keys else None,
            edit_graph_hash=row["edit_graph_hash"] if "edit_graph_hash" in keys else None,
        )

    def recover(self, project_path: Path) -> int:
        """Mark jobs interrupted by a prior service process as orphaned."""
        now = time.time()
        with self._connect(project_path) as con:
            cur = con.execute(
                "UPDATE render_jobs SET status='orphaned', error=?, updated_at=? "
                "WHERE status IN ('queued', 'running', 'cancelling')",
                ("render service restarted before completion", now),
            )
        return cur.rowcount

    def get(self, project_path: Path, job_id: str) -> RenderJob | None:
        with self._connect(project_path) as con:
            con.row_factory = sqlite3.Row
            row = con.execute("SELECT * FROM render_jobs WHERE job_id=?", (job_id,)).fetchone()
        return self._row(row) if row else None

    def list_jobs(self, project_path: Path) -> list[RenderJob]:
        with self._connect(project_path) as con:
            con.row_factory = sqlite3.Row
            rows = con.execute(
                "SELECT * FROM render_jobs ORDER BY created_at DESC"
            ).fetchall()
        return [self._row(row) for row in rows]

    def _update(self, project_path: Path, job_id: str, status: JobStatus, *,
                output_path: str | None = None, error: str | None = None,
                result: dict | None = None, qc_report: dict | None = None) -> None:
        with self._connect(project_path) as con:
            con.execute(
                "UPDATE render_jobs SET status=?, updated_at=?, output_path=?, error=?, "
                "result_json=?, qc_report=? WHERE job_id=?",
                (status, time.time(), output_path, error,
                 json.dumps(result, sort_keys=True) if result is not None else None,
                 json.dumps(qc_report, sort_keys=True) if qc_report is not None else None,
                 job_id),
            )

    @staticmethod
    def _graph_fingerprint(project_path: Path) -> tuple[int, str, str]:
        """Return (revision, hash, timeline_status) for the current edit graph."""
        db = project_path / ".open_edit" / "edit_graph.db"
        if not db.exists():
            # Fresh / uninitialized graph: allow renders; hash is empty.
            return 0, hashlib.sha256(b"[]").hexdigest(), "valid"
        from open_edit.storage.edit_graph import EditGraphStore

        store = EditGraphStore(db)
        ops = store.load_all()
        revision = store.graph_revision()
        # Must match serve/projects.py — otherwise the UI never auto-loads the
        # proxy that was just rendered for this graph.
        from open_edit.ir.hash import compute_edit_graph_hash

        digest = compute_edit_graph_hash(ops)
        timeline_status = "valid"
        try:
            from open_edit.ir.derive import derive_timeline
            from open_edit.ir.types import Project as IRProject
            from open_edit.storage.assets import list_assets_from_disk

            assets = {a.asset_hash: a for a in list_assets_from_disk(project_path)}
            derive_timeline(IRProject(
                project_id=store.project_id,
                name=project_path.name,
                workdir=project_path,
                assets=assets,
                edit_graph=ops,
            ))
        except Exception:
            timeline_status = "invalid"
        return revision, digest, timeline_status

    def enqueue(
        self,
        project_id: str,
        project_path: Path,
        mode: str,
        *,
        expected_revision: int | None = None,
        allow_invalid_timeline: bool = False,
        encoder_backend: str | None = None,
    ) -> RenderJob:
        if mode not in ("proxy", "final", "overlay"):
            raise ValueError("mode must be 'proxy', 'final', or 'overlay'")
        revision, graph_hash, timeline_status = self._graph_fingerprint(project_path)
        if timeline_status == "invalid" and not allow_invalid_timeline:
            raise RenderEnqueueError(
                "timeline_status=invalid; refuse render until the edit graph derives cleanly"
            )
        if expected_revision is not None and expected_revision != revision:
            raise RenderEnqueueError(
                f"stale graph revision: expected {expected_revision}, current {revision}"
            )
        now = time.time()
        # Coalesce: if a queued/running job already covers this graph+mode, reuse it.
        # If the in-memory worker task was lost (process restart / other process
        # wrote the row), re-attach a runner so the job does not sit forever.
        existing: RenderJob | None = None
        with self._connect(project_path) as con:
            row = con.execute(
                "SELECT job_id, status, created_at, updated_at, graph_revision, edit_graph_hash "
                "FROM render_jobs WHERE project_id = ? AND mode = ? "
                "AND edit_graph_hash = ? AND status IN ('queued', 'running') "
                "ORDER BY created_at DESC LIMIT 1",
                (project_id, mode, graph_hash),
            ).fetchone()
            if row is not None:
                existing = RenderJob(
                    row[0], project_id, mode, row[1], row[2], row[3],
                    graph_revision=row[4], edit_graph_hash=row[5],
                )
            else:
                existing = None
                job = RenderJob(
                    uuid.uuid4().hex, project_id, mode, "queued", now, now,
                    graph_revision=revision, edit_graph_hash=graph_hash,
                )
                con.execute(
                    "INSERT INTO render_jobs (job_id, project_id, mode, status, created_at, updated_at, "
                    "graph_revision, edit_graph_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        job.job_id, job.project_id, job.mode, job.status, job.created_at,
                        job.updated_at, job.graph_revision, job.edit_graph_hash,
                    ),
                )
                existing = job

        job = existing
        assert job is not None
        task = self._tasks.get(job.job_id)
        if task is None or task.done():
            # Reset stuck "running" rows that have no live process back to queued.
            if job.status == "running":
                self._update(project_path, job.job_id, "queued")
                job = self.get(project_path, job.job_id) or job
            self._tasks[job.job_id] = asyncio.create_task(self._run(project_path, job.job_id))
        if encoder_backend in ("gpu", "cpu"):
            self._job_encoder[job.job_id] = encoder_backend
        return job

    async def wait(self, project_path: Path, job_id: str) -> RenderJob:
        task = self._tasks.get(job_id)
        if task is not None:
            await asyncio.shield(task)
        job = self.get(project_path, job_id)
        if job is None:
            raise LookupError(f"render job not found: {job_id}")
        return job

    async def cancel(self, project_path: Path, job_id: str) -> RenderJob | None:
        job = self.get(project_path, job_id)
        if job is None or job.status in _TERMINAL:
            return job
        self._update(project_path, job_id, "cancelling")
        proc = self._processes.get(job_id)
        if proc is not None:
            await self._terminate_process_group(proc)
        task = self._tasks.get(job_id)
        if task is not None and not task.done():
            task.cancel()
        self._update(project_path, job_id, "cancelled", error="cancelled by user")
        return self.get(project_path, job_id)

    async def _terminate_process_group(self, proc: asyncio.subprocess.Process) -> None:
        if proc.returncode is not None:
            return
        try:
            if os.name == "posix":
                os.killpg(proc.pid, signal.SIGTERM)
            else:
                proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=self.cancel_grace_s)
            return
        except (asyncio.TimeoutError, ProcessLookupError):
            pass
        try:
            if os.name == "posix":
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
        except ProcessLookupError:
            return
        await proc.wait()

    async def _run(self, project_path: Path, job_id: str) -> None:
        initial = self.get(project_path, job_id)
        if initial is None:
            return
        lock = self._project_locks.setdefault(initial.project_id, asyncio.Lock())
        try:
            async with lock, self._semaphore:
                self._update(project_path, job_id, "running")
                result = await self._launch(project_path, job_id, initial.mode)
                result = await self._attach_qc(result, project_path)
                self._update(
                    project_path, job_id, "succeeded",
                    output_path=result["output_path"], result=result,
                    qc_report=result.get("qc_report"),
                )
        except asyncio.CancelledError:
            job = self.get(project_path, job_id)
            if job is not None and job.status not in _TERMINAL:
                self._update(project_path, job_id, "cancelled", error="cancelled")
            raise
        except Exception as exc:
            self._update(project_path, job_id, "failed", error=str(exc))
        finally:
            self._processes.pop(job_id, None)
            self._tasks.pop(job_id, None)
            self._job_encoder.pop(job_id, None)

    async def _attach_qc(self, result: dict, project_path: Path) -> dict:
        """Run the deterministic QC gate on a finished render and attach the
        report to the job result. QC findings are diagnostic: they never
        flip the job status (the render itself succeeded).
        """
        output_path = result.get("output_path")
        if not isinstance(output_path, str) or not output_path:
            return result
        from open_edit.qc.gate import run_qc_gate

        out = dict(result)
        try:
            target = result.get("duration_sec") or result.get("duration_s")
            qc = await asyncio.to_thread(
                run_qc_gate,
                output_path,
                project_path / "thumbs",
                target_duration_s=float(target) if target is not None else None,
                mode=out.get("mode"),
            )
            out["qc_report"] = qc.model_dump(mode="json")
        except Exception as exc:
            out["qc_report"] = {
                "passed": False,
                "checks": [
                    {"name": "qc_gate", "passed": False, "detail": f"qc gate failed: {exc}"},
                ],
            }
        return out

    async def _launch(self, project_path: Path, job_id: str, mode: str) -> dict:
        """Run the canonical Python CLI (or overlay bridge) and consume JSON."""
        if mode == "overlay":
            from open_edit.kernel.render_overlay import run_trigger_render as _bridge_trigger_render

            result = await asyncio.to_thread(_bridge_trigger_render, {"mode": "overlay"}, project_path)
            if not isinstance(result, dict):
                raise RuntimeError("overlay renderer returned a non-dict result")
            output_path = result.get("output_path") or result.get("path")
            if not output_path:
                raise RuntimeError(result.get("error") or "overlay renderer reported no output")
            out = dict(result)
            out["ok"] = True
            out["output_path"] = str(output_path)
            out["mode"] = "overlay"
            return out

        command = [sys.executable, "-m", "open_edit.cli", "render", "--mode", mode, "--json"]
        encoder = self._job_encoder.get(job_id) or os.environ.get("OPEN_EDIT_RENDER_BACKEND", "gpu")
        if encoder in ("gpu", "cpu"):
            command += ["--encoder", encoder]
        kwargs: dict = {
            "cwd": str(project_path), "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE, "limit": 16 * 1024 * 1024,
        }
        if os.name == "posix":
            kwargs["start_new_session"] = True
        proc = await asyncio.create_subprocess_exec(*command, **kwargs)
        self._processes[job_id] = proc
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout_s)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            await self._terminate_process_group(proc)
            raise
        if proc.returncode != 0:
            raise RuntimeError(stderr.decode("utf-8", errors="replace").strip() or
                               f"renderer exited {proc.returncode}")
        try:
            result = json.loads(stdout.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError("renderer did not emit a structured JSON result") from exc
        output_path = result.get("output_path")
        if not result.get("ok") or not isinstance(output_path, str) or not output_path:
            raise RuntimeError(result.get("error") or "renderer reported no output")
        return result


def public_job(job: RenderJob) -> dict:
    """Stable JSON-friendly job representation for REST and WebSocket callers."""
    return asdict(job)


# The service is process-wide by design: it owns the global concurrency limit.
DEFAULT_RENDER_SERVICE = RenderService()
