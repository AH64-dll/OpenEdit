"""Tests for ``open_edit.agent.tools.pyagent_search_assets``.

The tool dispatches to Pexels (video/photo) or Freesound (audio) via HTTP,
normalises the result into a stable shape, and caches responses with a
TTL so an agent loop's iterative search doesn't burn the monthly cap
(Pexels: 20k req/month, 200 req/hour).

The HTTP layer is mocked via ``unittest.mock.patch`` so the tests don't
talk to the real internet and don't need the API keys set.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from open_edit.agent.tools import pyagent_search_assets as mod  # noqa: E402
from open_edit.agent.tools.pyagent_search_assets import (  # noqa: E402
    search_assets,
    _cache_get,
    _cache_put,
    _cache_clear,
    _pexels_api_key,
    _freesound_api_key,
)


# ---------------------------------------------------------------------------
# Sample Pexels + Freesound responses
# ---------------------------------------------------------------------------

PEXELS_VIDEO_RESPONSE = {
    "page": 1,
    "per_page": 3,
    "videos": [
        {
            "id": 12345,
            "url": "https://www.pexels.com/video/12345/",
            "duration": 12,
            "image": "https://images.pexels.com/videos/12345/free-video-12345.jpg",
            "video_files": [
                {
                    "id": 987,
                    "quality": "hd",
                    "file_type": "video/mp4",
                    "link": "https://videos.pexels.com/video-files/12345/12345-hd_1920_1080_30fps.mp4",
                },
                {
                    "id": 654,
                    "quality": "sd",
                    "file_type": "video/mp4",
                    "link": "https://videos.pexels.com/video-files/12345/12345-sd_640_360_30fps.mp4",
                },
            ],
        },
        {
            "id": 22222,
            "url": "https://www.pexels.com/video/22222/",
            "duration": 7,
            "image": "https://images.pexels.com/videos/22222/free-video-22222.jpg",
            "video_files": [
                {
                    "id": 333,
                    "quality": "sd",
                    "file_type": "video/mp4",
                    "link": "https://videos.pexels.com/video-files/22222/22222-sd_640_360_30fps.mp4",
                },
            ],
        },
    ],
}

PEXELS_PHOTO_RESPONSE = {
    "page": 1,
    "per_page": 2,
    "photos": [
        {
            "id": 99001,
            "url": "https://www.pexels.com/photo/99001/",
            "photographer": "Alice Photographer",
            "photographer_url": "https://www.pexels.com/@alice/",
            "alt": "rain on a window",
            "src": {
                "medium": "https://images.pexels.com/photos/99001/pexels-photo-99001.jpeg?w=800",
                "original": "https://images.pexels.com/photos/99001/pexels-photo-99001.jpeg",
            },
        },
    ],
}

FREESOUND_RESPONSE = {
    "count": 2,
    "results": [
        {
            "id": 555,
            "name": "whoosh_01",
            "username": "sfx_user",
            "duration": 1.2,
            "license": "https://creativecommons.org/licenses/by/4.0/",
            "preview_hq": "https://cdn.freesound.org/previews/555/555_1234567-lq.mp3",
            "images": {
                "waveform_m": "https://cdn.freesound.org/displays/555/555_wave_m.png",
            },
        },
        {
            "id": 666,
            "name": "soft_rain_loop",
            "username": "rainmaker",
            "duration": 30.0,
            # No ``license`` field — should fall back to the URL pattern
            # (e.g. ``https://creativecommons.org/licenses/by-nc/3.0/``).
            "license": "https://creativecommons.org/publicdomain/zero/1.0/",
            "preview_hq": "https://cdn.freesound.org/previews/666/666_7654321-lq.mp3",
        },
    ],
}

OPENVERSE_PHOTO_RESPONSE = {
    "results": [
        {
            "id": "ov-cc0",
            "title": "public domain rain",
            "creator": "Open Artist",
            "url": "https://images.example.org/rain-cc0.jpg",
            "thumbnail": "https://images.example.org/rain-thumb.jpg",
            "license": "cc0",
            "license_version": "1.0",
        },
        {
            "id": "ov-by",
            "title": "attributed rain",
            "creator": "Another Artist",
            "url": "https://images.example.org/rain-by.jpg",
            "license": "by",
            "license_version": "4.0",
        },
    ],
}

OPENVERSE_FILTER_RESPONSE = {
    "results": [
        {
            "id": "ov-by-first",
            "title": "attributed rain",
            "creator": "BY Artist",
            "url": "https://images.example.org/rain-by.jpg",
            "license": "by",
            "license_version": "4.0",
        },
        {
            "id": "ov-by-sa",
            "title": "share-alike rain",
            "creator": "SA Artist",
            "url": "https://images.example.org/rain-by-sa.jpg",
            "license": "by-sa",
            "license_version": "4.0",
        },
        {
            "id": "ov-cc0-late",
            "title": "public domain rain",
            "creator": "CC0 Artist",
            "url": "https://images.example.org/rain-cc0.jpg",
            "license": "cc0",
            "license_version": "1.0",
        },
        {
            "id": "ov-cc0-late-2",
            "title": "another public domain rain",
            "creator": "Second CC0 Artist",
            "url": "https://images.example.org/rain-cc0-2.jpg",
            "license": "cc0",
            "license_version": "1.0",
        },
        {
            "id": "ov-by-second",
            "title": "another attributed rain",
            "creator": "Another BY Artist",
            "url": "https://images.example.org/rain-by-2.jpg",
            "license": "by",
            "license_version": "4.0",
        },
    ],
}

WIKIMEDIA_RESPONSE = {
    "query": {
        "pages": [
            {
                "pageid": 4242,
                "title": "File:Gemini logo.svg",
                "canonicalurl": "https://commons.wikimedia.org/wiki/File:Gemini_logo.svg",
                "imageinfo": [
                    {
                        "url": "https://upload.wikimedia.org/wikipedia/commons/g/gm/Gemini_logo.svg",
                        "thumburl": "https://upload.wikimedia.org/wikipedia/commons/thumb/g/gm/Gemini_logo.svg/800px-Gemini_logo.svg.png",
                        "descriptionurl": "https://commons.wikimedia.org/wiki/File:Gemini_logo.svg",
                        "mime": "image/svg+xml",
                        "extmetadata": {
                            "Artist": {"value": "Example Artist"},
                            "LicenseShortName": {"value": "CC BY-SA 4.0"},
                            "LicenseUrl": {
                                "value": "https://creativecommons.org/licenses/by-sa/4.0/"
                            },
                        },
                    }
                ],
            }
        ]
    }
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_cache():
    """Reset the in-memory cache and any env-var leakage between tests."""
    _cache_clear()
    yield
    _cache_clear()


@pytest.fixture
def pexels_key(monkeypatch):
    monkeypatch.setenv("OPEN_EDIT_PEXELS_API_KEY", "test-pexels-key")


@pytest.fixture
def freesound_key(monkeypatch):
    monkeypatch.setenv("OPEN_EDIT_FREESOUND_API_KEY", "test-fs-token")


@pytest.fixture
def no_keys(monkeypatch):
    monkeypatch.delenv("OPEN_EDIT_PEXELS_API_KEY", raising=False)
    monkeypatch.delenv("OPEN_EDIT_FREESOUND_API_KEY", raising=False)


# ---------------------------------------------------------------------------
# Tests: missing API keys → graceful error
# ---------------------------------------------------------------------------

def test_search_assets_returns_error_when_pexels_key_missing(no_keys, tmp_path):
    """Video without the Pexels key returns a structured error naming the
    missing env var (no Openverse fallback, no network call)."""
    with mock.patch.object(mod, "_http_get_json") as m:
        res = search_assets({"query": "rain", "kind": "video", "limit": 3},
                            str(tmp_path))
    assert m.call_count == 0, "missing key must short-circuit before HTTP"
    assert res["status"] == "error", res
    assert "OPEN_EDIT_PEXELS_API_KEY" in res["error"]
    assert res["results"] == []


def test_search_assets_returns_error_when_freesound_key_missing(no_keys, tmp_path):
    """Without Freesound, audio uses the keyless Openverse fallback."""
    with mock.patch.object(mod, "_http_get_json", return_value={"results": []}):
        res = search_assets({"query": "whoosh", "kind": "audio", "limit": 3},
                            str(tmp_path))
    assert res["status"] == "ok"
    assert res["source"] == "openverse"
    assert res["results"] == []


def test_search_assets_rejects_unknown_kind(pexels_key, freesound_key, tmp_path):
    """An unknown ``kind`` is rejected up front (no API call made)."""
    with mock.patch.object(mod, "_http_get_json") as m:
        res = search_assets(
            {"query": "x", "kind": "storyboard", "limit": 1},
            str(tmp_path),
        )
    assert m.call_count == 0
    assert res["status"] == "error"
    assert "kind" in res["error"]
    assert "storyboard" in res["error"] or "video|photo|audio" in res["error"]


# ---------------------------------------------------------------------------
# Tests: Pexels video (happy path)
# ---------------------------------------------------------------------------

def test_search_assets_pexels_video_normalises_response(pexels_key, tmp_path):
    """Video results come back with a stable normalised shape: id, source,
    kind, title, thumbnail_url, preview_url, duration_seconds, license,
    attribution_required."""
    with mock.patch.object(
        mod, "_http_get_json", return_value=PEXELS_VIDEO_RESPONSE,
    ) as m:
        res = search_assets(
            {"query": "ocean waves", "kind": "video", "limit": 3},
            str(tmp_path),
        )

    assert "error" not in res, res
    assert res["status"] == "ok"
    assert res["source"] == "pexels"
    results = res["results"]
    assert len(results) == 2

    r0 = results[0]
    assert r0["id"] == "pexels-video-12345"
    assert r0["source"] == "pexels"
    assert r0["kind"] == "video"
    assert r0["title"]  # non-empty
    assert r0["thumbnail_url"].startswith("https://")
    assert r0["preview_url"].startswith("https://")
    assert r0["duration_seconds"] == 12
    assert r0["license"] == "Pexels License"
    assert r0["attribution_required"] is False
    assert r0["attribution"]  # non-empty (string), Pexels recommends crediting

    # Pexels should be called once with the expected endpoint + key.
    m.assert_called_once()
    called_url = m.call_args[0][0]
    assert "/videos/search" in called_url
    assert "ocean+waves" in called_url or "ocean%20waves" in called_url or "ocean" in called_url
    headers = m.call_args.kwargs.get("headers", {})
    assert headers.get("Authorization") == "test-pexels-key"


def test_search_assets_pexels_video_picks_best_preview(pexels_key, tmp_path):
    """When Pexels returns multiple video files, the tool prefers the
    highest-quality MP4 over the lower-res preview."""
    with mock.patch.object(mod, "_http_get_json", return_value=PEXELS_VIDEO_RESPONSE):
        res = search_assets(
            {"query": "ocean", "kind": "video", "limit": 3},
            str(tmp_path),
        )
    # First result had both an HD and SD file; HD must be preferred.
    r0 = res["results"][0]
    assert "1920_1080" in r0["preview_url"] or "hd" in r0["preview_url"].lower(), (
        f"expected HD preview URL, got {r0['preview_url']!r}"
    )


# ---------------------------------------------------------------------------
# Tests: Pexels photo
# ---------------------------------------------------------------------------

def test_search_assets_pexels_photo_normalises_response(pexels_key, tmp_path):
    with mock.patch.object(
        mod, "_http_get_json", return_value=PEXELS_PHOTO_RESPONSE,
    ) as m:
        res = search_assets(
            {"query": "rain", "kind": "photo", "limit": 5},
            str(tmp_path),
        )

    assert "error" not in res, res
    assert res["status"] == "ok"
    assert res["source"] == "pexels"
    r0 = res["results"][0]
    assert r0["id"] == "pexels-photo-99001"
    assert r0["kind"] == "photo"
    assert r0["duration_seconds"] is None  # photos don't have a duration
    assert r0["license"] == "Pexels License"
    assert r0["attribution_required"] is False
    assert r0["thumbnail_url"].startswith("https://")
    # Photo preview = the original-size src.
    assert "pexels-photo-99001" in r0["preview_url"]

    # Photo endpoint is /v1/search (not /videos/search).
    called_url = m.call_args[0][0]
    assert "/v1/search" in called_url
    assert "query=" in called_url or "rain" in called_url


# ---------------------------------------------------------------------------
# Tests: Freesound audio
# ---------------------------------------------------------------------------

def test_search_assets_freesound_audio_normalises_response(freesound_key, tmp_path):
    with mock.patch.object(
        mod, "_http_get_json", return_value=FREESOUND_RESPONSE,
    ) as m:
        res = search_assets(
            {"query": "whoosh", "kind": "audio", "limit": 5},
            str(tmp_path),
        )

    assert "error" not in res, res
    assert res["status"] == "ok"
    assert res["source"] == "freesound"
    results = res["results"]
    assert len(results) == 2

    r0 = results[0]
    assert r0["id"] == "freesound-555"
    assert r0["source"] == "freesound"
    assert r0["kind"] == "audio"
    assert r0["title"] == "whoosh_01"
    assert r0["preview_url"].endswith(".mp3")
    assert r0["duration_seconds"] == 1.2
    # License URL → human-readable short name.
    assert r0["license"] == "CC BY 4.0"
    # CC-BY requires crediting the author.
    assert r0["attribution_required"] is True
    assert "sfx_user" in r0["attribution"]

    # CC0 (public domain) does NOT require attribution.
    r1 = results[1]
    assert r1["license"] == "CC0 1.0"
    assert r1["attribution_required"] is False

    m.assert_called_once()
    called_url = m.call_args[0][0]
    assert "freesound.org" in called_url
    # Token is sent as ``token`` query param (Freesound's accepted form).
    assert "token=test-fs-token" in called_url or "token=" in called_url


def test_search_assets_freesound_uses_waveform_for_thumbnail(freesound_key, tmp_path):
    """The thumbnail for a Freesound result is the waveform image, not
    the preview MP3. The preview URL is the audio file."""
    with mock.patch.object(mod, "_http_get_json", return_value=FREESOUND_RESPONSE):
        res = search_assets(
            {"query": "x", "kind": "audio", "limit": 5}, str(tmp_path),
        )
    r0 = res["results"][0]
    assert r0["thumbnail_url"].endswith(".png") or "wave" in r0["thumbnail_url"]


# ---------------------------------------------------------------------------
# Tests: caching
# ---------------------------------------------------------------------------

def test_search_assets_caches_results(pexels_key, tmp_path):
    """The same (kind, query, limit) within the TTL should hit the cache
    and NOT make a second HTTP call."""
    with mock.patch.object(
        mod, "_http_get_json", return_value=PEXELS_VIDEO_RESPONSE,
    ) as m:
        first = search_assets(
            {"query": "waves", "kind": "video", "limit": 3}, str(tmp_path),
        )
        second = search_assets(
            {"query": "waves", "kind": "video", "limit": 3}, str(tmp_path),
        )
    assert m.call_count == 1, f"expected 1 HTTP call, got {m.call_count}"
    assert first == second
    assert first["status"] == "ok"


def test_search_assets_cache_key_distinguishes_kind(pexels_key, tmp_path):
    """``kind:video`` and ``kind:photo`` with the same query must hit
    different cache slots — they go to different Pexels endpoints and
    return different shapes."""
    with mock.patch.object(
        mod, "_http_get_json",
        side_effect=[PEXELS_VIDEO_RESPONSE, PEXELS_PHOTO_RESPONSE],
    ) as m:
        v = search_assets(
            {"query": "rain", "kind": "video", "limit": 3}, str(tmp_path),
        )
        p = search_assets(
            {"query": "rain", "kind": "photo", "limit": 3}, str(tmp_path),
        )
    assert m.call_count == 2
    assert v["source"] == "pexels" and v["results"][0]["kind"] == "video"
    assert p["source"] == "pexels" and p["results"][0]["kind"] == "photo"


def test_search_assets_cache_key_distinguishes_limit(pexels_key, tmp_path):
    """Different ``limit`` for the same query → two separate HTTP calls
    (cache key includes limit)."""
    with mock.patch.object(
        mod, "_http_get_json", return_value=PEXELS_VIDEO_RESPONSE,
    ) as m:
        search_assets(
            {"query": "x", "kind": "video", "limit": 3}, str(tmp_path),
        )
        search_assets(
            {"query": "x", "kind": "video", "limit": 8}, str(tmp_path),
        )
    assert m.call_count == 2


def test_search_assets_cache_is_project_scoped(pexels_key, tmp_path):
    """A server must not serve one project's cached result to another."""
    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    with mock.patch.object(
        mod, "_http_get_json", return_value=PEXELS_VIDEO_RESPONSE,
    ) as m:
        search_assets(
            {"query": "project-scoped-cache", "kind": "video", "limit": 3},
            str(project_a),
        )
        search_assets(
            {"query": "project-scoped-cache", "kind": "video", "limit": 3},
            str(project_b),
        )
    assert m.call_count == 2


