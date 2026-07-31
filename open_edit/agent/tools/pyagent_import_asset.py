"""pyagent_import_asset: download + ingest a third-party media asset.

Two entry shapes:
- ``result_id`` from a prior ``search_assets`` call (the search
  result is looked up in the in-process result cache so the LLM
  doesn't have to re-pass license/attribution).
- ``source_url`` for a direct download (license/attribution must be
  supplied by the caller, or defaults to empty strings).

The downloaded bytes are written to a temp file and then handed to
``AssetStore.ingest_paths`` — the same code path the upload route in
``serve/app.py`` uses for user-uploaded files. The asset is stored in
the project's CAS at ``.open_edit/assets/<prefix>/<hash>`` with a
``<hash>.meta.json`` sidecar carrying the license/attribution.

The ``project_path`` is REQUIRED (the asset is project-scoped); unlike
``search_assets``, this tool is mutating and must be scoped.

Environment
-----------
No new env vars — the upstream API key is the one used by the search
that produced the result_id, and a direct ``source_url`` is open
content (we still require HTTPS to be safe).
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from open_edit.agent.tools._contract import tool_result
from open_edit.storage.paths import ProjectPaths

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Where the in-process search-result cache lives. ``search_assets``
# writes one JSON per result here, ``import_asset`` reads from it.
# Default: a per-process temp dir so tests can override it cheaply.
_SEARCH_RESULT_CACHE_DIR: Path = Path(
    os.environ.get(
        "OPEN_EDIT_SEARCH_CACHE_DIR",
        str(Path(tempfile.gettempdir()) / "open_edit_search_cache"),
    )
)

_HTTP_TIMEOUT_S: float = 60.0
_DOWNLOAD_CHUNK_BYTES: int = 1024 * 1024
# Cap on how many bytes the importer will buffer. A 4-minute 1080p
# proxy is ~600MB; we cap higher (2GB) so most real downloads fit.
_MAX_DOWNLOAD_BYTES: int = 2 * 1024 * 1024 * 1024

_ALLOWED_HOST_SUFFIXES = (
    "pexels.com", "pexelsusercontent.com", "freesound.org",
    "openverse.org", "wordpress.com", "wordpress.org", "wp.com", "s.w.org",
    "wikimedia.org", "flickr.com", "staticflickr.com", "archive.org",
)
_SAFE_RESULT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,255}\Z")


def _is_private_or_local_host(hostname: str) -> bool:
    host = hostname.lower().rstrip(".")
    if host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
        return True
    if host.endswith(".local") or host.endswith(".internal"):
        return True
    # Block obvious link-local / private IPv4 literals.
    if host.startswith(("10.", "192.168.", "169.254.")):
        return True
    if host.startswith("172."):
        try:
            second = int(host.split(".")[1])
            if 16 <= second <= 31:
                return True
        except (IndexError, ValueError):
            pass
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
    )


def _is_allowed_source_url(url: str, *, allow_any_https: bool = False) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
        # Accessing ``port`` validates malformed port syntax before urlopen.
        parsed.port
    except (TypeError, ValueError):
        return False
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    host = parsed.hostname.lower().rstrip(".")
    if _is_private_or_local_host(host):
        return False
    if allow_any_https:
        return True
    return any(host == suffix or host.endswith(f".{suffix}")
               for suffix in _ALLOWED_HOST_SUFFIXES)


def _validate_resolved_host(url: str) -> None:
    """Reject DNS names that resolve to private or local addresses."""
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname
    if not host:
        raise RuntimeError("download failed: URL has no host")
    try:
        addresses = socket.getaddrinfo(
            host, parsed.port or 443, type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise RuntimeError("download failed: hostname lookup failed") from exc
    if not addresses or any(
        _is_private_or_local_host(info[4][0]) for info in addresses
    ):
        raise RuntimeError("download failed: host resolves to a private address")


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Validate every redirect before urllib opens the target."""

    def __init__(self, *, allow_any_https: bool) -> None:
        super().__init__()
        self._allow_any_https = allow_any_https

    def redirect_request(
        self, req, fp, code, msg, headers, newurl,
    ):
        target = urllib.parse.urljoin(req.full_url, newurl)
        if not _is_allowed_source_url(
            target, allow_any_https=self._allow_any_https,
        ):
            raise RuntimeError(
                "download failed: redirect target host is not an "
                "allowed media provider"
            )
        _validate_resolved_host(target)
        return super().redirect_request(
            req, fp, code, msg, headers, target,
        )


