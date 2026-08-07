# Task 2 Brief

### Task 2: Add the manifest and status model

**Files:**
- Create: `open_edit/render/preview_manifest.py`
- Test: `tests/test_preview_manifest.py`

**Interfaces:**
- Consumes: `RenderProfile` fingerprints and `PreviewRange` values.
- Produces:

```python
PreviewStatus = Literal["red", "yellow", "green"]
PreviewMedia = Literal["video", "audio", "both"]

class PreviewRange(BaseModel):
    start_sec: float = Field(ge=0)
    end_sec: float = Field(gt=0)

class PreviewArtifact(BaseModel):
    artifact_id: str
    relative_path: str
    mime: str
    bytes: int = Field(ge=1)
    sha256: str
    graph_hash: str
    key: str

class PreviewPlaneState(BaseModel):
    status: PreviewStatus
    current: PreviewArtifact | None = None
    fallback: PreviewArtifact | None = None

class PreviewChunk(BaseModel):
    chunk_id: str
    index: int = Field(ge=0)
    start_frame: int = Field(ge=0)
    end_frame: int = Field(gt=0)
    start_sec: float = Field(ge=0)
    end_sec: float = Field(gt=0)
    status: PreviewStatus
    video: PreviewPlaneState
    audio: PreviewPlaneState
    playback: PreviewPlaneState

class PreviewManifest(BaseModel):
    schema_version: Literal[1] = 1
    project_id: str
    graph_revision: int = Field(ge=0)
    edit_graph_hash: str
    duration_frames: int = Field(ge=0)
    duration_sec: float = Field(ge=0)
    fps_num: int = Field(gt=0)
    fps_den: int = Field(gt=0)
    chunk_frames: int = Field(gt=0)
    profile: dict[str, Any]
    job_id: str | None = None
    updated_at: float
    chunks: list[PreviewChunk]
```

- [ ] **Step 1: Write failing tests for schema validation, status derivation, and same-range fallback.**

```python
def test_manifest_rejects_non_frame_aligned_chunk():
    with pytest.raises(ValidationError):
        PreviewChunk(
            chunk_id="bad", index=0, start_frame=30, end_frame=29,
            start_sec=1.0, end_sec=0.966, status="red",
            video=PreviewPlaneState(status="red"),
            audio=PreviewPlaneState(status="red"),
            playback=PreviewPlaneState(status="red"),
        )

def test_dirty_current_with_playable_fallback_is_yellow():
    old = artifact("old-key", "old-graph")
    chunk = PreviewChunk(
        chunk_id="000000-000030", index=0, start_frame=0, end_frame=30,
        start_sec=0.0, end_sec=1.0, status="yellow",
        video=PreviewPlaneState(status="yellow", fallback=old),
        audio=PreviewPlaneState(status="green", current=artifact("a", "new")),
        playback=PreviewPlaneState(status="yellow", fallback=old),
    )
    assert effective_status(chunk) == "yellow"

def test_no_current_or_fallback_is_red():
    assert effective_status(red_chunk()) == "red"
```

- [ ] **Step 2: Run the tests and verify they fail for missing models/functions.**

Run: `pytest tests/test_preview_manifest.py -q`

Expected: FAIL with import or validation errors before implementation.

- [ ] **Step 3: Implement the models and pure functions.** Enforce positive ranges, monotonic frame bounds, relative artifact paths, and `effective_status(chunk)` with the rules in this plan. Serialize with `model_dump(mode="json")`; never serialize absolute paths.

- [ ] **Step 4: Run focused and existing model tests.**

Run: `pytest tests/test_preview_manifest.py tests/test_render/test_profiles.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the manifest contract.**

```bash
git add open_edit/render/preview_manifest.py tests/test_preview_manifest.py
git commit -m "feat: define preview chunk manifest contract"
```
