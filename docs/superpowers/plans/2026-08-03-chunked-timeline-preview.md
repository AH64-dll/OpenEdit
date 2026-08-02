# Chunked Timeline Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a host-worker `preview-chunks` render path and a Review Studio HTML5 consumer so edited timeline ranges become independently cached, status-visible, and seekable without replacing the existing whole-file `mode=proxy` artifact.

**Architecture:** Extend the existing `trigger_render`/`RenderJobService` surface with a `preview-chunks` job kind whose output is an atomic manifest plus independently cached video, audio, and muxed playback artifacts. Use one-second, project-frame-aligned core chunks, compare per-chunk video/audio fingerprints against the previous manifest, preserve same-range artifacts as fallbacks while new chunks bake, and render through an M1-provided in-pipeline Remotion frame-engine seam. Review Studio consumes a manifest-backed sequential HTML5 playlist in M3; the consumer interface leaves room for an MSE/fMP4 strategy, but MSE is not a correctness prerequisite for this phase. Whole-file `mode=proxy` remains the shareable/review fallback and is never silently redefined as the chunk cache.

**Tech Stack:** Python 3.11 floor, Pydantic, FastAPI, SQLite-backed `RenderJobService`, MLT, FFmpeg, host-side Remotion frame engine, filesystem CAS-style preview cache, browser ES modules, native HTML5 `<video>`, and the existing Node-sandbox frontend tests.

## Global Constraints

- Do not modify `open_edit/` product code until AH64 confirms execution of this plan; this document is the only deliverable of the planning phase.
- All melt, FFmpeg, Remotion Chromium, and optional GPU work runs in the host render worker; free-form IR remains bwrap/seccomp/IR-only and never receives `/dev/dri`, CUDA, melt, or FFmpeg access.
- Keep the existing melt → rawvideo pipe → FFmpeg contract, including `f=rawvideo`; chunk rendering is a range-limited consumer of that spine, not a replacement compositor.
- Keep `mode=proxy` as a full-timeline low-resolution MP4 review artifact, keep `mode=final` as delivery output, and distinguish both from per-asset source proxies and timeline preview chunks in API, UI, and docs.
- Use project-frame boundaries for all chunk core ranges; never derive chunk boundaries from unrounded floating-point seconds.
- Default chunk geometry is one second at the project frame rate (`chunk_frames = round(fps_num / fps_den)`); expose a validated configuration override rather than allowing arbitrary client geometry.
- Every new preview cache has a byte cap, age/LRU eviction, atomic writes, and an operator wipe path before the feature is enabled.
- A chunk job must not publish a partial file as green; write to a job-scoped temporary path, validate it, atomically rename it, then atomically replace the manifest.
- The M3 consumer is sequential HTML5 playlist playback by default. MSE/fMP4 is an optional strategy behind the same consumer interface and must not be required for the M3 acceptance gate.
- No live MLT SDL/OpenGL preview daemon, shared-memory frame protocol, or GPU consumer is in scope; those are M4 decisions only if M3 scrub UX is insufficient.
- Preserve Python 3.11 compatibility and existing proxy/final/render-job tests.
- Do not use the free-form sandbox to generate or mutate preview files; preview files are host-worker outputs derived from the validated Edit Graph.

---

## Current Architecture and Integration Decisions

### Existing path to preserve

The current render path is:

```text
trigger_render / POST /render
  -> RenderJobService.enqueue()
  -> python -m open_edit.cli render --mode proxy|final --json
  -> render_project()
  -> derive_or_load_timeline()
  -> materialize_remotion_compositions()
  -> build_render_plan()
  -> emit_timeline()
  -> build_pipe_commands()
  -> melt rawvideo + melt audio + FFmpeg
  -> RenderCache / snapshots / QC
  -> Review Studio loads one MP4 in <video>
```

M3 adds a sibling path after the durable job boundary:

```text
trigger_render(mode="preview-chunks", ranges=[...])
  -> RenderJobService.enqueue()
  -> python -m open_edit.cli preview-chunks --job-id ... --json
  -> render_preview_chunks()
  -> derive current timeline + previous manifest
  -> compute frame-aligned dirty video/audio chunks
  -> M1 Remotion frame-engine / range renderer
  -> range emit + host melt/FFmpeg for video plane
  -> host melt/FFmpeg for audio plane
  -> cheap mux of current video/audio planes
  -> atomic artifact commits + atomic manifest updates
  -> GET preview manifest/file
  -> Review Studio sequential playlist, with same-range fallback and proxy fallback
```

### API decision

Use the existing `trigger_render` tool and `POST /api/projects/{project_id}/render` with a new `mode="preview-chunks"`. Do not add a second MCP render tool: two enqueue surfaces would otherwise diverge in graph capture, job polling, cancellation, encoder selection, and audit history.

The new mode accepts:

```json
{
  "mode": "preview-chunks",
  "ranges": [
    {"start_sec": 12.0, "end_sec": 20.0}
  ],
  "media": "both",
  "priority": "interactive",
  "wait": false
}
```

`ranges` is optional. When omitted, the worker computes all dirty chunks but processes them in manifest order. Review Studio always sends a small requested window around the playhead so opening a long project does not enqueue thousands of seconds before the user asks to view them. `media` is `both`, `video`, or `audio`; `priority` is `interactive` or `background`. Chunk size, codec, cache cap, and context policy remain server/profile policy, not arbitrary client input.

For REST only, retain `expected_revision` alongside the existing render request fields. The job captures the current graph hash and revision at enqueue time. The worker checks the graph before each chunk and stops publishing if the graph changed, leaving the old manifest/artifacts available as fallbacks.

### Manifest contract

`open_edit/render/preview_manifest.py` owns the Pydantic contract. The API representation must be JSON-compatible with this shape:

```json
{
  "schema_version": 1,
  "project_id": "project-id",
  "graph_revision": 42,
  "edit_graph_hash": "sha256",
  "timeline": {
    "duration_frames": 900,
    "duration_sec": 30.0,
    "fps_num": 30,
    "fps_den": 1,
    "chunk_frames": 30
  },
  "profile": {
    "name": "preview_chunk",
    "fingerprint": "sha256",
    "width": 640,
    "height": 360,
    "video_codec": "h264",
    "audio_codec": "aac"
  },
  "job_id": "active-job-or-null",
  "updated_at": 1785700000.0,
  "chunks": [
    {
      "chunk_id": "000000-000030",
      "index": 0,
      "start_frame": 0,
      "end_frame": 30,
      "start_sec": 0.0,
      "end_sec": 1.0,
      "status": "green",
      "video": {
        "status": "green",
        "current": {
          "artifact_id": "sha256",
          "relative_path": "video/sha256.mp4",
          "mime": "video/mp4",
          "bytes": 1234,
          "sha256": "sha256",
          "graph_hash": "sha256",
          "key": "sha256"
        },
        "fallback": null
      },
      "audio": {
        "status": "green",
        "current": {
          "artifact_id": "sha256",
          "relative_path": "audio/sha256.m4a",
          "mime": "audio/mp4",
          "bytes": 456,
          "sha256": "sha256",
          "graph_hash": "sha256",
          "key": "sha256"
        },
        "fallback": null
      },
      "playback": {
        "status": "green",
        "current": {
          "artifact_id": "sha256",
          "relative_path": "playback/sha256.mp4",
          "mime": "video/mp4",
          "bytes": 1678,
          "sha256": "sha256",
          "graph_hash": "sha256",
          "key": "sha256"
        },
        "fallback": null
      }
    }
  ]
}
```

