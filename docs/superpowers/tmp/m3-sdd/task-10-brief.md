# Task 10 Brief

### Task 10: Add manifest/file/wipe routes with project-scoped security

**Files:**
- Create: `open_edit/serve/routers/preview_chunks.py`
- Modify: `open_edit/serve/app.py`
- Modify: `open_edit/serve/review_mode.py`
- Modify: `open_edit/serve/routers/config.py`
- Test: `tests/test_serve_preview_chunks.py`
- Test: `tests/test_serve_env.py`

**Interfaces:**
- Consumes: `PreviewChunkCache`, `RenderJobService`, project resolution, and existing auth/rate-limit helpers.
- Produces:

```text
GET    /api/projects/{project_id}/preview-chunks
GET    /api/projects/{project_id}/preview-chunks/files/{artifact_id}
DELETE /api/projects/{project_id}/preview-chunks
```

The manifest route returns `{manifest, active_job, proxy_fallback}`. The file route accepts only an indexed artifact ID, verifies the path is under the project’s preview cache, and returns `FileResponse` with the artifact MIME type and `Accept-Ranges: bytes`. The wipe route cancels no final/proxy job, removes preview artifacts only, and returns removed byte/file counts.

- [ ] **Step 1: Write failing route tests.**

```python
def test_get_preview_manifest_returns_empty_contract(seeded_project):
    client, project_id = seeded_project.client()
    response = client.get(f"/api/projects/{project_id}/preview-chunks")
    assert response.status_code == 200
    body = response.json()
    assert body["manifest"] is None
    assert body["active_job"] is None

def test_preview_file_route_rejects_path_escape(seeded_project):
    client, project_id = seeded_project.client()
    response = client.get(
        f"/api/projects/{project_id}/preview-chunks/files/..%2Fedit_graph.db"
    )
    assert response.status_code == 404

def test_wipe_preview_cache_does_not_delete_edit_graph(seeded_project):
    client, project_id = seeded_project.client()
    seed_preview_cache(seeded_project.path)
    response = client.delete(f"/api/projects/{project_id}/preview-chunks")
    assert response.status_code == 200
    assert (seeded_project.path / ".open_edit" / "edit_graph.db").exists()
```

- [ ] **Step 2: Run the route tests and confirm the router is not registered.**

Run: `pytest tests/test_serve_preview_chunks.py -q`

Expected: FAIL with 404/import errors.

- [ ] **Step 3: Implement the router and register it.** Resolve the project once per request, apply the same rate-limit/auth policy as render routes, load the manifest atomically, find the active preview job by mode/project, and construct browser URLs from artifact IDs. Use `PreviewChunkCache.resolve_artifact()` for all file requests; never accept a relative path from the URL.

- [ ] **Step 4: Add `OPEN_EDIT_AUTO_PREVIEW` and expose the rollout gate.** Keep `OPEN_EDIT_AUTO_PROXY` unchanged. `auto_preview_enabled()` reads the new boolean env var and `preview_chunks_enabled()` reads `OPEN_EDIT_PREVIEW_CHUNKS`; `GET /api/ui-config` returns both `auto_preview` and `preview_chunks`. Default both new flags to false so existing Review Studio sessions do not unexpectedly fill disk. Task 9 enforces the flag for MCP/REST enqueue requests; this task verifies the config response and UI behavior.

- [ ] **Step 5: Run focused route/env/security tests.**

Run: `pytest tests/test_serve_preview_chunks.py tests/test_serve_env.py tests/test_serve_render_jobs.py -q`

Expected: PASS.

- [ ] **Step 6: Commit the preview HTTP surface.**

```bash
git add open_edit/serve/routers/preview_chunks.py open_edit/serve/app.py open_edit/serve/review_mode.py open_edit/serve/routers/config.py tests/test_serve_preview_chunks.py tests/test_serve_env.py
git commit -m "feat: serve preview manifests and chunk files"
```
