# Remotion In-Pipeline Frame Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Remotion from a serial, file-bake bottleneck toward an in-pipeline, on-demand frame engine while preserving the existing melt→ffmpeg proxy-artifact/final-export path and delivering the safe M0/M1 performance wins first.

**Architecture:** M0 adds stable product vocabulary and stage diagnostics without changing render behavior. M1 computes a deliverable cache key before materialization, tracks a successful materialization manifest for dirty-zone reuse, renders composition misses through a bounded host-worker pool, applies content-aware cache eviction and alpha policy, and skips QC only for verified proxy deliverable cache hits. In parallel, M1 defines and proves a host-only Remotion frame-pull protocol using the pinned programmatic renderer APIs; an opt-in ffmpeg overlay feeder is the incremental bridge to same-pass rendering, while materialized clips remain the default until frame parity and failure handling are proven.

**Tech Stack:** Python 3.11 floor, Pydantic IR models, pytest, filesystem/SQLite project state, Node.js, Remotion `4.0.278`, `@remotion/bundler`, `@remotion/renderer`, Chromium, melt rawvideo pipe, ffmpeg filter-complex overlays, and the existing FastAPI/Review Studio UI.

## Global Constraints

- The architecture is approved for planning only; do not modify `open_edit/` product code until AH64 approves this plan.
- All Remotion, Chromium, melt, ffmpeg, and optional GPU work runs on the host render worker. The free-form sandbox remains IR-only and receives no `/dev/dri`, shared CUDA/GL, or new render IPC.
- Keep melt→ffmpeg for final exports and whole-file proxy review artifacts. Preserve the existing melt consumer contract: `f=rawvideo`, `vcodec=rawvideo`, `pix_fmt=yuv420p`.
- `mode=proxy` means a full-timeline review artifact at the actual `fast_proxy` default of 640×360; it is not a per-asset source proxy and is not an interactive timeline-preview chunk.
- Remotion frame pull must be same-pass/on-demand with Open Edit; do not make external Remotion bake-then-stitch the long-term architecture. Materialization is the compatibility path and M1 default.
- Keep the pinned Remotion version at `4.0.278` everywhere. Include the Remotion version and alpha-policy version in keys and protocol metadata.
- Keep Python compatibility at the project’s 3.11 floor; do not introduce runtime-only 3.14 APIs.
- `force` for the whole-file deliverable cache and `force_remotion`/per-composition invalidation are separate controls.
- Every new or expanded cache has a byte cap, age policy, eviction behavior, and an operator-visible wipe path or documented directory.
- Final-export QC remains available and enabled by default. M1 chooses skip-on-verified-proxy-cache-hit rather than asynchronous QC; asynchronous attachment is a later policy option.
- Never log Remotion props, secrets, or full user-controlled source contents in diagnostics. Record identifiers, counts, durations, versions, and bounded error text only.
- Every M0/M1 change must retain a materialize fallback and preserve existing pipe, alpha, repair, and sandbox tests.

---

## Baseline decisions and terminology

The implementation starts from the approved architecture in `docs/superpowers/specs/2026-08-02-open-edit-rendering-architecture.md` and the handoff in `docs/superpowers/specs/2026-08-03-session-compact.md`.

The render products use these exact names:

| Name | API identity | Meaning |
|---|---|---|
| Review artifact | `mode=proxy` | Full-timeline 640×360-class MP4 for Review Studio and agent review |
| Final export | `mode=final` | Full-timeline delivery MP4 at the selected final profile |
| Source media | Asset/CAS file | Original or canonical project media used as a source; not a render mode |
| Source proxy | Future asset derivative | Per-asset low-resolution stand-in; not implemented by this plan |
| Timeline preview chunk | Future `preview-chunks` job | Range-limited interactive scrub artifact; not the whole-file proxy |
| Remotion materialized clip | Internal compatibility representation | A CAS-ingested composition clip used by the current overlay pipe |
| Remotion frame source | Future in-pipeline representation | A host broker/feeder that supplies frames on demand directly to the overlay input |

M0 must make these terms visible in diagnostics, docs, and Review Studio copy. The existing “Proxy 720p” and command-palette “540p” labels must be removed because the current default profile is 640×360.

## File map

| # | File(s) | Action and responsibility |
|---:|---|---|
| 1 | `open_edit/render/diagnostics.py` | Create the stable product descriptor and stage-timing recorder used by render results. |
| 2 | `open_edit/render/remotion/dirty.py` | Create manifest schema, interval comparison, dirty-zone selection, and atomic manifest I/O. |
| 3 | `open_edit/render/remotion/frame_engine.py` | Create the Python frame request/response contract, client, validation, and lifecycle interface. |
| 4 | `open_edit/render/remotion_frame_server.mjs` | Create the host-only Node bridge for pinned `bundle`/`selectComposition`/`renderStill` frame requests. |
| 5 | `open_edit/render/cache.py` | Add content-verified access timestamps, byte caps, LRU/TTL eviction, and bounded cache configuration. |
| 6 | `open_edit/render/materialize.py`, `orchestrator.py`, `timeline_plan.py`, `remotion/renderer.py`, `source_repair.py` | Add dirty/parallel materialization, early deliverable-cache gating, alpha propagation/policy, and repair early-out. |
| 7 | `open_edit/render/pipe_builder.py`, `open_edit/render/melt_runner.py` | Add the opt-in frame-stream overlay input contract while leaving the existing rawvideo base pipe intact. |
| 8 | `open_edit/kernel/render_jobs.py`, `open_edit/qc/policy.py`, `open_edit/cli.py` | Add proxy cache-hit QC policy, QC timing/skipped reports, and separate Remotion invalidation controls. |
| 9 | `open_edit/serve/static/app.js`, `open_edit/serve/static/index.html`, `docs/MCP.md`, `open_edit/render/remotion_scaffold.py`, `package.json`, `package-lock.json` | Reconcile UI/docs vocabulary and make the programmatic Remotion packages available to new projects. |
| 10 | `tests/test_render/test_diagnostics.py`, `tests/test_render/test_cache.py`, `tests/test_render/test_orchestrator.py`, `tests/test_remotion_ir_materialize.py`, `tests/test_remotion_renderer.py`, `tests/test_render/test_pipe_builder.py`, `tests/test_render_jobs.py`, `tests/test_remotion_frame_engine.py`, `tests/test_review_ui.py` | Add unit, integration, protocol, cache, policy, UI-copy, and benchmark-gate coverage. |

## Interfaces shared between tasks

Use these names and shapes consistently so individual tasks can be implemented and reviewed independently:

