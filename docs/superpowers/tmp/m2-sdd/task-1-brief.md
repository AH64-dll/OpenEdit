# Task 1 Brief

### Task 1: Add source-proxy metadata, profile, and CAS generation

**Files:**
- Create: `open_edit/render/source_proxy.py`
- Modify: `open_edit/ir/types.py:103-126` (`Asset`)
- Modify: `open_edit/storage/assets.py:110-248` (`AssetStore`)
- Test: `tests/test_render/test_source_proxy.py`
- Test: `tests/test_storage/test_assets.py`
- Test: `tests/test_ir/test_types.py`

**Interfaces:**

- Consumes: canonical `AssetStore.path(asset_hash)`, `AssetStore.get(asset_hash)`, ffprobe metadata, and a host `ffmpeg` executable.
- Produces:

```python
SourceProxyStatus = Literal[
    "none", "queued", "running", "ready", "failed", "not_needed",
]


@dataclass(frozen=True)
class SourceProxyProfile:
    name: str
    height: int
    vcodec: str
    crf: int
    preset: str
    acodec: str
    audio_bitrate: str
    version: int

    def fingerprint(self) -> str:
        return (
            f"{self.name}:v{self.version}:h{self.height}:"
            f"{self.vcodec}:crf={self.crf}:preset={self.preset}:"
            f"{self.acodec}:{self.audio_bitrate}"
        )


DEFAULT_SOURCE_PROXY_PROFILE = SourceProxyProfile(
    name="source_proxy_360_v1",
    height=360,
    vcodec="libx264",
    crf=28,
    preset="veryfast",
    acodec="aac",
    audio_bitrate="96k",
    version=1,
)


@dataclass(frozen=True)
class SourceProxyResult:
    asset_hash: str
    proxy_hash: str | None
    profile: str
    status: SourceProxyStatus
    output_path: str | None
    elapsed_sec: float
    error: str | None = None


def generate_asset_proxy(
    project_path: Path,
    asset_hash: str,
    *,
    profile: SourceProxyProfile = DEFAULT_SOURCE_PROXY_PROFILE,
    timeout_s: float | None = None,
) -> SourceProxyResult:
    """Generate or reuse one low-resolution source-proxy CAS object."""
```

- `Asset` gains `proxy_hash: str | None`, `proxy_profile: str | None`,
  `proxy_status: SourceProxyStatus = "none"`, `proxy_error: str = ""`, and
  `proxy_updated_at: str = ""`. Add `has_alpha: bool = False` to the probed
  metadata so an alpha source is not silently flattened into yuv420p.
- `AssetStore.store_derived(source_path) -> str` hashes a completed temporary
  file, atomically copies it into the normal `<hash[:2]>/<hash>` CAS location,
  and does not create a user-visible canonical-asset sidecar for the derived
  object.
- `AssetStore.update_proxy_metadata(asset_hash, *, proxy_hash, profile,
  status, error="") -> Asset` reloads the current sidecar, updates only proxy
  fields, and atomically replaces the JSON. `clear_proxy_metadata()` performs
  the same operation with `proxy_hash=None` and `status="none"`.

- [ ] **Step 1: Write the failing metadata and generation tests.**

Add these cases to `tests/test_render/test_source_proxy.py`:

```python
def test_asset_proxy_fields_round_trip_through_sidecar(tmp_path: Path) -> None:
    store = AssetStore(tmp_path / ".open_edit" / "assets")
    source = make_video_fixture(tmp_path / "source.mp4", width=1920, height=1080)
    asset = store.ingest(str(source), transcribe=False)

    updated = store.update_proxy_metadata(
        asset.asset_hash,
        proxy_hash="b" * 64,
        profile="source_proxy_360_v1",
        status="ready",
    )
    loaded = store.get(asset.asset_hash)

    assert loaded is not None
    assert loaded.proxy_hash == "b" * 64
    assert loaded.proxy_profile == "source_proxy_360_v1"
    assert loaded.proxy_status == "ready"
    assert updated.proxy_updated_at


def test_generate_asset_proxy_writes_low_res_hash_and_links_source(
    tmp_path: Path,
) -> None:
    source = make_video_fixture(tmp_path / "source.mp4", width=1920, height=1080)
    store = AssetStore(tmp_path / ".open_edit" / "assets")
    asset = store.ingest(str(source), transcribe=False)

    result = generate_asset_proxy(tmp_path, asset.asset_hash)

    assert result.status == "ready"
    assert result.proxy_hash is not None
    assert store.path(result.proxy_hash) is not None
    linked = store.get(asset.asset_hash)
    assert linked is not None
    assert linked.proxy_hash == result.proxy_hash
    assert linked.proxy_profile == DEFAULT_SOURCE_PROXY_PROFILE.name

    proxy_asset = store.get(result.proxy_hash)
    assert proxy_asset is not None
    assert proxy_asset.height <= 360
    assert proxy_asset.duration_sec == pytest.approx(asset.duration_sec, abs=0.2)


def test_generate_asset_proxy_reuses_matching_ready_proxy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = make_video_fixture(tmp_path / "source.mp4", width=1920, height=1080)
    store = AssetStore(tmp_path / ".open_edit" / "assets")
    asset = store.ingest(str(source), transcribe=False)
    first = generate_asset_proxy(tmp_path, asset.asset_hash)

    monkeypatch.setattr(source_proxy.subprocess, "run", fail_if_called)
    second = generate_asset_proxy(tmp_path, asset.asset_hash)

    assert second.status == "ready"
    assert second.proxy_hash == first.proxy_hash


def test_source_proxy_does_not_proxy_audio_or_alpha_sources(tmp_path: Path) -> None:
    audio = make_audio_fixture(tmp_path / "voice.wav")
    store = AssetStore(tmp_path / ".open_edit" / "assets")
    asset = store.ingest(str(audio), transcribe=False)

    result = generate_asset_proxy(tmp_path, asset.asset_hash)

    assert result.status == "not_needed"
    assert result.proxy_hash is None
    assert store.get(asset.asset_hash).proxy_status == "not_needed"


def test_source_proxy_failure_keeps_original_and_records_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = make_video_fixture(tmp_path / "source.mp4", width=1920, height=1080)
    store = AssetStore(tmp_path / ".open_edit" / "assets")
    asset = store.ingest(str(source), transcribe=False)
    monkeypatch.setattr(
        source_proxy.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args, 1, stdout="", stderr="encoder failed",
        ),
    )

    result = generate_asset_proxy(tmp_path, asset.asset_hash)

    assert result.status == "failed"
    assert result.proxy_hash is None
    linked = store.get(asset.asset_hash)
    assert linked is not None
    assert linked.proxy_status == "failed"
    assert "encoder failed" in linked.proxy_error
    assert store.path(asset.asset_hash) is not None
```

The fixture helper must create a real temporary ffmpeg video/audio file; do not
commit a large binary fixture. Use `pytest.skip` only when ffmpeg/ffprobe is
unavailable, matching the existing QC fixture convention.

- [ ] **Step 2: Run the focused tests and verify the new contract fails.**

Run:

```bash
/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest \
  tests/test_render/test_source_proxy.py \
  tests/test_storage/test_assets.py \
  tests/test_ir/test_types.py \
  -o addopts="" -q
```

Expected: FAIL because `Asset` has no proxy fields and
`generate_asset_proxy()`/the sidecar update methods do not exist.

- [ ] **Step 3: Implement the profile and CAS writer.**

Use a temporary `.mp4` under `<project>/.open_edit/tmp/source-proxy/`, with a
unique filename. The generated command must have this shape:

```python
[
    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
    "-i", str(source_path),
    "-map", "0:v:0", "-map", "0:a?",
    "-vf", "scale=w='if(gt(ih,360),-2,iw)':h='min(ih,360)'",
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
    "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-b:a", "96k",
    "-movflags", "+faststart",
    str(temp_output),
]
```

The implementation must:

1. Load the canonical asset and fail with a structured `failed` result when
   the hash or source bytes are missing.
2. Return `not_needed` without creating a proxy for audio, image, alpha, or a
   source whose height is already at or below the target height. The original
   path remains the resolver fallback.
3. Reuse a `ready` proxy only when `proxy_profile` equals the requested profile
   and `AssetStore.path(proxy_hash)` is still a file.
4. Set status to `running` before invoking ffmpeg and restore `failed` with
   captured stderr on any non-zero exit or timeout.
5. Use a timeout of `max(120.0, duration_sec * 4.0 + 60.0)` when the caller
   does not supply one.
6. Verify the temporary output is non-empty, store it by content hash, update
   the source sidecar only after the CAS copy succeeds, and remove the
   temporary file in `finally`.
7. Never overwrite or delete the canonical source CAS file.

Extend `_probe_media()` to record `pix_fmt` and `has_alpha`; keep existing
`Asset` constructors valid through defaults.

- [ ] **Step 4: Run the focused tests and the asset suite.**

Run:

```bash
/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest \
  tests/test_render/test_source_proxy.py \
  tests/test_storage/test_assets.py \
  tests/test_ir/test_types.py \
  -o addopts="" -q
```

Expected: PASS, including the pre-existing sidecar and metadata tests.

- [ ] **Step 5: Commit the independently testable source-proxy core.**

```bash
git add open_edit/render/source_proxy.py open_edit/ir/types.py \
  open_edit/storage/assets.py tests/test_render/test_source_proxy.py \
  tests/test_storage/test_assets.py tests/test_ir/test_types.py
git commit -m "feat(render): add source-proxy metadata and CAS generation"
```

---
