"""Tests for asset streaming in the Open Edit server.

Pins down v1.4 P0-2: a freshly-uploaded video must be visible in the
preview player. Concretely, three contracts are tested here:

1. **API shape contract**: the asset info returned in
   ``GET /api/projects/{id}`` and in the upload response includes a
   servable ``url`` field whose value points at the new
   ``/api/projects/{id}/assets/{hash}/file`` route.

2. **Streaming contract**: that route returns the file with a
   non-``application/octet-stream`` ``Content-Type`` (we use the
   stdlib ``mimetypes`` for the common mp4/mov/webm/png/jpg set) and
   supports HTTP Range requests (browsers seek in ``<video>`` via
   Range headers — without 206 support some browsers refuse to play).

3. **Ingest contract**: ``POST /api/projects/{id}/ingest`` actually
   writes the file into the CAS (the content-addressed asset store at
   ``.open_edit/assets/<prefix>/<hash>``) with a sidecar metadata
   JSON, **not** into a transient inbox that ``open_edit init`` would
   then fail to discover. Before this fix, the upload endpoint
   deposited the file under ``.open_edit/inbox/`` and re-ran
   ``open_edit init`` — which only scans the project root, so the
   file never reached the CAS and the preview had nothing to play.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Allow ``from _node_harness import ...`` from the tests/ dir.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _node_harness import (  # noqa: E402
    app_js_path,
    harness,
    run_node_script,
)

_TPKG_ROOT = Path(__file__).resolve().parents[1]
if str(_TPKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_TPKG_ROOT))

from open_edit.serve import app as app_mod  # noqa: E402
from open_edit.serve import projects as projects_mod  # noqa: E402

APP_JS = app_js_path()
assert APP_JS.exists(), f"missing {APP_JS}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTDATA_MP4 = REPO_ROOT / "testdata" / "clip_short.mp4"


@pytest.fixture
def projects_root_tmp(tmp_path, monkeypatch):
    """Point ``OPEN_EDIT_PROJECTS_ROOT`` at a fresh empty dir."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    monkeypatch.setenv("OPEN_EDIT_PROJECTS_ROOT", str(projects_dir))
    return projects_dir


@pytest.fixture
def seeded_project(projects_root_tmp):
    """A real, fully-initialised project under ``projects_root_tmp``.

    Runs ``open_edit init`` so the project has ``.open_edit/edit_graph.db``
    and is visible to the server.
    """
    proj = projects_root_tmp / "p1"
    proj.mkdir()
    from open_edit.cli import cmd_init
    import argparse
    rc = cmd_init(argparse.Namespace(folder=str(proj)))
    assert rc == 0
    project_id = projects_mod._project_id_from_path(proj.resolve())
    return proj, project_id


def _seed_asset_on_disk(project_path: Path, filename: str, contents: bytes) -> str:
    """Ingest ``contents`` into the project's CAS via ``AssetStore``.

    Returns the asset hash. The file is written to a temp path and
    ingested the same way the upload endpoint will. We bypass
    ``AssetStore.ingest`` for fake-content seeds because that runs
    ffprobe on the file (which would fail on the test bytes); instead
    we write the CAS file + sidecar directly, the same way
    ``AssetStore.ingest_paths`` does for a real file.
    """
    import hashlib as _hashlib
    from open_edit.ir.types import Asset
    from open_edit.storage.assets import AssetStore

    assets_dir = project_path / ".open_edit" / "assets"
    store = AssetStore(assets_dir)
    asset_hash = _hashlib.sha256(contents).hexdigest()
    cas_path = store._cas_path(asset_hash)
    cas_path.parent.mkdir(parents=True, exist_ok=True)
    cas_path.write_bytes(contents)
    sidecar = store._sidecar_path(asset_hash)
    asset = Asset(
        asset_hash=asset_hash,
        original_path=str(project_path / filename),
        stored_path=str(cas_path),
        type="video",
        duration_sec=10.0,
        fps=30.0,
        width=1920,
        height=1080,
        codec="h264",
        has_audio=False,
    )
    sidecar.write_text(asset.model_dump_json(indent=2))
    return asset_hash


# ---------------------------------------------------------------------------
# Contract 1: API shape — assets include a servable url
# ---------------------------------------------------------------------------