```python
RenderMode = Literal["proxy", "final"]
StageStatus = Literal["completed", "skipped", "failed"]

class StageRecorder:
    def record(
        self,
        name: str,
        elapsed_sec: float,
        *,
        status: StageStatus = "completed",
        **fields: object,
    ) -> None: ...

    def skip(self, name: str, *, reason: str, **fields: object) -> None: ...

    @property
    def stages(self) -> dict[str, dict[str, object]]: ...

@dataclass(frozen=True)
class DirtySelection:
    intervals: tuple[tuple[float, float], ...]
    composition_uids: frozenset[str]

@dataclass
class MaterializeReport:
    worker_count: int
    cache_hits: int
    cache_misses: int
    reused_manifest_entries: int
    rendered_uids: list[str]
    dirty_uids: list[str]
    elapsed_sec: float
    manifest_entries: list[dict[str, object]]

@dataclass(frozen=True)
class FrameRequest:
    request_id: str
    composition_id: str
    entry_point: str
    props: dict[str, object]
    frame: int
    width: int
    height: int
    fps: float
    alpha: bool
    remotion_version: str = "4.0.278"
```

The optional `report` argument on `materialize_remotion_compositions()` preserves its existing `Timeline` return type:

```python
def materialize_remotion_compositions(
    timeline: Timeline,
    project_path: Path,
    *,
    mode: Literal["proxy", "final"] = "proxy",
    timeout_s: float = 600.0,
    manifest_path: Path | None = None,
    force_remotion: bool = False,
    force_uids: Collection[str] = (),
    report: MaterializeReport | None = None,
) -> Timeline: ...
```

---

### Task 1: Establish the M0 product and diagnostics contract

**Files:**
- Create: `open_edit/render/diagnostics.py`
- Modify: `open_edit/render/orchestrator.py`
- Test: `tests/test_render/test_diagnostics.py`, `tests/test_render/test_orchestrator.py`

**Interfaces:**
- Consumes: `RenderResult`, `RenderProfile`, `mode`, and the existing `PipeResult` timing fields.
- Produces: `StageRecorder`, `product_descriptor(mode, profile)`, and the canonical diagnostics keys used by all later tasks.

- [ ] **Step 1: Write failing contract tests.**

```python
def test_product_descriptor_distinguishes_review_artifact_from_source_proxy():
    descriptor = product_descriptor("proxy", width=640, height=360)
    assert descriptor == {
        "kind": "review_artifact",
        "mode": "proxy",
        "label": "Review artifact",
        "width": 640,
        "height": 360,
        "interactive": False,
        "source_proxy": False,
        "timeline_preview_chunk": False,
    }


def test_stage_recorder_preserves_status_and_numeric_elapsed():
    recorder = StageRecorder()
    recorder.record("remotion_materialize", 1.25, cache_hits=2, cache_misses=1)
    recorder.skip("ffmpeg_encode", reason="deliverable_cache_hit")
    assert recorder.stages["remotion_materialize"]["elapsed_sec"] == 1.25
    assert recorder.stages["remotion_materialize"]["status"] == "completed"
    assert recorder.stages["ffmpeg_encode"] == {
        "elapsed_sec": 0.0,
        "status": "skipped",
        "reason": "deliverable_cache_hit",
    }


def test_legacy_stage_aliases_remain_available():
    result = RenderResult(
        ok=True,
        diagnostics={
            "stages": {
                "melt_video": {"elapsed_sec": 2.0},
                "ffmpeg_encode": {"elapsed_sec": 3.0},
            },
            "legacy_stage_aliases": {
                "melt": "melt_video",
                "ffmpeg": "ffmpeg_encode",
            },
        },
    )
    assert result.diagnostics["legacy_stage_aliases"]["melt"] == "melt_video"
```

- [ ] **Step 2: Run the focused tests to verify they fail.**

Run: `pytest -q tests/test_render/test_diagnostics.py tests/test_render/test_orchestrator.py`

Expected: collection or assertion failures because `open_edit.render.diagnostics` and the canonical stage schema do not yet exist.

- [ ] **Step 3: Implement the minimal diagnostics module.**

Use these canonical stage names:

```text
derive_timeline
render_cache_lookup
remotion_materialize
build_render_plan
emit_mlt
melt_audio
melt_video
ffmpeg_encode
source_repair
qc
```

`StageRecorder.record()` must coerce elapsed values to finite non-negative floats and retain additional scalar fields such as `bytes`, `cache_hits`, `cache_misses`, `worker_count`, and `reason`. `product_descriptor()` must map `proxy` to `review_artifact` and `final` to `final_export`; it must never claim that either mode is interactive.

- [ ] **Step 4: Run the focused tests and the current orchestrator tests.**

Run: `pytest -q tests/test_render/test_diagnostics.py tests/test_render/test_orchestrator.py`

Expected: PASS, with existing `diagnostics["stages"]["remotion_materialize"]`, `["melt"]`, `["ffmpeg"]`, and `["audio"]` assertions still passing during the transition.

- [ ] **Step 5: Commit the M0 diagnostics contract.**

```bash
git add open_edit/render/diagnostics.py open_edit/render/orchestrator.py \
  tests/test_render/test_diagnostics.py tests/test_render/test_orchestrator.py
git commit -m "feat: define render diagnostics contract"
```

---

### Task 2: Wire stage timing and reconcile UI/documentation names

**Files:**
- Modify: `open_edit/render/orchestrator.py`, `open_edit/render/melt_runner.py`, `open_edit/kernel/render_jobs.py`, `open_edit/cli.py`
- Modify: `open_edit/serve/static/app.js`, `open_edit/serve/static/index.html`, `docs/MCP.md`
- Test: `tests/test_render/test_orchestrator.py`, `tests/test_render_jobs.py`, `tests/test_review_ui.py`

**Interfaces:**
- Consumes: `StageRecorder` and `product_descriptor()` from Task 1; `PipeResult.melt_elapsed_sec`, `audio_elapsed_sec`, and `ffmpeg_elapsed_sec`.
- Produces: a stable `diagnostics["product"]`, canonical stage entries, and compatibility aliases for existing consumers.

- [ ] **Step 1: Write failing timing and copy tests.**

```python
def test_render_diagnostics_include_canonical_stages_and_product(
    monkeypatch, tmp_path
):
    result = run_fake_render(monkeypatch, tmp_path, mode="proxy")
    assert result.diagnostics["product"]["kind"] == "review_artifact"
    assert result.diagnostics["product"]["width"] == 640
    assert set(result.diagnostics["stages"]) >= {
        "derive_timeline",
        "render_cache_lookup",
        "remotion_materialize",
        "build_render_plan",
        "emit_mlt",
        "melt_audio",
        "melt_video",
        "ffmpeg_encode",
        "source_repair",
    }
    assert result.diagnostics["legacy_stage_aliases"]["ffmpeg"] == "ffmpeg_encode"


def test_review_ui_uses_actual_profile_and_separate_source_copy():
    app = Path("open_edit/serve/static/app.js").read_text(encoding="utf-8")
    html = Path("open_edit/serve/static/index.html").read_text(encoding="utf-8")
    docs = Path("docs/MCP.md").read_text(encoding="utf-8")
    assert "Review artifact · 640×360" in app
    assert "Proxy 720p" not in app
    assert "540p" not in app
    assert "Source media" in app or "Source media" in html
    assert "timeline preview chunks" in docs.lower()
```

- [ ] **Step 2: Run the focused tests to verify they fail.**

