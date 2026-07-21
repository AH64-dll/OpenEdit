"""Tests for ``open_edit.agent.tools.pyagent_import_asset``.

The tool takes either:
- a ``result_id`` from a prior ``search_assets`` call, OR
- a direct ``source_url`` (must be HTTPS, must be from a known source)

It downloads the file, ingests it into the project's CAS via
``AssetStore.ingest``, and tags the resulting ``Asset`` with
``license`` + ``attribution`` metadata so the preview UI can surface
the credit line.

The HTTP download is mocked via ``unittest.mock.patch`` so tests don't
talk to the real internet. The CAS is real (``AssetStore`` + sidecar
JSONs) so we exercise the full ingest path.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from open_edit.agent.tools import pyagent_import_asset as mod  # noqa: E402
from open_edit.agent.tools.pyagent_import_asset import (  # noqa: E402
    import_asset,
    _http_download,
    _lookup_result,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# We use a real test MP4 from testdata/ for the ingest tests so ffprobe
# can probe the file. The file is small (~3KB) and committed to the repo.
_REAL_MP4 = (
    Path(__file__).resolve().parents[1]
    / "tests" / "testdata" / "raw_videos" / "clip_a.mp4"
)


def _bootstrap_project(project_path: Path) -> None:
    """Create a real Open Edit project at ``project_path``.

    Mirrors the helper in ``test_serve_pi_bridge.py`` so the import
    tests can run end-to-end against a real ``edit_graph.db`` (needed
    because the tool is project-scoped and writes to the project CAS).
    """
    project_path.mkdir(parents=True, exist_ok=True)
    init = subprocess.run(
        ["open_edit", "init", str(project_path)],
        capture_output=True, text=True, timeout=60,
    )
    if init.returncode != 0:
        from open_edit.storage.edit_graph import EditGraphStore
        EditGraphStore(project_path / ".open_edit" / "edit_graph.db")


def _seed_search_result_file(cache_dir: Path, result_id: str, payload: dict) -> Path:
    """Write a search result to the in-process result cache.

    The real ``import_asset`` looks up ``result_id`` in a small file
    cache (see ``_lookup_result``) so the tool can be called by an
    LLM across multiple tool-call boundaries without the LLM having
    to forward the full result payload.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    p = cache_dir / f"{result_id}.json"
    p.write_text(json.dumps(payload))
    return p


# ---------------------------------------------------------------------------
# Tests: result_id → fetch metadata from search cache
# ---------------------------------------------------------------------------

def test_import_asset_by_result_id_uses_cached_metadata(tmp_path, monkeypatch):
    """When given a ``result_id`` from a prior search, the tool reads
    the cached search result (so it has license/attribution without
    the LLM having to re-pass them) and downloads the preview URL."""
    if not shutil.which("open_edit"):
        pytest.skip("open_edit CLI not on PATH; cannot bootstrap project")
    if not shutil.which("ffprobe"):
        pytest.skip("ffprobe not installed; cannot ingest media in tests")

    project = tmp_path / "proj"
    _bootstrap_project(project)

    # Stash a search result that the import will look up.
    cache = tmp_path / "search_cache"
    result_id = "pexels-video-12345"
    _seed_search_result_file(cache, result_id, {
        "id": result_id,
        "source": "pexels",
        "kind": "video",
        "title": "rain on a window",
        "thumbnail_url": "https://example.com/thumb.jpg",
        "preview_url": "https://example.com/clip.mp4",
        "duration_seconds": 12,
        "license": "Pexels License",
        "attribution_required": False,
        "attribution": "Source: Pexels",
    })
    monkeypatch.setattr(mod, "_SEARCH_RESULT_CACHE_DIR", cache)

    real_bytes = _REAL_MP4.read_bytes()
    with mock.patch.object(mod, "_http_download", return_value=real_bytes):
        res = import_asset(
            {"result_id": result_id, "project_id": "x"},
            str(project),
        )

    assert "error" not in res, res
    assert res["status"] == "ingested"
    assert res["asset_hash"]  # 64-char sha256
    assert res["source"] == "pexels"
    assert res["license"] == "Pexels License"
    assert res["attribution"] == "Source: Pexels"

    # The asset must be on disk in the project's CAS.
    from open_edit.storage.assets import AssetStore
    store = AssetStore(project / ".open_edit" / "assets")
    asset = store.get(res["asset_hash"])
    assert asset is not None
    assert asset.license == "Pexels License"
    assert asset.attribution == "Source: Pexels"


def test_import_asset_unknown_result_id_returns_error(tmp_path, monkeypatch):
    """A bogus ``result_id`` (not in the search cache) is a clear error,
    not a crash."""
    if not shutil.which("open_edit"):
        pytest.skip("open_edit CLI not on PATH; cannot bootstrap project")

    project = tmp_path / "proj"
    _bootstrap_project(project)
    monkeypatch.setattr(mod, "_SEARCH_RESULT_CACHE_DIR", tmp_path / "empty_cache")

    res = import_asset(
        {"result_id": "freesound-bogus", "project_id": "x"},
        str(project),
    )
    assert "error" in res
    assert "not found" in res["error"].lower() or "unknown" in res["error"].lower()
    assert "freesound-bogus" in res["error"]


# ---------------------------------------------------------------------------
# Tests: direct source_url
# ---------------------------------------------------------------------------