The on-disk manifest stores only relative paths. The API adds project-scoped file URLs; the browser never receives an arbitrary filesystem path.

### Status and fallback semantics

- `green`: the current graph/profile/media key is present, validated, and atomically committed for the exact core range.
- `yellow`: the current key is being baked or is dirty, but an exact-range prior artifact or whole-file proxy can play. A plane may be red internally while the effective chunk remains yellow because a fallback is usable.
- `red`: no current or prior artifact is usable for that exact range. The consumer must use the whole-file proxy if one exists, otherwise show an unavailable gap.
- `video.status` and `audio.status` are independent. `playback.status` becomes green only after the current requested planes are muxed successfully.
- A graph change moves a current artifact to `fallback` without deleting its file. Fallbacks are same-range, same-profile artifacts only; never substitute a neighboring time range.
- A video-only edit leaves an unchanged audio plane green. An audio-only gain/silence/normalization edit leaves the video plane green, bakes audio, and remuxes the playback artifact.
- If the current chunk has no playable artifact, Review Studio loads the newest successful whole-file proxy and labels it stale when its graph hash differs. This behavior is deliberately visible; it never pretends that proxy playback is an up-to-date chunk.

### Chunk and dirty-range policy

- Build core windows `[start_frame, end_frame)` from `chunk_frames`, with the final window ending at `duration_frames`.
- Derive fingerprints from frame-sliced timeline content, resolved source content fingerprints, active effects/transitions, overlay/Remotion inputs, profile fingerprint, and the plane (`video` or `audio`).
- Compare old and new per-chunk plane fingerprints. This is the correctness backstop for operations such as remove, ripple, revert, and source replacement whose new range is not directly present in the operation payload.
- Use operation classification to limit work before comparison: video/composite/Remotion operations affect video; `set_audio_gain` and `normalize_audio` affect audio; unknown/raw-MLT/free-form operations invalidate the full timeline.
- Expand a dirty request to adjacent chunks when a transition/effect/Remotion composition crosses a core boundary. Render a context window, then trim the encoded output back to the core frames so every published artifact remains exactly one core duration.
- If the prior timeline snapshot for the manifest graph hash is unavailable, mark all chunks dirty rather than guessing. If a source content fingerprint cannot be resolved, mark the affected plane dirty.
- Requested ranges are intersected with dirty chunks. Already-green chunks are returned without re-rendering. A background request can cover all dirty chunks; an interactive request prioritizes the requested window and its nearest dirty neighbors.

### Audio/video storage and playback policy

Store three related artifacts per chunk:

1. `video/<key>.mp4`: video-only encoded core output.
2. `audio/<key>.m4a`: audio-only encoded core output.
3. `playback/<key>.mp4`: cheap mux of the selected video and audio plane artifacts.

The browser uses the muxed playback file for synchronization and does not need a second `<audio>` element in M3. The independent plane artifacts are still first-class cache entries, so an audio-only edit does not re-render video. The `playback` field can later carry `streaming="mse"` plus init/media URLs for an MSE adapter; M3 publishes self-contained MP4 chunks and uses sequential source switching because that is testable in the existing Review Studio without making fMP4 timestamp stitching a phase gate.

### M1 readiness gate

M3 worker integration is blocked until M1 supplies all of these landmarks:

1. A stable render-profile/content-fingerprint contract that can be included in per-plane chunk keys.
2. A host-only `PreviewVideoRenderer`/Remotion frame-engine seam that accepts a range and the overlapping `composition_uid` set. The seam must support the approved in-pipeline/on-demand direction; M3 must not introduce a separate external Remotion bake-and-stitch program.
3. Dirty composition reuse or a bounded range materialization adapter, plus Remotion output eviction.
4. Tests proving a render can request only overlapping Remotion compositions and can reuse an unchanged composition without re-rendering it.

M3 API, manifest, cache, invalidation, and frontend work may be developed against a fake renderer before those landmarks land. The chunk worker must remain feature-gated until the real M1 renderer satisfies the contract. M2 source proxies are a soft dependency: if present, preview asset resolution uses them; if absent, preview chunks use canonical assets and the M3 acceptance tests still pass.

## File Map

### New files

- `open_edit/render/preview_manifest.py` — Pydantic manifest, range, artifact, plane-state, and status models; JSON serialization; status derivation.
- `open_edit/render/preview_invalidation.py` — frame-aligned chunk windows, timeline slicing, per-plane fingerprints, operation classification, dirty-range expansion, and Remotion UID collection.
- `open_edit/render/preview_cache.py` — `.open_edit/preview_chunks/` layout, atomic artifact/manifest commits, safe path resolution, cap/TTL/LRU eviction, and wipe.
- `open_edit/render/preview_pipe.py` — range-specific video/audio/mux command specifications; preserves existing `pipe_builder.build_pipe_commands()` for proxy/final.
- `open_edit/render/preview_chunks.py` — worker orchestration, graph-staleness checks, renderer seam invocation, per-chunk progress, partial-result reporting, and manifest publication.
- `open_edit/serve/routers/preview_chunks.py` — manifest, artifact-file, and wipe routes.
- `open_edit/serve/static/js/preview.js` — pure manifest selection/status helpers and sequential playlist consumer with a strategy interface for future MSE.
- `tests/test_preview_manifest.py` — schema/status/fallback contracts.
- `tests/test_preview_invalidation.py` — frame geometry, slicing, fingerprints, dirty classification, and boundary context.
- `tests/test_preview_cache.py` — atomic writes, path safety, eviction, and wipe.
- `tests/test_preview_pipe.py` — command and trim/mux contracts.
- `tests/test_preview_chunks.py` — worker orchestration with fake video renderer and fake melt/FFmpeg runner.
- `tests/test_serve_preview_chunks.py` — REST routes and job/manifest/file behavior.
- `tests/test_preview_frontend.py` — Node-sandbox tests for `preview.js` and Review Studio hooks.

### Modified files

- `open_edit/kernel/render_jobs.py` — allow and persist `preview-chunks`, pass normalized params to the internal CLI, skip whole-file QC for manifests, preserve progress/result metadata, and migrate the SQLite mode constraint.
- `open_edit/kernel/tool_registry.py` — add `preview-chunks` to `TriggerRenderArgs` and document ranges/media/priority.
- `open_edit/kernel/tool_executor.py` — validate the new mode, normalize preview params, and return the manifest-oriented result contract.
- `open_edit/cli.py` — add the internal `preview-chunks --job-id --json` command without changing `render --mode proxy|final`.
- `open_edit/render/profiles.py` — add the bounded `preview_chunk` video/audio profile and stable profile fingerprint fields.
- `open_edit/render/timeline_plan.py` — accept a range-sliced timeline/plane while leaving full proxy/final behavior unchanged.
- `open_edit/render/emitter.py` — emit local-coordinate range timelines and preserve audio-only tracks/effects for preview rendering.
- `open_edit/render/materialize.py` — consume the M1 renderer seam or provide the M1-approved range adapter; do not add an external Remotion relay.
- `open_edit/render/pipe_builder.py` — share pure overlay/filter helpers with `preview_pipe.py` only if the implementation requires it; existing command output remains regression-tested.
- `open_edit/serve/routers/renders.py` — accept the new mode/params, expose result metadata, and keep proxy/final render listing separate.
- `open_edit/serve/routers/config.py` and `open_edit/serve/review_mode.py` — expose `auto_preview` without changing the existing `auto_proxy` default.
- `open_edit/serve/app.py` — import and register the preview router alongside the existing `projects`, `renders`, `ops`, `config`, `assets`, and chat routers.
- `open_edit/serve/projects.py` — omit `preview-chunks` jobs from the whole-file renders list while continuing to list proxy/final artifacts.
- `open_edit/serve/static/js/api.js` — add manifest, preview enqueue, artifact URL, and wipe methods.
- `open_edit/serve/static/js/state.js` — track manifest, preview job, preview polling, auto-preview preference, and consumer instance.
- `open_edit/serve/static/app.js` — request windows on open/scrub, preserve proxy fallback, update the status map, and route global seek/playhead time through the chunk consumer.
- `open_edit/serve/static/index.html` and `open_edit/serve/static/style.css` — add preview-chunk controls/status map and accessible red/yellow/green styling.
- `skills/open-edit-mcp.md`, `skills/open-edit-mcp-reference.md`, `skills/tool_surface.md`, and synchronized `open_edit/harness_skills/` copies — document `preview-chunks` separately from `proxy`.
- `docs/MCP.md` — update the MCP/UI workflow and explain chunk requests, fallback labels, cache wipe, and the unchanged proxy/final workflow.