Run: `pytest -q tests/test_render/test_orchestrator.py tests/test_render_jobs.py tests/test_review_ui.py`

Expected: failures for missing canonical names and stale “720p”/“540p” copy.

- [ ] **Step 3: Add non-breaking stage wiring.**

Time these boundaries in `render_project()`:

1. `derive_timeline`
2. profile/content fingerprint and `render_cache_lookup`
3. `remotion_materialize`
4. `build_render_plan`
5. `emit_mlt`
6. `run_pipe()` overall, with `PipeResult` values mapped to `melt_audio`, `melt_video`, and `ffmpeg_encode`
7. `source_repair`
8. `qc` in the job/CLI layer

Keep the existing top-level `RenderResult.elapsed_sec` and legacy `melt`, `ffmpeg`, and `audio` stage entries. Add `legacy_stage_aliases` to point consumers to the canonical names rather than removing old keys. Record skipped stages explicitly with `status="skipped"` and a reason.

- [ ] **Step 4: Update user-facing copy without adding preview behavior.**

Use these exact labels:

```text
proxy render list: "Review artifact · 640×360"
final render list: "Final export · 1080p"
source fallback badge: "Source media"
command palette: "Render review artifact (640×360)"
preview panel helper: "Render a review artifact (`mode=proxy`) to review the full cut."
```

In `docs/MCP.md`, state that `mode=proxy` is a full-timeline review artifact, that source proxies are per-asset derivatives, and that timeline preview chunks are a separate future/interactive product. Replace the old “Render proxy (720p)” workflow text with the actual 640×360 profile.

- [ ] **Step 5: Run the focused tests and inspect the static copy.**

Run: `pytest -q tests/test_render/test_orchestrator.py tests/test_render_jobs.py tests/test_review_ui.py`

Run: `rg -n "Proxy 720p|Render Proxy Video \\(540p\\)|Render proxy \\(720p\\)" open_edit/serve docs/MCP.md`

Expected: the pytest command passes and the stale-copy search returns no matches.

- [ ] **Step 6: Commit M0 naming and timing.**

```bash
git add open_edit/render/orchestrator.py open_edit/render/melt_runner.py \
  open_edit/kernel/render_jobs.py open_edit/cli.py \
  open_edit/serve/static/app.js open_edit/serve/static/index.html docs/MCP.md \
  tests/test_render/test_orchestrator.py tests/test_render_jobs.py tests/test_review_ui.py
git commit -m "feat: instrument render stages and clarify artifact names"
```

---

### Task 3: Add dirty-zone selection and a successful materialization manifest

**Files:**
- Create: `open_edit/render/remotion/dirty.py`
- Modify: `open_edit/render/materialize.py`, `open_edit/render/orchestrator.py`
- Test: `tests/test_render/test_remotion_dirty.py`, `tests/test_remotion_ir_materialize.py`

**Interfaces:**
- Consumes: an unmaterialized `Timeline`, the previous successful manifest, the current mode/profile, and optional explicit `force_uids`.
- Produces: `DirtySelection`, a manifest with one entry per Remotion UID, and direct CAS reuse for unchanged compositions.

- [ ] **Step 1: Write failing interval and manifest tests.**

```python
def test_base_edit_selects_only_overlapping_remotion_uids():
    previous = manifest(
        clips=[clip("talk", 0.0, 20.0, "asset-a")],
        compositions=[
            comp("inside", 4.0, 3.0, "key-inside", "hash-inside"),
            comp("outside", 12.0, 2.0, "key-outside", "hash-outside"),
        ],
    )
    current = manifest(
        clips=[clip("talk", 0.0, 20.0, "asset-b")],
        compositions=[
            comp("inside", 4.0, 3.0, "key-inside", "hash-inside"),
            comp("outside", 12.0, 2.0, "key-outside", "hash-outside"),
        ],
    )
    selection = select_dirty_compositions(previous, current)
    assert selection.intervals == ((0.0, 20.0),)
    assert selection.composition_uids == frozenset({"inside", "outside"})


def test_content_change_is_dirty_even_without_an_overlapping_base_edit():
    previous = manifest(compositions=[comp("card", 2.0, 1.0, "old-key", "old-hash")])
    current = manifest(compositions=[comp("card", 2.0, 1.0, "new-key", "old-hash")])
    selection = select_dirty_compositions(previous, current)
    assert selection.composition_uids == frozenset({"card"})


def test_manifest_is_written_atomically_only_after_success(tmp_path):
    path = tmp_path / "materialize_manifest.proxy.json"
    write_manifest_atomic(path, manifest(compositions=[]))
    assert load_manifest(path)["schema"] == 1
    assert not list(tmp_path.glob("*.tmp"))
```

- [ ] **Step 2: Run the focused tests to verify they fail.**

Run: `pytest -q tests/test_render/test_remotion_dirty.py tests/test_remotion_ir_materialize.py`

Expected: import failures for `open_edit.render.remotion.dirty` and missing manifest behavior.

- [ ] **Step 3: Implement the manifest and half-open interval algorithm.**

Store one small JSON file per mode/profile under `.open_edit/remotion/out/`, outside the media cache:

```json
{
  "schema": 1,
  "mode": "proxy",
  "profile_fingerprint": "remotion_proxy|640x360|30/1|...",
  "graph_hash": "sha256",
  "clips": [
    {
      "clip_id": "clip-id",
      "track_id": "v1",
      "asset_hash": "sha256",
      "position_sec": 0.0,
      "duration_sec": 20.0,
      "in_point_sec": 0.0,
      "out_point_sec": 20.0
    }
  ],
  "compositions": [
    {
      "composition_uid": "uid",
      "composition_id": "TitleCard",
      "position_sec": 4.0,
      "duration_sec": 3.0,
      "cache_key": "sha256",
      "asset_hash": "sha256",
      "ext": "mp4",
      "alpha": false
    }
  ]
}
```

Compare current and previous base clips by `clip_id` and all timing/source/effect fields. Add the old and new half-open ranges for changed, added, and removed clips. A current Remotion UID is selected when its interval intersects any dirty range, when it is new, or when its content cache key/profile/alpha/duration changed. A removed UID contributes its old range but is not returned as a current render target. Merge touching ranges.

Use `os.replace()` from a same-directory temporary file for manifest writes. Only write after the complete render succeeds; a failed render must not make the next run believe that dirty work was delivered.

- [ ] **Step 4: Add direct reuse before composition cache lookup.**

For an unchanged current UID, reuse the manifest’s `asset_hash` only when:

```python
entry["cache_key"] == current_cache_key
entry["mode"] == mode
AssetStore.path(entry["asset_hash"]) is not None
```

Otherwise fall through to the content-verified `RenderCache.get()` lookup. This means unchanged compositions are injected without re-rendering or re-ingesting, while a missing CAS file remains recoverable from the composition cache.

- [ ] **Step 5: Run dirty-selection and materialization tests.**

Run: `pytest -q tests/test_render/test_remotion_dirty.py tests/test_remotion_ir_materialize.py`

