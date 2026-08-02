# Source Proxies and QC Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add host-worker per-asset source proxies with explicit emission policy, make proxy cache hits cheap to validate, bound final QC by a duration-aware budget, and keep final export on canonical originals without allowing derived caches to exhaust disk.

**Architecture:** A source proxy is a derived CAS object linked from the canonical asset sidecar by `proxy_hash`; it is never a replacement for the canonical asset and is regenerated when its profile or bytes are missing. A separate durable `generate-asset-proxy` host job creates that object, while render planning selects `original` or `proxy` through an explicit emission profile (`final`, `review-artifact`, `proxy-edit`, or `preview-chunk`) rather than inferring source-proxy semantics from `mode=proxy`. QC policy is selected from render mode and cache-hit state, and one content-aware cache policy owns eviction across render, Remotion, and source-proxy derivatives.

**Tech Stack:** Python 3.11, pydantic v2, pytest/pytest-asyncio, ffmpeg/ffprobe, MLT/melt, the existing `RenderJobService` conventions, SQLite, and the existing content-verified `RenderCache`.

## Global Constraints

- All GPU / melt / ffmpeg / Remotion work stays on the host render worker; free-form never gains `/dev/dri`, CUDA, Chromium, or a new IPC path.
- `mode=proxy` remains a full-timeline low-resolution review artifact; it is not the per-asset source-proxy mechanism and must not silently change its source-media policy.
- `render_project(mode="final")` always resolves canonical source CAS paths; a final render must never consume `Asset.proxy_hash`.
- Preserve the existing `f=rawvideo` frame-server contract and the existing melt → rawvideo → ffmpeg compositor path.
- Preserve canonical source CAS bytes and all source-asset sidecars during eviction. Derived proxy, Remotion, render, and temporary files are the only eviction candidates.
- Every new cache class has an explicit byte cap, age/LRU behavior, and an operator-visible wipe or cleanup path; no cache may grow without a bound.
- Keep `requires-python >= 3.11`, pydantic v2 model-copy patterns, and the existing Ruff configuration. Do not add a dependency.
- `render/` may import IR, storage, and kernel helpers but must not import `serve/`.
- All subprocess stderr is captured and included in structured failure details; no proxy or QC subprocess may use `DEVNULL`.
- Existing QC callers remain compatible: `run_qc_gate()` with no policy argument retains the current full ten-check behavior.
- Do not implement chunked preview, MSE/playlist playback, dirty-zone invalidation, or a live MLT consumer in this plan; those belong to M3/M4.
- No `open_edit/` product code is changed until AH64 approves the implementation plan.
- Use `/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest`; the stale global `open_edit` executable may point at a different worktree.

---

## Scope check

The requested source-proxy, emission, QC, repair, and eviction behaviors share
one correctness boundary: a render must identify which bytes it emitted, how
completely those bytes were checked, and which regenerable bytes may be
removed. Keeping them in one rollout prevents M3 from inventing a second
source-selection or cache/QC policy. Chunked preview generation and playback
remain explicitly deferred to M3.

---

## Scope, ordering, and file map

This is the M2 source-proxy plan plus the QC/disk slices called out by M0, M1, and M5. It has eight implementation tasks. M1 must land before Tasks 4–6 because those tasks consume M1’s cache-hit diagnostics, Remotion cache layout, and render-job lifecycle. Tasks 1–3 can be developed against the current code, but they must be rebased after M1 before touching shared files. M3 starts only after Tasks 1–3 and 5 are complete because the future chunk worker consumes the emission-profile and cache-policy contracts here.

Execution order:

1. M0 vocabulary/instrumentation and M1 cache/QC hooks.
2. Task 1: asset metadata, source-proxy profile, and CAS generation.
3. Task 2: durable `generate-asset-proxy` host job and status surface.
4. Task 3: explicit emission switches and final-original guard.
5. Task 4: cache-aware QC policy and duration-budgeted detectors.
6. Task 5: content-aware cache/disk eviction.
7. Task 6: M5 source-repair and final-export polish.
8. Task 7: operator/agent documentation and migration integration.
9. Task 8: full verification, rebench, and M3 handoff gate.

M1/M2 shared-file rule: if M1 has already modified `open_edit/render/cache.py`, `open_edit/render/materialize.py`, `open_edit/render/orchestrator.py`, or `open_edit/kernel/render_jobs.py`, port the behavior into the M1 version instead of restoring the pre-M1 file. If M1’s QC hook has a different name, preserve the interface below and adapt only the call site.

Files to create:

- `open_edit/render/source_proxy.py` — source-proxy profile, ffmpeg command construction, deterministic generation, CAS placement, and result model.
- `open_edit/kernel/asset_proxy_jobs.py` — durable host-worker queue for `generate-asset-proxy`.
- `open_edit/qc/policy.py` — cache-aware QC policy resolution, budgets, and skipped-report construction.
- `open_edit/storage/cache_policy.py` — byte/age budgets, reference-aware eviction, and cleanup reports.
- `tests/test_render/test_source_proxy.py`
- `tests/test_asset_proxy_jobs.py`
- `tests/test_qc/test_policy.py`
- `tests/test_storage/test_cache_policy.py`
- `tests/test_render/test_timeline_plan.py`
- `tests/test_serve_asset_proxy_jobs.py`

Files to modify:

- `open_edit/ir/types.py`, `open_edit/storage/assets.py` — sidecar metadata and derived-CAS helpers.
- `open_edit/render/timeline_plan.py`, `open_edit/render/orchestrator.py` — explicit source-media selection and diagnostics.
- `open_edit/render/cache.py`, `open_edit/render/materialize.py` — access metadata, cache-class metadata, and eviction hooks.
- `open_edit/qc/gate.py`, `open_edit/qc/black_frames.py`, `open_edit/qc/frozen_frames.py`, `open_edit/qc/silence.py` — policy-aware checks and bounded subprocesses.
- `open_edit/kernel/render_jobs.py`, `open_edit/cli.py` — QC policy selection and report attachment.
- `open_edit/serve/routers/assets.py`, `open_edit/serve/projects.py` — proxy-job endpoint and asset status fields.
- `.env.example`, `skills/qc-standards.md`, `open_edit/harness_skills/qc-standards.md`, `docs/MCP.md` — operator vocabulary, budgets, and source-proxy semantics.

No new MCP tool is added in M2. M3 may call the kernel job service from its host preview scheduler; the free-form IR surface remains unchanged.

---

### Task 1: Add source-proxy metadata, profile, and CAS generation

**Files:**
- Create: `open_edit/render/source_proxy.py`
- Modify: `open_edit/ir/types.py:103-126` (`Asset`)
- Modify: `open_edit/storage/assets.py:110-248` (`AssetStore`)
- Test: `tests/test_render/test_source_proxy.py`
- Test: `tests/test_storage/test_assets.py`
- Test: `tests/test_ir/test_types.py`