## Implementation Tasks

### Task 1: Freeze the M1 frame-engine handoff

**Files:**
- Create: `tests/test_preview_frame_engine_contract.py`
- Modify only if the M1 landmark is absent: `open_edit/render/frame_engine.py`
- Read for compatibility: `open_edit/render/materialize.py`, `open_edit/render/remotion/renderer.py`

**Interfaces:**
- Consumes: M1’s host-only Remotion/frame-engine implementation.
- Produces: the exact renderer contract used by `preview_chunks.py`:

```python
class PreviewVideoRequest(TypedDict):
    project_dir: Path
    timeline: Timeline
    render_start_frame: int
    render_end_frame: int
    core_start_frame: int
    core_end_frame: int
    composition_uids: tuple[str, ...]
    profile: RenderProfile
    output_path: Path

class PreviewVideoRenderer(Protocol):
    def render(self, request: PreviewVideoRequest) -> Path:
        """Render one range and return the validated video artifact path."""
```

- [ ] **Step 1: Write the failing contract test.** The test must instantiate a fake renderer, pass a request with two overlapping Remotion UIDs and a context range wider than the core range, and assert that `render()` receives the exact frame values and returns the requested output path.

```python
def test_preview_renderer_receives_core_and_context_frames(tmp_path):
    seen = {}

    class Fake:
        def render(self, request):
            seen.update(request)
            request["output_path"].write_bytes(b"video")
            return request["output_path"]

    output = tmp_path / "video.mp4"
    got = Fake().render({
        "project_dir": tmp_path,
        "timeline": Timeline(),
        "render_start_frame": 28,
        "render_end_frame": 62,
        "core_start_frame": 30,
        "core_end_frame": 60,
        "composition_uids": ("comp-a", "comp-b"),
        "profile": RenderProfile(name="preview_chunk", width=640, height=360),
        "output_path": output,
    })
    assert got == output
    assert seen["composition_uids"] == ("comp-a", "comp-b")
    assert (seen["render_start_frame"], seen["render_end_frame"]) == (28, 62)
    assert (seen["core_start_frame"], seen["core_end_frame"]) == (30, 60)
```

- [ ] **Step 2: Run the focused test to verify the contract is not accidentally satisfied by a different signature.**

Run: `pytest tests/test_preview_frame_engine_contract.py::test_preview_renderer_receives_core_and_context_frames -q`

Expected: FAIL until the M1 renderer seam and request type are present.

- [ ] **Step 3: Confirm the M1 implementation satisfies the contract.** If it does not, stop M3 execution and land the M1 adapter first. The adapter may materialize/reuse files internally or pull frames in the same pass, but `preview_chunks.py` must only call `PreviewVideoRenderer.render(request)` and must not invoke `render_composition()` directly.

- [ ] **Step 4: Run the contract and existing Remotion tests.**

Run: `pytest tests/test_preview_frame_engine_contract.py tests/test_remotion_renderer.py tests/test_render/test_orchestrator.py -q`

Expected: all selected tests pass; no M1 renderer test is skipped.

- [ ] **Step 5: Commit the contract gate.**

```bash
git add tests/test_preview_frame_engine_contract.py open_edit/render/frame_engine.py
git commit -m "test: freeze preview frame-engine handoff"
```

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

### Task 3: Implement frame-aligned chunk geometry and local timeline slicing

**Files:**
- Create: `open_edit/render/preview_invalidation.py`
- Modify: `open_edit/render/timeline_plan.py`
- Modify: `open_edit/render/emitter.py`
- Test: `tests/test_preview_invalidation.py`
- Regression tests: `tests/test_render_emitter.py`, `tests/test_render/test_emitter.py`

**Interfaces:**
- Consumes: `Timeline`, `PreviewManifest`, project FPS, and the M1 renderer request.
- Produces:

```python
@dataclass(frozen=True)
class ChunkWindow:
    index: int
    start_frame: int
    end_frame: int
    render_start_frame: int
    render_end_frame: int
    crop_head_frames: int
    crop_tail_frames: int

def make_chunk_windows(
    duration_frames: int,
    fps_num: int,
    fps_den: int,
    chunk_frames: int | None = None,
) -> list[ChunkWindow]:
    ...

def slice_timeline(
    timeline: Timeline,
    *,
    render_start_frame: int,
    render_end_frame: int,
    fps_num: int,
    fps_den: int,
    plane: Literal["video", "audio", "both"],
) -> Timeline:
    """Return local coordinates with render_start mapped to zero."""
```

- [ ] **Step 1: Write failing tests for one-second defaults, final short chunk, crossing clips, and context trimming.**

```python
def test_chunk_windows_use_project_frames():
    windows = make_chunk_windows(75, 30, 1)
    assert [(w.start_frame, w.end_frame) for w in windows] == [
        (0, 30), (30, 60), (60, 75)
    ]
    assert windows[0].render_start_frame == 0
    assert windows[0].crop_head_frames == 0

def test_slice_crossing_clip_rebases_source_points():
    timeline = timeline_with_clip(position=0.0, in_point=10.0, out_point=14.0)
    sliced = slice_timeline(
        timeline, render_start_frame=30, render_end_frame=60,
        fps_num=30, fps_den=1, plane="video",
    )
    clip = sliced.tracks[0].clips[0]
    assert clip.position_sec == pytest.approx(0.0)
    assert clip.in_point_sec == pytest.approx(11.0)
    assert clip.out_point_sec == pytest.approx(12.0)
    assert sliced.duration_sec == pytest.approx(1.0)

def test_transition_context_is_cropped_back_to_core():
    window = make_chunk_windows(90, 30, 1)[1]
    assert window.start_frame == 30 and window.end_frame == 60
    assert window.render_start_frame <= window.start_frame
    assert window.render_end_frame >= window.end_frame
    assert window.crop_head_frames == window.start_frame - window.render_start_frame
```

- [ ] **Step 2: Run the focused tests to verify missing geometry/slicing behavior.**

Run: `pytest tests/test_preview_invalidation.py -q`

Expected: FAIL before the new functions exist.

- [ ] **Step 3: Implement frame conversion and slicing.** Use integer frame arithmetic; calculate seconds only for Pydantic/API display. Clip overlap must adjust `position_sec`, `in_point_sec`, and `out_point_sec`; preserve clip-local effects; retain audio tracks only for `audio`/`both`; retain Remotion/HTML overlays that overlap the render window; rebase all retained positions. Include neighboring transition/effect context in `render_start_frame`/`render_end_frame`, and carry crop counts to the pipe builder.

