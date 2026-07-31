"""Filesystem-backed render cache, keyed by the edit-graph hash.

Single hash authority: keys are derived from
``open_edit.ir.hash.compute_edit_graph_hash`` so render-cache decisions
never disagree with the kernel/serve job-dedup hash.
"""
from __future__ import annotations

import os
import shutil
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

    def get(self, key: str, ext: str = "mp4") -> Path | None:
        path = self._cache_path(key, ext)
        if path.exists():
            return path
        return None

    def put(self, key: str, source_path: str | Path, ext: str = "mp4") -> Path:
        """Copy `source_path` into the cache. Returns the destination path."""
        dest = self._cache_path(key, ext)
        if not dest.exists():
            shutil.copy2(source_path, dest)
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
