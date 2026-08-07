# Task 8 Brief

### Task 8: Add the internal CLI and durable render-job kind

**Files:**
- Modify: `open_edit/kernel/render_jobs.py`
- Modify: `open_edit/cli.py`
- Modify: `open_edit/serve/projects.py`
- Test: `tests/test_render_jobs.py`
- Test: `tests/test_serve_render_jobs.py`
- Test: `tests/test_preview_chunks.py`

**Interfaces:**
- Consumes: stored `RenderJob.params`, `render_preview_chunks()`, and the existing subprocess/cancellation lifecycle.
- Produces: durable `mode="preview-chunks"` jobs with `output_path=manifest.json` and `result` progress fields.

- [ ] **Step 1: Write failing lifecycle tests.**

```python
def test_render_job_schema_accepts_preview_chunks(tmp_path):
    job = DEFAULT_RENDER_JOB_SERVICE.enqueue(
        "proj", tmp_path, "preview-chunks",
        params={"ranges": [{"start_sec": 0, "end_sec": 1}], "media": "both"},
    )
    assert job.mode == "preview-chunks"
    assert job.params["media"] == "both"

def test_preview_job_does_not_run_whole_file_qc(tmp_path, monkeypatch):
    monkeypatch.setattr(DEFAULT_RENDER_JOB_SERVICE, "_launch", fake_preview_launch)
    monkeypatch.setattr("open_edit.qc.gate.run_qc_gate", fail_if_called)
    job = DEFAULT_RENDER_JOB_SERVICE.enqueue("proj", tmp_path, "preview-chunks")
    completed = asyncio.run(DEFAULT_RENDER_JOB_SERVICE.wait(tmp_path, job.job_id))
    assert completed.status == "succeeded"
    assert completed.result["mode"] == "preview-chunks"
```

- [ ] **Step 2: Run the new lifecycle tests and confirm the SQLite mode constraint rejects the new kind.**

Run: `pytest tests/test_render_jobs.py tests/test_serve_render_jobs.py -k "preview_chunks or preview" -q`

Expected: FAIL before schema and mode support.

- [ ] **Step 3: Migrate the render-job schema.** Add `preview-chunks` to the SQLite `CHECK`, update the legacy table rebuild condition to rebuild when either `overlay` or `preview-chunks` is absent, and preserve every existing row/column during migration. Extend enqueue validation and keep exact-parameter coalescing for preview jobs; do not coalesce different ranges/media requests.

- [ ] **Step 4: Add the CLI command.** Keep `render --mode` choices as `proxy|final`; add an internal `preview-chunks` subparser with `--job-id` and `--json`. It loads the job from the project DB, invokes `render_preview_chunks`, prints exactly one JSON result when requested, and returns nonzero only for a worker-level failure. Do not run `run_qc_gate` for this mode.

- [ ] **Step 5: Route `_launch()` through the existing process-group path.** Use:

```text
python -m open_edit.cli preview-chunks --job-id <job_id> --json
```

Read params from the durable row rather than interpolating JSON/ranges into shell arguments. Skip `_attach_qc()` for `preview-chunks`; keep it unchanged for proxy/final. A cancelled process must terminate its melt/FFmpeg children through the existing process-group policy.

- [ ] **Step 6: Filter preview jobs from `list_renders()`.** The existing renders list remains the whole-file artifact history. Preview status comes from the dedicated manifest endpoint; a `manifest.json` must never be offered to `get_render_file()` as an MP4.

- [ ] **Step 7: Run lifecycle, migration, and proxy/final regression tests.**

Run: `pytest tests/test_render_jobs.py tests/test_serve_render_jobs.py tests/test_render/test_orchestrator.py -q`

Expected: PASS.

- [ ] **Step 8: Commit the durable job/CLI integration.**

```bash
git add open_edit/kernel/render_jobs.py open_edit/cli.py open_edit/serve/projects.py tests/test_render_jobs.py tests/test_serve_render_jobs.py tests/test_render/test_orchestrator.py
git commit -m "feat: schedule durable preview-chunks jobs"
```