def test_import_asset_by_source_url_without_license(tmp_path, monkeypatch):
    """When given a bare ``source_url`` with no license/attribution
    supplied, the tool still works (defaults to "Unknown" license) —
    the LLM shouldn't be forced to pass license info if it doesn't
    have it."""
    if not shutil.which("open_edit"):
        pytest.skip("open_edit CLI not on PATH; cannot bootstrap project")
    if not shutil.which("ffprobe"):
        pytest.skip("ffprobe not installed; cannot ingest media in tests")

    project = tmp_path / "proj"
    _bootstrap_project(project)

    real_bytes = _REAL_MP4.read_bytes()
    with mock.patch.object(mod, "_http_download", return_value=real_bytes):
        res = import_asset(
            {
                "source_url": "https://example.com/some-clip.mp4",
                "project_id": "x",
            },
            str(project),
        )

    assert "error" not in res, res
    assert res["status"] == "ingested"
    # The license is a string — default to a clear "Unknown" when the
    # caller didn't say, so the UI has something to render and the user
    # knows they need to investigate.
    assert "license" in res
    assert res["license"] == "Unknown"


def test_import_asset_with_explicit_license_attribution(tmp_path, monkeypatch):
    """``license`` and ``attribution`` args are stored verbatim on the asset."""
    if not shutil.which("open_edit"):
        pytest.skip("open_edit CLI not on PATH; cannot bootstrap project")
    if not shutil.which("ffprobe"):
        pytest.skip("ffprobe not installed; cannot ingest media in tests")

    project = tmp_path / "proj"
    _bootstrap_project(project)

    real_bytes = _REAL_MP4.read_bytes()
    with mock.patch.object(mod, "_http_download", return_value=real_bytes):
        res = import_asset(
            {
                "source_url": "https://example.com/x.mp4",
                "license": "CC BY 4.0",
                "attribution": "'x' by alice (CC BY 4.0)",
                "project_id": "x",
            },
            str(project),
        )
    assert "error" not in res, res
    assert res["license"] == "CC BY 4.0"
    assert res["attribution"] == "'x' by alice (CC BY 4.0)"

    from open_edit.storage.assets import AssetStore
    store = AssetStore(project / ".open_edit" / "assets")
    asset = store.get(res["asset_hash"])
    assert asset.license == "CC BY 4.0"
    assert asset.attribution == "'x' by alice (CC BY 4.0)"


def test_import_asset_rejects_non_https_url(tmp_path, monkeypatch):
    """HTTPS is required to keep download integrity sane (and to avoid
    http→https mixed-content issues in the preview player)."""
    if not shutil.which("open_edit"):
        pytest.skip("open_edit CLI not on PATH; cannot bootstrap project")

    project = tmp_path / "proj"
    _bootstrap_project(project)

    res = import_asset(
        {"source_url": "http://example.com/x.mp4", "project_id": "x"},
        str(project),
    )
    assert "error" in res
    assert "https" in res["error"].lower()


def test_import_asset_rejects_both_result_id_and_source_url_missing(tmp_path, monkeypatch):
    """The tool must reject calls with neither ``result_id`` nor ``source_url``.
    Don't guess which one the caller meant."""
    if not shutil.which("open_edit"):
        pytest.skip("open_edit CLI not on PATH; cannot bootstrap project")

    project = tmp_path / "proj"
    _bootstrap_project(project)

    res = import_asset({"project_id": "x"}, str(project))
    assert "error" in res
    assert "result_id" in res["error"] or "source_url" in res["error"]


# ---------------------------------------------------------------------------
# Tests: download failure → clean error
# ---------------------------------------------------------------------------

def test_import_asset_download_failure_returns_error(tmp_path, monkeypatch):
    """A 404 / network error during download is surfaced as a structured
    error — not a 500 from the bridge."""
    if not shutil.which("open_edit"):
        pytest.skip("open_edit CLI not on PATH; cannot bootstrap project")

    project = tmp_path / "proj"
    _bootstrap_project(project)

    with mock.patch.object(
        mod, "_http_download",
        side_effect=RuntimeError("upstream 404: not found"),
    ):
        res = import_asset(
            {"source_url": "https://example.com/missing.mp4", "project_id": "x"},
            str(project),
        )
    assert "error" in res
    assert "404" in res["error"] or "not found" in res["error"].lower()


# ---------------------------------------------------------------------------
# Tests: HTTP download helper
# ---------------------------------------------------------------------------

def test_http_download_uses_urlopen(monkeypatch):
    """The download helper must call ``urlopen`` with the right URL and
    return the response bytes."""
    # Fake response object — matches the relevant attributes of
    # ``http.client.HTTPResponse`` that ``_http_download`` reads.
    class _FakeResp:
        def __init__(self, body):
            self._body = body
        def read(self):
            return self._body
        def getcode(self):
            return 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    captured_urls = []
    def fake_urlopen(req, timeout=None):
        captured_urls.append((req.full_url, req.headers, timeout))
        return _FakeResp(b"hello-bytes")

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)

    out = mod._http_download("https://example.com/x.mp4", headers={"X-Foo": "bar"})
    assert out == b"hello-bytes"
    assert captured_urls
    url, headers, timeout = captured_urls[0]
    assert url == "https://example.com/x.mp4"
    assert headers.get("X-foo") == "bar"
    assert timeout is not None


# ---------------------------------------------------------------------------
# Tests: lookup helper
# ---------------------------------------------------------------------------

def test_lookup_result_returns_none_when_missing(tmp_path):
    """``_lookup_result`` returns None for an unknown id (the import
    tool then surfaces that as an error to the user)."""
    monkey = tmp_path / "cache"
    out = _lookup_result(monkey, "nonexistent")
    assert out is None


def test_lookup_result_round_trips_json(tmp_path):
    """A stashed search result is read back with the original fields."""
    cache = tmp_path / "cache"
    cache.mkdir()
    payload = {"id": "x", "license": "CC0", "preview_url": "https://x/y.mp3"}
    (cache / "x.json").write_text(json.dumps(payload))
    out = _lookup_result(cache, "x")
    assert out == payload
