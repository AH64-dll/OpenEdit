# Task 15 Brief

### Task 15: Add end-to-end acceptance coverage and diagnostics

**Files:**
- Modify: `tests/test_preview_chunks.py`
- Modify: `tests/test_serve_preview_chunks.py`
- Modify: `tests/test_e2e_render.py` only for a skip-safe preview fixture
- Modify: `open_edit/render/preview_chunks.py`
- Modify: `open_edit/serve/static/app.js` to expose the structured preview diagnostics labels

**Interfaces:**
- Consumes: the complete worker, API, cache, and consumer contracts.
- Produces: deterministic acceptance evidence for M3 without requiring the long production timeline or a GPU.

- [ ] **Step 1: Write failing acceptance tests against a short fixture.**

```python
def test_one_remotion_edit_updates_only_its_preview_zone(short_preview_project):
    first = bake_preview(short_preview_project, ranges=[{"start_sec": 0, "end_sec": 4}])
    assert green_indices(first) == {0, 1, 2, 3}
    append_one_remotion_edit(short_preview_project, position_sec=2.2, duration_sec=0.4)
    second = read_preview_manifest(short_preview_project)
    assert second.chunks[0].status == "green"
    assert second.chunks[2].status in {"yellow", "red"}
    assert second.chunks[3].status == "green"

def test_audio_gain_does_not_flush_video(short_preview_project):
    before = bake_preview(short_preview_project, ranges=[{"start_sec": 0, "end_sec": 4}])
    old_video_ids = video_ids(before)
    append_audio_gain(short_preview_project, clip_id="a1", gain_db=-6)
    after = bake_preview(short_preview_project, ranges=[{"start_sec": 0, "end_sec": 4}], media="audio")
    assert video_ids(after) == old_video_ids
    assert audio_ids(after) != audio_ids(before)

def test_review_route_streams_chunk_and_keeps_proxy_fallback(short_preview_project):
    seed_stale_proxy(short_preview_project)
    response = get_preview_file(short_preview_project, green_chunk_artifact_id())
    assert response.status_code == 200
    assert response.headers["accept-ranges"] == "bytes"
    assert stale_proxy_is_labeled_in_manifest_response(short_preview_project)
```

- [ ] **Step 2: Run the acceptance tests before final integration and record the missing behavior.**

Run: `pytest tests/test_preview_chunks.py tests/test_serve_preview_chunks.py -k "acceptance or remotion or audio or fallback" -q`

Expected: FAIL until all preceding tasks are integrated.

- [ ] **Step 3: Add structured diagnostics.** Include per-job counts, selected ranges, skipped-green count, video/audio/mux elapsed times, bytes written, cache hits/misses, eviction counts, and `graph_changed`/`partial` flags in the job result and worker logs. Do not include absolute source paths in browser-visible diagnostics.

- [ ] **Step 4: Run acceptance tests with the fake runner and, when melt/FFmpeg are installed, the short real host fixture.**

Run: `pytest tests/test_preview_chunks.py tests/test_serve_preview_chunks.py tests/test_e2e_render.py -q`

Expected: PASS; the real-media test may be marked with the repository’s existing external-binary marker and must not mask unit failures.

- [ ] **Step 5: Commit acceptance and diagnostics.**

```bash
git add tests/test_preview_chunks.py tests/test_serve_preview_chunks.py tests/test_e2e_render.py open_edit/render/preview_chunks.py open_edit/serve/static/app.js
git commit -m "test: verify preview chunk invalidation and fallback"
```
