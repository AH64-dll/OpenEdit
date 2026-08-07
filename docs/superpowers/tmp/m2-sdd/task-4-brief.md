# Task 4 Brief

### Task 4: Add cache-aware QC policy and duration-budgeted detectors

**Files:**
- Create: `open_edit/qc/policy.py`
- Modify: `open_edit/qc/gate.py`
- Modify: `open_edit/qc/black_frames.py`
- Modify: `open_edit/qc/frozen_frames.py`
- Modify: `open_edit/qc/silence.py`
- Modify: `open_edit/kernel/render_jobs.py`
- Modify: `open_edit/cli.py`
- Create: `tests/test_qc/test_policy.py`
- Test: `tests/test_qc/test_gate.py`
- Test: `tests/test_qc/test_black_frames.py`
- Test: `tests/test_render_jobs.py`

**Interfaces:**

- Consumes: `RenderResult.cache_hit`, render mode, current `QCReport`, and
  ffprobe’s container duration.
- Produces:

```python
QCMode = Literal["skip", "light", "full"]


@dataclass(frozen=True)
class QCPolicy:
    mode: QCMode
    total_budget_sec: float | None
    blackdetect_max_sec: float

    def blackdetect_timeout(self, duration_sec: float | None) -> float:
        if duration_sec is None or duration_sec <= 0:
            return min(60.0, self.blackdetect_max_sec)
        return max(
            60.0,
            min(self.blackdetect_max_sec, duration_sec * 0.75),
        )


def resolve_qc_policy(
    render_mode: str | None,
    *,
    cache_hit: bool,
) -> QCPolicy:
    """Resolve proxy warm/cold and final policy from mode plus environment."""


def skipped_qc_report(
    video_path: str,
    *,
    policy: QCPolicy,
    reason: str,
) -> QCReport:
    """Return a stable, explicit report without decoding the whole video."""
```

Policy defaults:

- Cold `proxy`: `OPEN_EDIT_PROXY_QC_MODE=light` (core file/stream/duration/
  audio-sync checks; black, frozen, silence, and thumbnail are marked skipped).
- Warm `proxy` cache hit: `OPEN_EDIT_PROXY_WARM_QC_MODE=skip` (no expensive
  decode; the report explicitly says it was skipped because the deliverable
  cache was hit). `light` remains an allowed operator override.
- `final`: always `full`, with `OPEN_EDIT_FINAL_QC_BUDGET_SEC=900` and
  `OPEN_EDIT_QC_BLACKDETECT_MAX_SEC=900` defaults.
- `overlay`: `full` unless an existing caller explicitly requests another
  policy.

The report remains diagnostic and never changes a successful render job to
`failed`. A final detector timeout is represented as
`passed=False`, `skipped=True`, and `complete=False` so delivery tooling cannot
mistake an incomplete final QC run for a clean delivery. A proxy light/skip
report uses `passed=True` for deliberately skipped checks but also sets
`complete=False` and includes `policy`/`reason`.

- [ ] **Step 1: Write failing policy and timeout tests.**

Add:

```python
def test_proxy_warm_cache_hit_defaults_to_skip(monkeypatch) -> None:
    monkeypatch.delenv("OPEN_EDIT_PROXY_WARM_QC_MODE", raising=False)
    policy = resolve_qc_policy("proxy", cache_hit=True)
    assert policy.mode == "skip"


def test_proxy_cold_defaults_to_light(monkeypatch) -> None:
    monkeypatch.delenv("OPEN_EDIT_PROXY_QC_MODE", raising=False)
    policy = resolve_qc_policy("proxy", cache_hit=False)
    assert policy.mode == "light"


def test_final_policy_is_full_and_duration_budgeted() -> None:
    policy = resolve_qc_policy("final", cache_hit=True)
    assert policy.mode == "full"
    assert policy.blackdetect_timeout(180.0) == pytest.approx(135.0)
    assert policy.blackdetect_timeout(3600.0) == 900.0


def test_light_policy_does_not_call_expensive_detectors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = write_valid_test_video(tmp_path / "out.mp4")
    monkeypatch.setattr(gate_mod, "list_black_frames", fail_if_called)
    monkeypatch.setattr(gate_mod, "list_frozen_frames", fail_if_called)
    monkeypatch.setattr(gate_mod, "list_silence", fail_if_called)

    report = run_qc_gate(
        str(output), tmp_path / "thumbs",
        target_duration_s=2.0,
        mode="proxy",
        policy=QCPolicy("light", None, 900.0),
    )

    assert report.policy == "light"
    assert report.complete is False
    assert all(
        check.skipped
        for check in report.checks
        if check.name in {"black_frames", "frozen_frames", "silence", "thumbnail"}
    )


def test_blackdetect_timeout_becomes_structured_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"not decoded")
    monkeypatch.setattr(black_frames_mod.shutil, "which", lambda _: "ffmpeg")
    monkeypatch.setattr(
        black_frames_mod.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired(kwargs["timeout"], kwargs["timeout"])
        ),
    )

    result = list_black_frames(str(source), timeout_s=7.0)

    assert result.ok is False
    assert "timed out" in (result.error or "")
```