**Interfaces:**

- Consumes: canonical `AssetStore.path(asset_hash)`, `AssetStore.get(asset_hash)`, ffprobe metadata, and a host `ffmpeg` executable.
- Produces:

```python
SourceProxyStatus = Literal[
    "none", "queued", "running", "ready", "failed", "not_needed",
]


@dataclass(frozen=True)
class SourceProxyProfile:
    name: str
    height: int
    vcodec: str
    crf: int
    preset: str
    acodec: str
    audio_bitrate: str
    version: int

    def fingerprint(self) -> str:
        return (
            f"{self.name}:v{self.version}:h{self.height}:"
            f"{self.vcodec}:crf={self.crf}:preset={self.preset}:"
            f"{self.acodec}:{self.audio_bitrate}"
        )


DEFAULT_SOURCE_PROXY_PROFILE = SourceProxyProfile(
    name="source_proxy_360_v1",
    height=360,
    vcodec="libx264",
    crf=28,
    preset="veryfast",
    acodec="aac",
    audio_bitrate="96k",
    version=1,
)


@dataclass(frozen=True)
class SourceProxyResult:
    asset_hash: str
    proxy_hash: str | None
    profile: str
    status: SourceProxyStatus
    output_path: str | None
    elapsed_sec: float
    error: str | None = None


def generate_asset_proxy(
    project_path: Path,
    asset_hash: str,
    *,
    profile: SourceProxyProfile = DEFAULT_SOURCE_PROXY_PROFILE,
    timeout_s: float | None = None,
) -> SourceProxyResult:
    """Generate or reuse one low-resolution source-proxy CAS object."""
```

- `Asset` gains `proxy_hash: str | None`, `proxy_profile: str | None`,
  `proxy_status: SourceProxyStatus = "none"`, `proxy_error: str = ""`, and
  `proxy_updated_at: str = ""`. Add `has_alpha: bool = False` to the probed
  metadata so an alpha source is not silently flattened into yuv420p.
- `AssetStore.store_derived(source_path) -> str` hashes a completed temporary
  file, atomically copies it into the normal `<hash[:2]>/<hash>` CAS location,
  and does not create a user-visible canonical-asset sidecar for the derived
  object.
- `AssetStore.update_proxy_metadata(asset_hash, *, proxy_hash, profile,
  status, error="") -> Asset` reloads the current sidecar, updates only proxy
  fields, and atomically replaces the JSON. `clear_proxy_metadata()` performs
  the same operation with `proxy_hash=None` and `status="none"`.

- [ ] **Step 1: Write the failing metadata and generation tests.**

Add these cases to `tests/test_render/test_source_proxy.py`:

```python
def test_asset_proxy_fields_round_trip_through_sidecar(tmp_path: Path) -> None:
    store = AssetStore(tmp_path / ".open_edit" / "assets")
    source = make_video_fixture(tmp_path / "source.mp4", width=1920, height=1080)
    asset = store.ingest(str(source), transcribe=False)

    updated = store.update_proxy_metadata(
        asset.asset_hash,
        proxy_hash="b" * 64,
        profile="source_proxy_360_v1",
        status="ready",
    )
    loaded = store.get(asset.asset_hash)

    assert loaded is not None
    assert loaded.proxy_hash == "b" * 64
    assert loaded.proxy_profile == "source_proxy_360_v1"
    assert loaded.proxy_status == "ready"
    assert updated.proxy_updated_at


def test_generate_asset_proxy_writes_low_res_hash_and_links_source(
    tmp_path: Path,
) -> None:
    source = make_video_fixture(tmp_path / "source.mp4", width=1920, height=1080)
    store = AssetStore(tmp_path / ".open_edit" / "assets")
    asset = store.ingest(str(source), transcribe=False)

    result = generate_asset_proxy(tmp_path, asset.asset_hash)

    assert result.status == "ready"
    assert result.proxy_hash is not None
    assert store.path(result.proxy_hash) is not None
    linked = store.get(asset.asset_hash)
    assert linked is not None
    assert linked.proxy_hash == result.proxy_hash
    assert linked.proxy_profile == DEFAULT_SOURCE_PROXY_PROFILE.name

    proxy_asset = store.get(result.proxy_hash)
    assert proxy_asset is not None
    assert proxy_asset.height <= 360
    assert proxy_asset.duration_sec == pytest.approx(asset.duration_sec, abs=0.2)


def test_generate_asset_proxy_reuses_matching_ready_proxy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = make_video_fixture(tmp_path / "source.mp4", width=1920, height=1080)
    store = AssetStore(tmp_path / ".open_edit" / "assets")
    asset = store.ingest(str(source), transcribe=False)
    first = generate_asset_proxy(tmp_path, asset.asset_hash)

    monkeypatch.setattr(source_proxy.subprocess, "run", fail_if_called)
    second = generate_asset_proxy(tmp_path, asset.asset_hash)

    assert second.status == "ready"
    assert second.proxy_hash == first.proxy_hash


def test_source_proxy_does_not_proxy_audio_or_alpha_sources(tmp_path: Path) -> None:
    audio = make_audio_fixture(tmp_path / "voice.wav")
    store = AssetStore(tmp_path / ".open_edit" / "assets")
    asset = store.ingest(str(audio), transcribe=False)

    result = generate_asset_proxy(tmp_path, asset.asset_hash)

    assert result.status == "not_needed"
    assert result.proxy_hash is None
    assert store.get(asset.asset_hash).proxy_status == "not_needed"


def test_source_proxy_failure_keeps_original_and_records_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = make_video_fixture(tmp_path / "source.mp4", width=1920, height=1080)
    store = AssetStore(tmp_path / ".open_edit" / "assets")
    asset = store.ingest(str(source), transcribe=False)
    monkeypatch.setattr(
        source_proxy.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args, 1, stdout="", stderr="encoder failed",
        ),
    )

    result = generate_asset_proxy(tmp_path, asset.asset_hash)

    assert result.status == "failed"
    assert result.proxy_hash is None
    linked = store.get(asset.asset_hash)
    assert linked is not None
    assert linked.proxy_status == "failed"
    assert "encoder failed" in linked.proxy_error
    assert store.path(asset.asset_hash) is not None
```

The fixture helper must create a real temporary ffmpeg video/audio file; do not
commit a large binary fixture. Use `pytest.skip` only when ffmpeg/ffprobe is
unavailable, matching the existing QC fixture convention.

- [ ] **Step 2: Run the focused tests and verify the new contract fails.**

Run:

```bash
/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest \
  tests/test_render/test_source_proxy.py \
  tests/test_storage/test_assets.py \
  tests/test_ir/test_types.py \
  -o addopts="" -q
```

