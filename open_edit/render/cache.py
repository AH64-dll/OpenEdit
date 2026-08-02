"""Filesystem-backed render cache, keyed by the edit-graph hash.

Single hash authority: keys are derived from
``open_edit.ir.hash.compute_edit_graph_hash`` so render-cache decisions
never disagree with the kernel/serve job-dedup hash.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from open_edit.ir.hash import compute_edit_graph_hash

DEFAULT_TTL_SEC = 86400  # 24h
ENV_TTL = "OPEN_EDIT_RENDER_CACHE_TTL_SEC"


def canonical_json_hash(obj: Any) -> str:
    """Deprecated compatibility shim: use ``compute_edit_graph_hash``.

    Retained only because ``render/orchestrator.py`` (task 5.7) still
    imports this name; it returns the identical digest, so cache keys are
    already unified on the ir graph hash.
    """
    return compute_edit_graph_hash(obj)


def render_cache_key(
    graph_hash: str,
    profile_fingerprint: str,
    content_fingerprint: str = "",
) -> str:
    """Cache key = graph + profile + referenced-content identity.

    The ``|`` separator is sanitized to ``_`` because the key is used
    verbatim as a filename and ``|`` is forbidden on Windows.
    """
    parts = [graph_hash, profile_fingerprint]
    if content_fingerprint:
        parts.append(content_fingerprint)
    return "|".join(parts).replace("|", "_")


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cache_ttl_sec() -> int:
    """Freshness window from ``OPEN_EDIT_RENDER_CACHE_TTL_SEC`` (default 24h)."""
    raw = os.environ.get(ENV_TTL)
    if raw is None:
        return DEFAULT_TTL_SEC
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_TTL_SEC


class RenderCache:
    """Filesystem-backed render cache, keyed by hash."""

    def __init__(self, cache_dir: str | Path, *, max_age_sec: int | None = None):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_age_sec = max_age_sec

    def _cache_path(self, key: str, ext: str = "mp4") -> Path:
        return self.cache_dir / f"{key}.{ext}"

    def _metadata_path(self, key: str, ext: str = "mp4") -> Path:
        return self.cache_dir / ".meta" / f"{key}.{ext}.json"

    def get(self, key: str, ext: str = "mp4") -> Path | None:
        path = self._cache_path(key, ext)
        if not path.is_file():
            return None
        metadata_path = self._metadata_path(key, ext)
        if metadata_path.is_file():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                expected = str(metadata.get("source_hash") or "")
                if not expected or _file_hash(path) != expected:
                    return None
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                return None
        # Legacy cache entries without metadata remain readable; a new put
        # immediately upgrades them to content-verified entries.
        return path

    def put(self, key: str, source_path: str | Path, ext: str = "mp4") -> Path:
        """Atomically store a content-verified cache entry."""
        dest = self._cache_path(key, ext)
        source = Path(source_path)
        source_hash = _file_hash(source)
        metadata_path = self._metadata_path(key, ext)
        metadata = {
            "schema": 1,
            "key": key,
            "ext": ext,
            "source_hash": source_hash,
            "size_bytes": source.stat().st_size,
            "updated_at": time.time(),
        }
        try:
            if dest.is_file() and metadata_path.is_file():
                existing = json.loads(metadata_path.read_text(encoding="utf-8"))
                if existing.get("source_hash") == source_hash and _file_hash(dest) == source_hash:
                    return dest
            dest.parent.mkdir(parents=True, exist_ok=True)
            metadata_path.parent.mkdir(parents=True, exist_ok=True)
            temp_dest: Path | None = None
            with tempfile.NamedTemporaryFile(
                dir=dest.parent, prefix=f".{dest.name}.", delete=False,
            ) as tmp:
                temp_dest = Path(tmp.name)
            shutil.copyfile(source, temp_dest)
            os.replace(temp_dest, dest)
            temp_meta: Path | None = None
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=metadata_path.parent,
                prefix=f".{metadata_path.name}.", delete=False,
            ) as tmp:
                temp_meta = Path(tmp.name)
                json.dump(metadata, tmp, sort_keys=True)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(temp_meta, metadata_path)
        finally:
            for temp in (
                locals().get("temp_dest"),
                locals().get("temp_meta"),
            ):
                if isinstance(temp, Path):
                    try:
                        temp.unlink(missing_ok=True)
                    except OSError:
                        pass
        return dest

    def is_fresh(self, path: Path, max_age_sec: int | None = None) -> bool:
        """True if the file exists and is younger than max_age_sec."""
        if not path.exists():
            return False
        if max_age_sec is None:
            max_age_sec = self.max_age_sec
        if max_age_sec is None:
            max_age_sec = cache_ttl_sec()
        age = time.time() - path.stat().st_mtime
        return age < max_age_sec