def test_get_project_state_assets_include_url(seeded_project):
    """``GET /api/projects/{id}`` returns assets whose ``url`` field
    points at the streaming route. This is the field the frontend's
    ``normalizeAssets`` will hand to the preview's ``<video src>``."""
    _proj, pid = seeded_project
    payload = bytes(range(256)) * 4  # 1 KB
    _seed_asset_on_disk(_proj, "seed.bin", payload)

    client = TestClient(app_mod.app)
    r = client.get(f"/api/projects/{pid}")
    assert r.status_code == 200
    body = r.json()
    assert body["assets"], "expected at least one asset"
    asset = body["assets"][0]
    assert "url" in asset, f"asset info missing 'url' field: {asset!r}"
    url = asset["url"]
    # The URL is server-relative (no scheme/host), so the browser uses
    # whatever origin it's on.
    assert url.startswith("/"), f"url should be server-relative, got {url!r}"
    assert pid in url, f"url should include the project id, got {url!r}"
    assert asset["hash"] in url, f"url should include the asset hash, got {url!r}"


# ---------------------------------------------------------------------------
# Contract 2: streaming — bytes, content-type, range support
# ---------------------------------------------------------------------------

def test_asset_file_endpoint_returns_bytes_with_content_type(seeded_project):
    """A GET on the asset's ``url`` returns the file with the right
    ``Content-Type`` for the original filename's extension. (The
    previous behaviour left the field unset and the browser refused
    to play the response.) The mime type is derived from
    ``asset.original_path`` (``<project>/<filename>``), so a file
    uploaded as ``movie.mp4`` gets ``video/mp4`` even though the CAS
    file itself has no extension."""
    _proj, pid = seeded_project
    payload = b"\x00\x01\x02\x03fake-mp4-bytes\xff\xff" * 16
    asset_hash = _seed_asset_on_disk(_proj, "movie.mp4", payload)

    client = TestClient(app_mod.app)
    # Build the URL the same way the API will.
    url = f"/api/projects/{pid}/assets/{asset_hash}/file"
    r = client.get(url)
    assert r.status_code == 200, f"got {r.status_code} body={r.text!r}"
    assert r.content == payload
    ctype = r.headers.get("content-type", "")
    assert "video/mp4" in ctype, (
        f"expected Content-Type to include 'video/mp4' for a .mp4 "
        f"asset, got {ctype!r} (the browser will refuse to play the "
        f"response without the right mime type)"
    )


def test_asset_file_endpoint_mp4_content_type(seeded_project):
    """An mp4 asset served via the streaming route has
    ``Content-Type: video/mp4`` — the actual user-visible bug."""
    _proj, pid = seeded_project
    # Ingest a real mp4 so mimetypes maps the on-disk extension.
    assert TESTDATA_MP4.exists(), f"missing test fixture: {TESTDATA_MP4}"
    payload = TESTDATA_MP4.read_bytes()
    # The on-disk CAS path has no extension, so we have to look up
    # the mime type from the original filename. The streaming route
    # takes that from the asset's ``Asset.original_path``.
    # We write the file to the project root first (mimicking what
    # the upload endpoint will do), then ingest.
    src_copy = _proj / "clip_short.mp4"
    src_copy.write_bytes(payload)
    try:
        from open_edit.storage.assets import AssetStore
        store = AssetStore(_proj / ".open_edit" / "assets")
        asset = store.ingest(str(src_copy))
    finally:
        src_copy.unlink(missing_ok=True)

    client = TestClient(app_mod.app)
    r = client.get(f"/api/projects/{pid}/assets/{asset.asset_hash}/file")
    assert r.status_code == 200
    ctype = r.headers.get("content-type", "")
    assert "video/mp4" in ctype, (
        f"expected Content-Type to include 'video/mp4' for an mp4 asset, "
        f"got {ctype!r} (the browser will refuse to play the response "
        f"without the right mime type)"
    )
    # And the file bytes match.
    assert r.content == payload
    # Accept-Ranges: bytes — let the browser know we support seeking.
    assert r.headers.get("accept-ranges") == "bytes", (
        f"expected Accept-Ranges: bytes, got {r.headers.get('accept-ranges')!r}"
    )


