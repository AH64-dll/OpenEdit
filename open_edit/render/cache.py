"""Filesystem-backed render cache, keyed by the edit-graph hash.

Single hash authority: keys are derived from
``open_edit.ir.hash.compute_edit_graph_hash`` so render-cache decisions
never disagree with the kernel/serve job-dedup hash.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from open_edit.ir.hash import compute_edit_graph_hash

DEFAULT_TTL_SEC = 86400  # 24h
ENV_TTL = "OPEN_EDIT_RENDER_CACHE_TTL_SEC"
DEFAULT_RENDER_CACHE_MAX_BYTES = 32 * 1024**3
DEFAULT_REMOTION_CACHE_MAX_BYTES = 512 * 1024**2
ENV_RENDER_CACHE_MAX_BYTES = "OPEN_EDIT_RENDER_CACHE_MAX_BYTES"
ENV_REMOTION_CACHE_MAX_BYTES = "OPEN_EDIT_REMOTION_CACHE_MAX_BYTES"

# Short aliases retain the naming style used by the existing TTL settings.
DEFAULT_MAX_BYTES = DEFAULT_RENDER_CACHE_MAX_BYTES
ENV_MAX_BYTES = ENV_RENDER_CACHE_MAX_BYTES
_CACHE_SIZE_RE = re.compile(r"^\s*(\d+)\s*(KiB|MiB|GiB)?\s*$", re.IGNORECASE)


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
    """Return a stable, filesystem-safe cache key under filename limits."""
    parts = [graph_hash, profile_fingerprint]
    if content_fingerprint:
        parts.append(content_fingerprint)
    raw = "|".join(parts).replace("|", "_")
    if len(raw) <= 180:
        return raw
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    markers: list[str] = []
    for marker in ("source_proxy_", "hyperframes=", "source-repair-", "emission="):
        match = re.search(rf"{re.escape(marker)}[^|]*", raw)
        if match:
            markers.append(match.group(0)[:36])
    readable = "_".join(markers)
    profile = profile_fingerprint.replace("|", "_")[:64]
    key = f"{graph_hash[:32]}_{profile}_{readable}_{digest}"
    return key[:180] if len(key) > 180 else key


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


def parse_cache_max_bytes(raw: str | None, default: int = DEFAULT_MAX_BYTES) -> int:
    """Parse a byte cap with optional binary-size suffix.

    Only integer byte counts and the explicitly supported ``KiB``, ``MiB``,
    and ``GiB`` suffixes are accepted. Invalid values use ``default`` so a
    malformed environment variable cannot disable cache bounds.
    """
    if raw is None:
        return default
    match = _CACHE_SIZE_RE.fullmatch(raw)
    if match is None:
        return default
    value = int(match.group(1))
    suffix = (match.group(2) or "").lower()
    multiplier = {
        "": 1,
        "kib": 1024,
        "mib": 1024**2,
        "gib": 1024**3,
    }[suffix]
    return value * multiplier


def cache_max_bytes(cache_dir: str | Path | None = None) -> int:
    """Return the configured cap for a render or Remotion cache.

    Remotion caches live below a path containing ``remotion`` and have a
    smaller conservative default. If only one of the two environment
    variables is set, it is accepted as a useful fallback for test and
    embedded callers that do not use the conventional directory layout.
    """
    is_remotion = (
        cache_dir is not None
        and any(part.lower() == "remotion" for part in Path(cache_dir).parts)
    )
    if is_remotion:
        preferred = (
            ENV_REMOTION_CACHE_MAX_BYTES,
            DEFAULT_REMOTION_CACHE_MAX_BYTES,
        )
        fallback = (ENV_RENDER_CACHE_MAX_BYTES, DEFAULT_RENDER_CACHE_MAX_BYTES)
    else:
        preferred = (ENV_RENDER_CACHE_MAX_BYTES, DEFAULT_RENDER_CACHE_MAX_BYTES)
        fallback = (
            ENV_REMOTION_CACHE_MAX_BYTES,
            DEFAULT_REMOTION_CACHE_MAX_BYTES,
        )

    for env_name, default in (preferred, fallback):
        raw = os.environ.get(env_name)
        if raw is not None:
            return parse_cache_max_bytes(raw, default)
    return preferred[1]


class RenderCache:
    """Filesystem-backed render cache, keyed by hash."""

    def __init__(
        self,
        cache_dir: str | Path,
        *,
        max_age_sec: int | None = None,
        max_bytes: int | None = None,
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_age_sec = max_age_sec
        if max_bytes is not None and max_bytes < 0:
            raise ValueError("max_bytes must be non-negative or None")
        self.max_bytes = (
            cache_max_bytes(self.cache_dir) if max_bytes is None else max_bytes
        )

    def _cache_path(self, key: str, ext: str = "mp4") -> Path:
        return self.cache_dir / f"{key}.{ext}"

    def _metadata_path(self, key: str, ext: str = "mp4") -> Path:
        return self.cache_dir / ".meta" / f"{key}.{ext}.json"

    def _metadata_path_for_artifact(self, path: Path) -> Path:
        return self.cache_dir / ".meta" / f"{path.name}.json"

    @staticmethod
    def _write_metadata(metadata_path: Path, metadata: dict[str, Any]) -> None:
        """Atomically write a metadata sidecar."""
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        temp_meta: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=metadata_path.parent,
                prefix=f".{metadata_path.name}.",
                delete=False,
            ) as tmp:
                temp_meta = Path(tmp.name)
                json.dump(metadata, tmp, sort_keys=True)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(temp_meta, metadata_path)
        finally:
            if temp_meta is not None:
                try:
                    temp_meta.unlink(missing_ok=True)
                except OSError:
                    pass

    def get(self, key: str, ext: str = "mp4") -> Path | None:
        path = self._cache_path(key, ext)
        if not path.is_file():
            return None
        metadata_path = self._metadata_path(key, ext)
        if metadata_path.is_file():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                if not isinstance(metadata, dict):
                    return None
                expected = str(metadata.get("source_hash") or "")
                if not expected or _file_hash(path) != expected:
                    return None
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                return None
            # Content verification completed. Refresh both access indicators
            # only after the hash check so tampered entries cannot stay hot.
            accessed_at = time.time()
            try:
                os.utime(path, (accessed_at, accessed_at))
                metadata["schema"] = 2
                metadata["size_bytes"] = path.stat().st_size
                if not isinstance(metadata.get("updated_at"), (int, float)):
                    metadata["updated_at"] = accessed_at
                metadata["last_accessed_at"] = accessed_at
                self._write_metadata(metadata_path, metadata)
            except OSError:
                # A verified artifact is still usable if its access metadata
                # cannot be refreshed (for example, a read-only cache mount).
                pass
            return path
        # Legacy cache entries without metadata remain readable; a new put
        # immediately upgrades them to content-verified entries.
        return path

    def put(
        self,
        key: str,
        source_path: str | Path,
        ext: str = "mp4",
        *,
        cache_class: str | None = None,
        mode: str | None = None,
    ) -> Path:
        """Atomically store a content-verified cache entry."""
        dest = self._cache_path(key, ext)
        source = Path(source_path)
        source_hash = _file_hash(source)
        metadata_path = self._metadata_path(key, ext)
        now = time.time()
        try:
            if dest.is_file() and metadata_path.is_file():
                try:
                    existing = json.loads(
                        metadata_path.read_text(encoding="utf-8")
                    )
                    if not isinstance(existing, dict):
                        raise TypeError("cache metadata must be an object")
                    existing_hash = existing.get("source_hash")
                    already_valid = (
                        existing_hash == source_hash
                        and _file_hash(dest) == source_hash
                    )
                except (OSError, TypeError, ValueError, json.JSONDecodeError):
                    already_valid = False
                    existing = {}
                if already_valid:
                    existing["schema"] = 2
                    existing["key"] = key
                    existing["ext"] = ext
                    existing["source_hash"] = source_hash
                    existing["size_bytes"] = dest.stat().st_size
                    existing.setdefault("updated_at", now)
                    existing["last_accessed_at"] = now
                    if cache_class is not None:
                        existing["cache_class"] = cache_class
                    if mode is not None:
                        existing["mode"] = mode
                    self._write_metadata(metadata_path, existing)
                    os.utime(dest, (now, now))
                    self.evict(protect=dest)
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
            metadata = {
                "schema": 2,
                "key": key,
                "ext": ext,
                "source_hash": source_hash,
                "size_bytes": dest.stat().st_size,
                "updated_at": now,
                "last_accessed_at": now,
            }
            if cache_class is not None:
                metadata["cache_class"] = cache_class
            if mode is not None:
                metadata["mode"] = mode
            self._write_metadata(metadata_path, metadata)
        finally:
            if "temp_dest" in locals() and temp_dest is not None:
                try:
                    temp_dest.unlink(missing_ok=True)
                except OSError:
                    pass
        self.evict(protect=dest)
        return dest

    def _last_accessed_at(self, path: Path) -> float:
        """Read an entry's LRU timestamp, falling back to artifact mtime."""
        metadata_path = self._metadata_path_for_artifact(path)
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if not isinstance(metadata, dict):
                raise TypeError("cache metadata must be an object")
            accessed_at = float(metadata.get("last_accessed_at"))
            if math.isfinite(accessed_at):
                return accessed_at
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            pass
        return path.stat().st_mtime

    def evict(self, protect: str | Path | None = None) -> int:
        """Remove least-recently-used artifacts until ``max_bytes`` is met.

        ``protect`` (an absolute artifact path) is exempt from eviction so a
        freshly stored entry is never deleted by its own ``put()``.
        """
        if self.max_bytes is None:
            return 0
        protected = str(Path(protect).resolve()) if protect is not None else None

        entries: list[tuple[float, int, Path]] = []
        total_bytes = 0
        for path in self.cache_dir.iterdir():
            if not path.is_file() or path.name.startswith("."):
                continue
            size = path.stat().st_size
            # A protected (just-written) entry still counts toward the cap so
            # the cap is honored globally, but it is never itself evicted.
            total_bytes += size
            if protected is not None and str(path.resolve()) == protected:
                continue
            entries.append((self._last_accessed_at(path), size, path))

        if total_bytes <= self.max_bytes:
            return 0

        deleted_bytes = 0
        for _, size, path in sorted(entries, key=lambda item: (item[0], item[2].name)):
            if total_bytes <= self.max_bytes:
                break
            try:
                path.unlink()
            except OSError:
                continue
            total_bytes -= size
            deleted_bytes += size
            try:
                self._metadata_path_for_artifact(path).unlink(missing_ok=True)
            except OSError:
                pass
        return deleted_bytes

    def remove(self, key: str, ext: str = "mp4") -> bool:
        """Remove one artifact and its metadata sidecar, if present."""
        path = self._cache_path(key, ext)
        removed = False
        try:
            path.unlink()
            removed = True
        except FileNotFoundError:
            pass
        except OSError:
            return False
        metadata_path = self._metadata_path(key, ext)
        try:
            metadata_path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass
        return removed

    def wipe(self) -> None:
        """Delete all cache artifacts, metadata, and stale temp files."""
        if not self.cache_dir.exists():
            return
        for path in self.cache_dir.iterdir():
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
            except OSError:
                pass

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