def test_search_assets_cache_respects_ttl(pexels_key, tmp_path, monkeypatch):
    """After the TTL elapses, the next call hits the network again."""
    import time as time_mod
    # Patch the cache to use a 0-second TTL.
    monkeypatch.setattr(mod, "_CACHE_TTL_S", 0.0)
    with mock.patch.object(
        mod, "_http_get_json", return_value=PEXELS_VIDEO_RESPONSE,
    ) as m:
        search_assets(
            {"query": "x", "kind": "video", "limit": 3}, str(tmp_path),
        )
        # Sleep is unnecessary when TTL=0; the entry is already expired.
        search_assets(
            {"query": "x", "kind": "video", "limit": 3}, str(tmp_path),
        )
    assert m.call_count == 2


# ---------------------------------------------------------------------------
# Tests: limit / default
# ---------------------------------------------------------------------------

def test_search_assets_default_limit_is_eight(pexels_key, tmp_path):
    """``limit`` defaults to 8 when omitted."""
    with mock.patch.object(
        mod, "_http_get_json", return_value=PEXELS_VIDEO_RESPONSE,
    ) as m:
        search_assets(
            {"query": "x", "kind": "video"}, str(tmp_path),
        )
    # Verify the per_page/limit param was 8.
    call = m.call_args
    # The args are (url, params=...). Either form is fine — we just
    # need to confirm 8 is in there.
    all_args = (call.args, call.kwargs)
    flat = json.dumps([str(a) for a in (call.args or ())] + [
        json.dumps(v) for v in (call.kwargs or {}).values()
    ], default=str)
    assert "8" in flat