def test_asset_file_endpoint_supports_range_request(seeded_project):
    """A Range request returns 206 Partial Content with the right
    ``Content-Range`` header. Without this, browsers cannot seek
    inside the video, and some refuse to play the file at all."""
    _proj, pid = seeded_project
    payload = b"".join(bytes([i % 256]) for i in range(8192))  # 8 KB
    asset_hash = _seed_asset_on_disk(_proj, "movie.mp4", payload)

    client = TestClient(app_mod.app)
    # Standard Range header — first 1024 bytes.
    r = client.get(
        f"/api/projects/{pid}/assets/{asset_hash}/file",
        headers={"Range": "bytes=0-1023"},
    )
    assert r.status_code == 206, (
        f"expected 206 Partial Content for a Range request, got "
        f"{r.status_code} (the browser will not be able to seek)"
    )
    assert r.content == payload[:1024]
    cr = r.headers.get("content-range", "")
    assert cr.startswith("bytes 0-1023/"), (
        f"expected Content-Range 'bytes 0-1023/<size>', got {cr!r}"
    )
    assert str(len(payload)) in cr
    # The 206 response also advertises Accept-Ranges: bytes.
    assert r.headers.get("accept-ranges") == "bytes"

    # A different range — middle 512 bytes starting at 4096.
    r2 = client.get(
        f"/api/projects/{pid}/assets/{asset_hash}/file",
        headers={"Range": "bytes=4096-4607"},
    )
    assert r2.status_code == 206
    assert r2.content == payload[4096:4608]
    cr2 = r2.headers.get("content-range", "")
    assert cr2.startswith("bytes 4096-4607/")
    assert str(len(payload)) in cr2

    # A request WITHOUT a Range header is a normal 200 with the full file.
    r3 = client.get(f"/api/projects/{pid}/assets/{asset_hash}/file")
    assert r3.status_code == 200
    assert r3.content == payload


def test_asset_file_endpoint_404_for_unknown_hash(seeded_project):
    """An unknown asset hash returns 404, not 500 (no exception leak)."""
    _proj, pid = seeded_project
    client = TestClient(app_mod.app)
    bogus = "0" * 64
    r = client.get(f"/api/projects/{pid}/assets/{bogus}/file")
    assert r.status_code == 404
    body = r.json()
    assert "error" in body, f"missing 'error' key in {body!r}"
    assert "not found" in body["error"].lower()


def test_asset_file_endpoint_404_for_unknown_project(seeded_project):
    """An unknown project id returns 404 (not 500)."""
    client = TestClient(app_mod.app)
    bogus = "0" * 64
    r = client.get(f"/api/projects/deadbeefdeadbeef/assets/{bogus}/file")
    assert r.status_code == 404


def test_asset_file_endpoint_rejects_path_traversal_in_hash(seeded_project):
    """The streaming route must reject malformed asset hashes. The
    hash is interpolated into a filesystem path, so accepting
    arbitrary text would let a caller probe the filesystem."""
    _proj, pid = seeded_project
    client = TestClient(app_mod.app)
    for bad in ["..", "..%2F..", "abc", "x" * 63, "g" * 64, "ZZ" * 32]:
        r = client.get(f"/api/projects/{pid}/assets/{bad}/file")
        # Either 400 (validation) or 404 (not found) is acceptable; the
        # important thing is we never get 200 and never crash.
        assert r.status_code in (400, 404), (
            f"expected 400/404 for malformed hash {bad!r}, got "
            f"{r.status_code} body={r.text!r}"
        )


# ---------------------------------------------------------------------------
# Contract 3: ingest — upload actually puts the file in CAS
# ---------------------------------------------------------------------------

import shutil as _shutil  # local alias for the ffprobe-skip check below


@pytest.fixture
def ffprobe_available() -> bool:
    """True iff ``ffprobe`` is on PATH. Mirrors the pattern in
    ``test_cli.py`` / ``test_e2e.py`` so the ffprobe-failure test
    skips cleanly on minimal environments instead of erroring."""
    return _shutil.which("ffprobe") is not None


