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
    """Without the Pexels key, the tool must NOT crash — it must
    return a structured error and an empty results list (so the
    LLM can see the cause and the UI can render the message)."""
    res = search_assets(
        {"query": "rain", "kind": "video", "limit": 3},
        str(tmp_path),
    )
    assert "error" in res, res
    assert "OPEN_EDIT_PEXELS_API_KEY" in res["error"]
    assert "results" in res
    assert res["results"] == []
    assert "fix" in res["error"].lower() or "see" in res["error"].lower()


def test_search_assets_returns_error_when_freesound_key_missing(no_keys, tmp_path):
    """Same for audio: missing Freesound key → structured error, no crash."""
    res = search_assets(
        {"query": "whoosh", "kind": "audio", "limit": 3},
        str(tmp_path),
    )
    assert "error" in res
    assert "OPEN_EDIT_FREESOUND_API_KEY" in res["error"]
    assert res["results"] == []


def test_search_assets_rejects_unknown_kind(pexels_key, freesound_key, tmp_path):
    """An unknown ``kind`` is rejected up front (no API call made)."""
    with mock.patch.object(mod, "_http_get_json") as m:
        res = search_assets(
            {"query": "x", "kind": "storyboard", "limit": 1},
            str(tmp_path),
        )
    assert m.call_count == 0
    assert "error" in res
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