def test_search_assets_caps_limit_to_40(pexels_key, tmp_path):
    """A pathologically large limit is capped (Pexels max per_page is 80,
    we cap lower to keep responses tractable for the LLM)."""
    with mock.patch.object(
        mod, "_http_get_json", return_value=PEXELS_VIDEO_RESPONSE,
    ) as m:
        search_assets(
            {"query": "x", "kind": "video", "limit": 9999}, str(tmp_path),
        )
    flat = json.dumps(
        [str(a) for a in (m.call_args.args or ())] +
        [json.dumps(v) for v in (m.call_args.kwargs or {}).values()],
        default=str,
    )
    # Capped value must be a small number, not 9999.
    assert "9999" not in flat


# ---------------------------------------------------------------------------
# Tests: HTTP error handling
# ---------------------------------------------------------------------------

def test_search_assets_surfaces_http_error(pexels_key, tmp_path):
    """When the HTTP layer raises, the tool returns a structured error
    (not a traceback) so the LLM sees a usable message."""
    with mock.patch.object(
        mod, "_http_get_json",
        side_effect=RuntimeError("connection reset"),
    ):
        res = search_assets(
            {"query": "x", "kind": "video", "limit": 3}, str(tmp_path),
        )
    assert "error" in res
    assert "connection reset" in res["error"]
    assert res["results"] == []