Expected: PASS, including the existing cache-hit, alpha-extension, and referenced-file invalidation tests.

- [ ] **Step 6: Commit dirty-zone materialization state.**

```bash
git add open_edit/render/remotion/dirty.py open_edit/render/materialize.py \
  open_edit/render/orchestrator.py tests/test_render/test_remotion_dirty.py \
  tests/test_remotion_ir_materialize.py
git commit -m "feat: track dirty remotion materialization zones"
```

---

### Task 4: Parallelize only Remotion cache misses with bounded workers

**Files:**
- Modify: `open_edit/render/materialize.py`, `open_edit/render/remotion/renderer.py`
- Test: `tests/test_remotion_ir_materialize.py`, `tests/test_remotion_renderer.py`

**Interfaces:**
- Consumes: pending composition records from Task 3, `MaterializeReport`, and `force_uids`.
- Produces: deterministic timeline injection, bounded subprocess concurrency, and per-composition cache-hit/miss diagnostics.

- [ ] **Step 1: Write failing concurrency and ordering tests.**

```python
def test_materialize_limits_inter_composition_workers(
    project_with_remotion, monkeypatch
):
    active = 0
    maximum = 0
    calls = []

    def fake_render(*args, **kwargs):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        calls.append(kwargs["composition_id"])
        time.sleep(0.03)
        active -= 1
        return fake_render_result(kwargs["output_path"])

    monkeypatch.setenv("OPEN_EDIT_REMOTION_WORKERS", "2")
    monkeypatch.setattr(materialize_module, "render_composition", fake_render)
    updated, report = materialize_with_report(project_with_remotion, count=5)
    assert maximum == 2
    assert report.worker_count == 2
    assert [c.composition_id for c in updated.remotion_compositions] == [
        "Comp0", "Comp1", "Comp2", "Comp3", "Comp4"
    ]
    assert len(calls) == 5


def test_render_failure_cancels_pending_workers_and_reports_uid(
    project_with_remotion, monkeypatch
):
    monkeypatch.setattr(
        materialize_module,
        "render_composition",
        failing_render_for_uid("broken"),
    )
    with pytest.raises(RemotionMaterializeError, match="broken"):
        materialize_with_report(project_with_remotion)
```

- [ ] **Step 2: Run the focused tests to verify they fail.**

Run: `pytest -q tests/test_remotion_ir_materialize.py tests/test_remotion_renderer.py`

Expected: the miss path remains serial and the report/concurrency assertions fail.

- [ ] **Step 3: Precompute and stage work in the caller thread.**

For every composition, validate the entry point, stage referenced assets, resolve the profile/extension, compute `composition_cache_key()`, and classify it as manifest reuse, composition-cache hit, or miss before creating a pool. Never perform timeline mutation from a worker. This also prevents concurrent writes to the same staged `public/` path.

- [ ] **Step 4: Add bounded worker selection.**

Implement:

```python
def remotion_worker_count() -> int:
    requested = int(os.environ.get("OPEN_EDIT_REMOTION_WORKERS", "2"))
    return min(4, max(1, requested))
```

Reject non-numeric or non-positive values by falling back to `2`. The worker pool is `ThreadPoolExecutor(max_workers=remotion_worker_count())`; each worker waits on one Remotion subprocess, so this does not rely on Python CPU parallelism. Keep the existing `OPEN_EDIT_REMOTION_CONCURRENCY` override for each Remotion invocation, but when it is unset derive a per-process value from a total CPU budget instead of allowing every subprocess to claim all cores.

- [ ] **Step 5: Make completion deterministic and failures hard.**

Collect `Future` results keyed by `composition_uid`, then apply `_inject_clip()` in the original timeline order. On the first failure, cancel pending futures, wait for the pool to close, and raise `RemotionMaterializeError` containing the UID and bounded error text. Do not write the successful manifest from a partial batch.

- [ ] **Step 6: Add structured report fields and run tests.**

Populate `MaterializeReport` with `worker_count`, `cache_hits`, `cache_misses`, `reused_manifest_entries`, `rendered_uids`, `dirty_uids`, and elapsed time. Run:

```bash
pytest -q tests/test_remotion_ir_materialize.py tests/test_remotion_renderer.py
```

Expected: PASS, including serial behavior when `OPEN_EDIT_REMOTION_WORKERS=1`.

- [ ] **Step 7: Commit bounded parallel materialization.**

```bash
git add open_edit/render/materialize.py open_edit/render/remotion/renderer.py \
  tests/test_remotion_ir_materialize.py tests/test_remotion_renderer.py
git commit -m "perf: parallelize bounded remotion cache misses"
```

---

### Task 5: Check the whole-file deliverable cache before materialization

**Files:**
- Modify: `open_edit/render/orchestrator.py`, `open_edit/cli.py`, `open_edit/kernel/render_jobs.py`
- Test: `tests/test_render/test_orchestrator.py`, `tests/test_render_jobs.py`

**Interfaces:**
- Consumes: the derived unmaterialized timeline, profile fingerprint, `render_reference_fingerprint()`, `RenderCache`, and Task 3 manifest path.
- Produces: a cache-hit fast path that never calls Remotion materialization, plus separate `force_remotion` and per-UID controls.

- [ ] **Step 1: Write the cache-ordering regression test.**

```python
def test_deliverable_cache_hit_skips_remotion_materialize(
    project_with_remotion, monkeypatch
):
    first = render_with_fake_pipe(project_with_remotion, force=False)
    assert first.ok and not first.cache_hit

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Remotion materialize must not run on MP4 hit")

    monkeypatch.setattr(orchestrator, "materialize_remotion_compositions", fail_if_called)
    second = render_with_fake_pipe(project_with_remotion, force=False)
    assert second.ok
    assert second.cache_hit is True
    assert second.diagnostics["cache"]["hit"] is True
    assert second.diagnostics["stages"]["remotion_materialize"]["status"] == "skipped"
    assert second.diagnostics["stages"]["remotion_materialize"]["reason"] == (
        "deliverable_cache_hit"
    )
```

- [ ] **Step 2: Run the regression test to verify it fails.**

Run: `pytest -q tests/test_render/test_orchestrator.py::test_deliverable_cache_hit_skips_remotion_materialize`

Expected: the second render calls the current materializer before checking the deliverable cache.

- [ ] **Step 3: Reorder `render_project()` without changing the cache key.**

The miss/hit order must become:

```text
load applied ops
→ derive/load unmaterialized timeline
→ resolve profile and alpha mode
→ compute graph hash and content fingerprint
→ compute deliverable cache key
→ RenderCache.get() + is_fresh()
→ return immediately on hit
→ load dirty manifest
→ materialize Remotion
→ build plan/source baseline
→ emit MLT
→ run melt→ffmpeg
→ repair
→ cache.put()
→ write successful materialization manifest
```

The pre-materialization content fingerprint must still hash Remotion source, props, referenced local-file bytes, duration, alpha mode, Remotion version, and repair policy. It is acceptable for the cache-hit path to inspect source content; it must not validate/render/ingest Remotion output unnecessarily.