- [ ] **Step 4: Add range-aware plan/emitter calls without changing full renders.** `build_render_plan()` should accept an already sliced timeline and continue to call `timeline_for_melt()` exactly as before. `emit_timeline()` should emit the local duration and local clip positions. Existing proxy/final tests must compare the same XML properties as before.

- [ ] **Step 5: Run focused and regression tests.**

Run: `pytest tests/test_preview_invalidation.py tests/test_render_emitter.py tests/test_render/test_emitter.py -q`

Expected: PASS, including existing 30 ms micro-fade assertions.

- [ ] **Step 6: Commit the geometry/slicing work.**

```bash
git add open_edit/render/preview_invalidation.py open_edit/render/timeline_plan.py open_edit/render/emitter.py tests/test_preview_invalidation.py tests/test_render_emitter.py tests/test_render/test_emitter.py
git commit -m "feat: add frame-aligned preview range slicing"
```

### Task 4: Add plane-aware dirty-range invalidation and keys

**Files:**
- Modify: `open_edit/render/preview_invalidation.py`
- Read/modify only for shared helpers: `open_edit/render/cache.py`, `open_edit/render/profiles.py`, `open_edit/ir/hash.py`, `open_edit/storage/timeline_cache.py`
- Test: `tests/test_preview_invalidation.py`

**Interfaces:**
- Consumes: old/new graph hashes, old/new `Timeline` snapshots, applied operations, `ChunkWindow` values, profile/content fingerprints, and requested ranges.
- Produces:

```python
@dataclass(frozen=True)
class ChunkFingerprint:
    video_key: str
    audio_key: str
    composition_uids: tuple[str, ...]
    video_dirty: bool
    audio_dirty: bool

def classify_operation_planes(op: Operation, timeline: Timeline) -> frozenset[Literal["video", "audio"]]:
    ...

def compute_chunk_fingerprints(
    *,
    old_timeline: Timeline | None,
    new_timeline: Timeline,
    old_graph_hash: str | None,
    new_graph_hash: str,
    operations: Sequence[Operation],
    windows: Sequence[ChunkWindow],
    profile_fingerprint: str,
    content_fingerprint: str,
) -> list[ChunkFingerprint]:
    ...

def select_dirty_windows(
    fingerprints: Sequence[ChunkFingerprint],
    requested_ranges: Sequence[PreviewRange],
    *,
    background: bool,
) -> list[int]:
    ...
```

- [ ] **Step 1: Write failing tests for video-only, audio-only, unknown, and missing-snapshot cases.**

```python
def test_gain_edit_keeps_video_key_and_dirties_audio():
    old = timeline_with_audio_clip()
    new = apply_gain(old)
    got = compute_chunk_fingerprints(
        old_timeline=old, new_timeline=new,
        old_graph_hash="old", new_graph_hash="new",
        operations=[SetAudioGainOp(clip_id="a1", gain_db=-3, author="user")],
        windows=make_chunk_windows(60, 30, 1),
        profile_fingerprint="profile", content_fingerprint="content",
    )[0]
    assert got.video_dirty is False
    assert got.audio_dirty is True

def test_remotion_edit_dirties_only_overlapping_video_windows():
    got = fingerprints_for_remotion_edit(position=2.0, duration=0.5)
    assert got[0].video_dirty is False
    assert got[1].video_dirty is True
    assert got[2].video_dirty is False

def test_unknown_free_form_edit_invalidates_every_plane():
    got = fingerprints_for_unknown_edit()
    assert all(item.video_dirty and item.audio_dirty for item in got)

def test_missing_old_snapshot_is_conservative():
    got = fingerprints_with_old_timeline_none()
    assert all(item.video_dirty and item.audio_dirty for item in got)
```

- [ ] **Step 2: Run the focused tests and verify the plane distinction is absent.**

Run: `pytest tests/test_preview_invalidation.py -k "gain or remotion or unknown or snapshot" -q`

Expected: FAIL until plane-specific fingerprints and classifications are implemented.

- [ ] **Step 3: Implement canonical per-plane keys.** Include the core frame interval, profile fingerprint, source content fingerprint, relevant timeline slice, relevant effect/transition/overlay/Remotion data, and plane name. Exclude audio-only effects from the video key and exclude video-only compositor data from the audio key. Include the overlapping `composition_uid` tuple in the returned fingerprint.

- [ ] **Step 4: Implement operation classification and conservative fallback.** `set_audio_gain` and `normalize_audio` are audio-only; video clip/track changes, transitions, effects, Remotion, HTML overlays, source replacement, speed/ripple/split, and unknown operations are video-affecting; operations on media with both planes affect both when their semantics change timing/content. `raw_mlt_xml` and `free_form_code` invalidate the full timeline. Compare old/new slices for final correctness even when classification narrows candidate windows.

- [ ] **Step 5: Implement requested-range prioritization.** Intersect ranges with dirty windows, include neighboring context windows, sort interactive jobs by distance from the first requested range, and let background jobs include all dirty windows. Already-green keys are not enqueued.

- [ ] **Step 6: Run the focused suite and commit.**

Run: `pytest tests/test_preview_invalidation.py -q`

Expected: PASS.

```bash
git add open_edit/render/preview_invalidation.py open_edit/render/cache.py open_edit/render/profiles.py tests/test_preview_invalidation.py
git commit -m "feat: add plane-aware preview invalidation"
```

### Task 5: Add preview profiles and independent video/audio/mux commands

**Files:**
- Create: `open_edit/render/preview_pipe.py`
- Modify: `open_edit/render/profiles.py`
- Read and regression-test: `open_edit/render/pipe_builder.py`
- Test: `tests/test_preview_pipe.py`
- Regression tests: `tests/test_render/test_pipe_builder.py`, `tests/test_render/test_encoder.py`

**Interfaces:**
- Consumes: `RenderProfile`, `EncoderSpec`, sliced local MLT XML, `OverlayClip` values, crop frame counts, and plane selection.
- Produces:

```python
@dataclass(frozen=True)
class PreviewPipeCommands:
    video_cmd: list[str] | None
    audio_cmd: list[str] | None
    mux_cmd: list[str] | None
    video_output: Path | None
    audio_output: Path | None
    playback_output: Path

def build_preview_pipe_commands(
    *,
    melt_bin: str,
    xml_path: Path,
    video_output: Path | None,
    audio_output: Path | None,
    playback_output: Path,
    profile: RenderProfile,
    encoder: EncoderSpec,
    overlays: Sequence[OverlayClip],
    crop_head_frames: int,
    crop_tail_frames: int,
    core_frames: int,
    media: Literal["video", "audio", "both"],
) -> PreviewPipeCommands:
    ...
```

- [ ] **Step 1: Write failing command assertions.**