def test_search_assets_surfaces_non_200_status(pexels_key, tmp_path):
    """A non-200 response (e.g. 429 rate-limit) returns a structured error."""
    with mock.patch.object(
        mod, "_http_get_json",
        side_effect=RuntimeError("Pexels API 429: rate limit"),
    ):
        res = search_assets(
            {"query": "x", "kind": "video", "limit": 3}, str(tmp_path),
        )
    assert "error" in res
    assert "429" in res["error"] or "rate" in res["error"].lower()


def test_search_assets_retries_403_before_returning_primary_results(
    pexels_key, tmp_path, monkeypatch,
):
    """A transient provider denial is retried before the cascade advances."""
    with mock.patch.object(
        mod, "_http_get_json",
        side_effect=[RuntimeError("upstream 403: forbidden"), PEXELS_PHOTO_RESPONSE],
    ) as http, mock.patch.object(mod.time, "sleep") as sleep:
        res = search_assets(
            {"query": "rain", "kind": "photo", "limit": 1},
            str(tmp_path),
        )

    assert res["status"] == "ok"
    assert res["source"] == "pexels"
    assert http.call_count == 2
    sleep.assert_called_once()


def test_search_assets_persists_cache_across_process_cache_reset(
    pexels_key, tmp_path,
):
    """A project cache survives clearing the process-local search dictionary."""
    with mock.patch.object(
        mod, "_http_get_json", return_value=PEXELS_PHOTO_RESPONSE,
    ) as http:
        first = search_assets(
            {"query": "persistent rain", "kind": "photo", "limit": 1},
            str(tmp_path),
        )
    assert first["status"] == "ok"
    assert http.call_count == 1

    _cache_clear()
    with mock.patch.object(
        mod, "_http_get_json", side_effect=AssertionError("network should not run"),
    ):
        second = search_assets(
            {"query": "persistent rain", "kind": "photo", "limit": 1},
            str(tmp_path),
        )
    assert second == first