- [ ] **Step 4: Add separate invalidation controls.**

Add `force_remotion: bool = False` and `remotion_uids: Collection[str] = ()` to `render_project()`. Add CLI `--force-remotion` and pass it through `RenderJobService` job params. `--force` bypasses only the whole-file MP4 cache; `--force-remotion` bypasses direct manifest reuse and composition-cache reuse for all current compositions; per-UID invalidation bypasses those entries only for the named UIDs. A normal cache hit must override neither control because `--force-remotion` still requires a full render to consume the invalidated composition.

- [ ] **Step 5: Run cache and job tests.**

Run:

```bash
pytest -q tests/test_render/test_orchestrator.py tests/test_render_jobs.py
```

Expected: PASS, including existing fake-pipe and durable-job tests. The warm path must show zero Remotion render calls.

- [ ] **Step 6: Commit cache-before-materialize ordering.**

```bash
git add open_edit/render/orchestrator.py open_edit/cli.py \
  open_edit/kernel/render_jobs.py tests/test_render/test_orchestrator.py \
  tests/test_render_jobs.py
git commit -m "perf: skip remotion on deliverable cache hits"
```

---

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

### Task 7: Skip proxy QC on verified hits and add repair early-out

**Files:**
- Create: `open_edit/qc/policy.py`
- Modify: `open_edit/kernel/render_jobs.py`, `open_edit/cli.py`, `open_edit/render/source_repair.py`
- Test: `tests/test_render_jobs.py`, `tests/test_render/test_source_repair.py`

**Interfaces:**
- Consumes: `mode`, `cache_hit`, diagnostics, and the existing `run_qc_gate()`/`repair_render_output()`.
- Produces: a deterministic QC policy, a persisted skipped-QC report, QC stage timing, and no-op repair short-circuiting.

- [ ] **Step 1: Write failing policy tests.**

```python
def test_proxy_cache_hit_skips_qc_by_default(monkeypatch):
    monkeypatch.delenv("OPEN_EDIT_PROXY_QC_POLICY", raising=False)
    assert qc_policy("proxy", cache_hit=True) == "skip"
    assert qc_policy("proxy", cache_hit=False) == "run"


def test_final_cache_hit_still_runs_qc():
    assert qc_policy("final", cache_hit=True) == "run"


def test_proxy_policy_can_force_always_or_never(monkeypatch):
    monkeypatch.setenv("OPEN_EDIT_PROXY_QC_POLICY", "always")
    assert qc_policy("proxy", cache_hit=True) == "run"
    monkeypatch.setenv("OPEN_EDIT_PROXY_QC_POLICY", "never")
    assert qc_policy("proxy", cache_hit=False) == "skip"


@pytest.mark.asyncio
async def test_render_job_persists_skipped_qc_report(tmp_path, monkeypatch):
    service = service_with_fake_successful_launch(
        tmp_path, result={"mode": "proxy", "cache_hit": True}
    )
    called = False

    def fail_if_qc_runs(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("QC must be skipped")

    monkeypatch.setattr("open_edit.qc.gate.run_qc_gate", fail_if_qc_runs)
    job = await wait_for_service(service, tmp_path)
    report = job.qc_report
    assert called is False
    assert report["skipped"] is True
    assert report["reason"] == "deliverable_cache_hit"
    assert job.result["diagnostics"]["stages"]["qc"]["status"] == "skipped"
```

- [ ] **Step 2: Run the focused tests to verify they fail.**

Run: `pytest -q tests/test_render_jobs.py tests/test_render/test_source_repair.py`

Expected: no policy module exists and proxy cache-hit jobs currently invoke the full QC gate.

- [ ] **Step 3: Implement the explicit M1 policy.**

Use these values for `OPEN_EDIT_PROXY_QC_POLICY`: `always`, `skip_on_hit` (default), and `never`. `final` and `overlay` always run QC regardless of the variable. A skipped report is a JSON-compatible diagnostic, not a passing `QCReport` pretending checks ran:

```python
{
    "passed": True,
    "skipped": True,
    "reason": "deliverable_cache_hit",
    "checks": [],
}
```

`RenderJobService._attach_qc()` must copy diagnostics before editing them, time both a real gate and a skip, attach `qc_report` to the result and SQLite row, and keep a QC failure diagnostic-only as today. The CLI’s human-readable non-JSON path uses the same policy and prints `QC: SKIPPED (deliverable cache hit)` when applicable; the JSON path remains a single render-result object for the job service.

- [ ] **Step 4: Add the repair no-op guard.**

In `repair_render_output()`, when `source_baseline` has no black/frozen spans and `repair_intentional_black` is false, return the existing `changed=False` structure before invoking black/frozen detectors. Preserve all existing behavior when a baseline span or intentional-black mode is present. Add a `reason` field such as `no_source_baseline_spans` for diagnostics.

- [ ] **Step 5: Run policy, repair, and existing QC tests.**

Run:

```bash
pytest -q tests/test_render_jobs.py tests/test_render/test_source_repair.py \
  tests/test_qc/test_gate.py tests/test_serve_agent_visual_verify.py
```

Expected: PASS. A final cache hit still has a real QC report; a proxy cache hit has a clearly marked skipped report.

- [ ] **Step 6: Commit QC and repair policy.**

```bash
git add open_edit/qc/policy.py open_edit/kernel/render_jobs.py open_edit/cli.py \
  open_edit/render/source_repair.py tests/test_render_jobs.py \
  tests/test_render/test_source_repair.py
git commit -m "perf: skip proxy qc on verified cache hits"
```

---

### Task 8: Define and prove the host-only Remotion frame-pull protocol

**Files:**
- Create: `open_edit/render/remotion/frame_engine.py`
- Create: `open_edit/render/remotion_frame_server.mjs`
- Modify: `open_edit/render/remotion_scaffold.py`, `package.json`, `package-lock.json`
- Test: `tests/test_remotion_frame_engine.py`, `tests/test_remotion_scaffold.py`

**Interfaces:**
- Consumes: the existing validated Remotion root/entry point and the pinned package versions.
- Produces: an opt-in Python client and a private Node process that returns one requested PNG frame without producing a composition video/CAS artifact.

#### API research required before implementation

The current tree has no programmatic frame engine. `open_edit/render/remotion/renderer.py` shells out to `open_edit/render/remotion_bridge.mjs`, and that bridge invokes the Remotion CLI with an output video path. The root `package.json` already contains `@remotion/renderer`, while the per-project scaffold only declares `@remotion/cli`, `react`, `react-dom`, and `remotion`.

At Remotion `4.0.278`, verify the installed TypeScript declarations and a temporary fixture for these APIs:

```javascript
import {bundle} from "@remotion/bundler";
import {
  selectComposition,
  renderStill,
  renderFrames,
} from "@remotion/renderer";

const serveUrl = await bundle({entryPoint});
const composition = await selectComposition({
  serveUrl,
  id: compositionId,
  inputProps: props,
});
const still = await renderStill({
  composition,
  serveUrl,
  frame,
  inputProps: props,
});
// With no output path, still.buffer must be the PNG/JPEG bytes.
```