Expected: FAIL because `Asset` has no proxy fields and
`generate_asset_proxy()`/the sidecar update methods do not exist.

- [ ] **Step 3: Implement the profile and CAS writer.**

Use a temporary `.mp4` under `<project>/.open_edit/tmp/source-proxy/`, with a
unique filename. The generated command must have this shape:

```python
[
    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
    "-i", str(source_path),
    "-map", "0:v:0", "-map", "0:a?",
    "-vf", "scale=w='if(gt(ih,360),-2,iw)':h='min(ih,360)'",
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
    "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-b:a", "96k",
    "-movflags", "+faststart",
    str(temp_output),
]
```

The implementation must:

1. Load the canonical asset and fail with a structured `failed` result when
   the hash or source bytes are missing.
2. Return `not_needed` without creating a proxy for audio, image, alpha, or a
   source whose height is already at or below the target height. The original
   path remains the resolver fallback.
3. Reuse a `ready` proxy only when `proxy_profile` equals the requested profile
   and `AssetStore.path(proxy_hash)` is still a file.
4. Set status to `running` before invoking ffmpeg and restore `failed` with
   captured stderr on any non-zero exit or timeout.
5. Use a timeout of `max(120.0, duration_sec * 4.0 + 60.0)` when the caller
   does not supply one.
6. Verify the temporary output is non-empty, store it by content hash, update
   the source sidecar only after the CAS copy succeeds, and remove the
   temporary file in `finally`.
7. Never overwrite or delete the canonical source CAS file.

Extend `_probe_media()` to record `pix_fmt` and `has_alpha`; keep existing
`Asset` constructors valid through defaults.

- [ ] **Step 4: Run the focused tests and the asset suite.**

Run:

```bash
/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest \
  tests/test_render/test_source_proxy.py \
  tests/test_storage/test_assets.py \
  tests/test_ir/test_types.py \
  -o addopts="" -q
```

Expected: PASS, including the pre-existing sidecar and metadata tests.

- [ ] **Step 5: Commit the independently testable source-proxy core.**

```bash
git add open_edit/render/source_proxy.py open_edit/ir/types.py \
  open_edit/storage/assets.py tests/test_render/test_source_proxy.py \
  tests/test_storage/test_assets.py tests/test_ir/test_types.py
git commit -m "feat(render): add source-proxy metadata and CAS generation"
```

---

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

### Task 3: Add explicit emission switches and enforce originals for final

**Files:**
- Modify: `open_edit/render/timeline_plan.py`
- Modify: `open_edit/render/orchestrator.py`
- Create: `tests/test_render/test_timeline_plan.py`
- Test: `tests/test_render/test_orchestrator.py`
- Test: `tests/test_render/test_emitter.py`

**Interfaces:**

- Consumes: `Asset.proxy_hash` and `Asset.proxy_status`, the Task 2 job service,
  and the existing logical-hash-to-path `asset_paths` map.
- Produces:

```python
EmissionProfile = Literal[
    "final", "review-artifact", "proxy-edit", "preview-chunk",
]
SourceMediaPolicy = Literal["original", "proxy"]


def source_media_policy_for(
    emission_profile: EmissionProfile,
) -> SourceMediaPolicy:
    """Map an explicit emission profile to source or derived media."""


class RenderPlan(BaseModel):
    melt_timeline: Timeline
    overlay_clips: list[OverlayClip]
    asset_paths: dict[str, str]
    emission_profile: EmissionProfile
    source_media_policy: SourceMediaPolicy
    source_proxy_hits: dict[str, str] = Field(default_factory=dict)
    source_proxy_fallbacks: dict[str, str] = Field(default_factory=dict)


def build_render_plan(
    timeline: Timeline,
    ops: list[Operation],
    store: AssetStore,
    mode: str,
    *,
    emission_profile: EmissionProfile | None = None,
    enqueue_missing_proxies: bool = True,
) -> RenderPlan:
    """Build a render plan with explicit source-media semantics."""
```

The policy mapping is intentionally explicit:

```python
{
    "final": "original",
    "review-artifact": "original",
    "proxy-edit": "proxy",
    "preview-chunk": "proxy",
}
```

Thus `mode="proxy"` defaults to `review-artifact` and remains a whole-file
review render. It does not become a source-proxy render merely because both
names contain “proxy”. M3’s future chunk worker will pass
`emission_profile="preview-chunk"`; a future proxy-edit worker will pass
`"proxy-edit"`.

- [ ] **Step 1: Write failing planner and final-safety tests.**

Add the following cases:

```python
def test_preview_chunk_uses_ready_source_proxy(tmp_path: Path) -> None:
    store, asset, proxy_path = seed_asset_with_ready_proxy(tmp_path)
    timeline, ops = timeline_for_asset(asset.asset_hash)

    plan = build_render_plan(
        timeline, ops, store, "proxy",
        emission_profile="preview-chunk",
        enqueue_missing_proxies=False,
    )

    assert plan.source_media_policy == "proxy"
    assert plan.source_proxy_hits[asset.asset_hash] == asset.proxy_hash
    assert plan.asset_paths[asset.asset_hash] == str(proxy_path)


def test_final_plan_uses_original_even_when_proxy_is_ready(tmp_path: Path) -> None:
    store, asset, proxy_path = seed_asset_with_ready_proxy(tmp_path)
    timeline, ops = timeline_for_asset(asset.asset_hash)

    plan = build_render_plan(
        timeline, ops, store, "final",
        emission_profile="final",
        enqueue_missing_proxies=False,
    )

    assert plan.source_media_policy == "original"
    assert plan.asset_paths[asset.asset_hash] == asset.stored_path
    assert str(proxy_path) not in plan.asset_paths.values()


def test_review_artifact_does_not_change_to_source_proxy_semantics(tmp_path: Path) -> None:
    store, asset, _ = seed_asset_with_ready_proxy(tmp_path)
    timeline, ops = timeline_for_asset(asset.asset_hash)

    plan = build_render_plan(
        timeline, ops, store, "proxy",
        emission_profile="review-artifact",
        enqueue_missing_proxies=False,
    )

    assert plan.source_media_policy == "original"
    assert plan.asset_paths[asset.asset_hash] == asset.stored_path


def test_missing_preview_proxy_falls_back_and_queues_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, asset = seed_asset_without_proxy(tmp_path)
    timeline, ops = timeline_for_asset(asset.asset_hash)
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "open_edit.kernel.asset_proxy_jobs.DEFAULT_ASSET_PROXY_JOB_SERVICE.enqueue",
        lambda project_id, project_path, asset_hash, profile: (
            calls.append((asset_hash, profile.name))
            or object()
        ),
    )

    plan = build_render_plan(
        timeline, ops, store, "proxy",
        emission_profile="proxy-edit",
        enqueue_missing_proxies=True,
    )

    assert plan.source_proxy_fallbacks[asset.asset_hash] == "queued"
    assert plan.asset_paths[asset.asset_hash] == asset.stored_path
    assert calls == [(asset.asset_hash, "source_proxy_360_v1")]


def test_final_render_rejects_non_final_emission_profile(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="final emission"):
        render_project(
            "project", tmp_path, tmp_path / "renders",
            mode="final", emission_profile="preview-chunk",
        )
```

