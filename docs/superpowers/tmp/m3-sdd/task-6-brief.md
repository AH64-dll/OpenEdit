# Task 6 Brief

### Task 6: Implement bounded atomic preview cache storage

**Files:**
- Create: `open_edit/render/preview_cache.py`
- Test: `tests/test_preview_cache.py`

**Interfaces:**
- Consumes: preview artifact keys, job-scoped temp paths, `PreviewManifest`, and environment cache policy.
- Produces:

```python
class PreviewChunkCache:
    def __init__(self, root: Path, *, max_bytes: int, max_age_sec: int | None): ...
    def read_manifest(self) -> PreviewManifest | None: ...
    def write_manifest(self, manifest: PreviewManifest) -> None: ...
    def commit_artifact(
        self, *, plane: Literal["video", "audio", "playback"],
        key: str, source: Path, suffix: str, graph_hash: str,
    ) -> PreviewArtifact: ...
    def resolve_artifact(self, artifact_id: str) -> Path | None: ...
    def prune(self, manifest: PreviewManifest | None) -> dict[str, int]: ...
    def wipe(self) -> dict[str, int]: ...
```

- [ ] **Step 1: Write failing tests for atomic publication, path traversal, cap eviction, and wipe.**

```python
def test_manifest_replace_never_exposes_partial_json(tmp_path):
    cache = PreviewChunkCache(tmp_path, max_bytes=1_000_000, max_age_sec=None)
    manifest = valid_manifest()
    cache.write_manifest(manifest)
    assert PreviewManifest.model_validate_json(
        (tmp_path / "manifest.json").read_text()
    ).schema_version == 1
    assert not list(tmp_path.glob("manifest.json.tmp*"))

def test_resolve_artifact_rejects_unknown_or_escaping_id(tmp_path):
    cache = PreviewChunkCache(tmp_path, max_bytes=1_000_000, max_age_sec=None)
    assert cache.resolve_artifact("../secret") is None
    assert cache.resolve_artifact("not-in-index") is None

def test_prune_removes_unreferenced_old_files_before_fallbacks(tmp_path):
    cache = PreviewChunkCache(tmp_path, max_bytes=10, max_age_sec=None)
    old = write_unreferenced(cache, b"1234567890")
    keep = write_referenced_fallback(cache, b"1234567890")
    result = cache.prune(manifest_referencing(keep))
    assert result["removed_files"] >= 1
    assert not old.exists()
    assert keep.exists()

def test_wipe_removes_all_preview_artifacts_but_not_edit_graph(tmp_path):
    cache = PreviewChunkCache(tmp_path / ".open_edit" / "preview_chunks", max_bytes=1_000_000, max_age_sec=None)
    cache.write_manifest(valid_manifest())
    cache.wipe()
    assert not (cache.root / "manifest.json").exists()
    assert (tmp_path / ".open_edit").exists()
```

- [ ] **Step 2: Run the focused tests to verify missing storage behavior.**

Run: `pytest tests/test_preview_cache.py -q`

Expected: FAIL.

- [ ] **Step 3: Implement the layout and safe writes.** Use `manifest.json`, `video/`, `audio/`, `playback/`, and `tmp/<job_id>/`. Hash and validate the committed file, reject zero-byte outputs, use `os.replace()` for artifacts and manifest, and maintain an artifact-id index so route resolution never accepts a path supplied by the client.

- [ ] **Step 4: Implement eviction and environment policy.** Read `OPEN_EDIT_PREVIEW_CACHE_MAX_BYTES` with a 512 MiB default and `OPEN_EDIT_PREVIEW_CACHE_MAX_AGE_SEC` with a seven-day default. Remove red/unreferenced/expired files first; never remove current green or fallback artifacts referenced by the live manifest until the manifest is updated to clear them. If cap pressure requires clearing fallbacks, rewrite those chunks red atomically. Treat a disk-full or below-minimum-free-space condition as a rejected preview job, not as a successful partial cache.

- [ ] **Step 5: Run the focused tests and commit.**

Run: `pytest tests/test_preview_cache.py -q`

Expected: PASS.

```bash
git add open_edit/render/preview_cache.py tests/test_preview_cache.py
git commit -m "feat: add bounded atomic preview cache"
```