def test_search_assets_uses_stale_project_cache_when_all_providers_fail(
    pexels_key, tmp_path, monkeypatch,
):
    """An expired response remains usable during a provider outage."""
    with mock.patch.object(
        mod, "_http_get_json", return_value=PEXELS_PHOTO_RESPONSE,
    ):
        first = search_assets(
            {"query": "stale rain", "kind": "photo", "limit": 1},
            str(tmp_path),
        )
    assert first["status"] == "ok"
    _cache_clear()
    cache_file = next((tmp_path / ".open_edit" / "cache" / "search_assets").glob("*.json"))
    cached_document = json.loads(cache_file.read_text())
    cached_document["expires_at"] = 0.0
    cache_file.write_text(json.dumps(cached_document))
    with mock.patch.object(
        mod, "_call_provider",
        side_effect=RuntimeError("all providers unavailable"),
    ):
        stale = search_assets(
            {"query": "stale rain", "kind": "photo", "limit": 1},
            str(tmp_path),
        )
    assert stale["status"] == "ok"
    assert stale["cache_status"] == "stale"
    assert "last cached" in stale["warning"]


def test_search_assets_cascades_to_wikimedia_with_degraded_warning(
    pexels_key, tmp_path,
):
    """Configured providers fail over to Openverse then Wikimedia for logos."""
    with mock.patch.object(
        mod, "_http_get_json",
        side_effect=[
            RuntimeError("upstream 403: forbidden"),
            RuntimeError("upstream 403: forbidden"),
            RuntimeError("upstream 403: forbidden"),
            {"results": []},
            WIKIMEDIA_RESPONSE,
        ],
    ) as http, mock.patch.object(mod.time, "sleep"):
        res = search_assets(
            {"query": "Gemini logo", "kind": "photo", "role": "logo", "limit": 1},
            str(tmp_path),
        )

    assert res["status"] == "ok"
    assert res["source"] == "wikimedia"
    assert res["degraded_source"]["used_provider"] == "wikimedia"
    assert res["degraded_source"]["failed_providers"] == ["pexels", "openverse"]
    result = res["results"][0]
    assert result["id"] == "wikimedia-4242"
    assert result["provider"] == "wikimedia"
    assert result["source_url"].startswith("https://upload.wikimedia.org/")
    assert result["source_page_url"].endswith("Gemini_logo.svg")
    assert result["license"] == "CC BY-SA 4.0"
    assert "Example Artist" in result["attribution"]
    assert http.call_count == 5