```python
def test_video_command_preserves_rawvideo_contract_and_core_trim(tmp_path):
    cmds = build_preview_pipe_commands(
        melt_bin="melt", xml_path=tmp_path / "chunk.mlt",
        video_output=tmp_path / "v.mp4", audio_output=None,
        playback_output=tmp_path / "p.mp4",
        profile=preview_profile(), encoder=h264_encoder(),
        overlays=[], crop_head_frames=2, crop_tail_frames=1, core_frames=30,
        media="video",
    )
    assert "f=rawvideo" in cmds.video_cmd
    assert "trim=start_frame=2" in " ".join(cmds.video_cmd or [])
    assert "-frames:v" in cmds.video_cmd and "30" in cmds.video_cmd
    assert cmds.audio_cmd is None
    assert cmds.mux_cmd is None

def test_audio_only_command_does_not_build_video_pipe(tmp_path):
    cmds = build_preview_pipe_commands(
        melt_bin="melt", xml_path=tmp_path / "chunk.mlt",
        video_output=None, audio_output=tmp_path / "a.m4a",
        playback_output=tmp_path / "p.mp4",
        profile=preview_profile(), encoder=h264_encoder(),
        overlays=[], crop_head_frames=0, crop_tail_frames=0, core_frames=30,
        media="audio",
    )
    assert cmds.video_cmd is None
    assert cmds.audio_cmd is not None
    assert cmds.mux_cmd is None

def test_mux_command_copies_selected_planes(tmp_path):
    cmds = build_preview_pipe_commands(
        melt_bin="melt", xml_path=tmp_path / "chunk.mlt",
        video_output=tmp_path / "v.mp4", audio_output=tmp_path / "a.m4a",
        playback_output=tmp_path / "p.mp4",
        profile=preview_profile(), encoder=h264_encoder(),
        overlays=[], crop_head_frames=0, crop_tail_frames=0, core_frames=30,
        media="both",
    )
    assert cmds.mux_cmd[:2] == ["ffmpeg", "-y"]
    assert "-c:v" in cmds.mux_cmd and "copy" in cmds.mux_cmd
    assert "-c:a" in cmds.mux_cmd and "copy" in cmds.mux_cmd
```

- [ ] **Step 2: Run the focused tests and verify the new command builder is missing.**

Run: `pytest tests/test_preview_pipe.py -q`

Expected: FAIL.

- [ ] **Step 3: Add the `preview_chunk` profile.** Start at the current fast proxy dimensions (640×360), project FPS, H.264/AAC browser-safe codecs, and a lower audio bitrate. Give video, audio, and mux settings separate stable profile fingerprints. Reject client attempts to change chunk geometry through arbitrary profile overrides.

- [ ] **Step 4: Implement the three command forms.** Reuse the existing rawvideo and overlay filter helpers; preserve `f=rawvideo`, `vcodec=rawvideo`, profile size, and FPS. Video output must trim `crop_head_frames` and limit to exactly `core_frames`; audio output must be independently encoded and core-trimmed to the same duration. Mux must use `-c:v copy -c:a copy -shortest` and write only to a temporary output path before validation.

- [ ] **Step 5: Run focused and regression tests.**

Run: `pytest tests/test_preview_pipe.py tests/test_render/test_pipe_builder.py tests/test_render/test_encoder.py -q`

Expected: PASS with existing proxy/final command lists unchanged.

- [ ] **Step 6: Commit the independent plane commands.**

```bash
git add open_edit/render/preview_pipe.py open_edit/render/profiles.py tests/test_preview_pipe.py tests/test_render/test_pipe_builder.py tests/test_render/test_encoder.py
git commit -m "feat: build independent preview plane commands"
```

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

### Task 9: Extend MCP and REST enqueue/poll contracts

**Files:**
- Modify: `open_edit/kernel/tool_registry.py`
- Modify: `open_edit/kernel/tool_executor.py`
- Modify: `open_edit/serve/routers/renders.py`
- Test: `tests/test_tool_registry.py`
- Test: `tests/test_tool_executor.py`
- Test: `tests/test_serve_render_jobs.py`

**Interfaces:**
- Consumes: `PreviewRange`, `PreviewMedia`, render-job params, and `RenderJobService`.
- Produces:

```python
class TriggerRenderArgs(BaseModel):
    mode: Literal["proxy", "final", "overlay", "preview-chunks"] = "proxy"
    encoder: Literal["gpu", "cpu"] | None = None
    wait: bool = False
    ranges: list[PreviewRange] = Field(default_factory=list)
    media: Literal["video", "audio", "both"] = "both"
    priority: Literal["interactive", "background"] = "interactive"
    # Existing proxy/final quality fields remain unchanged.
```

`RenderRequest` mirrors `mode`, `ranges`, `media`, `priority`, and `expected_revision`. `RenderJobResponse` adds `result: dict[str, Any] | None` so clients can inspect partial/graph-changed status without reading a private path.

- [ ] **Step 1: Write failing schema and forwarding tests.**

```python
def test_trigger_render_schema_advertises_preview_ranges():
    schema = next(s for s in build_tool_schemas() if s["name"] == "trigger_render")
    assert "preview-chunks" in schema["input_schema"]["properties"]["mode"]["enum"]
    assert "ranges" in schema["input_schema"]["properties"]

def test_execute_trigger_render_forwards_preview_params(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        RenderJobService, "enqueue",
        capture_enqueue(captured),
    )
    result = asyncio.run(execute_trigger_render({
        "mode": "preview-chunks",
        "ranges": [{"start_sec": 2, "end_sec": 4}],
        "media": "audio",
        "priority": "interactive",
    }, tmp_path))
    assert result["mode"] == "preview-chunks"
    assert captured["params"]["media"] == "audio"
    assert captured["params"]["ranges"] == [{"start_sec": 2, "end_sec": 4}]
```

- [ ] **Step 2: Run focused tests and verify the existing literal/validation rejects the new mode.**

Run: `pytest tests/test_tool_registry.py tests/test_tool_executor.py tests/test_serve_render_jobs.py -k "trigger_render or render_request" -q`

Expected: FAIL before the contract is extended.

- [ ] **Step 3: Implement validation and forwarding.** Normalize ranges, reject `end_sec <= start_sec`, reject negative starts, reject unknown media/priority values, cap the number of ranges per request, and preserve existing quality/codec validation. When `preview_chunks_enabled()` is false, return the established feature-disabled error for `preview-chunks` while leaving proxy/final/overlay untouched. For `wait=true`, return the manifest-oriented result rather than treating `manifest.json` as a playable MP4.

- [ ] **Step 4: Update REST enqueue/poll models and route validation.** Accept `preview-chunks`, pass params to `enqueue()`, return `result`, and keep invalid modes/quality/codec errors at HTTP 400. Preserve 409 stale-revision behavior.

- [ ] **Step 5: Run focused and full contract tests.**

Run: `pytest tests/test_tool_registry.py tests/test_tool_executor.py tests/test_serve_render_jobs.py -q`

Expected: PASS.

- [ ] **Step 6: Commit the public render contract.**

```bash
git add open_edit/kernel/tool_registry.py open_edit/kernel/tool_executor.py open_edit/serve/routers/renders.py tests/test_tool_registry.py tests/test_tool_executor.py tests/test_serve_render_jobs.py
git commit -m "feat: expose preview-chunks through render APIs"
```

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

### Task 11: Add frontend API/state contracts

**Files:**
- Modify: `open_edit/serve/static/js/api.js`
- Modify: `open_edit/serve/static/js/state.js`
- Test: `tests/test_preview_frontend.py`

**Interfaces:**
- Consumes: the REST routes from Task 10.
- Produces:

```javascript
api.getPreviewManifest(projectId)
api.renderPreviewChunks(projectId, { ranges, media = 'both', priority = 'interactive' })
api.previewChunkFileUrl(projectId, artifactId)
api.wipePreviewChunks(projectId)

state.previewManifest
state.previewJob
state.previewConsumer
state.previewPollTimer
state.autoPreview
```

- [ ] **Step 1: Write failing Node-sandbox tests for request bodies and state defaults.**

```javascript
async function captureRenderPreviewBody(requestPromise, fetchCalls) {
  await requestPromise;
  return JSON.parse(fetchCalls.at(-1).options.body);
}

const body = await captureRenderPreviewBody(
  api.renderPreviewChunks('p1', {
    ranges: [{ start_sec: 2, end_sec: 4 }],
    media: 'audio',
    priority: 'interactive',
  })
);
if (body.mode !== 'preview-chunks') throw new Error('wrong mode');
if (body.ranges[0].start_sec !== 2) throw new Error('wrong range');
if (body.media !== 'audio') throw new Error('wrong media');
if (state.previewManifest !== null) throw new Error('state must start empty');
```

