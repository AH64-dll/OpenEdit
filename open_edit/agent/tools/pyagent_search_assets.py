"""pyagent_search_assets: agent-initiated internet search for stock media.

Dispatches to:
- Pexels for ``kind in ("video", "photo")``
- Freesound for ``kind == "audio"``

Normalises the result into a stable shape so the LLM, the TS extension
and the frontend all see the same fields regardless of the source:

    {
        "id": str,                  # e.g. "pexels-video-12345"
        "source": str,              # "pexels" | "freesound"
        "kind": str,                # "video" | "photo" | "audio"
        "title": str,
        "thumbnail_url": str,
        "preview_url": str,         # playable URL (mp4 / mp3 / jpeg)
        "duration_seconds": float | None,
        "license": str,             # human-readable ("Pexels License" / "CC BY 4.0")
        "attribution_required": bool,
        "attribution": str,         # the credit text to display, "" if none
    }

When the relevant API key is missing, the tool returns a structured
``{"error": "...", "results": []}`` payload rather than crashing — the
LLM can read the error and the UI can render a helpful message.

Caching: a small in-memory dict keyed by ``kind:query:limit`` with a
5-minute TTL (configurable via ``_CACHE_TTL_S``). The cache lives for
the lifetime of the process; it's wiped on server restart. This is
deliberately simple — sqlite would be overkill for v1.4 (one entry
per LLM turn, server lifetime is hours at most).

Environment
-----------
``OPEN_EDIT_PEXELS_API_KEY``     — Pexels API key (header auth).
``OPEN_EDIT_FREESOUND_API_KEY``  — Freesound API token (query-param auth).
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from typing import Any

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# How long a cached (kind, query, limit) entry stays valid. 5 min is a
# good default: long enough to survive a multi-step agent turn, short
# enough that the user can re-roll a query without hitting the API.
_CACHE_TTL_S: float = 300.0

# Cap on per-call ``limit`` to keep responses tractable for the LLM.
# Pexels' own per_page max is 80; we cap lower because the LLM rarely
# needs more than a handful of choices and large responses bloat the
# context.
_MAX_LIMIT: int = 40
_DEFAULT_LIMIT: int = 8

# Network timeout for upstream calls. Short enough that a hung API
# doesn't block the chat turn for too long.
_HTTP_TIMEOUT_S: float = 20.0

_PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"
_PEXELS_PHOTO_URL = "https://api.pexels.com/v1/search"
_FREESOUND_SEARCH_URL = "https://freesound.org/apiv2/search/text/"


# ---------------------------------------------------------------------------
# Env-var helpers
# ---------------------------------------------------------------------------

def _pexels_api_key() -> str:
    return os.environ.get("OPEN_EDIT_PEXELS_API_KEY", "").strip()


def _freesound_api_key() -> str:
    return os.environ.get("OPEN_EDIT_FREESOUND_API_KEY", "").strip()


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _http_get_json(url: str, *, headers: dict[str, str] | None = None,
                   params: dict[str, Any] | None = None,
                   timeout: float = _HTTP_TIMEOUT_S) -> dict[str, Any]:
    """GET ``url`` (optionally with query params) and return parsed JSON.

    Raises ``RuntimeError`` with a useful message on non-200 status or
    network failure. The bridge layer catches and rewraps this as a
    structured tool result.
    """
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        # Read the body for a more useful error message (e.g. rate-limit text).
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            detail = ""
        raise RuntimeError(
            f"upstream {exc.code} for {url}: {detail or exc.reason}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"network error for {url}: {exc.reason}"
        ) from exc
    if status != 200:
        raise RuntimeError(f"upstream HTTP {status} for {url}")
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"upstream returned non-JSON for {url}: {exc}") from exc


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _cache_key(kind: str, query: str, limit: int) -> str:
    # Lowercase the query so "Rain" and "rain" share the cache slot.
    return f"{kind}:{query.strip().lower()}:{limit}"


def _cache_get(key: str) -> dict[str, Any] | None:
    entry = _CACHE.get(key)
    if entry is None:
        return None
    ts, value = entry
    if (time.monotonic() - ts) > _CACHE_TTL_S:
        _CACHE.pop(key, None)
        return None
    return value


def _cache_put(key: str, value: dict[str, Any]) -> None:
    _CACHE[key] = (time.monotonic(), value)


def _cache_clear() -> None:
    _CACHE.clear()


# ---------------------------------------------------------------------------
# License normalisation (Freesound)
# ---------------------------------------------------------------------------

# Map a Freesound license URL to a human-readable short name. Unknown
# URLs fall through to the URL itself (better than a blank string — at
# least the user sees the terms URL).
_FREESOUND_LICENSE_MAP: dict[str, str] = {
    "https://creativecommons.org/publicdomain/zero/1.0/": "CC0 1.0",
    "https://creativecommons.org/licenses/by/4.0/": "CC BY 4.0",
    "https://creativecommons.org/licenses/by/3.0/": "CC BY 3.0",
    "https://creativecommons.org/licenses/by/2.0/": "CC BY 2.0",
    "https://creativecommons.org/licenses/by-sa/4.0/": "CC BY-SA 4.0",
    "https://creativecommons.org/licenses/by-sa/3.0/": "CC BY-SA 3.0",
    "https://creativecommons.org/licenses/by-nc/4.0/": "CC BY-NC 4.0",
    "https://creativecommons.org/licenses/by-nc/3.0/": "CC BY-NC 3.0",
    "https://creativecommons.org/licenses/by-nc-sa/4.0/": "CC BY-NC-SA 4.0",
    "https://creativecommons.org/licenses/by-nd/4.0/": "CC BY-ND 4.0",
    "https://creativecommons.org/licenses/by-nc-nd/4.0/": "CC BY-NC-ND 4.0",
    "https://creativecommons.org/licenses/sampling+/1.0/": "Sampling+ 1.0",
}


def _short_license(url: str) -> str:
    return _FREESOUND_LICENSE_MAP.get(url, url or "")


def _freesound_attribution_required(license_url: str) -> bool:
    """CC0 = no attribution required; everything else does."""
    if not license_url:
        return True  # conservative default when unknown
    return "publicdomain/zero" not in license_url.lower()


def _freesound_attribution_text(name: str, username: str, license_short: str) -> str:
    """Human-readable credit line, e.g. ``'whoosh_01' by sfx_user (CC BY 4.0)``."""
    bits: list[str] = []
    if name:
        bits.append(f"'{name}'")
    if username:
        bits.append(f"by {username}")
    if license_short:
        bits.append(f"({license_short})")
    return " ".join(bits)


# ---------------------------------------------------------------------------
# Source dispatchers
# ---------------------------------------------------------------------------

def _search_pexels_video(query: str, limit: int) -> dict[str, Any]:
    params = {"query": query, "per_page": limit, "page": 1}
    url = _PEXELS_VIDEO_URL + "?" + urllib.parse.urlencode(params)
    data = _http_get_json(
        url,
        headers={"Authorization": _pexels_api_key()},
    )
    results: list[dict[str, Any]] = []
    for v in data.get("videos", []) or []:
        # Pick the best (highest-quality) MP4 preview. Pexels
        # sometimes returns several; we prefer HD over SD, then any
        # video file at all.
        files = v.get("video_files") or []
        mp4s = [f for f in files if (f.get("file_type") or "").lower() == "video/mp4"]
        if not mp4s:
            continue
        # Sort: highest quality first, then widest. Quality is a
        # Pexels-assigned label ("4k" > "hd" > "sd"). When quality is
        # missing, fall back to width (some Pexels responses omit
        # quality but include width).
        quality_rank = {"4k": 3, "hd": 2, "sd": 1}
        mp4s.sort(
            key=lambda f: (
                quality_rank.get((f.get("quality") or "").lower(), 0),
                f.get("width") or 0,
                f.get("id") or 0,
            ),
            reverse=True,
        )
        preview = mp4s[0].get("link") or ""
        if not preview:
            continue
        # The image field is a JPEG poster. Pexels returns a
        # relative path; we keep it as-is (it's already a full URL).
        results.append({
            "id": f"pexels-video-{v.get('id', '')}",
            "source": "pexels",
            "kind": "video",
            "title": v.get("url") or f"Pexels video {v.get('id', '')}",
            "thumbnail_url": v.get("image") or "",
            "preview_url": preview,
            "duration_seconds": v.get("duration"),
            "license": "Pexels License",
            "attribution_required": False,
            # Pexels doesn't *require* attribution but crediting is
            # appreciated. We leave a hint string so the UI can show
            # "Source: Pexels" as a courtesy.
            "attribution": "Source: Pexels",
        })
    return {"source": "pexels", "results": results}


def _search_pexels_photo(query: str, limit: int) -> dict[str, Any]:
    params = {"query": query, "per_page": limit, "page": 1}
    url = _PEXELS_PHOTO_URL + "?" + urllib.parse.urlencode(params)
    data = _http_get_json(
        url,
        headers={"Authorization": _pexels_api_key()},
    )
    results: list[dict[str, Any]] = []
    for p in data.get("photos", []) or []:
        src = p.get("src") or {}
        preview = src.get("original") or src.get("large") or src.get("medium") or ""
        thumb = src.get("medium") or src.get("small") or src.get("portrait") or preview
        if not preview:
            continue
        photographer = p.get("photographer") or ""
        # Pexels photo license page URL is the photo's own page.
        page_url = p.get("url") or ""
        title = p.get("alt") or page_url or f"Pexels photo {p.get('id', '')}"
        results.append({
            "id": f"pexels-photo-{p.get('id', '')}",
            "source": "pexels",
            "kind": "photo",
            "title": title,
            "thumbnail_url": thumb,
            "preview_url": preview,
            "duration_seconds": None,
            "license": "Pexels License",
            "attribution_required": False,
            "attribution": (
                f"Photo by {photographer} on Pexels" if photographer else ""
            ),
        })
    return {"source": "pexels", "results": results}


def _search_freesound(query: str, limit: int) -> dict[str, Any]:
    params = {
        "query": query,
        "page_size": limit,
        "token": _freesound_api_key(),
    }
    url = _FREESOUND_SEARCH_URL + "?" + urllib.parse.urlencode(params)
    data = _http_get_json(url)
    results: list[dict[str, Any]] = []
    for r in data.get("results", []) or []:
        preview = r.get("preview_hq") or r.get("preview_lq") or ""
        if not preview:
            continue
        license_url = r.get("license") or ""
        license_short = _short_license(license_url)
        name = r.get("name") or ""
        username = r.get("username") or ""
        images = r.get("images") or {}
        thumb = images.get("waveform_m") or images.get("spectral_m") or ""
        results.append({
            "id": f"freesound-{r.get('id', '')}",
            "source": "freesound",
            "kind": "audio",
            "title": name or f"Freesound {r.get('id', '')}",
            "thumbnail_url": thumb,
            "preview_url": preview,
            "duration_seconds": r.get("duration"),
            "license": license_short,
            "attribution_required": _freesound_attribution_required(license_url),
            "attribution": _freesound_attribution_text(
                name, username, license_short,
            ),
        })
    return {"source": "freesound", "results": results}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

_VALID_KINDS = ("video", "photo", "audio")


def search_assets(args: dict, project_path: str) -> dict:
    """Search Pexels / Freesound for stock media matching ``args['query']``.

    The ``project_path`` is unused (the tool is project-agnostic) but
    is part of the standard tool signature so the bridge can dispatch
    uniformly. Future versions might scope the search to the project's
    style profile.
    """
    query = (args.get("query") or "").strip()
    if not query:
        return {
            "error": "search_assets: 'query' is required and must be non-empty",
            "results": [],
        }

    kind = (args.get("kind") or "").strip().lower()
    if kind not in _VALID_KINDS:
        return {
            "error": (
                f"search_assets: invalid kind={args.get('kind')!r}; "
                f"expected one of: {', '.join(_VALID_KINDS)}"
            ),
            "results": [],
            "valid_kinds": list(_VALID_KINDS),
        }

    try:
        limit = int(args.get("limit") or _DEFAULT_LIMIT)
    except (TypeError, ValueError):
        limit = _DEFAULT_LIMIT
    if limit <= 0:
        limit = _DEFAULT_LIMIT
    limit = min(limit, _MAX_LIMIT)

    # Env-var gating — graceful degradation, never crash the chat turn.
    if kind in ("video", "photo"):
        if not _pexels_api_key():
            return {
                "error": (
                    "OPEN_EDIT_PEXELS_API_KEY not set; "
                    "set it (and OPEN_EDIT_FREESOUND_API_KEY for audio) "
                    "in your environment, then restart the server. "
                    "See .env.example for the full list."
                ),
                "results": [],
            }
    elif kind == "audio":
        if not _freesound_api_key():
            return {
                "error": (
                    "OPEN_EDIT_FREESOUND_API_KEY not set; "
                    "set it (and OPEN_EDIT_PEXELS_API_KEY for video/photo) "
                    "in your environment, then restart the server. "
                    "See .env.example for the full list."
                ),
                "results": [],
            }

    # Cache lookup. Key includes kind + query + limit so different
    # requests for the same query don't conflate.
    cache_key = _cache_key(kind, query, limit)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    # Dispatch to the right backend.
    try:
        if kind == "video":
            payload = _search_pexels_video(query, limit)
        elif kind == "photo":
            payload = _search_pexels_photo(query, limit)
        else:  # audio
            payload = _search_freesound(query, limit)
    except Exception as exc:  # noqa: BLE001 — surface any upstream error
        return {"error": f"search_assets({kind}) failed: {exc}", "results": []}

    # Stash query/kind in the payload for cache-key introspection +
    # frontend rendering. The frontend uses these to drive the
    # "Search again for <query>" affordance.
    payload.setdefault("query", query)
    payload.setdefault("kind", kind)
    payload.setdefault("limit", limit)
    _cache_put(cache_key, payload)

    # Also write each result to the import-side cache so a follow-up
    # ``import_asset(result_id=...)`` call can look up the license /
    # attribution without the LLM having to re-pass them. Best-effort —
    # see ``_store_result`` for failure modes.
    try:
        from open_edit.agent.tools.pyagent_import_asset import (
            _SEARCH_RESULT_CACHE_DIR,
            _store_result,
        )
        for r in payload.get("results", []):
            _store_result(_SEARCH_RESULT_CACHE_DIR, r)
    except Exception:
        # Never let cache writes crash the search.
        pass

    return payload
