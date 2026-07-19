"""Render cache keyed by SHA-256 of canonical JSON of the edit graph."""
from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any, Optional


def canonical_json_hash(obj: Any) -> str:
    """SHA-256 of canonical JSON. Sorted keys, no whitespace, list-ordered."""
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class RenderCache:
    """Filesystem-backed render cache, keyed by hash."""

    DEFAULT_MAX_AGE_SEC = 3600  # 1 hour

    def __init__(self, cache_dir: str | Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.mp4"

    def get(self, key: str) -> Optional[Path]:
        path = self._cache_path(key)
        if path.exists():
            return path
        return None

    def put(self, key: str, source_path: str | Path) -> Path:
        """Copy `source_path` into the cache. Returns the destination path."""
        dest = self._cache_path(key)
        if not dest.exists():
            shutil.copy2(source_path, dest)
        return dest

    def is_fresh(self, path: Path, max_age_sec: Optional[int] = None) -> bool:
        """True if the file exists and is younger than max_age_sec."""
        if not path.exists():
            return False
        if max_age_sec is None:
            max_age_sec = self.DEFAULT_MAX_AGE_SEC
        age = time.time() - path.stat().st_mtime
        return age < max_age_sec