Verify that `renderFrames()` accepts a single-frame/range selection and writes an image sequence, and verify the exact `openBrowser()`/browser-instance reuse option before using it. Do not substitute `renderMedia()` for frame pull: it encodes/stitches a whole media output and therefore preserves the rejected bake-then-stitch model. If the pinned declarations do not support the expected `renderStill()` buffer return, fail the API probe with the installed signature and keep the materialized compatibility path; do not invent an undocumented call shape.

- [ ] **Step 1: Write failing protocol tests with a fake frame server.**

```python
def test_frame_client_validates_request_and_reads_exact_png_bytes(tmp_path):
    fake_server = write_fake_frame_server(tmp_path, payload=b"\x89PNGfake")
    client = FramePullClient(
        [sys.executable, str(fake_server)],
        timeout_s=1.0,
    )
    frame = client.request_frame(
        FrameRequest(
            request_id="r1",
            composition_id="TitleCard",
            entry_point="src/index.ts",
            props={"titleText": "Hi"},
            frame=12,
            width=640,
            height=360,
            fps=30.0,
            alpha=False,
        )
    )
    assert frame.content_type == "image/png"
    assert frame.bytes == b"\x89PNGfake"
    client.close()


def test_frame_client_rejects_oversized_or_out_of_range_request():
    with pytest.raises(FrameProtocolError, match="frame"):
        FrameRequest(
            request_id="r",
            composition_id="Comp",
            entry_point="../escape.tsx",
            props={},
            frame=-2,
            width=640,
            height=360,
            fps=30.0,
            alpha=False,
        )
```

- [ ] **Step 2: Run the protocol tests to verify they fail.**

Run: `pytest -q tests/test_remotion_frame_engine.py`

Expected: missing `FramePullClient`, request validation, and server lifecycle failures.

- [ ] **Step 3: Implement a bounded stdin/stdout protocol.**

Use one private process per render job, no TCP listener and no network exposure:

```text
client → server: one JSON line per request
server → client: one JSON header line
server → client: exactly byte_length binary bytes
```

The response header contains `request_id`, `ok`, `content_type`, `byte_length`, `width`, `height`, `frame`, and `remotion_version`; errors contain a bounded `error` string and no props. The Python client must validate entry-point relativity, positive dimensions/fps, non-negative frame, maximum props JSON bytes, maximum response bytes, matching request ID, content type, and exact payload length. It must terminate the process on timeout, malformed framing, EOF, or a nonzero exit.

- [ ] **Step 4: Implement the Node renderer using the verified APIs.**

`remotion_frame_server.mjs` must:

1. Resolve and validate the project root and entry point under `.open_edit/remotion/`.
2. Bundle once per entry point with `@remotion/bundler`.
3. Cache selected composition metadata by `(composition_id, props hash, width, height, fps)`.
4. Call `renderStill()` for the requested frame with `output` omitted and return its buffer.
5. Use PNG for alpha frames; do not transcode through a lossy format.
6. Enforce request dimensions, frame bounds from `durationInFrames`, and a per-request timeout.
7. Exit cleanly when stdin closes or the parent is terminated.

Use `openBrowser()` reuse only if the pinned type signature confirms how to pass the browser to `renderStill()`; otherwise use the verified renderer lifecycle and record the slower path in diagnostics. The process runs only in the host worker; free-form code cannot start it.

- [ ] **Step 5: Add the package/scaffold declarations.**

Add `@remotion/bundler: "4.0.278"` and `@remotion/renderer: "4.0.278"` to the generated project scaffold. Keep the root renderer pin and regenerate the lockfile with:

```bash
npm install --package-lock-only
```

Do not install dependencies into a user project from a free-form operation. The scaffold remains private and preserves the existing Remotion license notice.

- [ ] **Step 6: Add an opt-in engine selector without changing the default.**

Define `OPEN_EDIT_REMOTION_FRAME_ENGINE=materialize|pull`, defaulting to `materialize`. During M1, `pull` is available to the protocol/integration tests only; a normal proxy/final render continues through materialization unless the explicit same-pass feeder in Task 9 is enabled. An explicit unsupported pull request returns a structured `remotion_frame_pull_unavailable` error rather than silently reverting.

- [ ] **Step 7: Run protocol, scaffold, and JavaScript syntax tests.**

Run:

```bash
pytest -q tests/test_remotion_frame_engine.py tests/test_remotion_scaffold.py
node --check open_edit/render/remotion_frame_server.mjs
npm ls @remotion/bundler @remotion/renderer remotion
```

Expected: PASS with all three Remotion packages resolving to `4.0.278`. If Node/Remotion is unavailable, the Python protocol tests still run with the fake server and the API probe reports the missing host dependency explicitly.

- [ ] **Step 8: Commit the frame protocol, not a bake replacement.**

```bash
git add open_edit/render/remotion/frame_engine.py \
  open_edit/render/remotion_frame_server.mjs \
  open_edit/render/remotion_scaffold.py package.json package-lock.json \
  tests/test_remotion_frame_engine.py tests/test_remotion_scaffold.py
git commit -m "feat: add host remotion frame pull protocol"
```

---

### Task 9: Add the incremental same-pass ffmpeg frame feeder behind a feature gate

**Files:**
- Create: `open_edit/render/remotion/frame_feeder.py`
- Modify: `open_edit/render/pipe_builder.py`, `open_edit/render/melt_runner.py`, `open_edit/render/timeline_plan.py`, `open_edit/render/orchestrator.py`
- Test: `tests/test_remotion_frame_engine.py`, `tests/test_render/test_pipe_builder.py`, `tests/test_render/test_run_pipe.py`

**Interfaces:**
- Consumes: `FramePullClient` from Task 8, `OverlayClip`, the base melt rawvideo pipe, and a list of frame-overlay specifications.
- Produces: an opt-in ffmpeg overlay input that requests frames in PTS order and writes them directly to ffmpeg without a persistent Remotion MP4/MOV/WebM artifact.

- [ ] **Step 1: Write failing command and feeder tests.**

```python
def test_pull_overlay_adds_nonseekable_image_pipe_without_changing_melt_pipe(tmp_path):
    commands = build_pipe_commands(
        "melt",
        tmp_path / "timeline.mlt",
        tmp_path / "out.mp4",
        profile=proxy_profile(),
        spec=cpu_encoder(),
        overlays=[frame_overlay(position_sec=2.0, duration_sec=1.0)],
        frame_engine="pull",
        workdir=tmp_path,
    )
    assert "f=rawvideo" in commands.melt_video_cmd
    assert "pipe:3" in commands.ffmpeg_cmd
    assert "-f" in commands.ffmpeg_cmd
    assert "image2pipe" in commands.ffmpeg_cmd
    assert ".open_edit/remotion/out/cache" not in " ".join(commands.ffmpeg_cmd)


def test_frame_feeder_requests_monotonic_source_frames(monkeypatch):
    requests = []
    client = fake_client(record=requests)
    feeder = FrameFeeder(client, frame_overlay(position_sec=2.0, duration_sec=1.0))
    feeder.write_frames(output=io.BytesIO(), output_fps=30.0)
    assert [request.frame for request in requests] == list(range(30))
    assert all(request.frame >= 0 for request in requests)
```

