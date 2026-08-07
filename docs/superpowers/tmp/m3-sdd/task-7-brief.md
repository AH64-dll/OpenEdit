# Task 7 Brief

### Task 7: Build the chunk worker around the manifest/cache contracts

**Files:**
- Create: `open_edit/render/preview_chunks.py`
- Modify: `open_edit/render/materialize.py` only to call the M1 renderer seam.
- Test: `tests/test_preview_chunks.py`

**Interfaces:**
- Consumes: current project graph, `PreviewChunkCache`, `compute_chunk_fingerprints()`, `slice_timeline()`, `build_render_plan()`, `emit_timeline()`, `build_preview_pipe_commands()`, and the M1 `PreviewVideoRenderer`.
- Produces:

```python
def render_preview_chunks(
    *,
    project_id: str,
    project_dir: Path,
    job_id: str,
    renderer: PreviewVideoRenderer | None = None,
    run_commands: Callable[[PreviewPipeCommands], None] | None = None,
) -> dict[str, Any]:
    """Bake requested dirty ranges and return manifest-oriented JSON."""
```

When `renderer` or `run_commands` is omitted, production code constructs the
M1-approved host renderer and the existing subprocess runner through explicit
factories (`get_preview_video_renderer(project_dir)` and
`run_preview_pipe(commands)`). Tests always inject both fakes so no external
binary is required.

- [ ] **Step 1: Write a fake-runner test for one green chunk and one skipped green chunk.**

```python
def test_worker_reuses_green_chunk_and_publishes_new_chunk(tmp_path):
    seed_manifest_with_green_chunk(tmp_path, index=0, graph_hash="same")
    renderer = FakePreviewVideoRenderer()
    result = render_with_params(
        tmp_path,
        params={"ranges": [{"start_sec": 1.0, "end_sec": 2.0}], "media": "both"},
        renderer=renderer,
    )
    manifest = read_manifest(tmp_path)
    assert result["ok"] is True
    assert renderer.calls == [1]
    assert manifest.chunks[0].status == "green"
    assert manifest.chunks[1].status == "green"

def test_worker_preserves_old_artifact_as_yellow_fallback_during_bake(tmp_path):
    seed_manifest_with_green_chunk(tmp_path, index=1, graph_hash="old")
    renderer = BlockingFakeRenderer()
    started = start_worker(tmp_path, renderer)
    wait_until(lambda: read_manifest(tmp_path).chunks[1].status == "yellow")
    old_id = read_manifest(tmp_path).chunks[1].playback.fallback.artifact_id
    assert old_id == "old-playback"
    renderer.release()
    wait_for_worker(started)
    assert read_manifest(tmp_path).chunks[1].status == "green"

def test_worker_stops_publishing_when_graph_revision_changes(tmp_path):
    renderer = GraphChangingFakeRenderer(tmp_path)
    result = render_with_params(tmp_path, renderer=renderer)
    assert result["graph_changed"] is True
    assert read_manifest(tmp_path).graph_revision == renderer.original_revision
```

- [ ] **Step 2: Run the worker tests and verify orchestration is absent.**

Run: `pytest tests/test_preview_chunks.py -q`

Expected: FAIL.

- [ ] **Step 3: Implement project snapshot loading and prioritization.** Capture revision/hash before work, load the previous manifest and matching timeline snapshot, make frame-aligned windows, compute fingerprints, and select requested dirty windows. Update only the selected chunks to yellow while preserving same-range fallback references.

- [ ] **Step 4: Implement per-chunk plane work.** For each selected window, slice local timelines, collect overlapping Remotion UIDs, call the M1 renderer for video, run the audio path when requested, mux selected current planes, validate duration/stream presence, commit artifacts, and replace the manifest. If a plane fails, mark that plane red, retain fallback, continue independent chunks, and return `partial=true` with failed chunk IDs. If graph hash/revision changes before publication, stop and return `graph_changed=true` without replacing a newer manifest.

- [ ] **Step 5: Add progress and cleanup.** Set `job_id` in the manifest while active, publish after each completed chunk, remove only the job’s temporary directory in `finally`, run eviction after successful publication, and return:

```python
{
    "ok": True,
    "mode": "preview-chunks",
    "output_path": str(cache.root / "manifest.json"),
    "manifest_path": str(cache.root / "manifest.json"),
    "ready_chunks": 12,
    "green_chunks": 12,
    "yellow_chunks": 2,
    "red_chunks": 0,
    "failed_chunks": [],
    "partial": False,
    "graph_changed": False,
}
```

- [ ] **Step 6: Run focused worker tests and commit.**

Run: `pytest tests/test_preview_chunks.py -q`

Expected: PASS with no real melt/FFmpeg invocation.

```bash
git add open_edit/render/preview_chunks.py open_edit/render/materialize.py tests/test_preview_chunks.py
git commit -m "feat: bake dirty preview chunks with fallbacks"
```