- [ ] **Step 2: Run the frontend test and verify the methods/state fields are absent.**

Run: `pytest tests/test_preview_frontend.py -k "api or state" -q`

Expected: FAIL.

- [ ] **Step 3: Implement the REST client methods.** Reuse `_extractError()`, URL-encode project/artifact IDs, send JSON for enqueue, and return parsed JSON. Do not make `getPreviewManifest()` throw for a valid empty manifest.

- [ ] **Step 4: Add state fields and reset semantics.** Reset preview manifest/job/consumer/timer on project switch; clear the timer on no project; keep `proxyRenderInFlight`, `previewRenderId`, and existing render polling independent.

- [ ] **Step 5: Run Node-sandbox and module-structure tests.**

Run: `pytest tests/test_preview_frontend.py tests/test_serve_module_structure.py -q`

Expected: PASS.

- [ ] **Step 6: Commit the frontend API/state seam.**

```bash
git add open_edit/serve/static/js/api.js open_edit/serve/static/js/state.js tests/test_preview_frontend.py
git commit -m "feat: add preview manifest frontend state"
```

### Task 12: Implement the sequential HTML5 playlist consumer

**Files:**
- Create: `open_edit/serve/static/js/preview.js`
- Test: `tests/test_preview_frontend.py`
- Read for DOM conventions: `open_edit/serve/static/js/dom.js`, `tests/_node_harness.py`

**Interfaces:**
- Consumes: `PreviewManifest`, artifact URL callback, `<video>` element, and global timeline seconds.
- Produces:

```javascript
export function choosePreviewChunk(manifest, globalSec) {}
export function playableArtifact(chunk) {}
export function coalesceStatusRuns(chunks) {}
export function renderPreviewStatusMap(container, manifest, onSelect) {}

export class SequentialPreviewPlayer {
  constructor(video, {
    artifactUrl,
    onGlobalTime,
    onNeedRange,
    onFallback,
  }) {}
  load(manifest, { startSec = 0, autoplay = false } = {}) {}
  seek(globalSec) {}
  play() {}
  pause() {}
  dispose() {}
}

export function createPreviewConsumer(video, options) {
  // Select MSE only when a future manifest explicitly advertises it and the
  // browser supports it; M3 manifests select sequential playback.
}
```

- [ ] **Step 1: Write failing pure-function tests.**

```javascript
function fixtureManifest(chunks) {
  return {
    timeline: { duration_sec: 3 },
    chunks: chunks.map((chunk, index) => ({
      index,
      start_sec: chunk.start_sec,
      end_sec: chunk.end_sec,
      status: chunk.status,
      playback: {
        status: chunk.status,
        current: chunk.status === 'green' ? { artifact_id: `chunk-${index}` } : null,
        fallback: null,
      },
    })),
  };
}

const manifest = fixtureManifest([
  { start_sec: 0, end_sec: 1, status: 'green' },
  { start_sec: 1, end_sec: 2, status: 'yellow' },
  { start_sec: 2, end_sec: 3, status: 'red' },
]);
if (choosePreviewChunk(manifest, 1.25).index !== 1) throw new Error('wrong chunk');
if (playableArtifact(manifest.chunks[2]) !== null) throw new Error('red must be unavailable');
const runs = coalesceStatusRuns(manifest.chunks);
if (runs.map(r => r.status).join(',') !== 'green,yellow,red') throw new Error('wrong runs');
```

- [ ] **Step 2: Write a fake-video test for global/local time mapping and sequential advance.**

```javascript
function fakeVideo() {
  const listeners = new Map();
  return {
    src: '',
    currentTime: 0,
    duration: 1,
    paused: true,
    preload: 'auto',
    addEventListener(name, fn) {
      listeners.set(name, fn);
    },
    removeEventListener(name) {
      listeners.delete(name);
    },
    emit(name, event = {}) {
      listeners.get(name)?.(event);
    },
    load() {},
    play() { this.paused = false; return Promise.resolve(); },
    pause() { this.paused = true; },
  };
}

const seen = [];
const video = fakeVideo();
const player = new SequentialPreviewPlayer(video, {
  artifactUrl: id => `/files/${id}`,
  onGlobalTime: t => seen.push(t),
  onNeedRange: () => {},
  onFallback: () => { throw new Error('unexpected fallback'); },
});
player.load(manifest, { startSec: 1.25, autoplay: true });
video.emit('loadedmetadata', { duration: 1 });
if (video.currentTime !== 0.25) throw new Error('local seek missing');
video.currentTime = 0.99;
video.emit('timeupdate');
if (video.src !== '/files/chunk-2') throw new Error('did not advance');
```

- [ ] **Step 3: Run the focused frontend tests and verify the consumer is absent.**

Run: `pytest tests/test_preview_frontend.py -k "chunk or player or status" -q`

Expected: FAIL.

- [ ] **Step 4: Implement the pure selection/status helpers.** Choose exact-range current artifacts first, then same-range fallbacks, and return null for unavailable chunks. Coalesce adjacent status runs so a long timeline does not create thousands of status DOM nodes. Add `aria-label`, `title`, and status text to each rendered run.

- [ ] **Step 5: Implement `SequentialPreviewPlayer`.** Set a chunk URL only after selecting a playable artifact; preserve a pending global seek while metadata loads; map `video.currentTime + chunk.start_sec` to the timeline playhead; on chunk end choose the next playable chunk and preserve play state; invoke `onNeedRange` when the current/next chunk is yellow/red; call `onFallback` when no chunk is playable. `dispose()` removes listeners and revokes any object URLs created by the consumer.

- [ ] **Step 6: Implement the strategy seam without requiring MSE.** `createPreviewConsumer()` returns the sequential player for M3 self-contained MP4 chunks. If a future manifest has `streaming: "mse"` but the browser lacks `MediaSource`, it falls back to sequential and reports the fallback through `onFallback`; do not append incompatible fMP4 data in M3.

- [ ] **Step 7: Run frontend tests and commit.**

Run: `pytest tests/test_preview_frontend.py -q`

Expected: PASS.

```bash
git add open_edit/serve/static/js/preview.js tests/test_preview_frontend.py
git commit -m "feat: add sequential chunk preview consumer"
```

### Task 13: Integrate Review Studio controls, status map, and proxy fallback

**Files:**
- Modify: `open_edit/serve/static/app.js`
- Modify: `open_edit/serve/static/index.html`
- Modify: `open_edit/serve/static/style.css`
- Modify: `open_edit/serve/static/js/state.js` if integration needs one additional reset field
- Test: `tests/test_preview_frontend.py`
- Regression tests: `tests/test_serve_loading_state.py`, `tests/test_serve_module_structure.py`

**Interfaces:**
- Consumes: `api` methods from Task 11, `SequentialPreviewPlayer` from Task 12, existing `loadRenderInPreview()`, `seekToSec()`, `maybeAutoLoadPreview()`, and `tlDurationSec`.
- Produces: visible chunk status map, explicit “Render chunks” and “Clear chunk cache” controls, and global timeline seek/playback that can use chunks without breaking proxy playback.

- [ ] **Step 1: Write failing integration assertions.** Extend the Node module contract test to require `refreshPreviewManifest`, `requestPreviewWindow`, and `renderPreviewStatusMap` test hooks. Add a fake manifest test that loads a green chunk and asserts the video URL is the chunk URL, while a red-only manifest asserts the existing proxy fallback callback is used.

