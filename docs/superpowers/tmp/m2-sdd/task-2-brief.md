# Task 2 Brief

### Task 2: Add the durable `generate-asset-proxy` host job

**Files:**
- Create: `open_edit/kernel/asset_proxy_jobs.py`
- Create: `tests/test_asset_proxy_jobs.py`
- Create: `tests/test_serve_asset_proxy_jobs.py`
- Modify: `open_edit/serve/routers/assets.py`
- Modify: `open_edit/serve/projects.py`
- Modify: `open_edit/agent/tools/pyagent_list_assets.py`
- Test: `tests/test_serve_asset_stream.py`

**Interfaces:**

- Consumes: `generate_asset_proxy()` and `DEFAULT_SOURCE_PROXY_PROFILE` from
  Task 1, the project path resolver, and the existing durable-job style.
- Produces:

```python
AssetProxyJobStatus = Literal[
    "queued", "running", "succeeded", "failed", "orphaned",
]


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


class AssetProxyJobService:
    def enqueue(
        self,
        project_id: str,
        project_path: Path,
        asset_hash: str,
        *,
        profile: SourceProxyProfile = DEFAULT_SOURCE_PROXY_PROFILE,
    ) -> AssetProxyJob:
        """Persist and start one host-worker proxy job."""

    def get(self, project_path: Path, job_id: str) -> AssetProxyJob | None: ...

    def list_jobs(self, project_path: Path) -> list[AssetProxyJob]: ...

    async def wait(self, project_path: Path, job_id: str) -> AssetProxyJob: ...

    def recover(self, project_path: Path) -> int: ...


DEFAULT_ASSET_PROXY_JOB_SERVICE = AssetProxyJobService()
```

The service stores `.open_edit/asset_proxy_jobs.db` with
`job_id`, `project_id`, `asset_hash`, `profile`, `status`, timestamps,
`proxy_hash`, and `error`. Enqueue coalesces queued/running/succeeded rows for
the same `(asset_hash, profile)` and permits a new attempt after `failed`,
`orphaned`, or a missing CAS object. The worker runs
`generate_asset_proxy()` in a bounded host `ThreadPoolExecutor`; it never
enters `run_script`, bwrap, or the free-form IR path. On process restart,
`recover()` marks `queued` and `running` rows `orphaned`, matching the
existing render-job recovery semantics.

- [ ] **Step 1: Write the failing lifecycle and API tests.**

Add these service assertions:

```python
@pytest.mark.asyncio
async def test_proxy_job_persists_runs_and_can_be_reloaded(tmp_path: Path) -> None:
    service = AssetProxyJobService(max_concurrency=1)
    asset_hash = seed_high_res_asset(tmp_path)

    with mock.patch(
        "open_edit.kernel.asset_proxy_jobs.generate_asset_proxy",
        return_value=SourceProxyResult(
            asset_hash=asset_hash,
            proxy_hash="c" * 64,
            profile="source_proxy_360_v1",
            status="ready",
            output_path=str(tmp_path / "proxy"),
            elapsed_sec=0.2,
        ),
    ):
        job = service.enqueue("project", tmp_path, asset_hash)
        finished = await service.wait(tmp_path, job.job_id)

    assert finished.status == "succeeded"
    assert finished.proxy_hash == "c" * 64
    restored = AssetProxyJobService().get(tmp_path, job.job_id)
    assert restored is not None
    assert restored.status == "succeeded"


def test_proxy_job_coalesces_same_asset_and_profile(tmp_path: Path) -> None:
    service = AssetProxyJobService()
    asset_hash = seed_high_res_asset(tmp_path)

    first = service.enqueue("project", tmp_path, asset_hash)
    second = service.enqueue("project", tmp_path, asset_hash)

    assert second.job_id == first.job_id


def test_proxy_job_recovery_marks_interrupted_rows_orphaned(tmp_path: Path) -> None:
    service = AssetProxyJobService()
    insert_running_proxy_job(service, tmp_path, asset_hash="d" * 64)

    assert service.recover(tmp_path) == 1
    assert service.list_jobs(tmp_path)[0].status == "orphaned"
```

Add route tests for:

```python
def test_post_asset_proxy_returns_accepted_job(seeded_project) -> None:
    response = client.post(
        f"/api/projects/{project_id}/assets/{asset_hash}/proxy",
        json={"profile": "source_proxy_360_v1"},
    )
    assert response.status_code == 202
    assert response.json()["job_id"]
    assert response.json()["asset_hash"] == asset_hash


def test_post_asset_proxy_rejects_malformed_hash(seeded_project) -> None:
    response = client.post(
        f"/api/projects/{project_id}/assets/not-a-hash/proxy",
        json={},
    )
    assert response.status_code == 400
```

- [ ] **Step 2: Run the new tests to verify they fail.**

```bash
/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest \
  tests/test_asset_proxy_jobs.py tests/test_serve_asset_proxy_jobs.py \
  -o addopts="" -q
```

Expected: FAIL because the service, database, and routes do not exist.

- [ ] **Step 3: Implement the durable host-worker service.**

Use the same terminal job states as render jobs, but keep a separate database
and dataclass so `RenderJob.mode` remains limited to `proxy`, `final`, and
`overlay`. The enqueue path must:

1. Validate the asset exists before inserting a row.
2. Persist the row before submitting work.
3. Coalesce on `asset_hash` + `profile`; do not coalesce by edit-graph hash.
4. Mark the row `running` before calling the generator.
5. Store `proxy_hash` on success and the generator error on failure.
6. Make `wait()` return the durable row after the worker future finishes.
7. Use an advisory per-project/per-asset lock so two server processes cannot
   encode the same proxy simultaneously.

Add these routes to `open_edit/serve/routers/assets.py`:

```python
@router.post(
    "/api/projects/{project_id}/assets/{asset_hash}/proxy",
    status_code=202,
)
async def post_asset_proxy(project_id: str, asset_hash: str, request: AssetProxyRequest):
    """Queue host-side source-proxy generation and return its job id."""


@router.get(
    "/api/projects/{project_id}/asset_proxy_jobs/{job_id}",
)
async def get_asset_proxy_job(project_id: str, job_id: str):
    """Return durable source-proxy job state."""
```

Only accept the profile name `source_proxy_360_v1` in this task. Unknown
profiles return HTTP 400. Do not expose a free-form command or an arbitrary
ffmpeg argument list.

Extend `serve.projects.AssetInfo` and `_asset_to_info()` with
`proxy_hash`, `proxy_profile`, and `proxy_status`. Extend
`pyagent_list_assets(detail=True)` with the same fields so agents can see
whether a proxy is ready without seeing a guessed filesystem path. Keep
source-proxy derivatives out of the default compact asset listing.

- [ ] **Step 4: Run lifecycle, route, and existing asset-stream tests.**

```bash
/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest \
  tests/test_asset_proxy_jobs.py tests/test_serve_asset_proxy_jobs.py \
  tests/test_serve_asset_stream.py tests/test_storage/test_assets.py \
  -o addopts="" -q
```

Expected: PASS with no changes to the existing canonical asset streaming
contract.

- [ ] **Step 5: Commit the host-worker job surface.**

```bash
git add open_edit/kernel/asset_proxy_jobs.py open_edit/serve/routers/assets.py \
  open_edit/serve/projects.py open_edit/agent/tools/pyagent_list_assets.py \
  tests/test_asset_proxy_jobs.py tests/test_serve_asset_proxy_jobs.py \
  tests/test_serve_asset_stream.py
git commit -m "feat(render): queue durable host source-proxy jobs"
```

---