def test_upload_invalid_media_returns_400_with_error_shape(
    seeded_project, tmp_path, ffprobe_available
):
    """Uploading a file that ffprobe can't parse (here: a small text
    file with a ``.mp4`` extension) returns 400 with the v1.4
    ``{"error": "..."}`` shape — not a generic 500, and not a leaky
    traceback. This is the one piece of the new error contract the
    success-path and CAS-roundtrip tests don't cover.
    """
    if not ffprobe_available:
        pytest.skip("ffprobe not installed")
    _proj, pid = seeded_project
    fake = tmp_path / "not-really-an-mp4.mp4"
    fake.write_text("this is just plain text, not a media file\n", encoding="utf-8")

    client = TestClient(app_mod.app)
    with fake.open("rb") as fh:
        r = client.post(
            f"/api/projects/{pid}/ingest",
            files={"file": ("not-really-an-mp4.mp4", fh, "video/mp4")},
        )
    assert r.status_code == 400, (
        f"expected 400 for unparseable media, got {r.status_code} "
        f"body={r.text!r}"
    )
    body = r.json()
    # v1.4 error contract: the response is ``{"error": "..."}`` (not
    # FastAPI's default ``{"detail": "..."}``). See app.py:142.
    assert "error" in body, (
        f"missing 'error' key in {body!r} — the v1.4 frontend can't "
        f"display this error without it"
    )
    assert isinstance(body["error"], str) and body["error"], (
        f"'error' should be a non-empty string, got {body['error']!r}"
    )
    # And the file should NOT have landed in the CAS — ffprobe failed,
    # so AssetStore.ingest never wrote the sidecar.
    assets_dir = _proj / ".open_edit" / "assets"
    assert not any(assets_dir.rglob("*.meta.json")), (
        f"expected no asset metadata after a failed ingest, but found "
        f"sidecars under {assets_dir}"
    )

def test_upload_writes_file_to_cas(seeded_project):
    """``POST /api/projects/{id}/ingest`` writes the file into the CAS
    (i.e., ``.open_edit/assets/<prefix>/<hash>`` with a sidecar
    ``<hash>.meta.json``). Before this fix, the endpoint deposited the
    file in ``.open_edit/inbox/`` and re-ran ``open_edit init`` — which
    only scans the project root — so the file never reached the CAS
    and the preview had nothing to play.
    """
    _proj, pid = seeded_project
    assert TESTDATA_MP4.exists(), f"missing test fixture: {TESTDATA_MP4}"
    payload = TESTDATA_MP4.read_bytes()
    expected_hash = hashlib.sha256(payload).hexdigest()

    client = TestClient(app_mod.app)
    with TESTDATA_MP4.open("rb") as fh:
        r = client.post(
            f"/api/projects/{pid}/ingest",
            files={"file": ("clip_short.mp4", fh, "video/mp4")},
        )
    assert r.status_code in (200, 202), (
        f"upload failed: status={r.status_code} body={r.text!r}"
    )

    # The CAS file should exist under .open_edit/assets/<hash[:2]>/<hash>.
    cas_file = _proj / ".open_edit" / "assets" / expected_hash[:2] / expected_hash
    assert cas_file.exists(), (
        f"uploaded file did not land in CAS at {cas_file} — the bug "
        f"was that the endpoint wrote to .open_edit/inbox/ and then "
        f"open_edit init (which only scans the project root) never "
        f"saw it."
    )
    assert cas_file.read_bytes() == payload

    # The sidecar metadata JSON should be present.
    sidecar = cas_file.parent / f"{expected_hash}.meta.json"
    assert sidecar.exists(), f"missing sidecar metadata: {sidecar}"
    meta = json.loads(sidecar.read_text())
    assert meta["asset_hash"] == expected_hash
    assert meta["type"] == "video"


def test_upload_response_includes_servable_url(seeded_project):
    """The upload response includes a servable URL the frontend can
    use to play the video. The brief requires the upload response and
    the asset-list response to return a stable, servable URL field —
    the frontend uses the upload response to play the file
    immediately (no extra round trip) and the asset-list response
    later to refresh the list."""
    _proj, pid = seeded_project
    client = TestClient(app_mod.app)
    with TESTDATA_MP4.open("rb") as fh:
        r = client.post(
            f"/api/projects/{pid}/ingest",
            files={"file": ("clip_short.mp4", fh, "video/mp4")},
        )
    assert r.status_code in (200, 202), (
        f"upload failed: status={r.status_code} body={r.text!r}"
    )
    body = r.json()
    # The response carries the new asset's identity.
    assert "asset" in body, (
        f"upload response missing 'asset' key (frontend can't play "
        f"the video without it): {body!r}"
    )
    asset = body["asset"]
    assert asset.get("hash"), f"asset missing 'hash': {asset!r}"
    assert asset.get("url"), f"asset missing 'url': {asset!r}"
    # And the URL is servable — a GET on it returns the bytes.
    payload = TESTDATA_MP4.read_bytes()
    r2 = client.get(asset["url"])
    assert r2.status_code == 200, (
        f"GET on returned URL {asset['url']!r} returned {r2.status_code}: "
        f"{r2.text!r}"
    )
    assert r2.content == payload
    ctype = r2.headers.get("content-type", "")
    assert "video/mp4" in ctype, (
        f"expected Content-Type video/mp4 for an mp4 upload, got {ctype!r}"
    )