```javascript
const hooks = globalThis.OpenEdit.__testHooks;
for (const name of ['refreshPreviewManifest', 'requestPreviewWindow', 'renderPreviewStatusMap']) {
  if (typeof hooks[name] !== 'function') throw new Error(`missing ${name}`);
}
```

- [ ] **Step 2: Run the integration tests and verify the hooks/controls are absent.**

Run: `pytest tests/test_preview_frontend.py tests/test_serve_module_structure.py -q`

Expected: FAIL.

- [ ] **Step 3: Add the UI structure.** Insert a status row below `#preview-player` with `#preview-cache-badge`, `#preview-chunk-map`, and `#preview-cache-detail`; add `#btn-render-chunks` and `#btn-clear-chunks` beside the existing proxy/final buttons. Keep the existing Render Proxy button copy and behavior.

- [ ] **Step 4: Integrate manifest loading and polling.** On project load and after graph revision changes, call `api.getPreviewManifest()`, render the map, and load a chunk consumer only when a playable chunk exists. Poll the manifest every second while the active preview job is queued/running; stop polling on terminal state or project switch. Polling is separate from the five-second whole-file render list polling.

- [ ] **Step 5: Implement request-window behavior.** `requestPreviewWindow(sec)` sends a debounced range covering the current chunk plus four neighboring chunks, clamped to timeline duration. The Render Chunks button sends the current visible timeline range. If `state.autoPreview` is true, scrub requests are sent after 250 ms; if false, a red/yellow seek uses the proxy fallback and shows “Render chunks to update this zone.”

- [ ] **Step 6: Route playback and seek correctly.** `seekToSec()` calls `state.previewConsumer.seek(clamped)` when a chunk consumer exists; otherwise it keeps the current MP4 `currentTime` behavior. Player timeupdate events update global `state.playheadSec`, the existing timecode, and the timeline playhead. Loading a proxy must dispose the chunk consumer and loading chunks must not clear the latest proxy render ID.

- [ ] **Step 7: Add status styling and accessibility.** Use red/yellow/green classes with text/icon labels, not color alone. The map’s widths must be proportional to chunk duration, and the stale whole-file proxy badge must be explicit. The status map must remain usable in review-only and full modes.

- [ ] **Step 8: Run focused frontend tests and commit.**

Run: `pytest tests/test_preview_frontend.py tests/test_serve_module_structure.py tests/test_serve_loading_state.py -q`

Expected: PASS.

```bash
git add open_edit/serve/static/app.js open_edit/serve/static/index.html open_edit/serve/static/style.css open_edit/serve/static/js/state.js tests/test_preview_frontend.py tests/test_serve_module_structure.py tests/test_serve_loading_state.py
git commit -m "feat: integrate chunk preview into Review Studio"
```

### Task 14: Document the new job and preserve the three-product vocabulary

**Files:**
- Modify: `skills/open-edit-mcp.md`
- Modify: `skills/open-edit-mcp-reference.md`
- Modify: `skills/tool_surface.md`
- Modify: `open_edit/harness_skills/open-edit-mcp.md`
- Modify: `open_edit/harness_skills/open-edit-mcp-reference.md`
- Modify: `open_edit/harness_skills/tool_surface.md`
- Modify: `docs/MCP.md`
- Test: `tests/test_mcp_server.py`
- Test: `tests/test_tool_contract.py`

**Interfaces:**
- Consumes: the finalized MCP/REST contracts from Tasks 8–10.
- Produces: synchronized host-facing instructions that say `preview-chunks` is a background range cache, `proxy` is a whole-file artifact, `final` is delivery, and free-form never renders preview media.

- [ ] **Step 1: Write failing documentation-contract tests.**

```python
def test_mcp_playbook_distinguishes_proxy_and_preview_chunks():
    text = Path("skills/open-edit-mcp.md").read_text()
    assert "`preview-chunks`" in text
    assert "whole-file" in text
    assert "audio" in text and "independent" in text
    assert "live MLT" in text and "M4" in text

def test_packaged_skill_matches_canonical_preview_section():
    paths = [
        Path("skills/open-edit-mcp.md"),
        Path("open_edit/harness_skills/open-edit-mcp.md"),
    ]
    for path in paths:
        text = path.read_text()
        assert "`preview-chunks`" in text
        assert "sequential" in text
        assert "same-range" in text
```

- [ ] **Step 2: Run the documentation tests and verify the new wording is missing.**

Run: `pytest tests/test_mcp_server.py tests/test_tool_contract.py -q`

Expected: FAIL on the new assertions only.

- [ ] **Step 3: Update the canonical skill docs.** Add a `preview-chunks` example with ranges/media/priority, explain non-blocking polling and manifest status, describe same-range fallback and stale proxy fallback, show the wipe endpoint, and state that MSE is optional while sequential playback is the M3 default.

- [ ] **Step 4: Synchronize packaged skill copies and update `docs/MCP.md`.** Keep existing proxy/final examples unchanged except for terminology clarifications. Document `OPEN_EDIT_AUTO_PREVIEW`, cache cap/TTL knobs, and the unchanged final workflow.

- [ ] **Step 5: Run documentation/MCP tests and commit.**

Run: `pytest tests/test_mcp_server.py tests/test_tool_contract.py -q`

Expected: PASS.

```bash
git add skills/open-edit-mcp.md skills/open-edit-mcp-reference.md skills/tool_surface.md open_edit/harness_skills/open-edit-mcp.md open_edit/harness_skills/open-edit-mcp-reference.md open_edit/harness_skills/tool_surface.md docs/MCP.md tests/test_mcp_server.py tests/test_tool_contract.py
git commit -m "docs: describe chunked timeline preview workflow"
```

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

### Task 16: Verify rollout gates, cache safety, and final non-regression

**Files:**
- Test/modify only as needed: `tests/test_render_jobs.py`, `tests/test_serve_render_jobs.py`, `tests/test_preview_cache.py`, `tests/test_preview_frontend.py`
- Read-only verification: architecture/spec files and all changed implementation paths

**Interfaces:**
- Consumes: all completed M3 tasks and the M1 dependency evidence.
- Produces: a merge-ready verification record; no new product behavior.

- [ ] **Step 1: Run the full Python suite and frontend-focused suite.**

Run:

```bash
pytest -q
pytest tests/test_preview_frontend.py tests/test_serve_module_structure.py -q
```

Expected: all tests pass; no existing proxy/final/Review Studio regression appears.

- [ ] **Step 2: Run static/lint checks on every changed Python file and inspect diagnostics.**

Run:

```bash
python -m compileall -q open_edit
```

Expected: exit code 0. Run the repository-configured checks explicitly:

```bash
ruff check open_edit/render/preview_manifest.py open_edit/render/preview_invalidation.py open_edit/render/preview_cache.py open_edit/render/preview_pipe.py open_edit/render/preview_chunks.py open_edit/kernel/render_jobs.py open_edit/kernel/tool_registry.py open_edit/kernel/tool_executor.py open_edit/serve/routers/preview_chunks.py
mypy open_edit/render/preview_manifest.py open_edit/render/preview_invalidation.py open_edit/render/preview_cache.py open_edit/render/preview_pipe.py open_edit/render/preview_chunks.py
```

Do not introduce a new tool or dependency for M3.

- [ ] **Step 3: Exercise the manual host-worker smoke path.**

