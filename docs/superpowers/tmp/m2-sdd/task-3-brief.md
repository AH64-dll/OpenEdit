# Task 3 Brief

### Task 3: Add explicit emission switches and enforce originals for final

**Files:**
- Modify: `open_edit/render/timeline_plan.py`
- Modify: `open_edit/render/orchestrator.py`
- Create: `tests/test_render/test_timeline_plan.py`
- Test: `tests/test_render/test_orchestrator.py`
- Test: `tests/test_render/test_emitter.py`

**Interfaces:**

- Consumes: `Asset.proxy_hash` and `Asset.proxy_status`, the Task 2 job service,
  and the existing logical-hash-to-path `asset_paths` map.
- Produces:

```python
EmissionProfile = Literal[
    "final", "review-artifact", "proxy-edit", "preview-chunk",
]
SourceMediaPolicy = Literal["original", "proxy"]


def source_media_policy_for(
    emission_profile: EmissionProfile,
) -> SourceMediaPolicy:
    """Map an explicit emission profile to source or derived media."""


class RenderPlan(BaseModel):
    melt_timeline: Timeline
    overlay_clips: list[OverlayClip]
    asset_paths: dict[str, str]
    emission_profile: EmissionProfile
    source_media_policy: SourceMediaPolicy
    source_proxy_hits: dict[str, str] = Field(default_factory=dict)
    source_proxy_fallbacks: dict[str, str] = Field(default_factory=dict)


def build_render_plan(
    timeline: Timeline,
    ops: list[Operation],
    store: AssetStore,
    mode: str,
    *,
    emission_profile: EmissionProfile | None = None,
    enqueue_missing_proxies: bool = True,
) -> RenderPlan:
    """Build a render plan with explicit source-media semantics."""
```

The policy mapping is intentionally explicit:

```python
{
    "final": "original",
    "review-artifact": "original",
    "proxy-edit": "proxy",
    "preview-chunk": "proxy",
}
```

Thus `mode="proxy"` defaults to `review-artifact` and remains a whole-file
review render. It does not become a source-proxy render merely because both
names contain “proxy”. M3’s future chunk worker will pass
`emission_profile="preview-chunk"`; a future proxy-edit worker will pass
`"proxy-edit"`.

- [ ] **Step 1: Write failing planner and final-safety tests.**

Add the following cases:

```python
def test_preview_chunk_uses_ready_source_proxy(tmp_path: Path) -> None:
    store, asset, proxy_path = seed_asset_with_ready_proxy(tmp_path)
    timeline, ops = timeline_for_asset(asset.asset_hash)

    plan = build_render_plan(
        timeline, ops, store, "proxy",
        emission_profile="preview-chunk",
        enqueue_missing_proxies=False,
    )

    assert plan.source_media_policy == "proxy"
    assert plan.source_proxy_hits[asset.asset_hash] == asset.proxy_hash
    assert plan.asset_paths[asset.asset_hash] == str(proxy_path)


def test_final_plan_uses_original_even_when_proxy_is_ready(tmp_path: Path) -> None:
    store, asset, proxy_path = seed_asset_with_ready_proxy(tmp_path)
    timeline, ops = timeline_for_asset(asset.asset_hash)

    plan = build_render_plan(
        timeline, ops, store, "final",
        emission_profile="final",
        enqueue_missing_proxies=False,
    )

    assert plan.source_media_policy == "original"
    assert plan.asset_paths[asset.asset_hash] == asset.stored_path
    assert str(proxy_path) not in plan.asset_paths.values()


def test_review_artifact_does_not_change_to_source_proxy_semantics(tmp_path: Path) -> None:
    store, asset, _ = seed_asset_with_ready_proxy(tmp_path)
    timeline, ops = timeline_for_asset(asset.asset_hash)

    plan = build_render_plan(
        timeline, ops, store, "proxy",
        emission_profile="review-artifact",
        enqueue_missing_proxies=False,
    )

    assert plan.source_media_policy == "original"
    assert plan.asset_paths[asset.asset_hash] == asset.stored_path


def test_missing_preview_proxy_falls_back_and_queues_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, asset = seed_asset_without_proxy(tmp_path)
    timeline, ops = timeline_for_asset(asset.asset_hash)
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "open_edit.kernel.asset_proxy_jobs.DEFAULT_ASSET_PROXY_JOB_SERVICE.enqueue",
        lambda project_id, project_path, asset_hash, profile: (
            calls.append((asset_hash, profile.name))
            or object()
        ),
    )

    plan = build_render_plan(
        timeline, ops, store, "proxy",
        emission_profile="proxy-edit",
        enqueue_missing_proxies=True,
    )

    assert plan.source_proxy_fallbacks[asset.asset_hash] == "queued"
    assert plan.asset_paths[asset.asset_hash] == asset.stored_path
    assert calls == [(asset.asset_hash, "source_proxy_360_v1")]


def test_final_render_rejects_non_final_emission_profile(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="final emission"):
        render_project(
            "project", tmp_path, tmp_path / "renders",
            mode="final", emission_profile="preview-chunk",
        )
```

