"""Content-aware eviction for regenerable project media.

Canonical source CAS objects and their sidecars are never eviction
candidates.  Only derived source proxies, render/Remotion artifacts, and
orphaned temporary files are considered for cleanup.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from open_edit.render.cache import (
    DEFAULT_RENDER_CACHE_MAX_BYTES,
    DEFAULT_REMOTION_CACHE_MAX_BYTES,
    parse_cache_max_bytes,
)
from open_edit.storage.assets import AssetStore


DEFAULT_SOURCE_PROXY_MAX_BYTES = 1024**3
DEFAULT_CACHE_MAX_AGE_SEC = 86400
DEFAULT_CACHE_MIN_FREE_BYTES = 512 * 1024**2

ENV_RENDER_CACHE_MAX_BYTES = "OPEN_EDIT_RENDER_CACHE_MAX_BYTES"
ENV_REMOTION_CACHE_MAX_BYTES = "OPEN_EDIT_REMOTION_CACHE_MAX_BYTES"
ENV_SOURCE_PROXY_MAX_BYTES = "OPEN_EDIT_SOURCE_PROXY_MAX_BYTES"
ENV_CACHE_MAX_AGE_SEC = "OPEN_EDIT_CACHE_MAX_AGE_SEC"
ENV_CACHE_MIN_FREE_BYTES = "OPEN_EDIT_CACHE_MIN_FREE_BYTES"

_HASH_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_ORPHAN_SUFFIXES = (".audio.wav", ".repaired.mp4", ".melt.mp4")
_MODE_NAMES = {"final", "proxy", "overlay"}
_CLASS_ORDER = ("remotion", "render", "source_proxy", "temp")


@dataclass(frozen=True)
class CacheSettings:
    """Byte, age, and disk-pressure limits for derived project media."""

    render_cache_max_bytes: int
    remotion_cache_max_bytes: int
    source_proxy_max_bytes: int
    max_age_sec: int
    min_free_bytes: int

    @classmethod
    def from_env(cls) -> "CacheSettings":
        """Read cache limits, falling back safely for bad environment data."""
        return cls(
            render_cache_max_bytes=_positive_bytes(
                ENV_RENDER_CACHE_MAX_BYTES,
                DEFAULT_RENDER_CACHE_MAX_BYTES,
            ),
            remotion_cache_max_bytes=_positive_bytes(
                ENV_REMOTION_CACHE_MAX_BYTES,
                DEFAULT_REMOTION_CACHE_MAX_BYTES,
            ),
            source_proxy_max_bytes=_positive_bytes(
                ENV_SOURCE_PROXY_MAX_BYTES,
                DEFAULT_SOURCE_PROXY_MAX_BYTES,
            ),
            max_age_sec=_positive_integer(
                ENV_CACHE_MAX_AGE_SEC,
                DEFAULT_CACHE_MAX_AGE_SEC,
            ),
            min_free_bytes=_positive_bytes(
                ENV_CACHE_MIN_FREE_BYTES,
                DEFAULT_CACHE_MIN_FREE_BYTES,
            ),
        )


@dataclass(frozen=True)
class CacheEvictionReport:
    """Accounting for one best-effort project-cache enforcement pass."""

    inspected_bytes: int
    deleted_bytes: int
    deleted_paths: tuple[str, ...]
    protected_paths: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class _Candidate:
    path: Path
    cache_class: str
    size_bytes: int
    accessed_at: float
    mode: str | None = None
    metadata_path: Path | None = None
    source_refs: tuple[tuple[Path, str], ...] = ()
    content_verified: bool = True


def enforce_project_cache(
    project_path: Path,
    *,
    active_paths: Iterable[Path] = (),
    settings: CacheSettings | None = None,
) -> CacheEvictionReport:
    """Bound all expendable project caches without deleting source CAS."""
    project = Path(project_path).resolve()
    limits = settings or CacheSettings.from_env()
    warnings: list[str] = []
    protected: set[Path] = set()
    candidates: list[_Candidate] = []

    active = _normalise_active_paths(project, active_paths)
    protected.update(active)

    candidates.extend(_scan_render_cache(project, warnings))
    candidates.extend(_scan_remotion(project, warnings))
    source_candidates, source_protected = _scan_source_proxies(project, warnings)
    candidates.extend(source_candidates)
    protected.update(source_protected)
    candidates.extend(_scan_temporary_files(project, warnings))
    candidates = _deduplicate_candidates(candidates)

    for candidate in candidates:
        if _is_protected(candidate.path, protected):
            protected.add(candidate.path)
    _protect_newest_deliverables(candidates, protected)

    inspected_bytes = sum(candidate.size_bytes for candidate in candidates)
    deleted_bytes = 0
    deleted_paths: list[str] = []
    deleted_keys: set[Path] = set()

    class_caps = {
        "remotion": max(0, int(limits.remotion_cache_max_bytes)),
        "render": max(0, int(limits.render_cache_max_bytes)),
        "source_proxy": max(0, int(limits.source_proxy_max_bytes)),
    }
    now = time.time()
    for cache_class in _CLASS_ORDER:
        class_candidates = [
            candidate
            for candidate in candidates
            if candidate.cache_class == cache_class
        ]
        if not class_candidates:
            continue
        cap = class_caps.get(cache_class)
        _, class_bytes = _evict_class(
            class_candidates,
            cap=cap,
            max_age_sec=limits.max_age_sec,
            now=now,
            protected=protected,
            deleted_keys=deleted_keys,
            deleted_paths=deleted_paths,
            warnings=warnings,
        )
        deleted_bytes += class_bytes

    min_free_bytes = max(0, int(limits.min_free_bytes))
    if min_free_bytes > 0:
        deleted_bytes += _evict_for_disk_pressure(
            project,
            candidates,
            min_free_bytes=min_free_bytes,
            max_age_sec=limits.max_age_sec,
            now=now,
            protected=protected,
            deleted_keys=deleted_keys,
            deleted_paths=deleted_paths,
            warnings=warnings,
        )

    return CacheEvictionReport(
        inspected_bytes=inspected_bytes,
        deleted_bytes=deleted_bytes,
        deleted_paths=tuple(deleted_paths),
        protected_paths=tuple(sorted(str(path) for path in protected)),
        warnings=tuple(_unique_strings(warnings)),
    )


def _positive_bytes(env_name: str, default: int) -> int:
    raw = os.environ.get(env_name)
    if raw is None:
        return default
    parsed = parse_cache_max_bytes(raw, default=0)
    return parsed if parsed > 0 else default


def _positive_integer(env_name: str, default: int) -> int:
    raw = os.environ.get(env_name)
    if raw is None:
        return default
    try:
        parsed = int(raw.strip())
    except (AttributeError, TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _iter_files(root: Path, *, recursive: bool) -> Iterator[Path]:
    if not root.is_dir():
        return
    try:
        paths = root.rglob("*") if recursive else root.iterdir()
        for path in paths:
            try:
                if path.is_file() and not path.is_symlink():
                    yield path
            except OSError:
                continue
    except OSError:
        return


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stat_candidate(
    path: Path,
    *,
    cache_class: str,
    mode: str | None = None,
    metadata_path: Path | None = None,
    source_refs: tuple[tuple[Path, str], ...] = (),
    content_verified: bool = True,
) -> _Candidate | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    resolved = _safe_resolve(path)
    if resolved is None:
        return None
    return _Candidate(
        path=resolved,
        cache_class=cache_class,
        size_bytes=max(0, stat.st_size),
        accessed_at=_safe_mtime(path),
        mode=mode,
        metadata_path=metadata_path,
        source_refs=source_refs,
        content_verified=content_verified,
    )


def _safe_mtime(path: Path) -> float:
    try:
        value = float(path.stat().st_mtime)
        return value if math.isfinite(value) else 0.0
    except (OSError, TypeError, ValueError):
        return 0.0


def _safe_resolve(path: Path) -> Path | None:
    try:
        return path.resolve()
    except OSError:
        return None


def _scan_render_cache(
    project: Path,
    warnings: list[str],
) -> list[_Candidate]:
    open_edit = project / ".open_edit"
    candidates: list[_Candidate] = []
    cache_dir = open_edit / "render_cache"
    for path in _iter_files(cache_dir, recursive=False):
        candidate = _cache_candidate(
            path,
            cache_dir=cache_dir,
            cache_class="render",
            mode=None,
            warnings=warnings,
        )
        if candidate is not None:
            candidates.append(candidate)

    renders_dir = open_edit / "renders"
    for path in _iter_files(renders_dir, recursive=True):
        if _is_orphan_temp_name(path):
            continue
        candidate = _stat_candidate(
            path,
            cache_class="render",
            mode=_infer_mode(path),
        )
        if candidate is not None:
            candidates.append(candidate)

    # The host render path writes a successful staging artifact directly in
    # .open_edit before RenderCache copies it. Keep this bounded as well.
    if open_edit.is_dir():
        for path in _iter_files(open_edit, recursive=False):
            if (
                path.suffix.lower() in {".mp4", ".mov", ".webm"}
                and not _is_orphan_temp_name(path)
            ):
                candidate = _stat_candidate(
                    path,
                    cache_class="render",
                    mode=_infer_mode(path),
                )
                if candidate is not None:
                    candidates.append(candidate)
    return candidates


def _scan_remotion(
    project: Path,
    warnings: list[str],
) -> list[_Candidate]:
    out_dir = project / ".open_edit" / "remotion" / "out"
    candidates: list[_Candidate] = []
    for dirname, mode, recursive in (
        ("cache", None, False),
        ("proxy", "proxy", True),
        ("final", "final", True),
    ):
        directory = out_dir / dirname
        for path in _iter_files(directory, recursive=recursive):
            candidate = _cache_candidate(
                path,
                cache_dir=directory,
                cache_class="remotion",
                mode=mode or _infer_mode(path),
                warnings=warnings,
            ) if dirname == "cache" else _stat_candidate(
                path,
                cache_class="remotion",
                mode=mode,
            )
            if candidate is not None:
                candidates.append(candidate)
    return candidates


def _cache_candidate(
    path: Path,
    *,
    cache_dir: Path,
    cache_class: str,
    mode: str | None,
    warnings: list[str],
) -> _Candidate | None:
    metadata_path = cache_dir / ".meta" / f"{path.name}.json"
    payload: dict[str, Any] | None = None
    content_verified = True
    if metadata_path.is_file():
        try:
            raw = json.loads(metadata_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise TypeError("metadata must be an object")
            payload = raw
            expected = str(raw.get("source_hash") or "")
            if not expected or _file_hash(path) != expected:
                content_verified = False
                warnings.append(
                    f"cache content verification failed: {path}",
                )
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            content_verified = False
            warnings.append(f"cache metadata is invalid: {metadata_path}")

    accessed_at = _safe_mtime(path)
    if payload is not None:
        try:
            timestamp = float(payload.get("last_accessed_at"))
            if math.isfinite(timestamp):
                accessed_at = timestamp
        except (TypeError, ValueError):
            pass
        metadata_mode = payload.get("mode")
        if mode is None and isinstance(metadata_mode, str) and metadata_mode:
            mode = metadata_mode
    candidate = _stat_candidate(
        path,
        cache_class=cache_class,
        mode=mode or _infer_mode(path),
        metadata_path=metadata_path if metadata_path.is_file() else None,
        content_verified=content_verified,
    )
    if candidate is None:
        return None
    return _Candidate(
        path=candidate.path,
        cache_class=candidate.cache_class,
        size_bytes=candidate.size_bytes,
        accessed_at=accessed_at,
        mode=candidate.mode,
        metadata_path=candidate.metadata_path,
        source_refs=candidate.source_refs,
        content_verified=candidate.content_verified,
    )


def _scan_source_proxies(
    project: Path,
    warnings: list[str],
) -> tuple[list[_Candidate], set[Path]]:
    roots: list[Path] = []
    for root in (
        project / ".open_edit" / "assets",
        project / "assets",
    ):
        if root.is_dir() and root not in roots:
            roots.append(root)

    protected: set[Path] = set()
    references: dict[Path, set[tuple[Path, str]]] = {}
    canonical_paths: set[Path] = set()
    all_data_paths: set[Path] = set()
    for root in roots:
        for path in _iter_files(root, recursive=True):
            if not path.name.endswith(".meta.json"):
                resolved = _safe_resolve(path)
                if resolved is not None:
                    all_data_paths.add(resolved)
        for sidecar in _iter_files(root, recursive=True):
            if not sidecar.name.endswith(".meta.json"):
                continue
            resolved_sidecar = _safe_resolve(sidecar)
            if resolved_sidecar is None:
                warnings.append(f"unable to resolve asset sidecar: {sidecar}")
                continue
            sidecar = resolved_sidecar
            protected.add(sidecar)
            asset_hash = sidecar.name[: -len(".meta.json")]
            source_path = sidecar.with_name(asset_hash)
            if source_path.is_file():
                canonical_paths.add(source_path.resolve())
                protected.add(source_path.resolve())
            try:
                payload = json.loads(sidecar.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise TypeError("metadata must be an object")
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                warnings.append(f"asset sidecar is invalid: {sidecar}")
                continue

            stored_path = payload.get("stored_path")
            if isinstance(stored_path, str) and stored_path:
                stored = Path(stored_path)
                if not stored.is_absolute():
                    stored = project / stored
                try:
                    stored = stored.resolve()
                    stored.relative_to(root.resolve())
                except (OSError, ValueError):
                    stored = None
                if stored is not None and stored.is_file():
                    canonical_paths.add(stored)
                    protected.add(stored)

            proxy_hash = payload.get("proxy_hash")
            if not isinstance(proxy_hash, str) or not _HASH_RE.fullmatch(proxy_hash):
                continue
            proxy_path = _safe_resolve(root / proxy_hash[:2] / proxy_hash)
            if proxy_path is None:
                warnings.append(
                    f"unable to resolve source proxy path: {proxy_hash}",
                )
                continue
            if not proxy_path.is_file():
                continue
            proxy_sidecar = proxy_path.with_name(f"{proxy_hash}.meta.json")
            if proxy_path in canonical_paths or proxy_sidecar.is_file():
                protected.add(proxy_path)
                if proxy_sidecar.is_file():
                    protected.add(proxy_sidecar.resolve())
                warnings.append(
                    f"source proxy points at canonical CAS bytes: {proxy_path}",
                )
                continue
            references.setdefault(proxy_path, set()).add((root, asset_hash))

    candidates: list[_Candidate] = []
    for path, source_refs in references.items():
        candidate = _stat_candidate(
            path,
            cache_class="source_proxy",
            source_refs=tuple(sorted(source_refs, key=lambda item: (str(item[0]), item[1]))),
        )
        if candidate is not None:
            candidates.append(candidate)
    # Files without a sidecar or a source-proxy reference are deliberately
    # conservative: they may be canonical bytes whose metadata was lost.
    for path in all_data_paths:
        if path not in references or path in canonical_paths:
            protected.add(path)
    return candidates, protected


def _scan_temporary_files(
    project: Path,
    warnings: list[str],
) -> list[_Candidate]:
    del warnings
    open_edit = project / ".open_edit"
    tmp_dir = open_edit / "tmp"
    candidates: list[_Candidate] = []
    seen: set[Path] = set()
    for path in _iter_files(tmp_dir, recursive=True):
        candidate = _stat_candidate(path, cache_class="temp")
        if candidate is not None:
            candidates.append(candidate)
            seen.add(candidate.path)

    excluded = [
        open_edit / "assets",
        open_edit / "render_cache",
        open_edit / "remotion",
        open_edit / "renders",
    ]
    for path in _iter_files(open_edit, recursive=True):
        if path.resolve() in seen or not _is_orphan_temp_name(path):
            continue
        if any(_is_descendant(path, root) for root in excluded):
            continue
        candidate = _stat_candidate(path, cache_class="temp")
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def _is_orphan_temp_name(path: Path) -> bool:
    name = path.name.lower()
    if name.endswith(_ORPHAN_SUFFIXES):
        return True
    try:
        open_edit_index = max(
            index
            for index, part in enumerate(path.parts)
            if part == ".open_edit"
        )
        relevant_parts = path.parts[open_edit_index + 1 :]
    except ValueError:
        relevant_parts = path.parts[-3:]
    return any(
        part.lower() in {
            "tmp",
            "temp",
            "proxy-job",
            "proxy-jobs",
            "proxy_jobs",
            "asset-proxy-job",
            "asset-proxy-jobs",
            "asset_proxy_jobs",
            "source-proxy",
        }
        for part in relevant_parts
    )


def _infer_mode(path: Path) -> str | None:
    for part in reversed(path.parts):
        lowered = part.lower()
        if lowered in _MODE_NAMES:
            return lowered
    tokens = re.split(r"[^a-z0-9]+", path.stem.lower())
    for mode in ("final", "proxy", "overlay"):
        if mode in tokens:
            return mode
    return None


def _deduplicate_candidates(
    candidates: Iterable[_Candidate],
) -> list[_Candidate]:
    by_path: dict[Path, _Candidate] = {}
    for candidate in candidates:
        existing = by_path.get(candidate.path)
        if existing is None:
            by_path[candidate.path] = candidate
            continue
        if existing.cache_class == "temp" and candidate.cache_class != "temp":
            by_path[candidate.path] = candidate
    return list(by_path.values())


def _normalise_active_paths(
    project: Path,
    active_paths: Iterable[Path],
) -> set[Path]:
    normalised: set[Path] = set()
    for raw_path in active_paths:
        path = Path(raw_path)
        if not path.is_absolute():
            path = project / path
        try:
            resolved = path.resolve()
            resolved.relative_to(project)
        except (OSError, ValueError):
            continue
        normalised.add(resolved)
    return normalised


def _is_descendant(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except (OSError, ValueError):
        return False


def _is_protected(path: Path, protected: set[Path]) -> bool:
    resolved = _safe_resolve(path)
    if resolved is None:
        return True
    return any(
        resolved == item or _is_descendant(resolved, item)
        for item in protected
    )


def _protect_newest_deliverables(
    candidates: Iterable[_Candidate],
    protected: set[Path],
) -> None:
    deliverables = [
        candidate
        for candidate in candidates
        if candidate.cache_class in {"render", "remotion"}
        and candidate.content_verified
        and candidate.mode
    ]
    by_mode: dict[str, list[_Candidate]] = {}
    for candidate in deliverables:
        assert candidate.mode is not None
        by_mode.setdefault(candidate.mode, []).append(candidate)
    for entries in by_mode.values():
        newest = max(entries, key=lambda item: (item.accessed_at, str(item.path)))
        protected.add(newest.path)

    # Older host renders may not have mode metadata or a mode-bearing name.
    # Keep the newest such staging artifact as the successful-deliverable
    # fallback, while still allowing all older artifacts to be reclaimed.
    unknown = [
        candidate
        for candidate in candidates
        if candidate.cache_class == "render"
        and candidate.content_verified
        and candidate.mode is None
        and (
            candidate.path.parent.name == "renders"
            or candidate.path.name.startswith("project_")
        )
    ]
    if unknown:
        protected.add(max(
            unknown,
            key=lambda item: (item.accessed_at, str(item.path)),
        ).path)


def _is_stale(candidate: _Candidate, *, now: float, max_age_sec: int) -> bool:
    age_limit = max(0, int(max_age_sec))
    return now - candidate.accessed_at >= age_limit


def _ordered_for_eviction(
    candidates: Iterable[_Candidate],
    *,
    now: float,
    max_age_sec: int,
) -> list[_Candidate]:
    return sorted(
        candidates,
        key=lambda item: (
            not _is_stale(item, now=now, max_age_sec=max_age_sec),
            item.accessed_at,
            str(item.path),
        ),
    )


def _evict_class(
    candidates: list[_Candidate],
    *,
    cap: int | None,
    max_age_sec: int,
    now: float,
    protected: set[Path],
    deleted_keys: set[Path],
    deleted_paths: list[str],
    warnings: list[str],
) -> tuple[set[Path], int]:
    if not candidates:
        return set(), 0
    total = sum(candidate.size_bytes for candidate in candidates)
    removed: set[Path] = set()
    deleted_bytes = 0

    def remove(candidate: _Candidate) -> None:
        nonlocal total, deleted_bytes
        if candidate.path in deleted_keys or _is_protected(candidate.path, protected):
            return
        if not _delete_candidate(candidate, warnings):
            return
        deleted_keys.add(candidate.path)
        removed.add(candidate.path)
        total -= candidate.size_bytes
        deleted_bytes += candidate.size_bytes
        deleted_paths.append(str(candidate.path))

    ordered = _ordered_for_eviction(
        candidates,
        now=now,
        max_age_sec=max_age_sec,
    )
    for candidate in ordered:
        if _is_stale(candidate, now=now, max_age_sec=max_age_sec):
            remove(candidate)

    if cap is not None:
        for candidate in ordered:
            if total <= cap:
                break
            remove(candidate)
    return removed, deleted_bytes


def _evict_for_disk_pressure(
    project: Path,
    candidates: list[_Candidate],
    *,
    min_free_bytes: int,
    max_age_sec: int,
    now: float,
    protected: set[Path],
    deleted_keys: set[Path],
    deleted_paths: list[str],
    warnings: list[str],
) -> int:
    free = _disk_free(project, warnings)
    if free is None or free >= min_free_bytes:
        return 0
    class_priority = {name: index for index, name in enumerate(_CLASS_ORDER)}
    ordered = sorted(
        candidates,
        key=lambda item: (
            not _is_stale(item, now=now, max_age_sec=max_age_sec),
            class_priority.get(item.cache_class, len(_CLASS_ORDER)),
            item.accessed_at,
            str(item.path),
        ),
    )
    deleted_bytes = 0
    for candidate in ordered:
        if free >= min_free_bytes:
            break
        if candidate.path in deleted_keys or _is_protected(candidate.path, protected):
            continue
        if not _delete_candidate(candidate, warnings):
            continue
        deleted_keys.add(candidate.path)
        deleted_bytes += candidate.size_bytes
        deleted_paths.append(str(candidate.path))
        free = _disk_free(project, warnings)
        if free is None:
            break
    if free is not None and free < min_free_bytes:
        warnings.append(
            f"cache pressure remains below {min_free_bytes} free bytes",
        )
    return deleted_bytes


def _disk_free(project: Path, warnings: list[str]) -> int | None:
    try:
        return int(shutil.disk_usage(project).free)
    except OSError as exc:
        warnings.append(f"unable to inspect free disk space: {exc}")
        return None


def _delete_candidate(candidate: _Candidate, warnings: list[str]) -> bool:
    if candidate.cache_class == "source_proxy":
        for assets_root, asset_hash in candidate.source_refs:
            try:
                AssetStore(assets_root).clear_proxy_metadata(asset_hash)
            except Exception as exc:
                warnings.append(
                    f"cannot clear source-proxy reference for {candidate.path}: {exc}",
                )
                return False
    try:
        candidate.path.unlink()
    except FileNotFoundError:
        return False
    except OSError as exc:
        warnings.append(f"cannot delete cache entry {candidate.path}: {exc}")
        return False

    if candidate.metadata_path is not None:
        try:
            candidate.metadata_path.unlink(missing_ok=True)
        except OSError as exc:
            warnings.append(
                f"cannot delete cache metadata {candidate.metadata_path}: {exc}",
            )
    return True


def _unique_strings(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