Add a `RenderJobService` test that patches `run_qc_gate`, returns a
`RenderResult` with `mode="proxy"` and `cache_hit=True`, and asserts the
service passes `QCMode.skip` rather than full. Add a final-mode test asserting
`QCMode.full` is passed even when `cache_hit=True`.

- [ ] **Step 2: Run QC/job tests and verify policy plumbing fails.**

```bash
/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest \
  tests/test_qc/test_policy.py tests/test_qc/test_gate.py \
  tests/test_qc/test_black_frames.py tests/test_render_jobs.py \
  -o addopts="" -q
```

Expected: FAIL because the policy model, skipped fields, and detector timeout
arguments do not exist.

- [ ] **Step 3: Implement the policy without changing default full QC.**

Add `skipped: bool = False` to `QCCheck`, and add `policy: QCMode = "full"`,
`complete: bool = True`, `elapsed_sec: float = 0.0`, and `reason: str = ""`
to `QCReport`. Extend `run_qc_gate()` with
`policy: QCPolicy | QCMode | None = None`; normalize a string to a
`QCPolicy`, but keep `None` equivalent to full.

For light/skip reports, emit the same named checks as the full report so UI
consumers do not need a second schema. Mark skipped checks with
`skipped=True` and a detail such as
`"skipped by policy=light; render completed successfully"`.

In `RenderJobService._attach_qc()`:

```python
policy = resolve_qc_policy(
    out.get("mode"),
    cache_hit=bool(out.get("cache_hit", False)),
)
out["qc_policy"] = policy.mode
qc = await asyncio.to_thread(
    run_qc_gate,
    output_path,
    project_path / "thumbs",
    target_duration_s=float(target) if target is not None else None,
    mode=out.get("mode"),
    source_baseline=(result.get("diagnostics") or {}).get("source_baseline"),
    policy=policy,
)
```

Do not call the expensive detectors at all for `skip` or `light`. The CLI’s
human-readable path must use the same resolver after a successful non-JSON
render; the JSON path remains render-result-only because the server attaches
QC after consuming JSON.

- [ ] **Step 4: Fix blackdetect and other detector timeouts.**

Change `list_black_frames()` to accept `timeout_s: float | None = None`,
defaulting to 60 seconds for direct callers, and catch
`subprocess.TimeoutExpired`. Pass the duration-aware value from `run_qc_gate()`:

```python
black_timeout = policy.blackdetect_timeout(duration_sec)
bf_result = list_black_frames(video_path, timeout_s=black_timeout)
```

Add optional `timeout_s` parameters to `list_frozen_frames()` and
`list_silence()` and pass the remaining final-QC budget to each expensive
detector. Every timeout returns a structured result and allows the gate to
finish the other checks. The existing scale-height optimization remains in
place; do not remove it in favor of a larger timeout.

- [ ] **Step 5: Run all QC and render-job tests.**

```bash
/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest \
  tests/test_qc/ tests/test_render_jobs.py tests/test_serve_render_jobs.py \
  tests/test_cli.py \
  -o addopts="" -q
```

Expected: PASS. Existing default `run_qc_gate()` tests must still report ten
checks and retain their current check names.

- [ ] **Step 6: Commit cache-aware QC policy.**

```bash
git add open_edit/qc/policy.py open_edit/qc/gate.py \
  open_edit/qc/black_frames.py open_edit/qc/frozen_frames.py \
  open_edit/qc/silence.py open_edit/kernel/render_jobs.py open_edit/cli.py \
  tests/test_qc/test_policy.py tests/test_qc/test_gate.py \
  tests/test_qc/test_black_frames.py tests/test_render_jobs.py
git commit -m "feat(qc): add cache-aware policies and duration budgets"
```

---
