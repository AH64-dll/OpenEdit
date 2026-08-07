# Task 5 Brief

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