def test_upload_then_asset_list_consistent_url(seeded_project):
    """The URL returned by the upload response and the URL in the
    subsequent ``GET /api/projects/{id}`` asset list point to the
    same file. The frontend uses both; they must agree."""
    _proj, pid = seeded_project
    client = TestClient(app_mod.app)
    with TESTDATA_MP4.open("rb") as fh:
        r = client.post(
            f"/api/projects/{pid}/ingest",
            files={"file": ("clip_short.mp4", fh, "video/mp4")},
        )
    body = r.json()
    upload_url = body["asset"]["url"]
    upload_hash = body["asset"]["hash"]

    r2 = client.get(f"/api/projects/{pid}")
    listed = [a for a in r2.json()["assets"] if a["hash"] == upload_hash]
    assert listed, (
        f"newly uploaded asset {upload_hash!r} is not in the asset list"
    )
    assert listed[0]["url"] == upload_url, (
        f"upload URL {upload_url!r} differs from list URL "
        f"{listed[0]['url']!r} — the frontend will not be able to "
        f"play it."
    )


# ---------------------------------------------------------------------------
# Frontend: normalizeAssets passes the url through to the preview src
# ---------------------------------------------------------------------------

def test_frontend_normalize_assets_passes_through_url():
    """The frontend's ``normalizeAssets`` (in ``static/app.js``) maps
    the backend's asset shape into the shape the preview component
    reads. The new backend contract adds a ``url`` field; the
    normalizer MUST pass it through so the preview can set
    ``<video src>`` to it.

    We run the file in a Node sandbox with stubbed browser APIs and
    call the real ``normalizeAssets`` via the test export
    (``window.OpenEdit.__testHooks.normalizeAssets``). The export
    exists so tests can exercise the function in its real module
    closure — extracting the function body via regex and re-evaluating
    it in a fresh ``Function`` would let typos in field names slip
    through (the extracted copy has no closure state, so refactors
    that introduce cross-references between normalizers would not
    be caught by tests).

    As of v1.4 P2 the frontend is an ES module. The harness in
    ``tests/_node_harness.py`` loads it via ``import()`` instead of
    the old ``vm.runInContext`` pattern.
    """
    script = harness(r"""
const testHooks = globalThis.OpenEdit && globalThis.OpenEdit.__testHooks;
if (!testHooks || typeof testHooks.normalizeAssets !== 'function') {
  console.error('window.OpenEdit.__testHooks.normalizeAssets not exposed');
  process.exit(2);
}
const input = [
  {
    hash: 'abc123',
    filename: 'clip_short.mp4',
    duration_s: 10.0,
    fps: 30,
    width: 1920,
    height: 1080,
    codec: 'h264',
    has_audio: false,
    url: '/api/projects/abc/assets/abc123/file',
  },
  // Legacy shape (no url field) — should still work.
  {
    hash: 'legacy',
    filename: 'old.mp4',
    duration_s: 5.0,
  },
];
const out = testHooks.normalizeAssets(input);
console.log(JSON.stringify(out));
""")
    rc, out, err = run_node_script(script, APP_JS)
    assert rc == 0, (
        f"node harness failed (rc={rc}): "
        f"stdout={out!r} stderr={err!r}"
    )
    out = json.loads(out.strip().splitlines()[-1])

    # New-shape asset: url is preserved.
    assert len(out) == 2
    assert out[0]["url"] == "/api/projects/abc/assets/abc123/file", (
        f"normalizeAssets dropped the new 'url' field — the preview "
        f"player will not be able to play the video. Got: {out[0]!r}"
    )
    # And the other fields are still mapped (regression check).
    assert out[0]["filename"] == "clip_short.mp4"
    assert out[0]["duration_s"] == 10.0
    # Legacy shape: url defaults to empty string (defensive parsing).
    assert out[1]["url"] == "", (
        f"legacy-shape asset should default url to '' (not crash), "
        f"got {out[1]!r}"
    )