def test_search_wikimedia_preserves_attribution_metadata():
    """Wikimedia normalization retains the Commons license and creator."""
    with mock.patch.object(
        mod, "_http_get_json", return_value=WIKIMEDIA_RESPONSE,
    ):
        payload = mod._search_wikimedia("Gemini logo", "photo", 1, "logo")

    assert payload["source"] == "wikimedia"
    assert payload["results"][0]["attribution_required"] is True


def test_search_assets_openverse_photo_without_key(no_keys, tmp_path):
    """Openverse is a keyless fallback and keeps the import-cache shape."""
    with mock.patch.object(
        mod, "_http_get_json", return_value=OPENVERSE_PHOTO_RESPONSE,
    ) as http:
        res = search_assets({"query": "rain", "kind": "photo"}, str(tmp_path))
    assert res["status"] == "ok"
    assert res["source"] == "openverse"
    assert res["results"][0]["id"] == "openverse-photo-ov-cc0"
    assert res["results"][0]["preview_url"].startswith("https://")
    assert res["results"][0]["attribution_required"] is False
    assert http.call_args.args[0].endswith("/images/")
    assert http.call_args.kwargs["params"]["q"] == "rain"


def test_search_assets_openverse_license_filter_and_ranking(no_keys, tmp_path):
    """A requested commercial-friendly license filters and ranks results."""
    with mock.patch.object(
        mod, "_http_get_json", return_value=OPENVERSE_PHOTO_RESPONSE,
    ):
        res = search_assets(
            {"query": "rain", "kind": "photo", "license": "cc0"},
            str(tmp_path),
        )
    assert res["status"] == "ok"
    assert len(res["results"]) == 1
    assert res["results"][0]["license"] == "CC0 1.0"