def _open_url(
    req: urllib.request.Request, *, timeout: float, allow_any_https: bool,
):
    _validate_resolved_host(req.full_url)
    opener = urllib.request.build_opener(
        _SafeRedirectHandler(allow_any_https=allow_any_https),
    )
    return opener.open(req, timeout=timeout)


def _http_download(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = _HTTP_TIMEOUT_S,
    allow_any_https: bool = False,
) -> bytes:
    """Download ``url`` and return the raw bytes.

    Validates HTTPS + allowlisted host on the initial URL and again on the
    final response URL (after redirects). Streams into a bounded buffer so
    oversized responses fail before exhausting memory.

    ``allow_any_https`` is used for cached Openverse results whose CDNs are
    not on the static provider suffix list (still blocks private/localhost).
    """
    if not _is_allowed_source_url(url, allow_any_https=allow_any_https):
        raise RuntimeError(
            "download failed: URL host is not an allowed media provider"
        )
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with _open_url(
            req, timeout=timeout, allow_any_https=allow_any_https,
        ) as resp:
            final_url = getattr(resp, "geturl", lambda: url)()
            if not _is_allowed_source_url(final_url, allow_any_https=allow_any_https):
                raise RuntimeError(
                    "download failed: redirect target host is not an "
                    "allowed media provider"
                )
            status = getattr(resp, "status", None) or resp.getcode()
            response_headers = getattr(resp, "headers", None)
            if response_headers is not None:
                try:
                    content_length = int(
                        response_headers.get("Content-Length", "")
                    )
                except (TypeError, ValueError):
                    content_length = None
                if content_length is not None and content_length > _MAX_DOWNLOAD_BYTES:
                    raise RuntimeError(
                        f"download failed: response exceeds the "
                        f"{_MAX_DOWNLOAD_BYTES}-byte cap"
                    )
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = resp.read(_DOWNLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > _MAX_DOWNLOAD_BYTES:
                    raise RuntimeError(
                        f"download failed: response exceeds the "
                        f"{_MAX_DOWNLOAD_BYTES}-byte cap"
                    )
                chunks.append(chunk)
            data = b"".join(chunks)
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            detail = ""
        raise RuntimeError(
            f"download failed: upstream {exc.code}: "
            f"{detail or exc.reason}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"download failed: network error: {exc.reason}"
        ) from exc
    if status != 200:
        raise RuntimeError(f"download failed: HTTP {status}")
    return data


# ---------------------------------------------------------------------------
# Search-result cache (lookup by result_id)
# ---------------------------------------------------------------------------

def _cache_result_path(cache_dir: Path, result_id: object) -> Path | None:
    """Return a cache path only for a safe, single filename component."""
    if not isinstance(result_id, str) or not _SAFE_RESULT_ID_RE.fullmatch(result_id):
        return None
    try:
        path = cache_dir / f"{result_id}.json"
        if path.resolve().parent != cache_dir.resolve():
            return None
        return path
    except OSError:
        return None


def _lookup_result(cache_dir: Path, result_id: str) -> dict[str, Any] | None:
    """Read a search result back from the cache by ``result_id``.

    Returns ``None`` if the id is unknown (which the import tool then
    surfaces as an error to the user — the LLM may have hallucinated
    a result id that wasn't in the search response).
    """
    p = _cache_result_path(cache_dir, result_id)
    if p is None or p.is_symlink() or not p.is_file():
        return None
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _store_result(cache_dir: Path, result: dict[str, Any]) -> None:
    """Persist a search result so ``import_asset`` can look it up later.

    Called by ``search_assets`` after a successful response. Best-effort —
    if the cache dir isn't writable we silently skip; the LLM can still
    call ``import_asset`` with a direct ``source_url`` instead.
    """
    rid = result.get("id")
    p = _cache_result_path(cache_dir, rid)
    if p is None:
        return
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=cache_dir,
                prefix=".result-", suffix=".tmp", delete=False,
            ) as tmp:
                tmp_path = Path(tmp.name)
                json.dump(result, tmp)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(tmp_path, p)
        finally:
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass
    except (OSError, TypeError, ValueError):
        pass


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