Add an emitter assertion that a final plan’s XML contains the canonical
`stored_path`, not the proxy path, for the logical asset hash.

- [ ] **Step 2: Run planner tests and verify the old mode-only planner fails.**

```bash
/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest \
  tests/test_render/test_timeline_plan.py \
  tests/test_render/test_orchestrator.py \
  tests/test_render/test_emitter.py \
  -o addopts="" -q
```

Expected: FAIL because `RenderPlan` has no emission fields and
`resolve_asset_paths()` always returns the original CAS path.

- [ ] **Step 3: Implement the explicit source-media resolver.**

Keep `asset_paths` keyed by the logical canonical `asset_hash`; only the
value changes to the physical proxy path. For each referenced asset:

1. `source_media_policy="original"` returns `AssetStore.path(asset_hash)`.
2. `source_media_policy="proxy"` selects a proxy only when
   `proxy_status == "ready"`, `proxy_profile == "source_proxy_360_v1"`,
   `proxy_hash` is present, and `AssetStore.path(proxy_hash)` exists.
3. A missing/stale proxy records a fallback reason, optionally enqueues one
   Task 2 job, and returns the canonical source path for the current render.
4. Materialized Remotion assets are not source-proxied: they have no
   `proxy_hash` and continue to use the profile-specific materialized CAS
   clip generated by `materialize_remotion_compositions()`.
5. A final plan raises before emission if its policy is not `original`.

Add `emission_profile` as an optional keyword to `render_project()`. Infer
`final` for `mode="final"` and `review-artifact` for `mode="proxy"` when the
caller omits it. Include `source_media_policy`, hit/fallback maps, and the
requested profile fingerprint in `RenderResult.diagnostics`.

For a non-default proxy-edit render, include the source-proxy profile
fingerprint in the cache content fingerprint so a proxy-backed output cannot
collide with an original-backed output. Keep current `mode=proxy` and
`mode=final` cache keys stable when their default profiles are used.

- [ ] **Step 4: Run the planner, emitter, orchestrator, and pre-existing render tests.**

```bash
/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest \
  tests/test_render/test_timeline_plan.py \
  tests/test_render/test_orchestrator.py \
  tests/test_render/test_emitter.py \
  tests/test_render/ \
  -o addopts="" -q
```

Expected: PASS, including the existing profile-scoped cache and hwaccel retry
tests.

- [ ] **Step 5: Commit the source-media emission contract.**

```bash
git add open_edit/render/timeline_plan.py open_edit/render/orchestrator.py \
  tests/test_render/test_timeline_plan.py tests/test_render/test_orchestrator.py \
  tests/test_render/test_emitter.py
git commit -m "feat(render): add explicit source-media emission profiles"
```

---
