# Task 3 Brief

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
