"""Durable host-worker jobs for per-asset source-proxy generation.

Source proxies are deliberately kept out of the render-job and free-form IR
surfaces.  This service persists a small job record per project, then runs the
trusted ``generate_asset_proxy`` function in a bounded host thread pool.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator, Literal

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows uses the thread fallback.
    fcntl = None  # type: ignore[assignment]

from open_edit.render.source_proxy import (
    DEFAULT_SOURCE_PROXY_PROFILE,
    SourceProxyProfile,
    generate_asset_proxy,
)
from open_edit.storage.assets import AssetStore
from open_edit.storage.paths import ProjectPaths


AssetProxyJobStatus = Literal[
    "queued", "running", "succeeded", "failed", "orphaned",
]

_TERMINAL = frozenset({"succeeded", "failed", "orphaned"})
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_UNSET = object()
_FALLBACK_LOCKS: dict[str, threading.Lock] = {}
_FALLBACK_LOCKS_GUARD = threading.Lock()


@dataclass(frozen=True)
class AssetProxyJob:
    job_id: str
    project_id: str
    asset_hash: str
    profile: str
    status: AssetProxyJobStatus
    created_at: float
    updated_at: float
    proxy_hash: str | None = None
    error: str | None = None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS asset_proxy_jobs (
    job_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    asset_hash TEXT NOT NULL,
    profile TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('queued', 'running', 'succeeded', 'failed', 'orphaned')
    ),
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    proxy_hash TEXT,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_asset_proxy_jobs_created
    ON asset_proxy_jobs(created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_asset_proxy_jobs_active_key
    ON asset_proxy_jobs(asset_hash, profile)
    WHERE status IN ('queued', 'running', 'succeeded');
"""


def _project_root(project_path: Path) -> Path:
    """Resolve a project root through the canonical path helper."""
    path = Path(project_path)
    if path.name == ".open_edit":
        return ProjectPaths.for_workdir(path).root
    return ProjectPaths.for_project(path).root