Add an emitter assertion that a final plan’s XML contains the canonical
`stored_path`, not the proxy path, for the logical asset hash.

- [ ] **Step 2: Run planner tests and verify the old mode-only planner fails.**

```bash
/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest \
  tests/test_render/test_timeline_plan.py \
  tests/test_render/test_orchestrator.py \
  tests/test_render/test_emitter.py \
  -o addopts="" -q
```

Expected: FAIL because `RenderPlan` has no emission fields and
`resolve_asset_paths()` always returns the original CAS path.

- [ ] **Step 3: Implement the explicit source-media resolver.**

Keep `asset_paths` keyed by the logical canonical `asset_hash`; only the
value changes to the physical proxy path. For each referenced asset:

1. `source_media_policy="original"` returns `AssetStore.path(asset_hash)`.
2. `source_media_policy="proxy"` selects a proxy only when
   `proxy_status == "ready"`, `proxy_profile == "source_proxy_360_v1"`,
   `proxy_hash` is present, and `AssetStore.path(proxy_hash)` exists.
3. A missing/stale proxy records a fallback reason, optionally enqueues one
   Task 2 job, and returns the canonical source path for the current render.
4. Materialized Remotion assets are not source-proxied: they have no
   `proxy_hash` and continue to use the profile-specific materialized CAS
   clip generated by `materialize_remotion_compositions()`.
5. A final plan raises before emission if its policy is not `original`.

Add `emission_profile` as an optional keyword to `render_project()`. Infer
`final` for `mode="final"` and `review-artifact` for `mode="proxy"` when the
caller omits it. Include `source_media_policy`, hit/fallback maps, and the
requested profile fingerprint in `RenderResult.diagnostics`.

For a non-default proxy-edit render, include the source-proxy profile
fingerprint in the cache content fingerprint so a proxy-backed output cannot
collide with an original-backed output. Keep current `mode=proxy` and
`mode=final` cache keys stable when their default profiles are used.

- [ ] **Step 4: Run the planner, emitter, orchestrator, and pre-existing render tests.**

```bash
/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest \
  tests/test_render/test_timeline_plan.py \
  tests/test_render/test_orchestrator.py \
  tests/test_render/test_emitter.py \
  tests/test_render/ \
  -o addopts="" -q
```

Expected: PASS, including the existing profile-scoped cache and hwaccel retry
tests.

- [ ] **Step 5: Commit the source-media emission contract.**

```bash
git add open_edit/render/timeline_plan.py open_edit/render/orchestrator.py \
  tests/test_render/test_timeline_plan.py tests/test_render/test_orchestrator.py \
  tests/test_render/test_emitter.py
git commit -m "feat(render): add explicit source-media emission profiles"
```

---

### Task 4: Add cache-aware QC policy and duration-budgeted detectors

**Files:**
- Create: `open_edit/qc/policy.py`
- Modify: `open_edit/qc/gate.py`
- Modify: `open_edit/qc/black_frames.py`
- Modify: `open_edit/qc/frozen_frames.py`
- Modify: `open_edit/qc/silence.py`
- Modify: `open_edit/kernel/render_jobs.py`
- Modify: `open_edit/cli.py`
- Create: `tests/test_qc/test_policy.py`
- Test: `tests/test_qc/test_gate.py`
- Test: `tests/test_qc/test_black_frames.py`
- Test: `tests/test_render_jobs.py`

**Interfaces:**

- Consumes: `RenderResult.cache_hit`, render mode, current `QCReport`, and
  ffprobe’s container duration.
- Produces:

```python
QCMode = Literal["skip", "light", "full"]


@dataclass(frozen=True)
class QCPolicy:
    mode: QCMode
    total_budget_sec: float | None
    blackdetect_max_sec: float

    def blackdetect_timeout(self, duration_sec: float | None) -> float:
        if duration_sec is None or duration_sec <= 0:
            return min(60.0, self.blackdetect_max_sec)
        return max(
            60.0,
            min(self.blackdetect_max_sec, duration_sec * 0.75),
        )


def resolve_qc_policy(
    render_mode: str | None,
    *,
    cache_hit: bool,
) -> QCPolicy:
    """Resolve proxy warm/cold and final policy from mode plus environment."""


def skipped_qc_report(
    video_path: str,
    *,
    policy: QCPolicy,
    reason: str,
) -> QCReport:
    """Return a stable, explicit report without decoding the whole video."""
```

Policy defaults:

- Cold `proxy`: `OPEN_EDIT_PROXY_QC_MODE=light` (core file/stream/duration/
  audio-sync checks; black, frozen, silence, and thumbnail are marked skipped).
- Warm `proxy` cache hit: `OPEN_EDIT_PROXY_WARM_QC_MODE=skip` (no expensive
  decode; the report explicitly says it was skipped because the deliverable
  cache was hit). `light` remains an allowed operator override.
- `final`: always `full`, with `OPEN_EDIT_FINAL_QC_BUDGET_SEC=900` and
  `OPEN_EDIT_QC_BLACKDETECT_MAX_SEC=900` defaults.
- `overlay`: `full` unless an existing caller explicitly requests another
  policy.

The report remains diagnostic and never changes a successful render job to
`failed`. A final detector timeout is represented as
`passed=False`, `skipped=True`, and `complete=False` so delivery tooling cannot
mistake an incomplete final QC run for a clean delivery. A proxy light/skip
report uses `passed=True` for deliberately skipped checks but also sets
`complete=False` and includes `policy`/`reason`.

- [ ] **Step 1: Write failing policy and timeout tests.**

Add:

```python
def test_proxy_warm_cache_hit_defaults_to_skip(monkeypatch) -> None:
    monkeypatch.delenv("OPEN_EDIT_PROXY_WARM_QC_MODE", raising=False)
    policy = resolve_qc_policy("proxy", cache_hit=True)
    assert policy.mode == "skip"


def test_proxy_cold_defaults_to_light(monkeypatch) -> None:
    monkeypatch.delenv("OPEN_EDIT_PROXY_QC_MODE", raising=False)
    policy = resolve_qc_policy("proxy", cache_hit=False)
    assert policy.mode == "light"


def test_final_policy_is_full_and_duration_budgeted() -> None:
    policy = resolve_qc_policy("final", cache_hit=True)
    assert policy.mode == "full"
    assert policy.blackdetect_timeout(180.0) == pytest.approx(135.0)
    assert policy.blackdetect_timeout(3600.0) == 900.0


def test_light_policy_does_not_call_expensive_detectors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = write_valid_test_video(tmp_path / "out.mp4")
    monkeypatch.setattr(gate_mod, "list_black_frames", fail_if_called)
    monkeypatch.setattr(gate_mod, "list_frozen_frames", fail_if_called)
    monkeypatch.setattr(gate_mod, "list_silence", fail_if_called)

    report = run_qc_gate(
        str(output), tmp_path / "thumbs",
        target_duration_s=2.0,
        mode="proxy",
        policy=QCPolicy("light", None, 900.0),
    )

    assert report.policy == "light"
    assert report.complete is False
    assert all(
        check.skipped
        for check in report.checks
        if check.name in {"black_frames", "frozen_frames", "silence", "thumbnail"}
    )


def test_blackdetect_timeout_becomes_structured_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"not decoded")
    monkeypatch.setattr(black_frames_mod.shutil, "which", lambda _: "ffmpeg")
    monkeypatch.setattr(
        black_frames_mod.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired(kwargs["timeout"], kwargs["timeout"])
        ),
    )

    result = list_black_frames(str(source), timeout_s=7.0)

    assert result.ok is False
    assert "timed out" in (result.error or "")
```

Add a `RenderJobService` test that patches `run_qc_gate`, returns a
`RenderResult` with `mode="proxy"` and `cache_hit=True`, and asserts the
service passes `QCMode.skip` rather than full. Add a final-mode test asserting
`QCMode.full` is passed even when `cache_hit=True`.

- [ ] **Step 2: Run QC/job tests and verify policy plumbing fails.**

```bash
/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest \
  tests/test_qc/test_policy.py tests/test_qc/test_gate.py \
  tests/test_qc/test_black_frames.py tests/test_render_jobs.py \
  -o addopts="" -q
```

Expected: FAIL because the policy model, skipped fields, and detector timeout
arguments do not exist.

- [ ] **Step 3: Implement the policy without changing default full QC.**

Add `skipped: bool = False` to `QCCheck`, and add `policy: QCMode = "full"`,
`complete: bool = True`, `elapsed_sec: float = 0.0`, and `reason: str = ""`
to `QCReport`. Extend `run_qc_gate()` with
`policy: QCPolicy | QCMode | None = None`; normalize a string to a
`QCPolicy`, but keep `None` equivalent to full.

For light/skip reports, emit the same named checks as the full report so UI
consumers do not need a second schema. Mark skipped checks with
`skipped=True` and a detail such as
`"skipped by policy=light; render completed successfully"`.

In `RenderJobService._attach_qc()`:

```python
policy = resolve_qc_policy(
    out.get("mode"),
    cache_hit=bool(out.get("cache_hit", False)),
)
out["qc_policy"] = policy.mode
qc = await asyncio.to_thread(
    run_qc_gate,
    output_path,
    project_path / "thumbs",
    target_duration_s=float(target) if target is not None else None,
    mode=out.get("mode"),
    source_baseline=(result.get("diagnostics") or {}).get("source_baseline"),
    policy=policy,
)
```

Do not call the expensive detectors at all for `skip` or `light`. The CLI’s
human-readable path must use the same resolver after a successful non-JSON
render; the JSON path remains render-result-only because the server attaches
QC after consuming JSON.

- [ ] **Step 4: Fix blackdetect and other detector timeouts.**

Change `list_black_frames()` to accept `timeout_s: float | None = None`,
defaulting to 60 seconds for direct callers, and catch
`subprocess.TimeoutExpired`. Pass the duration-aware value from `run_qc_gate()`:

```python
black_timeout = policy.blackdetect_timeout(duration_sec)
bf_result = list_black_frames(video_path, timeout_s=black_timeout)
```

Add optional `timeout_s` parameters to `list_frozen_frames()` and
`list_silence()` and pass the remaining final-QC budget to each expensive
detector. Every timeout returns a structured result and allows the gate to
finish the other checks. The existing scale-height optimization remains in
place; do not remove it in favor of a larger timeout.

- [ ] **Step 5: Run all QC and render-job tests.**

```bash
/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest \
  tests/test_qc/ tests/test_render_jobs.py tests/test_serve_render_jobs.py \
  tests/test_cli.py \
  -o addopts="" -q
```

Expected: PASS. Existing default `run_qc_gate()` tests must still report ten
checks and retain their current check names.

- [ ] **Step 6: Commit cache-aware QC policy.**

```bash
git add open_edit/qc/policy.py open_edit/qc/gate.py \
  open_edit/qc/black_frames.py open_edit/qc/frozen_frames.py \
  open_edit/qc/silence.py open_edit/kernel/render_jobs.py open_edit/cli.py \
  tests/test_qc/test_policy.py tests/test_qc/test_gate.py \
  tests/test_qc/test_black_frames.py tests/test_render_jobs.py
git commit -m "feat(qc): add cache-aware policies and duration budgets"
```

---

### Task 5: Enforce content-aware disk and cache eviction

**Files:**
- Create: `open_edit/storage/cache_policy.py`
- Modify: `open_edit/render/cache.py`
- Modify: `open_edit/render/materialize.py`
- Modify: `open_edit/render/orchestrator.py`
- Modify: `open_edit/render/source_proxy.py`
- Modify: `open_edit/kernel/asset_proxy_jobs.py`
- Modify: `.env.example`
- Create: `tests/test_storage/test_cache_policy.py`
- Test: `tests/test_render/test_cache.py`
- Test: `tests/test_remotion_ir_materialize.py`

**Interfaces:**

- Consumes: content-verified `RenderCache` metadata, source sidecar
  `proxy_hash` references, Remotion `out/cache`, `out/proxy`, `out/final`,
  render output cache, and active job paths.
- Produces:

```python
@dataclass(frozen=True)
class CacheSettings:
    render_cache_max_bytes: int
    remotion_cache_max_bytes: int
    source_proxy_max_bytes: int
    max_age_sec: int
    min_free_bytes: int

    @classmethod
    def from_env(cls) -> "CacheSettings": ...


@dataclass(frozen=True)
class CacheEvictionReport:
    inspected_bytes: int
    deleted_bytes: int
    deleted_paths: tuple[str, ...]
    protected_paths: tuple[str, ...]
    warnings: tuple[str, ...]


def enforce_project_cache(
    project_path: Path,
    *,
    active_paths: Iterable[Path] = (),
    settings: CacheSettings | None = None,
) -> CacheEvictionReport:
    """Bound all expendable project caches without deleting source CAS."""
```

Default environment values are conservative for this host:

```text
OPEN_EDIT_RENDER_CACHE_MAX_BYTES=1073741824
OPEN_EDIT_REMOTION_CACHE_MAX_BYTES=536870912
OPEN_EDIT_SOURCE_PROXY_MAX_BYTES=1073741824
OPEN_EDIT_CACHE_MAX_AGE_SEC=86400
OPEN_EDIT_CACHE_MIN_FREE_BYTES=536870912
```

Every value is overrideable and invalid/non-positive values fall back to the
documented default. `min_free_bytes` is an additional pressure signal; the
evictor applies the same ordering when free space falls below it.

- [ ] **Step 1: Write failing eviction and LRU tests.**

Add:

```python
def test_render_cache_hit_updates_last_access_without_changing_source_hash(
    tmp_path: Path,
) -> None:
    cache = RenderCache(tmp_path / "render_cache")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"render")
    cached = cache.put("key", source)
    before = json.loads(
        (tmp_path / "render_cache" / ".meta" / "key.mp4.json").read_text()
    )["source_hash"]

    time.sleep(0.01)
    assert cache.get("key") == cached

    metadata = json.loads(
        (tmp_path / "render_cache" / ".meta" / "key.mp4.json").read_text()
    )
    assert metadata["source_hash"] == before
    assert metadata["last_accessed_at"] >= metadata["updated_at"]


def test_eviction_keeps_canonical_sources_and_active_final(
    tmp_path: Path,
) -> None:
    project = seed_project_with_source_and_caches(tmp_path)
    active_final = project / ".open_edit" / "renders" / "project-final.mp4"
    report = enforce_project_cache(
        project,
        active_paths=[active_final],
        settings=CacheSettings(
            render_cache_max_bytes=100,
            remotion_cache_max_bytes=100,
            source_proxy_max_bytes=100,
            max_age_sec=0,
            min_free_bytes=0,
        ),
    )

    assert active_final.exists()
    assert canonical_source_path(project).exists()
    assert report.deleted_bytes > 0


def test_eviction_clears_source_proxy_reference_when_proxy_is_deleted(
    tmp_path: Path,
) -> None:
    project, source_hash, proxy_hash = seed_project_with_proxy(tmp_path)

    enforce_project_cache(
        project,
        settings=CacheSettings(
            render_cache_max_bytes=10**9,
            remotion_cache_max_bytes=10**9,
            source_proxy_max_bytes=1,
            max_age_sec=0,
            min_free_bytes=0,
        ),
    )

    source = AssetStore(project / ".open_edit" / "assets").get(source_hash)
    assert source is not None
    assert source.proxy_hash is None
    assert source.proxy_status == "none"
    assert AssetStore(project / ".open_edit" / "assets").path(proxy_hash) is None
```

- [ ] **Step 2: Run cache tests and verify eviction APIs are absent.**

```bash
/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest \
  tests/test_storage/test_cache_policy.py tests/test_render/test_cache.py \
  tests/test_remotion_ir_materialize.py \
  -o addopts="" -q
```

Expected: FAIL because there is no project evictor and `RenderCache.get()`
does not record access time.

- [ ] **Step 3: Implement the content-aware eviction order.**

Extend `RenderCache.put()` metadata with `cache_class`, optional `mode`, and
`last_accessed_at`; extend `get()` to update only `last_accessed_at` after
content verification. Add `remove()` that deletes a data file and its
`.meta` sidecar together. Existing callers that do not pass metadata retain
the current schema and behavior.

`enforce_project_cache()` must use this order:

1. Never delete canonical source CAS objects or their sidecars.
2. Protect active render outputs, active proxy-job temporary files, newest
   successful final deliverable, and newest review artifact per mode.
3. Evict stale/unreferenced Remotion `out/proxy`/`out/final` outputs and
   stale Remotion cache entries by `last_accessed_at`.
4. Evict old render-cache entries while retaining the protected newest
   deliverables.
5. Evict source-proxy CAS objects by oldest access/creation order when the
   source-proxy budget is exceeded; clear every source sidecar that points at
   a deleted proxy and leave the source status `none`.
6. Remove orphaned `.audio.wav`, `.repaired.mp4`, `.melt.mp4`, and proxy-job
   temp files only when no active job references them.

The reference scanner must distinguish a derived source proxy from a
canonical asset by reading source sidecars. It must not infer “safe to delete”
from a filename alone. Deleting a corrupted cache entry is allowed only after
its content metadata fails verification; deleting a canonical CAS file is
never allowed.

Call `enforce_project_cache()` after a successful render-cache put, after a
Remotion materialize cache put, and after a source-proxy job completes. Add
eviction counts and warnings under `diagnostics["cache_eviction"]`; cleanup
failure must not turn an otherwise successful render into a failed render.

Append the five environment variables above to `.env.example` with comments
that identify source CAS as protected and all values as byte/second budgets.

- [ ] **Step 4: Run cache/materialize tests and a disk-pressure smoke test.**

```bash
/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest \
  tests/test_storage/test_cache_policy.py tests/test_render/test_cache.py \
  tests/test_remotion_ir_materialize.py tests/test_render/test_orchestrator.py \
  -o addopts="" -q
```

Expected: PASS, with no deletion of canonical source bytes and no orphaned
`.meta` files for deleted derived entries.

- [ ] **Step 5: Commit bounded cache policy.**

```bash
git add open_edit/storage/cache_policy.py open_edit/render/cache.py \
  open_edit/render/materialize.py open_edit/render/orchestrator.py \
  open_edit/render/source_proxy.py open_edit/kernel/asset_proxy_jobs.py \
  .env.example tests/test_storage/test_cache_policy.py \
  tests/test_render/test_cache.py tests/test_remotion_ir_materialize.py
git commit -m "feat(storage): bound render, Remotion, and source-proxy caches"
```

---

### Task 6: Apply M5 repair and final-export polish

**Files:**
- Modify: `open_edit/render/source_repair.py`
- Modify: `open_edit/render/orchestrator.py`
- Test: `tests/test_render/test_source_repair.py`
- Test: `tests/test_render/test_orchestrator.py`
- Test: `tests/test_e2e_render.py`

**Interfaces:**

- Consumes: Task 3’s source-media policy, Task 4’s detector budgets, existing
  source-baseline spans, and the overlay-protection interval logic.
- Produces a bounded repair API:

```python
def repair_render_output(
    video_path: str | Path,
    output_path: str | Path,
    source_baseline: dict[str, Any] | None = None,
    *,
    repair_source_black: bool = True,
    repair_source_frozen: bool = False,
    repair_intentional_black: bool = False,
    protected_spans: Iterable[dict[str, Any] | tuple[float, float]] = (),
    detector_timeout_s: float | None = None,
    skip_if_no_source_defects: bool = True,
) -> dict[str, Any]:
    """Repair only confirmed source defects within the allowed budget."""
```

- [ ] **Step 1: Write failing early-out and protected-overlay tests.**

Add:

```python
def test_repair_returns_without_output_decode_when_source_has_no_defects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    rendered = make_rendered_video(tmp_path / "rendered.mp4")
    monkeypatch.setattr(mod, "list_black_frames", fail_if_called)
    monkeypatch.setattr(mod, "list_frozen_frames", fail_if_called)

    result = mod.repair_render_output(
        rendered,
        tmp_path / "repaired.mp4",
        source_baseline={"black_frames": [], "frozen_frames": [], "errors": []},
    )

    assert result["ok"] is True
    assert result["changed"] is False
    assert result["output_path"] == str(rendered)


def test_repair_never_rewrites_protected_overlay_interval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    rendered = make_rendered_video(tmp_path / "rendered.mp4")
    captured: dict[str, object] = {}

    def fake_black(path, *args, **kwargs):
        captured["black_kwargs"] = kwargs
        return black_result_for_span(0.0, 4.0)

    monkeypatch.setattr(mod, "list_black_frames", fake_black)
    monkeypatch.setattr(mod, "list_frozen_frames", lambda *a, **k: frozen_result_empty())
    monkeypatch.setattr(mod, "_repair_stream", fake_repair_stream)

    result = mod.repair_render_output(
        rendered,
        tmp_path / "repaired.mp4",
        source_baseline={
            "black_frames": [{"start_sec": 0.0, "end_sec": 4.0}],
            "frozen_frames": [],
        },
        protected_spans=[(1.0, 3.0)],
        detector_timeout_s=30.0,
    )

    assert result["ok"] is True
    assert result["protected_spans"] == [{"start_sec": 1.0, "end_sec": 3.0}]
    assert captured["black_kwargs"]["timeout_s"] == 30.0
```

- [ ] **Step 2: Run source-repair tests to verify the optimization fails.**

```bash
/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest \
  tests/test_render/test_source_repair.py tests/test_render/test_orchestrator.py \
  -o addopts="" -q
```

Expected: FAIL because repair currently probes the complete output even when
the baseline is empty and has no detector budget argument.

- [ ] **Step 3: Implement the safe M5 repair policy.**

Change `SOURCE_REPAIR_POLICY_VERSION` to a new value that names the early-out
and overlay-protected semantics. Before output detection, return
`changed=False` when all of these are true:

- `skip_if_no_source_defects` is true;
- both source black/frozen span lists are empty;
- `source_baseline["errors"]` is empty;
- `repair_intentional_black` is false.

When source spans exist, expand each source span by 1 second, clamp it to the
render duration, merge overlapping windows, and call black/frozen detection
only over those windows with `timeout_s=detector_timeout_s`. Keep
`_subtract_protected_spans()` as the final step before `_merge_repair_spans()`;
never interpolate over a Remotion or video-overlay interval.

In `render_project()`:

- `emission_profile="final"` always uses original source paths, source
  baseline collection, repair, and full final QC.
- `emission_profile="review-artifact"` retains the existing repair behavior but
  receives the same detector budget and policy diagnostics.
- `emission_profile` values used by future preview/chunk workers do not run
  source repair in this whole-file orchestrator.
- Pass final QC’s remaining budget to repair and record
  `diagnostics["repair_policy"]`, `changed`, `protected_spans`, and timeout
  details.
- Keep the optional “concat short overlays” optimization out of the default
  path. It may be implemented only in a later task if a Phase 1-style N-overlay
  rebench demonstrates a measured ffmpeg regression; it is not required for
  the source-proxy/QC contract.

- [ ] **Step 4: Run repair and final safety tests.**

```bash
/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest \
  tests/test_render/test_source_repair.py \
  tests/test_render/test_orchestrator.py \
  tests/test_e2e_render.py \
  -o addopts="" -q
```

Expected: PASS, including the existing regression that source repair cannot
erase overlays and the existing source-byte immutability test.

- [ ] **Step 5: Commit M5 repair polish.**

```bash
git add open_edit/render/source_repair.py open_edit/render/orchestrator.py \
  tests/test_render/test_source_repair.py tests/test_render/test_orchestrator.py \
  tests/test_e2e_render.py
git commit -m "perf(render): bound source repair and preserve final overlays"
```

---

### Task 7: Document policy, operator controls, and M0 terminology

**Files:**
- Modify: `.env.example`
- Modify: `skills/qc-standards.md`
- Modify: `open_edit/harness_skills/qc-standards.md`
- Modify: `docs/MCP.md`
- Test: `tests/test_mcp_server.py`
- Test: `tests/test_serve_projects.py`

**Interfaces:**

- Consumes: the final `AssetInfo` proxy fields, `QCReport.policy/complete`,
  cache diagnostics, and the explicit emission-profile names.
- Produces operator and agent documentation that uses three distinct terms:
  `mode=proxy` review artifact, per-asset source proxy, and future timeline
  preview chunks.

- [ ] **Step 1: Write documentation contract tests.**

Add tests that load both QC skill copies and assert they contain:

```python
required_terms = (
    "mode=proxy",
    "source proxy",
    "preview chunks",
    "qc_report",
    "complete",
    "final export",
)
for term in required_terms:
    assert term in canonical_skill
    assert term in harness_skill
assert canonical_skill == harness_skill
```

Add a project-state test that serializes an `Asset` with
`proxy_status="queued"` and verifies the API exposes status but not a guessed
filesystem path for the proxy.

- [ ] **Step 2: Update the operator/agent copy.**

Document:

1. Source proxies are low-resolution CAS siblings selected only by
   `proxy-edit`/`preview-chunk` emission profiles.
2. `mode=proxy` is still a complete review MP4 and is not interactive scrub.
3. `mode=final` always uses canonical originals.
4. Proxy warm hits may report `policy=skip` or `policy=light`; inspect
   `qc_report.complete` before treating a proxy as fully QC’d.
5. Final QC remains available and uses a duration-aware blackdetect budget;
   a timeout is incomplete diagnostic evidence, not permission to ship
   blindly.
6. Cache eviction protects canonical sources and newest deliverables but may
   remove regenerable source proxies and Remotion/render derivatives.

Keep `skills/qc-standards.md` and
`open_edit/harness_skills/qc-standards.md` byte-identical. Update `docs/MCP.md`
to replace the misleading “proxy = 720p” wording with the actual
`fast_proxy` 640×360 artifact and to explain that source proxies are a
separate host-worker derivative. Do not add a new free-form or MCP command.

Append the source-proxy, QC, and cache environment variables from Tasks 4 and
5 to `.env.example`; retain existing user values and comments.

- [ ] **Step 3: Run documentation and API contract tests.**

```bash
/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest \
  tests/test_mcp_server.py tests/test_serve_projects.py \
  tests/test_serve_asset_proxy_jobs.py \
  -o addopts="" -q
cmp -s skills/qc-standards.md open_edit/harness_skills/qc-standards.md
```