- [ ] **Step 2: Run the focused tests to verify they fail.**

Run:

```bash
pytest -q tests/test_remotion_frame_engine.py tests/test_render/test_pipe_builder.py \
  tests/test_render/test_run_pipe.py
```

Expected: `build_pipe_commands()` has no frame-source input and `run_pipe()` cannot manage additional file descriptors/feeders.

- [ ] **Step 3: Define the frame-overlay input shape.**

Add a `FrameOverlaySpec` that carries:

```text
composition_uid, composition_id, entry_point, props,
position_sec, duration_sec, width, height, fps, alpha
```

Normalize file overlays and frame overlays into one filter metadata list so `overlay_filter_chain()` retains the same `setpts`, `enable=between(t,...)`, scale, and alpha rules. The input index must be deterministic: base video `0`, audio `1`, then overlays in timeline order. Do not let the frame engine alter the base melt command.

- [ ] **Step 4: Add a backpressured ffmpeg image pipe.**

For each frame overlay, add an explicit non-seekable input:

```text
-thread_queue_size 8
-f image2pipe
-vcodec png
-framerate <composition fps>
-i pipe:<allocated fd>
```

`run_pipe()` allocates the descriptors, starts the frame feeder after ffmpeg is ready, and closes/terminates all feeders when ffmpeg exits, melt fails, timeout occurs, or the frame server reports an error. The feeder requests frames monotonically from `0` through `ceil(duration_sec * fps)-1`; ffmpeg’s filter applies the timeline offset. A feeder must not pre-render the full composition or write its frames to CAS.

On Linux, use inherited descriptors with `pass_fds`. On Windows, keep `frame_engine=pull` disabled until a named-pipe implementation has equivalent lifecycle tests; the default materializer remains the cross-platform path. A pull failure is a render failure unless the caller explicitly sets `OPEN_EDIT_FRAME_PULL_FALLBACK=materialize`.

- [ ] **Step 5: Wire the feature gate and diagnostics.**

The orchestrator uses frame pull only when all of these are true:

```text
OPEN_EDIT_REMOTION_FRAME_ENGINE == "pull"
mode == "proxy" unless OPEN_EDIT_ALLOW_EXPERIMENTAL_FRAME_PULL=1
host protocol/API probe passed
platform feeder support passed
```

Otherwise it uses the Task 4 materializer. Record `remotion_frame_pull` with `requested`, `enabled`, `frames_requested`, `elapsed_sec`, `fallback`, and bounded error fields. The default remains `materialize`; final export does not silently switch engines.

- [ ] **Step 6: Run protocol/pipe parity tests.**

Run:

```bash
pytest -q tests/test_remotion_frame_engine.py tests/test_render/test_pipe_builder.py \
  tests/test_render/test_run_pipe.py
```

When ffmpeg is available, render a tiny base clip with a deterministic fake frame server through both paths and compare selected output-frame hashes, alpha blending, frame count, and PTS. The pull output must not create a composition artifact in `remotion/out/cache`; the materialize path must continue to create the expected `.mp4`, `.webm`, or `.mov`.

- [ ] **Step 7: Commit only after parity and lifecycle tests pass.**

```bash
git add open_edit/render/remotion/frame_feeder.py \
  open_edit/render/pipe_builder.py open_edit/render/melt_runner.py \
  open_edit/render/timeline_plan.py open_edit/render/orchestrator.py \
  tests/test_remotion_frame_engine.py tests/test_render/test_pipe_builder.py \
  tests/test_render/test_run_pipe.py
git commit -m "feat: gate same-pass remotion frame overlays"
```

---

### Task 10: Run the M0/M1 verification matrix and performance gate

**Files:**
- Modify only files from Tasks 1–9 when verification exposes a defect.
- Test: all affected Python tests, existing golden/e2e render tests, and Phase 1 benchmark outputs under `docs/superpowers/specs/phase1-raw/` or a separately named benchmark directory.

**Interfaces:**
- Consumes: all Task 1–9 outputs and the approved Phase 1 fixtures/measurement harness.
- Produces: evidence for M0/M1 acceptance, a documented hardware/concurrency limit when necessary, and no unreviewed behavior change.

- [ ] **Step 1: Run the focused regression matrix.**

Run:

```bash
pytest -q \
  tests/test_render/test_diagnostics.py \
  tests/test_render/test_cache.py \
  tests/test_render/test_orchestrator.py \
  tests/test_render/test_source_repair.py \
  tests/test_render/test_timeline_plan.py \
  tests/test_render/test_pipe_builder.py \
  tests/test_render/test_run_pipe.py \
  tests/test_remotion_renderer.py \
  tests/test_remotion_ir_materialize.py \
  tests/test_remotion_frame_engine.py \
  tests/test_render_jobs.py \
  tests/test_qc/test_gate.py \
  tests/test_review_ui.py
```

Expected: PASS with no sandbox test changes and with the existing `f=rawvideo` assertions intact.

- [ ] **Step 2: Run the broader render and sandbox regressions.**

Run:

```bash
pytest -q tests/test_e2e_render.py tests/test_remotion_proxy_golden.py \
  tests/test_phase567_edit_render.py tests/test_sandbox/test_render_sandbox.py \
  tests/test_serve_render_jobs.py
```

Expected: PASS or explicit environment skips only for missing melt/ffmpeg/Chromium. No test may authorize GPU or Remotion inside the free-form sandbox.

- [ ] **Step 3: Re-benchmark cold proxy, warm proxy, and alpha cases.**

Use the existing Phase 1 harness against restored fixtures:

```bash
python docs/superpowers/scripts/phase1_run_bench.py C \
  --mode proxy --force --label C_proxy_m1_parallel \
  --out /tmp/C_proxy_m1_parallel.json
python docs/superpowers/scripts/phase1_run_bench.py C \
  --mode proxy --label C_proxy_m1_warm \
  --out /tmp/C_proxy_m1_warm.json
python docs/superpowers/scripts/phase1_run_bench.py B \
  --mode proxy --force --label B_proxy_m1_alpha \
  --out /tmp/B_proxy_m1_alpha.json
```

Compare `stage_breakdown_sec.remotion_materialize`, `cache_hit_render`, `remotion.composition_cache_hits`, `qc`, `project_bytes.remotion_out`, and worker/concurrency diagnostics against the Phase 1 raw JSON. The target is C proxy cold Remotion wall at or below roughly 50% of the measured 93.7s under parallel×2 or better; if the host cannot meet it, record the observed CPU/RAM/Chromium limit rather than making an unsupported performance claim. Warm proxy wall must be far below the old 5.0–15.4s QC-dominated range when the MP4 cache hits and proxy QC is skipped.