@contextmanager
def _asset_advisory_lock(project_path: Path, asset_hash: str) -> Iterator[None]:
    """Serialize source-proxy encoding for one project/asset pair.

    ``flock`` makes the lock effective across server processes on POSIX.  The
    in-process fallback keeps tests and Windows callers serialized as well.
    """
    lock_path = project_path / ".open_edit" / "locks" / f"asset-proxy-{asset_hash}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if fcntl is None:
        key = str(lock_path.resolve())
        with _FALLBACK_LOCKS_GUARD:
            lock = _FALLBACK_LOCKS.setdefault(key, threading.Lock())
        with lock:
            yield
        return

    with lock_path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class AssetProxyJobService:
    """Persist and execute source-proxy jobs on the host."""

    def __init__(self, *, max_concurrency: int | None = None) -> None:
        configured = (
            max_concurrency
            if max_concurrency is not None
            else int(os.environ.get("OPEN_EDIT_ASSET_PROXY_CONCURRENCY", "1"))
        )
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, configured),
            thread_name_prefix="open-edit-asset-proxy",
        )
        self._futures: dict[tuple[str, str], Future[None]] = {}

    @staticmethod
    def db_path(project_path: Path) -> Path:
        return _project_root(project_path) / ".open_edit" / "asset_proxy_jobs.db"

    def _connect(self, project_path: Path) -> sqlite3.Connection:
        path = self.db_path(project_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(path, timeout=30)
        con.execute("PRAGMA busy_timeout=30000")
        con.execute("PRAGMA journal_mode=WAL")
        self._ensure_schema(con)
        return con

    @staticmethod
    def _ensure_schema(con: sqlite3.Connection) -> None:
        con.executescript(_SCHEMA)

    @staticmethod
    def _row(row: sqlite3.Row) -> AssetProxyJob:
        return AssetProxyJob(
            job_id=row["job_id"],
            project_id=row["project_id"],
            asset_hash=row["asset_hash"],
            profile=row["profile"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            proxy_hash=row["proxy_hash"],
            error=row["error"],
        )

    def _load(self, project_path: Path, job_id: str) -> AssetProxyJob | None:
        with self._connect(project_path) as con:
            con.row_factory = sqlite3.Row
            row = con.execute(
                "SELECT * FROM asset_proxy_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        return self._row(row) if row is not None else None

    def _update(
        self,
        project_path: Path,
        job_id: str,
        status: AssetProxyJobStatus,
        *,
        proxy_hash: str | None | object = _UNSET,
        error: str | None | object = _UNSET,
    ) -> None:
        assignments = ["status = ?", "updated_at = ?"]
        values: list[object] = [status, time.time()]
        if proxy_hash is not _UNSET:
            assignments.append("proxy_hash = ?")
            values.append(proxy_hash)
        if error is not _UNSET:
            assignments.append("error = ?")
            values.append(error)
        values.append(job_id)
        with self._connect(project_path) as con:
            con.execute(
                f"UPDATE asset_proxy_jobs SET {', '.join(assignments)} WHERE job_id = ?",
                values,
            )

    @staticmethod
    def _validate_asset(project_path: Path, asset_hash: str) -> None:
        if not _HASH_RE.fullmatch(asset_hash):
            raise ValueError("asset_hash must be a 64-character lowercase SHA-256 hash")
        store = AssetStore(ProjectPaths.for_project(project_path).assets_dir)
        asset = store.get(asset_hash)
        if asset is None or store.path(asset_hash) is None:
            raise FileNotFoundError(f"canonical asset bytes are missing: {asset_hash}")

    @staticmethod
    def _proxy_cas_exists(project_path: Path, proxy_hash: str | None) -> bool:
        if not proxy_hash:
            # ``not_needed`` source-proxy results legitimately have no CAS
            # object and remain coalescible.
            return True
        store = AssetStore(ProjectPaths.for_project(project_path).assets_dir)
        return store.path(proxy_hash) is not None

    def enqueue(
        self,
        project_id: str,
        project_path: Path,
        asset_hash: str,
        *,
        profile: SourceProxyProfile = DEFAULT_SOURCE_PROXY_PROFILE,
    ) -> AssetProxyJob:
        """Persist and start one host-worker proxy job."""
        root = _project_root(project_path)
        self._validate_asset(root, asset_hash)
        profile_name = profile.name

        # The same lock covers the coalescing read/insert and the worker's
        # encode section.  SQLite's partial unique index is the final guard
        # against a race between separate service processes.
        with _asset_advisory_lock(root, asset_hash):
            with self._connect(root) as con:
                con.row_factory = sqlite3.Row
                row = con.execute(
                    "SELECT * FROM asset_proxy_jobs "
                    "WHERE asset_hash = ? AND profile = ? "
                    "AND status IN ('queued', 'running', 'succeeded') "
                    "ORDER BY created_at DESC LIMIT 1",
                    (asset_hash, profile_name),
                ).fetchone()
                if row is not None:
                    existing = self._row(row)
                    if (
                        existing.status != "succeeded"
                        or self._proxy_cas_exists(root, existing.proxy_hash)
                    ):
                        return existing
                    # A durable success without its derived CAS object is
                    # stale; free its coalescing key for a new attempt.
                    con.execute(
                        "UPDATE asset_proxy_jobs SET status='failed', "
                        "updated_at=?, error=? WHERE job_id=?",
                        (
                            time.time(),
                            "source proxy CAS object is missing",
                            existing.job_id,
                        ),
                    )

                now = time.time()
                job = AssetProxyJob(
                    job_id=uuid.uuid4().hex,
                    project_id=project_id,
                    asset_hash=asset_hash,
                    profile=profile_name,
                    status="queued",
                    created_at=now,
                    updated_at=now,
                )
                try:
                    con.execute(
                        "INSERT INTO asset_proxy_jobs "
                        "(job_id, project_id, asset_hash, profile, status, "
                        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            job.job_id,
                            job.project_id,
                            job.asset_hash,
                            job.profile,
                            job.status,
                            job.created_at,
                            job.updated_at,
                        ),
                    )
                except sqlite3.IntegrityError:
                    # A process that did not share the advisory lock may
                    # still have won the partial unique-index race.
                    raced = con.execute(
                        "SELECT * FROM asset_proxy_jobs "
                        "WHERE asset_hash=? AND profile=? "
                        "AND status IN ('queued', 'running', 'succeeded') "
                        "ORDER BY created_at DESC LIMIT 1",
                        (asset_hash, profile_name),
                    ).fetchone()
                    if raced is None:
                        raise
                    job = self._row(raced)

        if job.status == "queued":
            key = (str(root.resolve()), job.job_id)
            try:
                self._futures[key] = self._executor.submit(
                    self._run, root, job.job_id, profile,
                )
            except Exception as exc:
                self._update(root, job.job_id, "failed", error=str(exc))
                raise
        return job

    def get(self, project_path: Path, job_id: str) -> AssetProxyJob | None:
        return self._load(_project_root(project_path), job_id)

    def list_jobs(self, project_path: Path) -> list[AssetProxyJob]:
        root = _project_root(project_path)
        with self._connect(root) as con:
            con.row_factory = sqlite3.Row
            rows = con.execute(
                "SELECT * FROM asset_proxy_jobs ORDER BY created_at DESC"
            ).fetchall()
        return [self._row(row) for row in rows]

    async def wait(self, project_path: Path, job_id: str) -> AssetProxyJob:
        """Wait for a local worker, then return the durable database row."""
        root = _project_root(project_path)
        key = (str(root.resolve()), job_id)
        future = self._futures.get(key)
        if future is not None:
            try:
                await asyncio.shield(asyncio.wrap_future(future))
            except Exception:
                # The durable row is the source of truth even if a future
                # failed before its final status update.
                pass
        else:
            # A restored service can observe a worker owned by another
            # process. Poll the durable row until that process reaches a
            # terminal state; recover() handles workers that died.
            while True:
                job = self.get(root, job_id)
                if job is None:
                    raise LookupError(f"asset proxy job not found: {job_id}")
                if job.status in _TERMINAL:
                    return job
                await asyncio.sleep(0.05)

        job = self.get(root, job_id)
        if job is None:
            raise LookupError(f"asset proxy job not found: {job_id}")
        return job

    def recover(self, project_path: Path) -> int:
        """Mark jobs interrupted by a prior service process as orphaned."""
        root = _project_root(project_path)
        now = time.time()
        with self._connect(root) as con:
            cur = con.execute(
                "UPDATE asset_proxy_jobs SET status='orphaned', "
                "error=?, updated_at=? "
                "WHERE status IN ('queued', 'running')",
                ("asset proxy service restarted before completion", now),
            )
        return cur.rowcount

    def _run(
        self,
        project_path: Path,
        job_id: str,
        profile: SourceProxyProfile,
    ) -> None:
        job = self.get(project_path, job_id)
        if job is None or job.status in _TERMINAL:
            return
        self._update(project_path, job_id, "running", proxy_hash=None, error=None)
        try:
            with _asset_advisory_lock(project_path, job.asset_hash):
                result = generate_asset_proxy(
                    project_path,
                    job.asset_hash,
                    profile=profile,
                )
            if result.status == "failed":
                self._update(
                    project_path,
                    job_id,
                    "failed",
                    proxy_hash=None,
                    error=result.error or "source proxy generation failed",
                )
            else:
                self._update(
                    project_path,
                    job_id,
                    "succeeded",
                    proxy_hash=result.proxy_hash,
                    error=result.error,
                )
        except Exception as exc:
            self._update(
                project_path,
                job_id,
                "failed",
                proxy_hash=None,
                error=str(exc) or exc.__class__.__name__,
            )


def public_job(job: AssetProxyJob) -> dict:
    """Stable JSON-friendly representation for API callers."""
    return asdict(job)


DEFAULT_ASSET_PROXY_JOB_SERVICE = AssetProxyJobService()