Expected: PASS and byte-identical skill copies.

- [ ] **Step 4: Commit terminology and operator policy.**

```bash
git add .env.example skills/qc-standards.md \
  open_edit/harness_skills/qc-standards.md docs/MCP.md \
  tests/test_mcp_server.py tests/test_serve_projects.py
git commit -m "docs(render): document source-proxy and QC cache policy"
```

---

### Task 8: Run the integration gate and hand off stable M3 contracts

**Files:** No product files are created in this task; verification and
measurement only.

**Interfaces:**

- Consumes every Task 1–7 interface.
- Produces the evidence required to start M3 without reinterpreting
  `mode=proxy` or reimplementing cache/QC behavior.

- [ ] **Step 1: Run focused source-proxy, QC, cache, and job tests.**

```bash
/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest \
  tests/test_render/test_source_proxy.py \
  tests/test_render/test_timeline_plan.py \
  tests/test_render/test_source_repair.py \
  tests/test_qc/ \
  tests/test_storage/test_cache_policy.py \
  tests/test_render/test_cache.py \
  tests/test_asset_proxy_jobs.py \
  tests/test_serve_asset_proxy_jobs.py \
  tests/test_render_jobs.py \
  -o addopts="" -q
```

Expected: 0 failures.

- [ ] **Step 2: Run all render, storage, serve, and layering tests.**

```bash
/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest \
  tests/test_render/ tests/test_storage/ tests/test_qc/ \
  tests/test_serve_render_jobs.py tests/test_serve_projects.py \
  tests/test_serve_asset_stream.py tests/test_layering.py \
  -o addopts="" -q
```

Expected: 0 failures and no free-form sandbox changes.

- [ ] **Step 3: Run the complete suite and static checks.**

```bash
/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest \
  -o addopts="" -q tests/
/home/ah64/apps/mlt-pipeline/.venv/bin/ruff check open_edit/
/home/ah64/apps/mlt-pipeline/.venv/bin/python -m compileall -q open_edit
```

Expected: the full suite passes, Ruff reports no errors, and bytecode
compilation succeeds.

- [ ] **Step 4: Re-run Phase 1 fixtures with source-proxy and QC diagnostics.**

Run the existing host-only benchmark harness against fixtures A, B, and C
once cold and once warm. Record JSON containing:

- source-proxy generation time, profile, source/proxy hashes, and bytes;
- `source_media_policy`, proxy hits, and fallback reasons;
- `qc_policy`, `qc_report.complete`, detector elapsed times, and timeout
  details;
- cache bytes before/after and `deleted_bytes`.

Acceptance evidence:

1. A final render’s emitted MLT references original source CAS paths even when
   a ready `proxy_hash` exists.
2. A preview-chunk/proxy-edit plan uses a ready source proxy and queues one
   job when it is missing; a fallback is explicit.
3. A warm proxy cache hit does not run blackdetect, freezedetect, silence, or
   thumbnail extraction under the default policy.
4. A long final does not fail at the old fixed 60-second blackdetect timeout;
   a budget exhaustion produces an explicit incomplete QC report.
5. Repeated renders cannot grow render/Remotion/source-proxy cache classes
   beyond their configured caps, and canonical source CAS remains intact.
6. The frame-server `f=rawvideo` tests and final-original guard remain green.

- [ ] **Step 5: Record the M3 handoff, then stop before chunk implementation.**

The handoff must name these stable calls:

```python
build_render_plan(
    timeline,
    ops,
    store,
    mode="proxy",
    emission_profile="preview-chunk",
)

source_media_policy_for("preview-chunk")  # "proxy"
source_media_policy_for("final")          # "original"

DEFAULT_ASSET_PROXY_JOB_SERVICE.enqueue(
    project_id,
    project_path,
    asset_hash,
)

enforce_project_cache(project_path)
```

M3 may add range emission, chunk sidecars, dirty invalidation, audio
independence, and Review Studio playback. It must not duplicate source-proxy
generation, final-original enforcement, QC policy resolution, or eviction.

---

## Explicit non-goals

- Do not implement the M3 `preview-chunks` job, chunk sidecar schema, dirty
  interval invalidation, playlist/MSE playback, or audio-independent chunk
  cache here.
- Do not rename or repurpose `mode=proxy`; it remains a whole-file review
  artifact and is not the interactive scrub solution.
- Do not use source proxies for `mode=final`, even when a proxy is newer or
  cheaper to decode.
- Do not replace MLT/melt, the rawvideo pipe, ffmpeg overlay burn-in, or the
  Remotion frame engine.
- Do not put ffmpeg, melt, Chromium, CUDA, or `/dev/dri` inside the free-form
  sandbox.
- Do not evict canonical source CAS bytes, rewrite source media, or make
  agents reference proxy filesystem paths directly.
- Do not add a new MCP tool or free-form IR operation for source-proxy
  generation in M2.
- Do not broaden this work into asset-library indexing, provider search,
  licensing, attribution, or semantic asset ranking.
- Do not make source-proxy generation synchronous on every ingest by default;
  generation is an explicit durable host job and preview/profile selection may
  queue it with an original-media fallback.
- Do not mark timed-out final QC as clean; preserve the successful render
  status while reporting incomplete diagnostic evidence.
- Do not implement speculative overlay concatenation or a greenfield
  zero-copy/GPU compositor without a new measurement-backed plan.

## Risks and mitigations

- **M1 merge overlap:** Tasks 4–6 touch M1 files. Rebase after M1 and preserve
  M1’s cache-hit gate, Remotion concurrency, and diagnostics rather than
  applying these hunks mechanically.
- **Proxy fallback hides a slow first preview:** return explicit fallback
  diagnostics and job id/status; never claim a proxy hit when the original was
  used.
- **Alpha or unsupported media is flattened:** probe alpha and mark such
  assets `not_needed`; use the canonical original until an alpha-preserving
  profile exists.
- **Proxy sidecar races with transcription/import metadata:** every sidecar
  update reloads the current model and atomically replaces only its own
  fields; add concurrent-update regression coverage if the existing store
  gains a lock.
- **Derived CAS files lose their owner:** eviction is reference-aware and
  clears `proxy_hash` before/with deletion; missing references cause
  regeneration, never source deletion.
- **Budgeted QC is mistaken for a full pass:** `policy`, `complete`, `skipped`,
  and timeout details are persisted in `qc_report` and documented for agents.
- **Long detector subprocesses outlive their budget:** every detector receives
  an explicit timeout and catches `TimeoutExpired`; the final job remains
  cancellable through the existing host-worker process lifecycle.
- **Source proxies are expected to fix Remotion cost:** benchmark and document
  that they reduce heavy-source decode/scale cost only; Remotion materialize
  remains M1’s responsibility.

