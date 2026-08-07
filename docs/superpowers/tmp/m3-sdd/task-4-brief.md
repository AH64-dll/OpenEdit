# Task 4 Brief

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