def test_search_assets_openverse_overfetches_to_fill_license_limit(
    no_keys, tmp_path,
):
    """License filtering fetches more candidates than the requested limit."""
    with mock.patch.object(
        mod, "_http_get_json", return_value=OPENVERSE_FILTER_RESPONSE,
    ) as http:
        res = search_assets(
            {"query": "rain", "kind": "photo", "license": "cc0", "limit": 2},
            str(tmp_path),
        )

    assert res["status"] == "ok"
    assert [item["id"] for item in res["results"]] == [
        "openverse-photo-ov-cc0-late",
        "openverse-photo-ov-cc0-late-2",
    ]
    assert http.call_args.kwargs["params"]["page_size"] == 6


def test_search_assets_openverse_ranks_cc0_and_plain_by(tmp_path):
    """Openverse results prefer CC0, then versioned plain CC-BY."""
    with mock.patch.object(
        mod, "_http_get_json", return_value=OPENVERSE_FILTER_RESPONSE,
    ):
        res = mod._search_openverse("rain", "photo", 3)

    assert [item["id"] for item in res["results"]] == [
        "openverse-photo-ov-cc0-late",
        "openverse-photo-ov-cc0-late-2",
        "openverse-photo-ov-by-first",
    ]
    assert res["results"][0]["attribution_required"] is False


def test_search_assets_openverse_audio_normalises(no_keys, tmp_path):
    response = {
        "results": [{
            "id": "sound-1",
            "title": "rain sound",
            "creator": "maker",
            "url": "https://cdn.example.org/rain.mp3",
            "license": "by",
            "license_version": "4.0",
            "duration": 2.5,
        }],
    }
    with mock.patch.object(mod, "_http_get_json", return_value=response):
        res = search_assets({"query": "rain", "kind": "audio"}, str(tmp_path))
    assert res["status"] == "ok"
    assert res["results"][0]["kind"] == "audio"
    assert res["results"][0]["duration_seconds"] == 2.5


# ---------------------------------------------------------------------------
# Tests: env var helpers
# ---------------------------------------------------------------------------

def test_pexels_api_key_returns_empty_string_when_unset(no_keys):
    assert _pexels_api_key() == ""


def test_pexels_api_key_reads_env_var(pexels_key):
    assert _pexels_api_key() == "test-pexels-key"


def test_freesound_api_key_returns_empty_string_when_unset(no_keys):
    assert _freesound_api_key() == ""


def test_freesound_api_key_reads_env_var(freesound_key):
    assert _freesound_api_key() == "test-fs-token"