- [ ] **Step 4: Verify cache and disk safety.**

Run the cache-cap tests with a tiny cap, inspect that old entries and metadata are removed, and verify source CAS files remain:

```bash
OPEN_EDIT_REMOTION_CACHE_MAX_BYTES=1024 \
  pytest -q tests/test_render/test_cache.py tests/test_remotion_ir_materialize.py
```

Inspect benchmark `project_bytes.remotion_out` and confirm it does not grow without bound after repeated profile/content changes. Confirm ProRes alpha is used only when VP8/VP9 capability is not proven and that opaque cards do not request RGBA.

- [ ] **Step 5: Verify naming and API research evidence.**

Run:

```bash
rg -n "Proxy 720p|540p|mode=proxy|source proxy|timeline preview chunk|Review artifact" \
  open_edit/serve docs/MCP.md
node --check open_edit/render/remotion_frame_server.mjs
npm ls @remotion/bundler @remotion/renderer remotion
```

Expected: the three product systems are distinguishable, the actual 640×360 proxy profile is documented, and the installed Remotion versions are all `4.0.278`.

- [ ] **Step 6: Record the final M0/M1 acceptance evidence.**

The handoff must include:

```text
A1 vocabulary/schema: diagnostics + UI/docs tests
A2 cache gate: materializer call-count test + warm benchmark
A3 dirty/parallel Remotion: selection test + worker/concurrency benchmark
A4 content-aware cache: external-file invalidation + tamper/LRU tests
A5 alpha policy: capability probe + transparent/opaque pipe tests
A6 QC: proxy-hit skip and final-hit run policy tests
A7 repair: no-baseline early-out + existing repair regressions
A8 frame engine: protocol/API probe + fake-server parity
A9 same-pass feeder: gated ffmpeg pipe/lifecycle/alpha tests
A10 constraints: rawvideo and sandbox regression tests
```

- [ ] **Step 7: Make the verification checkpoint commit only after review.**

```bash
git status --short
git diff --check
git log -5 --oneline
```

If fixes were required, create a new focused commit with the relevant test evidence. Do not amend a prior commit unless the repository’s commit protocol explicitly permits it and the user requests that integration step.

## Commit checkpoints

Keep the work reviewable at these gates:

1. `feat: define render diagnostics contract` — Task 1, before behavior changes.
2. `feat: instrument render stages and clarify artifact names` — Task 2, M0 complete.
3. `feat: track dirty remotion materialization zones` — Task 3.
4. `perf: parallelize bounded remotion cache misses` — Task 4.
5. `perf: skip remotion on deliverable cache hits` — Task 5.
6. `perf: bound render caches and preserve remotion alpha` — Task 6.
7. `perf: skip proxy qc on verified cache hits` — Task 7.
8. `feat: add host remotion frame pull protocol` — Task 8, API-proven but still materialize-default.
9. `feat: gate same-pass remotion frame overlays` — Task 9, only after frame parity/lifecycle evidence.
10. A final verification-only commit is unnecessary unless Task 10 fixes a tested defect.

## Acceptance criteria

- M0 is non-breaking: existing render outputs, cache keys, pipe commands, and sandbox boundaries remain valid; diagnostics gain canonical names and UI/docs stop conflating review artifacts, source proxies, and chunks.
- A whole-file `RenderCache` hit is checked before Remotion materialization and returns with `remotion_materialize=skipped`.
- A graph/content edit selects only affected composition UIDs/ranges for re-rendering; unchanged composition CAS assets are reused from the successful manifest.
- Remotion misses run with a bounded worker count, deterministic injection order, hard failure on any composition error, and no worker-side mutation of shared timeline state.
- Content changes in Remotion source, props-referenced files, alpha policy, duration, profile, Remotion version, or repair policy cannot reuse an old deliverable/composition artifact.
- Cache growth is capped and evictable; ProRes alpha does not become an unbounded disk sink.
- `composition.alpha=False` does not add `format=rgba`; transparent compositions retain the existing alpha correctness tests.
- Proxy cache hits skip QC by explicit policy; proxy misses and all final exports retain available QC; skipped reports are distinguishable from real reports.
- Repair exits before detector/encode work when there are no source spans to repair and no intentional-black request.
- The frame server uses verified pinned Remotion APIs, returns exact requested frames, stays host-only, and produces no whole-composition media file.
- The opt-in same-pass feeder supplies frames directly to ffmpeg overlay inputs, preserves the melt rawvideo base pipe, handles timeout/EOF/child cleanup, and has output-frame/alpha parity with materialization before being enabled for normal renders.

## Open questions and risks

1. **Remotion renderer signature drift:** `renderStill()` buffer output and browser reuse must be verified against the installed `4.0.278` declarations. The implementation must report the exact probe failure and remain materialize-default if the API differs.
2. **Chromium lifecycle cost:** A persistent frame server may reduce launch overhead but can retain browser memory. Measure browser reuse and set a per-job timeout/termination policy before increasing parallelism.
3. **Parallel memory pressure:** ProRes 4444 and multiple Chromium workers can exhaust RAM or thrash disk. The default worker cap is 2, hard maximum 4; benchmark evidence can lower the default.
4. **Cross-platform descriptor plumbing:** Linux `pass_fds` is straightforward; Windows named-pipe support needs a separate lifecycle implementation. Pull must remain opt-in/materialize-fallback until both paths are safe.
5. **Multiple render processes:** The project lock serializes normal jobs, but direct CLI invocations can race. Manifest writes must be atomic and mode/profile-specific; a file lock is required if concurrent direct renders can be supported.
6. **Frame-pull ffmpeg scheduling:** A non-seekable overlay input relies on ffmpeg consuming frames in order. If ffmpeg requests frames out of order during filter negotiation, the feeder must reject the request and the feature gate must fall back or fail explicitly rather than producing a shifted overlay.
7. **Alpha codec acceptance:** VP8/WebM may be faster and smaller, but the host probe and visual parity test—not a codec label—decide whether it is acceptable. ProRes remains the correctness fallback.
8. **QC policy visibility:** Skipping QC improves warm proxy latency but reduces automatic evidence on cache hits. The persisted `skipped` reason and `always` override must remain visible to agents and operators.
9. **Long-form validation:** The 180s/12-composition Phase 1 fixture is not the missing timeline-test workload. Do not extrapolate a universal 2× claim without rerunning the restored long-form project.
10. **Remotion licensing:** Adding programmatic renderer/bundler use does not remove the existing Remotion license requirement; retain scaffold notices and document deployment/licensing review before shipping.

## Handoff to the orchestrator

- Plan path: `docs/superpowers/plans/2026-08-03-remotion-in-pipeline-engine.md`
- Task count: 10
- First execution gate: Tasks 1–2 (M0) only after plan approval.
- M1 execution order: Tasks 3–7, then Task 8 protocol proof, then Task 9 gated feeder.
- Product-code constraint: this planning pass creates only this plan file; no `open_edit/` implementation is included.