```text
1. Start Review Studio in review-only mode.
2. Load a project with a short video/audio timeline.
3. Click Render Proxy and confirm one full MP4 still appears in the renders list.
4. Click Render chunks for a 4–8 second window.
5. Confirm red → yellow → green map transitions and sequential playback across two green chunks.
6. Seek into a red chunk and confirm the UI labels the whole-file proxy fallback rather than silently claiming chunk readiness.
7. Apply one Remotion overlay edit; confirm only the affected range changes color.
8. Apply audio gain; confirm video artifact IDs remain unchanged while audio/playback IDs change.
9. Restart the server and confirm the manifest/job state is recoverable from disk/SQLite.
10. Use Clear chunk cache and confirm the edit graph and proxy render remain.
```

- [ ] **Step 4: Verify the M1/M2 gates explicitly.** Record the M1 frame-engine contract test result, dirty composition reuse result, Remotion eviction result, and optional M2 source-proxy result. If any M1 hard dependency is absent, keep the preview worker feature-disabled and report the exact gate rather than shipping a bake path that violates the in-pipeline Remotion decision.

- [ ] **Step 5: Verify the M3 acceptance criteria.**

```text
- One Remotion overlay edit produces a visible update in its chunk zone without waiting for the full proxy.
- Untouched green zones remain seekable.
- Silence/gain-only edits do not invalidate video chunk keys.
- A prior exact-range chunk or stale whole-file proxy remains available while a new chunk bakes.
- Cache size and wipe controls work.
- Free-form IR remains sandboxed and never owns preview rendering.
- No live MLT SDL/OpenGL consumer was added.
```

- [ ] **Step 6: Commit only verification/test adjustments, if any.**

```bash
git add tests/test_render_jobs.py tests/test_serve_render_jobs.py tests/test_preview_cache.py tests/test_preview_frontend.py
git commit -m "test: finalize chunked preview rollout gates"
```

If no test adjustment is required, do not create an empty commit.

## Commit Sequence

The intended reviewable commit sequence is:

1. `test: freeze preview frame-engine handoff`
2. `feat: define preview chunk manifest contract`
3. `feat: add frame-aligned preview range slicing`
4. `feat: add plane-aware preview invalidation`
5. `feat: build independent preview plane commands`
6. `feat: add bounded atomic preview cache`
7. `feat: bake dirty preview chunks with fallbacks`
8. `feat: schedule durable preview-chunks jobs`
9. `feat: expose preview-chunks through render APIs`
10. `feat: serve preview manifests and chunk files`
11. `feat: add preview manifest frontend state`
12. `feat: add sequential chunk preview consumer`
13. `feat: integrate chunk preview into Review Studio`
14. `docs: describe chunked timeline preview workflow`
15. `test: verify preview chunk invalidation and fallback`
16. `test: finalize chunked preview rollout gates`

Each commit must pass its task’s focused tests before the next task starts. Do not squash the commits until review has accepted the boundaries; the separate commits make it possible to reject MSE/consumer details without hiding cache or invalidation changes.

## Acceptance and Rollback

### M3 acceptance

- A `preview-chunks` MCP or REST request returns a durable job ID and never blocks by default.
- The job produces a schema-versioned manifest and independently addressable video/audio/playback artifacts.
- The manifest visibly exposes red/yellow/green state and preserves prior same-range fallbacks.
- A one-second, frame-aligned chunk can be selected and played by the Review Studio consumer with global timeline seek mapping.
- A Remotion edit invalidates only overlapping video chunks when the M1 frame-engine contract supplies the affected UIDs.
- Audio gain/silence/normalization changes do not flush unchanged video keys.
- Whole-file `mode=proxy` continues to render, list, stream, and load exactly as before.
- Cache cap, eviction, atomic recovery, path safety, and wipe are tested.
- No free-form GPU access or live MLT SDL consumer is introduced.

### Feature flag and rollback

Keep chunk generation behind `OPEN_EDIT_PREVIEW_CHUNKS=1` until the short-fixture acceptance test and manual smoke path pass. When unset, the API may return a clear 404/409 feature-disabled response for `preview-chunks`, while proxy/final remain fully available. If a worker or browser issue appears after enablement, set the flag to `0`; existing proxy artifacts and the Edit Graph remain untouched, and the cache wipe route can remove preview files without altering timeline state.

## Risks and Mitigations

- **M1 frame-engine seam is late or incompatible:** block worker enablement and use fake-renderer tests only; do not create an external Remotion bake relay. The hard dependency is the range-aware host renderer contract, not M1’s exact internal implementation.
- **Sequential source switching has visible gaps:** keep the last exact-range artifact and whole-file proxy fallback; pre-load the next source with `preload="auto"`; measure gap duration on a real browser before considering MSE.
- **MSE/fMP4 timestamp complexity:** do not make M3 depend on MSE. Preserve a strategy interface and manifest field so a later fMP4 implementation can be tested independently.
- **Audio/video drift during independent remux:** keep core frame/sample durations in the manifest, use local zero-based timestamps, mux with `-shortest`, and test two adjacent chunks with non-empty audio.
- **Transitions/effects cross boundaries:** render context frames and crop to core; conservatively invalidate adjacent chunks; unknown/raw-MLT/free-form changes invalidate the full timeline.
- **Graph changes during a long bake:** check graph revision/hash before every publication, stop stale workers, and retain the previous manifest/artifacts instead of replacing a newer graph’s manifest.
- **Disk pressure:** use the 512 MiB default cap, seven-day expiry, referenced-artifact protection, minimum-free-space refusal, and wipe API; never leave red temporary files unbounded.
- **Render-job schema migration:** rebuild only the old mode-check table when required and copy every existing row; run migration tests against a database created with the pre-M3 schema.
- **API/UI vocabulary regression:** filter preview jobs from the renders artifact list and retain explicit `Preview chunks`, `Proxy artifact`, and `Final export` labels.
- **Long timelines create too many DOM nodes or jobs:** coalesce adjacent status runs, request only a playhead window interactively, and process full dirty coverage only for explicit background requests.
- **M2 source proxies are unavailable:** resolve canonical assets for preview; source-proxy use is an optimization, not a correctness dependency.
- **Hardware variance:** preview profile defaults to CPU-safe browser codecs; optional host GPU encoding follows existing encoder selection and never enters the sandbox.
- **Live MLT scope creep:** any request for SDL/OpenGL/shared-memory playback is a separate M4 plan and is rejected from this M3 task sequence.

## Return Summary

- **Plan path:** `docs/superpowers/plans/2026-08-03-chunked-timeline-preview.md`
- **Task count:** 16 implementation tasks, each with focused TDD steps and a commit boundary.
- **Key files:** `open_edit/render/preview_manifest.py`, `preview_invalidation.py`, `preview_cache.py`, `preview_pipe.py`, `preview_chunks.py`; `open_edit/kernel/render_jobs.py`, `tool_registry.py`, `tool_executor.py`; `open_edit/serve/routers/preview_chunks.py`, `renders.py`; `open_edit/serve/static/js/preview.js`, `api.js`, `state.js`, `app.js`, `index.html`, `style.css`; and the corresponding preview/cache/route/frontend tests.
- **M1 dependencies:** stable profile/content fingerprints, a range-aware host Remotion frame-engine/renderer seam, dirty composition UID reuse, bounded Remotion output eviction, and passing M1 contract tests. M2 source proxies are optional.
- **Main risks:** HTML5 source-switch gaps, A/V sync during plane remux, transition boundary correctness, stale jobs racing graph edits, disk pressure, and M1 seam timing. The plan mitigates each with exact-range fallbacks, context cropping, atomic graph checks, cache caps/wipe, and a feature flag.
- **Out of scope:** live MLT SDL/OpenGL consumer and any GPU/free-form sandbox redesign; both remain M4 or later decisions.
