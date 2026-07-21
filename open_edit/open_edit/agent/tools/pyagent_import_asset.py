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

import json
import os
import shutil
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

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
# Cap on how many bytes the importer will buffer. A 4-minute 1080p
# proxy is ~600MB; we cap higher (2GB) so most real downloads fit.
_MAX_DOWNLOAD_BYTES: int = 2 * 1024 * 1024 * 1024


# ---------------------------------------------------------------------------
# HTTP download
# ---------------------------------------------------------------------------

def _http_download(url: str, *, headers: dict[str, str] | None = None,
                   timeout: float = _HTTP_TIMEOUT_S) -> bytes:
    """Download ``url`` and return the raw bytes.

    Mirrors ``_http_get_json`` from ``pyagent_search_assets`` but for
    binary payloads. Raises ``RuntimeError`` with a useful message on
    HTTP error or network failure.
    """
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            data = resp.read()
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            detail = ""
        raise RuntimeError(
            f"download failed: upstream {exc.code} for {url}: "
            f"{detail or exc.reason}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"download failed: network error for {url}: {exc.reason}"
        ) from exc
    if status != 200:
        raise RuntimeError(f"download failed: HTTP {status} for {url}")
    if len(data) > _MAX_DOWNLOAD_BYTES:
        raise RuntimeError(
            f"download failed: {len(data)} bytes exceeds the {_MAX_DOWNLOAD_BYTES}-byte cap"
        )
    return data


# ---------------------------------------------------------------------------
# Search-result cache (lookup by result_id)
# ---------------------------------------------------------------------------

def _lookup_result(cache_dir: Path, result_id: str) -> dict[str, Any] | None:
    """Read a search result back from the cache by ``result_id``.

    Returns ``None`` if the id is unknown (which the import tool then
    surfaces as an error to the user — the LLM may have hallucinated
    a result id that wasn't in the search response).
    """
    p = cache_dir / f"{result_id}.json"
    if not p.exists():
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
    if not rid:
        return
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / f"{rid}.json").write_text(json.dumps(result))
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def import_asset(args: dict, project_path: str) -> dict:
    """Import a third-party media asset into the project's CAS.

    Args:
        args: ``{result_id?} | {source_url?}, license?, attribution?`` plus
            ``project_id`` (the bridge auto-injects this from
            ``EditGraphStore``, same as every other project-scoped tool).
        project_path: absolute path to the project folder.

    Returns:
        ``{status, asset_hash, source, license, attribution, ...}`` on
        success, or ``{error: "..."}`` on failure.
    """
    result_id = (args.get("result_id") or "").strip()
    source_url = (args.get("source_url") or "").strip()
    if not result_id and not source_url:
        return {
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
                "error": (
                    f"import_asset: cached search result {result_id!r} has "
                    f"no preview_url; cannot download."
                ),
            }

    if not source_url.lower().startswith("https://"):
        return {
            "error": (
                f"import_asset: source_url must be HTTPS (got {source_url!r}). "
                f"fix: use the secure URL — http:// is rejected to keep the "
                f"download integrity sane."
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
        data = _http_download(source_url)
    except Exception as exc:  # noqa: BLE001 — surface any download error
        return {
            "error": f"import_asset: {exc}",
        }

    if not data:
        return {
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
        assets_dir = Path(project_path) / ".open_edit" / "assets"
        store = AssetStore(assets_dir)
        try:
            assets = store.ingest_paths(
                [str(tmp_path)], license=license_str, attribution=attribution_str,
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "error": f"import_asset: ingest failed: {exc}",
            }
        asset = assets[0]
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass

    return {
        "status": "ingested",
        "asset_hash": asset.asset_hash,
        "source": source_name,
        "kind": asset.type,
        "license": license_str,
        "attribution": attribution_str,
        "filename": Path(asset.original_path).name,
        "duration_sec": asset.duration_sec,
    }