def test_frontend_open_asset_preview_annotates_title_when_no_url():
    """When an asset has no servable URL the preview modal would
    otherwise be a blank ``<video>`` with no explanation. The title
    must be annotated so the user knows why the player is empty.

    Before this fix, ``openAssetPreview`` set the title to the
    filename on the happy path and the no-URL branch only cleared
    the video's ``src`` — the title stayed as the bare filename,
    which made the no-URL state indistinguishable from a working
    preview that hadn't loaded yet.
    """
    script = harness(r"""
// Capture the title and video elements so the test can inspect
// their state after ``openAssetPreview`` runs.
const titleEl = { textContent: '' };
const videoEl = {
  src: '',
  load: () => {},
  removeAttribute: () => {},
};
const modalEl = { classList: { add: () => {}, remove: () => {} } };
const docStubs = new Map([
  ['#asset-preview-title', titleEl],
  ['#asset-preview-video', videoEl],
  ['#modal-asset-preview', modalEl],
]);
// Replace the harness's stub ``document.querySelector`` with a
// targeted map for the three selectors the test cares about. The
// module code calls ``$('#asset-preview-title')`` etc. at runtime
// so this swap takes effect immediately.
globalThis.document.querySelector = (sel) => docStubs.get(sel) || {
  appendChild: () => {}, setAttribute: () => {}, addEventListener: () => {},
  classList: { add: () => {}, remove: () => {}, toggle: () => {} },
  dataset: {}, style: {}, children: [], textContent: '', innerHTML: '',
  value: '', removeAttribute: () => {}, load: () => {}, focus: () => {},
  click: () => {}, replaceWith: () => {}, remove: () => {},
  querySelector: () => null, querySelectorAll: () => [],
};

const testHooks = globalThis.OpenEdit && globalThis.OpenEdit.__testHooks;
if (!testHooks || typeof testHooks.openAssetPreview !== 'function') {
  console.error('window.OpenEdit.__testHooks.openAssetPreview not exposed');
  process.exit(2);
}

// Case 1: no URL — title should be annotated with a "no preview" hint.
titleEl.textContent = 'unset';
videoEl.src = '';
testHooks.openAssetPreview({ filename: 'broken.mp4', url: '' });
const noUrlTitle = titleEl.textContent;
const noUrlVideoSrc = videoEl.src;

// Case 2: with URL — title is the bare filename, video src is set.
titleEl.textContent = 'unset';
videoEl.src = '';
testHooks.openAssetPreview({
  filename: 'good.mp4',
  url: '/api/projects/x/assets/y/file',
});
const withUrlTitle = titleEl.textContent;
const withUrlVideoSrc = videoEl.src;

console.log(JSON.stringify({
  noUrlTitle,
  noUrlVideoSrc,
  withUrlTitle,
  withUrlVideoSrc,
}));
""")
    rc, out, err = run_node_script(script, APP_JS)
    assert rc == 0, (
        f"node harness failed (rc={rc}): "
        f"stdout={out!r} stderr={err!r}"
    )
    out = json.loads(out.strip().splitlines()[-1])

    # No-URL case: title is annotated, video src is empty.
    assert out["noUrlTitle"] != "unset", "openAssetPreview didn't touch the title"
    assert "broken.mp4" in out["noUrlTitle"], (
        f"no-URL title should still include the filename, got "
        f"{out['noUrlTitle']!r}"
    )
    assert "no preview" in out["noUrlTitle"].lower(), (
        f"no-URL title should mention the missing preview, got "
        f"{out['noUrlTitle']!r} (the user will stare at a blank modal "
        f"wondering why the player is empty)"
    )
    assert out["noUrlVideoSrc"] == "", (
        f"no-URL case should leave video.src empty, got "
        f"{out['noUrlVideoSrc']!r}"
    )

    # With-URL case: title is the bare filename, video src is the URL.
    assert out["withUrlTitle"] == "good.mp4", (
        f"with-URL title should be the bare filename, got "
        f"{out['withUrlTitle']!r}"
    )
    assert out["withUrlVideoSrc"] == "/api/projects/x/assets/y/file", (
        f"with-URL case should set video.src to the asset URL, got "
        f"{out['withUrlVideoSrc']!r}"
    )
