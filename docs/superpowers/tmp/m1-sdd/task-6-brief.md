# Task 6 Brief

### Task 6: Verify content-aware caching, eviction, and alpha/ProRes policy

**Files:**
- Modify: `open_edit/render/cache.py`, `open_edit/render/remotion/renderer.py`, `open_edit/render/materialize.py`, `open_edit/render/timeline_plan.py`, `open_edit/render/orchestrator.py`
- Test: `tests/test_render/test_cache.py`, `tests/test_remotion_renderer.py`, `tests/test_remotion_ir_materialize.py`, `tests/test_render/test_timeline_plan.py`

**Interfaces:**
- Consumes: existing `render_cache_key()`, `render_reference_fingerprint()`, `composition_cache_key()`, `OverlayClip`, and `RenderProfile`.
- Produces: content-verified cache behavior under a bounded disk policy and correct opaque/alpha overlay metadata.

- [ ] **Step 1: Write failing cache-integrity and eviction tests.**

```python
def test_cache_get_rejects_tampered_content(tmp_path):
    cache = RenderCache(tmp_path / "cache")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"original")
    cached = cache.put("key", source)
    cached.write_bytes(b"tampered")
    assert cache.get("key") is None


def test_cache_hit_refreshes_lru_access_time(tmp_path):
    cache = RenderCache(tmp_path / "cache", max_bytes=8)
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    first.write_bytes(b"1234")
    second.write_bytes(b"5678")
    first_cached = cache.put("first", first)
    time.sleep(0.01)
    second_cached = cache.put("second", second)
    assert cache.get("first") == first_cached
    cache.evict()
    assert first_cached.exists()
    assert second_cached.exists() or not second_cached.exists()


def test_external_remotion_asset_change_misses_deliverable_cache(
    project_with_remotion, monkeypatch
):
    first = render_with_fake_pipe(project_with_remotion)
    change_referenced_file(project_with_remotion, b"new-bytes")
    second = render_with_fake_pipe(project_with_remotion)
    assert first.edit_graph_hash == second.edit_graph_hash
    assert second.cache_hit is False


def test_opaque_remotion_composition_does_not_request_rgba():
    plan = build_plan_with_remotion(alpha=False)
    assert plan.overlay_clips[0].alpha is False
    assert "format=rgba" not in "".join(
        overlay_filter_chain(plan.overlay_clips, 640, 360)
    )
```

- [ ] **Step 2: Run the focused tests to verify missing behavior.**

Run:

```bash
pytest -q tests/test_render/test_cache.py tests/test_remotion_renderer.py \
  tests/test_remotion_ir_materialize.py tests/test_render/test_timeline_plan.py
```

Expected: the new cache cap/LRU and opaque-alpha assertions fail; existing content-key tests document the portions already implemented.

- [ ] **Step 3: Extend `RenderCache` with a bounded policy.**

Add `max_bytes: int | None = None` to the constructor and parse:

```text
OPEN_EDIT_RENDER_CACHE_MAX_BYTES
OPEN_EDIT_REMOTION_CACHE_MAX_BYTES
```

The parser accepts an integer byte count and case-insensitive `KiB`, `MiB`, or `GiB` suffixes; invalid values use the configured default. `get()` must validate the metadata hash as it does today and touch the artifact mtime/`last_accessed_at` after a valid hit. `put()` writes metadata atomically with `schema=2`, `source_hash`, `size_bytes`, `updated_at`, and `last_accessed_at`, then calls `evict()`.

`evict()` counts only artifact files, not `.meta` JSON. It removes the oldest last-accessed entries and their metadata until the byte budget is met. If a single new entry exceeds the cap, it is removed after the put and the caller continues using its source output for the current render; this avoids silently allowing an unbounded cache. Retain legacy metadata-less entries as readable but do not count them as content-verified hits for new writes.

- [ ] **Step 4: Verify and extend content-aware keys.**

Keep `render_reference_fingerprint()` as the whole-file content authority and ensure the payload includes:

```text
composition UID/ID, source bundle, props,
referenced-file resolved path and SHA-256 bytes,
duration, alpha flag, resolved alpha mode,
profile fingerprint, REMOTION_VERSION,
ALPHA_POLICY_VERSION, SOURCE_REPAIR_POLICY_VERSION
```

Do not use mtime-only identity. Add tests for a changed `file://` prop asset, a changed `public/staticFile()` asset, a changed composition duration, a changed alpha mode, and a changed repair-policy version. Existing `test_materialize_invalidates_when_prop_file_changes()` must remain green.

- [ ] **Step 5: Apply proxy-aware alpha policy and propagate the IR flag.**

Extend `resolve_alpha_mode()` with `mode: Literal["proxy", "final"] | None = None` while retaining `OPEN_EDIT_ALPHA_MODE` compatibility. Use `OPEN_EDIT_PROXY_ALPHA_MODE` for proxy when present and `OPEN_EDIT_FINAL_ALPHA_MODE` for final when present; otherwise fall back to `OPEN_EDIT_ALPHA_MODE` and then `auto`. `auto` selects VP8/WebM only when `probe_alpha_capability()` proves transparent pixels survive; otherwise it selects ProRes 4444. Explicit VP8/VP9 requests on an unproven host fail with a clear configuration error rather than silently producing opaque frames.

Pass `composition.alpha` into `_remotion_overlay_clips()` so `OverlayClip.alpha=False` omits `format=rgba` for opaque compositions. Keep `.webm` for VP8/VP9 alpha and `.mov` for ProRes 4444. Record the selected alpha mode and extension in materialization diagnostics and cache keys.

- [ ] **Step 6: Run cache, alpha, and pipe regressions.**

Run:

```bash
pytest -q tests/test_render/test_cache.py tests/test_remotion_renderer.py \
  tests/test_remotion_ir_materialize.py tests/test_render/test_timeline_plan.py \
  tests/test_render/test_pipe_builder.py
```

Expected: PASS, including all existing ProRes alpha and transparent composite tests. On this host, the capability-false path must remain ProRes rather than being forced to WebM.

- [ ] **Step 7: Commit content-aware cache and alpha policy.**

```bash
git add open_edit/render/cache.py open_edit/render/remotion/renderer.py \
  open_edit/render/materialize.py open_edit/render/timeline_plan.py \
  open_edit/render/orchestrator.py tests/test_render/test_cache.py \
  tests/test_remotion_renderer.py tests/test_remotion_ir_materialize.py \
  tests/test_render/test_timeline_plan.py
git commit -m "perf: bound render caches and preserve remotion alpha"
```

---
