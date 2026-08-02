"""pyagent_search_assets: durable, provider-cascaded stock media search.

Configured Pexels/Freesound providers are attempted first, followed by
Openverse and (for still images, logos, and icons) Wikimedia Commons. Every
provider is normalized to the same result contract and provider failures are
isolated from the editing pipeline. Search responses are cached under the
project's ``.open_edit/cache`` directory so a server restart does not discard
usable results.

Normalises the result into a stable shape so the LLM, the TS extension
and the frontend all see the same fields regardless of the source:

    {
        "id": str,                  # e.g. "pexels-video-12345"
        "source": str,              # provider id
        "provider": str,            # same as source
        "kind": str,                # "video" | "photo" | "audio"
        "title": str,
        "thumbnail_url": str,
        "preview_url": str,         # playable URL (mp4 / mp3 / jpeg)
        "source_url": str,          # exact bytes to import
        "source_page_url": str,     # human-facing source page
        "duration_seconds": float | None,
        "license": str,             # human-readable license
        "license_url": str,
        "content_hash": str,        # populated after import when bytes are fetched
        "attribution_required": bool,
        "attribution": str,         # the credit text to display, "" if none
    }

When the relevant API key is missing, the tool returns a structured
``{"status": "error", "error": "...", "results": []}`` payload rather
than crashing — the LLM can read the error and the UI can render a
helpful message.

Caching uses a process-local fast path plus an atomic JSON cache under the
project. The key includes provider role, kind, query, license, and limit.
Expired entries remain available as a stale fallback if every provider is
temporarily unavailable.

Environment
-----------
``OPEN_EDIT_PEXELS_API_KEY``     — Pexels API key (header auth).
``OPEN_EDIT_FREESOUND_API_KEY``  — Freesound API token (query-param auth).
``OPEN_EDIT_OPENVERSE_API_KEY``  — optional Openverse bearer token.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from open_edit.agent.tools._contract import tool_result

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
# context. Must stay <= the serve result capper's list cap
# (open_edit/serve/result_capper.py: _MAX_LIST_ITEMS = 20), otherwise
# items 21..N are fetched, charged, and then discarded as ``[...]``.
_MAX_LIMIT: int = 20
_DEFAULT_LIMIT: int = 8
_OPENVERSE_MAX_FETCH: int = 100
_MAX_PROVIDER_ATTEMPTS: int = 3
_RETRY_BACKOFF_S = (0.05, 0.15)

# Network timeout for upstream calls. Short enough that a hung API
# doesn't block the chat turn for too long.
_HTTP_TIMEOUT_S: float = 20.0
_HTTP_RESPONSE_CHUNK_BYTES: int = 64 * 1024
_MAX_RESPONSE_BYTES: int = 8 * 1024 * 1024

_PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"
_PEXELS_PHOTO_URL = "https://api.pexels.com/v1/search"
_FREESOUND_SEARCH_URL = "https://freesound.org/apiv2/search/text/"
_OPENVERSE_URL = "https://api.openverse.org/v1"
_WIKIMEDIA_API_URL = "https://commons.wikimedia.org/w/api.php"


# ---------------------------------------------------------------------------
# Env-var helpers
# ---------------------------------------------------------------------------

def _pexels_api_key() -> str:
    return os.environ.get("OPEN_EDIT_PEXELS_API_KEY", "").strip()


def _freesound_api_key() -> str:
    return os.environ.get("OPEN_EDIT_FREESOUND_API_KEY", "").strip()


def _openverse_api_key() -> str:
    return os.environ.get("OPEN_EDIT_OPENVERSE_API_KEY", "").strip()


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _endpoint_for_error(url: str) -> str:
    """Keep query parameters (including API tokens) out of error payloads."""
    try:
        parsed = urllib.parse.urlsplit(url)
        return urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, "", "")
        )
    except (TypeError, ValueError):
        return "<upstream>"


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
    endpoint = _endpoint_for_error(url)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = resp.read(_HTTP_RESPONSE_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > _MAX_RESPONSE_BYTES:
                    raise RuntimeError(
                        f"upstream response exceeds the {_MAX_RESPONSE_BYTES}-byte cap"
                    )
                chunks.append(chunk)
            body = b"".join(chunks).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        # Read the body for a more useful error message (e.g. rate-limit text).
        try:
            detail = exc.read(_MAX_RESPONSE_BYTES + 1).decode(
                "utf-8", errors="replace"
            )[:200]
        except Exception:
            detail = ""
        raise RuntimeError(
            f"upstream {exc.code} for {endpoint}: {detail or exc.reason}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"network error for {endpoint}: {exc.reason}"
        ) from exc
    if status != 200:
        raise RuntimeError(f"upstream HTTP {status} for {endpoint}")
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"upstream returned non-JSON for {endpoint}: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_SCHEMA = 1


def _cache_key(
    kind: str,
    query: str,
    limit: int,
    license: str = "any",
    role: str = "",
    provider_scope: str = "",
) -> str:
    """Build the durable key for one normalized search request."""
    # Lowercase the query so "Rain" and "rain" share the cache slot.
    return "|".join((
        kind.strip().lower(),
        query.strip().lower(),
        license.strip().lower(),
        role.strip().lower() or kind.strip().lower(),
        provider_scope.strip().lower(),
        str(limit),
    ))


def _project_cache_path(project_path: str | Path, key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return (
        Path(project_path).expanduser().resolve()
        / ".open_edit" / "cache" / "search_assets" / f"{digest}.json"
    )


def _memory_cache_key(
    project_path: str | Path | None, key: str,
) -> str:
    """Keep process-local results isolated when one server serves projects."""
    if not project_path:
        return key
    return f"{Path(project_path).expanduser().resolve()}::{key}"


def _read_persistent_cache(
    project_path: str | Path | None, key: str,
) -> tuple[dict[str, Any] | None, bool]:
    """Return ``(payload, is_stale)`` from the project cache."""
    if not project_path:
        return None, False
    path = _project_cache_path(project_path, key)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema") != _CACHE_SCHEMA:
            return None, False
        payload = document.get("payload")
        if not isinstance(payload, dict):
            return None, False
        is_stale = float(document.get("expires_at", 0.0)) <= time.time()
        return payload, is_stale
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None, False


def _cache_get(
    key: str, project_path: str | Path | None = None,
) -> dict[str, Any] | None:
    memory_key = _memory_cache_key(project_path, key)
    entry = _CACHE.get(memory_key)
    if entry is not None:
        ts, value = entry
        if (time.monotonic() - ts) <= _CACHE_TTL_S:
            return value
        _CACHE.pop(memory_key, None)
    payload, is_stale = _read_persistent_cache(project_path, key)
    if payload is not None and not is_stale:
        _CACHE[memory_key] = (time.monotonic(), payload)
        return payload
    return None


def _cache_put(
    key: str,
    value: dict[str, Any],
    project_path: str | Path | None = None,
    *,
    attempts: int = 1,
) -> None:
    _CACHE[_memory_cache_key(project_path, key)] = (time.monotonic(), value)
    if not project_path:
        return
    path = _project_cache_path(project_path, key)
    document = {
        "schema": _CACHE_SCHEMA,
        "cache_key": key,
        "provider": value.get("provider") or value.get("source") or "",
        "query": value.get("query", ""),
        "kind": value.get("kind", ""),
        "license": value.get("requested_license", "any"),
        "role": value.get("role", ""),
        "fetched_at": time.time(),
        "expires_at": time.time() + _CACHE_TTL_S,
        "attempts": attempts,
        "payload": value,
    }
    tmp_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as tmp:
            tmp_path = Path(tmp.name)
            json.dump(document, tmp, sort_keys=True)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_path, path)
    except (OSError, TypeError, ValueError):
        # Search remains useful if the cache directory is read-only.
        pass
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass


def _cache_stale(
    project_path: str | Path | None, key: str,
) -> dict[str, Any] | None:
    payload, is_stale = _read_persistent_cache(project_path, key)
    return payload if payload is not None and is_stale else None


def _is_retryable_provider_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in (
        " 403", " 408", " 429", "timeout", "timed out",
        "temporarily unavailable", "connection reset", "network error",
    ))


def _call_provider(
    provider: str,
    operation,
) -> tuple[dict[str, Any], int]:
    """Run one provider with bounded retry/backoff.

    Provider errors are deliberately raised after the retry budget so the
    cascade can try the next provider. The attempt count is retained in the
    durable cache metadata for diagnostics.
    """
    last_error: Exception | None = None
    for attempt in range(1, _MAX_PROVIDER_ATTEMPTS + 1):
        try:
            result = operation()
            return result, attempt
        except Exception as exc:  # noqa: BLE001 - isolate upstream failures
            last_error = exc
            if attempt >= _MAX_PROVIDER_ATTEMPTS or not _is_retryable_provider_error(exc):
                break
            time.sleep(_RETRY_BACKOFF_S[min(attempt - 1, len(_RETRY_BACKOFF_S) - 1)])
    assert last_error is not None
    raise RuntimeError(f"{provider}: {last_error}") from last_error


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
            "provider": "pexels",
            "kind": "video",
            "title": v.get("url") or f"Pexels video {v.get('id', '')}",
            "thumbnail_url": v.get("image") or "",
            "preview_url": preview,
            "source_url": preview,
            "source_page_url": v.get("url") or "",
            "duration_seconds": v.get("duration"),
            "license": "Pexels License",
            "license_url": "https://www.pexels.com/license/",
            "content_hash": "",
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
            "provider": "pexels",
            "kind": "photo",
            "title": title,
            "thumbnail_url": thumb,
            "preview_url": preview,
            "source_url": preview,
            "source_page_url": page_url,
            "duration_seconds": None,
            "license": "Pexels License",
            "license_url": "https://www.pexels.com/license/",
            "content_hash": "",
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
            "provider": "freesound",
            "kind": "audio",
            "title": name or f"Freesound {r.get('id', '')}",
            "thumbnail_url": thumb,
            "preview_url": preview,
            "source_url": preview,
            "source_page_url": r.get("url") or f"https://freesound.org/s/{r.get('id', '')}/",
            "duration_seconds": r.get("duration"),
            "license": license_short,
            "license_url": license_url,
            "content_hash": "",
            "attribution_required": _freesound_attribution_required(license_url),
            "attribution": _freesound_attribution_text(
                name, username, license_short,
            ),
        })
    return {"source": "freesound", "results": results}


def _openverse_license_name(item: dict[str, Any]) -> str:
    name = str(item.get("license") or "").strip()
    version = str(item.get("license_version") or "").strip()
    return f"{name.upper()} {version}".strip() or "Unknown"


def _license_token(license_name: str) -> str:
    """Return a punctuation-insensitive license token."""
    return "".join(char for char in license_name.lower() if char.isalnum())


def _is_cc0_license(license_name: str) -> bool:
    tok = _license_token(license_name)
    return tok.startswith("cc0") or "publicdomain" in tok


def _is_plain_by_license(license_name: str) -> bool:
    """Whether ``license_name`` is the plain CC-BY family."""
    tok = _license_token(license_name)
    if tok.startswith("cc"):
        tok = tok[2:]
    return tok.startswith("by") and not any(
        marker in tok for marker in ("sa", "nc", "nd")
    )


def _license_matches(license_name: str, requested: str) -> bool:
    if not requested or requested.lower() == "any":
        return True
    wanted = _license_token(requested)
    actual = _license_token(license_name)
    if wanted in {"cc0", "publicdomain"}:
        return _is_cc0_license(license_name)
    if wanted in {"by", "ccby"}:
        # Exact CC-BY family, not BY-SA / BY-NC.
        return _is_plain_by_license(license_name)
    if wanted in {"bysa", "ccbysa"}:
        return "bysa" in actual and "nc" not in actual
    # Exact token equality (avoid substring false positives).
    return actual == wanted or actual.startswith(wanted)


def _license_rank_key(license_name: str) -> tuple[int, int]:
    """Lower is better: prefer CC0, then plain BY, then everything else."""
    if _is_cc0_license(license_name):
        return (0, 0)
    if _is_plain_by_license(license_name):
        return (1, 0)
    return (2, 0)


def _search_openverse(
    query: str, kind: str, limit: int, requested_license: str = "any",
) -> dict[str, Any]:
    """Search Openverse and normalize its media records."""
    endpoint_kind = "images" if kind == "photo" else kind
    headers = {}
    if _openverse_api_key():
        headers["Authorization"] = f"Bearer {_openverse_api_key()}"
    # Over-fetch when filtering by license so local filter can still fill limit.
    requested_license = requested_license.strip() or "any"
    fetch_size = (
        min(_OPENVERSE_MAX_FETCH, max(limit * 3, limit))
        if requested_license.lower() != "any"
        else limit
    )
    data = _http_get_json(
        f"{_OPENVERSE_URL}/{endpoint_kind}/",
        headers=headers,
        params={"q": query, "page_size": fetch_size},
    )
    results: list[dict[str, Any]] = []
    for item in data.get("results", []) or []:
        preview = item.get("url") or item.get("audio_url") or ""
        if not preview:
            continue
        license_name = _openverse_license_name(item)
        if not _license_matches(license_name, requested_license):
            continue
        title = item.get("title") or f"Openverse {kind} {item.get('id', '')}"
        creator = str(item.get("creator") or "").strip()
        source_page_url = (
            item.get("foreign_landing_url")
            or item.get("detail_url")
            or item.get("creator_url")
            or ""
        )
        results.append({
            "id": f"openverse-{kind}-{item.get('id', '')}",
            "source": "openverse",
            "provider": "openverse",
            "kind": kind,
            "title": title,
            "thumbnail_url": item.get("thumbnail") or preview,
            "preview_url": preview,
            "source_url": preview,
            "source_page_url": source_page_url,
            "duration_seconds": item.get("duration") if kind == "audio" else None,
            "license": license_name,
            "license_url": item.get("license_url") or "",
            "content_hash": "",
            "attribution_required": not _is_cc0_license(license_name),
            "attribution": f"{title} by {creator} ({license_name})" if creator else "",
        })
    results.sort(key=lambda r: _license_rank_key(r["license"]))
    return {"source": "openverse", "results": results[:limit]}


def _metadata_value(metadata: dict[str, Any], key: str) -> str:
    value = metadata.get(key)
    if isinstance(value, dict):
        value = value.get("value")
    return str(value or "").strip()


def _search_wikimedia(
    query: str, kind: str, limit: int, role: str = "",
) -> dict[str, Any]:
    """Search Wikimedia Commons files and preserve page-level provenance."""
    if kind != "photo":
        return {"source": "wikimedia", "provider": "wikimedia", "results": []}
    search_text = " ".join(part for part in (role, query) if part).strip()
    data = _http_get_json(
        _WIKIMEDIA_API_URL,
        params={
            "action": "query",
            "generator": "search",
            "gsrsearch": search_text,
            "gsrnamespace": 6,
            "gsrlimit": limit,
            "prop": "imageinfo",
            "iiprop": "url|mime|size|extmetadata",
            "iiurlwidth": 1600,
            "format": "json",
            "formatversion": 2,
        },
    )
    results: list[dict[str, Any]] = []
    pages = (data.get("query") or {}).get("pages") or []
    for page in pages:
        image_info = (page.get("imageinfo") or [{}])[0]
        source_url = str(image_info.get("url") or "").strip()
        if not source_url.startswith("https://"):
            continue
        metadata = image_info.get("extmetadata") or {}
        title = str(page.get("title") or "").removeprefix("File:").strip()
        page_url = str(
            image_info.get("descriptionurl")
            or page.get("canonicalurl")
            or ""
        )
        license_name = _metadata_value(metadata, "LicenseShortName")
        license_name = license_name or "Wikimedia Commons"
        license_url = _metadata_value(metadata, "LicenseUrl")
        artist = _metadata_value(metadata, "Artist")
        page_id = page.get("pageid")
        stable_key = str(page_id or page_url or source_url or title)
        stable_id = f"wikimedia-{hashlib.sha256(stable_key.encode()).hexdigest()[:16]}"
        if page_id is not None:
            stable_id = f"wikimedia-{page_id}"
        attribution = (
            f"{artist} — Wikimedia Commons" if artist else "Wikimedia Commons"
        )
        results.append({
            "id": stable_id,
            "source": "wikimedia",
            "provider": "wikimedia",
            "kind": "photo",
            "role": role or "photo",
            "title": title or f"Wikimedia image {page_id or ''}".strip(),
            "thumbnail_url": image_info.get("thumburl") or source_url,
            "preview_url": source_url,
            "source_url": source_url,
            "source_page_url": page_url,
            "duration_seconds": None,
            "license": license_name,
            "license_url": license_url,
            "content_hash": "",
            "attribution_required": not _is_cc0_license(license_name),
            "attribution": attribution,
        })
    return {
        "source": "wikimedia",
        "provider": "wikimedia",
        "results": results[:limit],
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

_VALID_KINDS = ("video", "photo", "audio")


@tool_result
def search_assets(args: dict, project_path: str) -> dict:
    """Search the provider cascade for stock media."""
    query = (args.get("query") or "").strip()
    if not query:
        return {
            "status": "error",
            "error": "search_assets: 'query' is required and must be non-empty",
            "results": [],
        }

    kind = (args.get("kind") or "").strip().lower()
    if kind not in _VALID_KINDS:
        return {
            "status": "error",
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
    requested_license = str(args.get("license") or "any").strip() or "any"
    role = str(args.get("role") or "").strip().lower()

    provider_scope_parts: list[str] = []
    if requested_license.lower() == "any":
        if kind == "video" and _pexels_api_key():
            provider_scope_parts.append("pexels")
        elif kind == "photo" and _pexels_api_key():
            provider_scope_parts.append("pexels")
        elif kind == "audio" and _freesound_api_key():
            provider_scope_parts.append("freesound")
    provider_scope_parts.append("openverse")
    if kind == "photo":
        provider_scope_parts.append("wikimedia")
    provider_scope = ">".join(provider_scope_parts)
    cache_key = _cache_key(
        kind, query, limit, requested_license, role, provider_scope,
    )
    cached = _cache_get(cache_key, project_path)
    if cached is not None:
        return cached

    # Openverse's unauthenticated video endpoint is not a usable fallback in
    # practice. Keep the explicit configuration error instead of waiting
    # through a guaranteed 403; photos and audio still cascade keylessly.
    if (
        kind == "video"
        and requested_license.lower() == "any"
        and not _pexels_api_key()
    ):
        return {
            "status": "error",
            "error": (
                "search_assets(video): OPEN_EDIT_PEXELS_API_KEY is not set; "
                "set it to search Pexels video, or pass a license=... "
                "filter to use Openverse"
            ),
            "results": [],
        }

    provider_specs: list[tuple[str, Any]] = []
    license_any = requested_license.lower() == "any"
    if license_any:
        if kind == "video" and _pexels_api_key():
            provider_specs.append(
                ("pexels", lambda: _search_pexels_video(query, limit)),
            )
        elif kind == "photo" and _pexels_api_key():
            provider_specs.append(
                ("pexels", lambda: _search_pexels_photo(query, limit)),
            )
        elif kind == "audio" and _freesound_api_key():
            provider_specs.append(
                ("freesound", lambda: _search_freesound(query, limit)),
            )
    provider_specs.append((
        "openverse",
        lambda: _search_openverse(query, kind, limit, requested_license),
    ))
    if kind == "photo":
        provider_specs.append((
            "wikimedia",
            lambda: _search_wikimedia(query, kind, limit, role),
        ))

    failed_providers: list[str] = []
    provider_errors: dict[str, str] = {}
    attempts_by_provider: dict[str, int] = {}
    payload: dict[str, Any] | None = None
    served_stale = False
    for index, (provider, operation) in enumerate(provider_specs):
        try:
            candidate, attempts = _call_provider(provider, operation)
            attempts_by_provider[provider] = attempts
        except Exception as exc:  # noqa: BLE001 - continue the cascade
            failed_providers.append(provider)
            provider_errors[provider] = str(exc)
            continue
        candidate_results = candidate.get("results") or []
        has_later_provider = index < len(provider_specs) - 1
        if candidate_results or not has_later_provider:
            payload = candidate
            break
        failed_providers.append(provider)
        provider_errors[provider] = "provider returned no results"

    if payload is None:
        stale = _cache_stale(project_path, cache_key)
        if stale is not None:
            payload = dict(stale)
            served_stale = True
            payload["cache_status"] = "stale"
            payload["warning"] = (
                "All configured asset providers were unavailable; "
                "returned the last cached response."
            )
        else:
            detail = "; ".join(
                f"{provider}: {error}"
                for provider, error in provider_errors.items()
            )
            return {
                "status": "error",
                "error": (
                    f"search_assets({kind}) failed across providers"
                    + (f": {detail}" if detail else "")
                ),
                "results": [],
                "provider_failures": failed_providers,
            }

    payload.setdefault("query", query)
    payload.setdefault("kind", kind)
    payload.setdefault("limit", limit)
    payload.setdefault("role", role or kind)
    payload.setdefault("provider_scope", provider_scope)
    payload.setdefault("requested_license", requested_license)
    payload["status"] = "ok"
    payload.setdefault("provider", payload.get("source", ""))
    if failed_providers and payload.get("provider") != failed_providers[0]:
        payload["degraded_source"] = {
            "used_provider": payload.get("provider") or payload.get("source"),
            "failed_providers": failed_providers,
            "message": (
                "A configured provider failed; results came from the "
                "next available provider."
            ),
        }
    payload["provider_attempts"] = attempts_by_provider
    if not served_stale:
        _cache_put(
            cache_key, payload, project_path,
            attempts=sum(attempts_by_provider.values()) or 1,
        )

    # Also write each result to the import-side cache so a follow-up
    # ``import_asset(result_id=...)`` call can look up the license /
    # attribution without the LLM having to re-pass them. Best-effort —
    # see ``_store_result`` for failure modes.
    try:
        from open_edit.agent.tools.pyagent_import_asset import (
            _SEARCH_RESULT_CACHE_DIR,
            _store_result,
        )
        project_result_cache = (
            Path(project_path).expanduser().resolve()
            / ".open_edit" / "cache" / "search_results"
        )
        for r in payload.get("results", []):
            _store_result(_SEARCH_RESULT_CACHE_DIR, r)
            _store_result(project_result_cache, r)
    except Exception:
        # Never let cache writes crash the search.
        pass

    return payload