@tool_result
def import_asset(args: dict, project_path: str) -> dict:
    """Import a third-party media asset into the project's CAS.

    Args:
        args: ``{result_id?} | {source_url?}, license?, attribution?`` plus
            ``project_id`` (the bridge auto-injects this from
            ``EditGraphStore``, same as every other project-scoped tool).
        project_path: absolute path to the project folder.

    Returns:
        ``{status, asset_hash, source, license, attribution, ...}`` on
        success, or ``{status: "error", error: "..."}`` on failure.
    """
    result_id = (args.get("result_id") or "").strip()
    source_url = (args.get("source_url") or "").strip()
    if not result_id and not source_url:
        return {
            "status": "error",
            "error": (
                "import_asset: must provide either 'result_id' (from a prior "
                "search_assets call) or 'source_url' (direct HTTPS link)."
            ),
        }

    # Resolve the metadata: either from the search-result cache (preferred
    # — has license/attribution) or from the explicit ``source_url`` path.
    cached: dict[str, Any] | None = None
    if result_id:
        cached = _lookup_result(_SEARCH_RESULT_CACHE_DIR, result_id)
        if cached is None:
            return {
                "status": "error",
                "error": (
                    f"import_asset: result_id {result_id!r} not found in the "
                    f"search cache. The search_assets call that returned it "
                    f"may have expired — re-run the search and import a "
                    f"fresh result id."
                ),
            }
        # Use the cached preview_url as the actual download target so
        # the LLM can't pick a different file than the one the search
        # returned (which might be a different license).
        source_url = cached.get("preview_url") or ""
        if not source_url:
            return {
                "status": "error",
                "error": (
                    f"import_asset: cached search result {result_id!r} has "
                    f"no preview_url; cannot download."
                ),
            }

    allow_any_https = bool(cached and cached.get("source") == "openverse")
    if not _is_allowed_source_url(source_url, allow_any_https=allow_any_https):
        return {
            "status": "error",
            "error": (
                "import_asset: source_url must be HTTPS and from a known "
                "media provider host (or a cached Openverse result)."
            ),
        }

    # License/attribution resolution priority:
    # 1. Explicit args (caller-supplied, always wins).
    # 2. Cached search result (carries the license from the search).
    # 3. "Unknown" — better than an empty string in the UI; reminds
    #    the user they need to figure it out before publishing.
    license_str = (
        args.get("license")
        or (cached or {}).get("license")
        or "Unknown"
    )
    attribution_str = (
        args.get("attribution")
        or (cached or {}).get("attribution")
        or ""
    )
    source_name = (cached or {}).get("source") or "direct"

    # Download to a temp file so ``AssetStore.ingest_paths`` can hash it
    # (it needs an on-disk path, not raw bytes).
    try:
        data = _http_download(source_url, allow_any_https=allow_any_https)
    except Exception as exc:  # noqa: BLE001 — surface any download error
        return {
            "status": "error",
            "error": f"import_asset: {exc}",
        }

    if not data:
        return {
            "status": "error",
            "error": "import_asset: download returned 0 bytes — empty file",
        }

    # Sniff a sensible extension from the URL so the sidecar's
    # ``original_path`` is meaningful (the Asset's mime type then comes
    # from ffprobe, but the original filename is what the UI shows).
    parsed = urllib.parse.urlparse(source_url)
    ext = Path(parsed.path).suffix.lower() or ""
    if not ext:
        # Best-effort: match against known mime types.
        ext = ".bin"

    with tempfile.NamedTemporaryFile(
        prefix="open_edit_import_", suffix=ext, delete=False,
    ) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        # Hand off to the real AssetStore so the CAS + sidecar JSON
        # get written exactly the way the upload route does.
        from open_edit.storage.assets import AssetStore
        assets_dir = ProjectPaths.for_project(project_path).assets_dir
        store = AssetStore(assets_dir)
        try:
            assets = store.ingest_paths(
                [str(tmp_path)], license=license_str, attribution=attribution_str,
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "error",
                "error": f"import_asset: ingest failed: {exc}",
            }
        asset = assets[0]
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass

    return {
        "status": "ok",
        "result": "ingested",
        "asset_hash": asset.asset_hash,
        "source": source_name,
        "kind": asset.type,
        "license": license_str,
        "attribution": attribution_str,
        "filename": Path(asset.original_path).name,
        "duration_sec": asset.duration_sec,
    }
