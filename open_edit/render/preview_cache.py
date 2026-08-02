"""Bounded, atomically published storage for timeline preview chunks.

Preview artifacts are written below a cache root and are addressable only by
IDs recorded in the local index.  A manifest is replaced only after its
referenced artifacts have been content-verified, so a failed render cannot
publish a partial green chunk.
"""
from __future__ import annotations

import errno
import hashlib
import json
import mimetypes
import os
import shutil
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal

from pydantic import ValidationError

from open_edit.render.cache import parse_cache_max_bytes
from open_edit.render.preview_manifest import (
    PreviewArtifact,
    PreviewChunk,
    PreviewManifest,
    PreviewPlaneState,
    effective_status,
)

PreviewPlane = Literal["video", "audio", "playback"]

DEFAULT_PREVIEW_CACHE_MAX_BYTES = 512 * 1024**2
DEFAULT_PREVIEW_CACHE_MAX_AGE_SEC = 7 * 24 * 60 * 60
DEFAULT_PREVIEW_CACHE_MIN_FREE_BYTES = 512 * 1024**2

ENV_PREVIEW_CACHE_MAX_BYTES = "OPEN_EDIT_PREVIEW_CACHE_MAX_BYTES"
ENV_PREVIEW_CACHE_MAX_AGE_SEC = "OPEN_EDIT_PREVIEW_CACHE_MAX_AGE_SEC"
ENV_CACHE_MIN_FREE_BYTES = "OPEN_EDIT_CACHE_MIN_FREE_BYTES"

_PLANES = frozenset({"video", "audio", "playback"})
_UNSET = object()


class PreviewCacheError(OSError):
    """A preview write was rejected before it could publish an artifact."""


def preview_cache_max_bytes(raw: str | None = None) -> int:
    """Return the configured preview byte cap.

    The parser accepts the same binary suffixes as the existing render cache.
    Invalid values fall back to the conservative 512 MiB default.
    """

    if raw is None:
        raw = os.environ.get(ENV_PREVIEW_CACHE_MAX_BYTES)
    return parse_cache_max_bytes(raw, default=DEFAULT_PREVIEW_CACHE_MAX_BYTES)


def preview_cache_max_age_sec(raw: str | None = None) -> int:
    """Return the configured preview artifact age limit."""

    if raw is None:
        raw = os.environ.get(ENV_PREVIEW_CACHE_MAX_AGE_SEC)
    if raw is None:
        return DEFAULT_PREVIEW_CACHE_MAX_AGE_SEC
    try:
        value = int(raw.strip())
    except (AttributeError, TypeError, ValueError):
        return DEFAULT_PREVIEW_CACHE_MAX_AGE_SEC
    return max(0, value)


def preview_cache_min_free_bytes(raw: str | None = None) -> int:
    """Return the minimum free-space reserve used by preview writes."""

    if raw is None:
        raw = os.environ.get(ENV_CACHE_MIN_FREE_BYTES)
    return parse_cache_max_bytes(raw, default=DEFAULT_PREVIEW_CACHE_MIN_FREE_BYTES)


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_component(value: str, *, name: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError(f"{name} must be a non-empty path component")
    if value in {".", ".."} or "/" in value or "\\" in value:
        raise ValueError(f"{name} must not contain path separators")
    windows_path = PureWindowsPath(value)
    if windows_path.is_absolute() or windows_path.drive:
        raise ValueError(f"{name} must not be an absolute path")
    return value


def _safe_relative_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("relative_path must be a non-empty relative path")
    if "\\" in value:
        raise ValueError("relative_path must use POSIX separators")
    posix_path = PurePosixPath(value)
    windows_path = PureWindowsPath(value)
    if (
        posix_path.is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or any(part == ".." for part in posix_path.parts)
    ):
        raise ValueError("relative_path must not escape the cache root")
    return value


def _normalise_suffix(suffix: str) -> str:
    if not isinstance(suffix, str):
        raise ValueError("suffix must be a string")
    extension = suffix.lstrip(".")
    return _safe_component(extension, name="suffix")


def _mime_for(plane: PreviewPlane, suffix: str) -> str:
    guessed, _ = mimetypes.guess_type(f"artifact.{suffix}")
    if guessed:
        return guessed
    if plane == "audio":
        return "audio/mp4"
    return "video/mp4"


class PreviewChunkCache:
    """Filesystem-backed preview artifact and manifest cache."""

    def __init__(
        self,
        root: Path,
        *,
        max_bytes: int | None = None,
        max_age_sec: int | None | object = _UNSET,
        min_free_bytes: int | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        for plane in _PLANES:
            (self.root / plane).mkdir(parents=True, exist_ok=True)
        (self.root / "tmp").mkdir(parents=True, exist_ok=True)

        resolved_max_bytes = (
            preview_cache_max_bytes() if max_bytes is None else max_bytes
        )
        if not isinstance(resolved_max_bytes, int) or resolved_max_bytes < 0:
            raise ValueError("max_bytes must be a non-negative integer")
        self.max_bytes = resolved_max_bytes

        if max_age_sec is _UNSET:
            resolved_max_age: int | None = preview_cache_max_age_sec()
        elif max_age_sec is None:
            resolved_max_age = None
        else:
            if not isinstance(max_age_sec, int) or max_age_sec < 0:
                raise ValueError("max_age_sec must be non-negative or None")
            resolved_max_age = max_age_sec
        self.max_age_sec = resolved_max_age

        resolved_min_free = (
            preview_cache_min_free_bytes()
            if min_free_bytes is None
            else min_free_bytes
        )
        if not isinstance(resolved_min_free, int) or resolved_min_free < 0:
            raise ValueError("min_free_bytes must be a non-negative integer")
        self.min_free_bytes = resolved_min_free

        self._index: dict[str, dict[str, Any]] = {}
        self._load_index()

    @property
    def manifest_path(self) -> Path:
        return self.root / "manifest.json"

    @property
    def index_path(self) -> Path:
        return self.root / ".artifact_index.json"

    def read_manifest(self) -> PreviewManifest | None:
        """Read and validate the last atomically published manifest."""

        try:
            payload = self.manifest_path.read_bytes()
            manifest = PreviewManifest.model_validate_json(payload)
        except (OSError, UnicodeDecodeError, ValidationError, ValueError):
            return None

        # Reconstruct an index when a cache was created before the durable
        # index was introduced.  Invalid or missing files remain unresolved.
        self._register_manifest_artifacts(manifest, persist=True)
        return manifest

    def write_manifest(self, manifest: PreviewManifest) -> None:
        """Validate and atomically replace ``manifest.json``."""

        try:
            validated = PreviewManifest.model_validate(manifest)
        except ValidationError:
            raise

        next_index = dict(self._index)
        for artifact in self._manifest_artifacts(validated):
            entry = self._entry_from_artifact(artifact)
            self._validate_artifact_file(artifact)
            previous = next_index.get(artifact.artifact_id)
            if (
                previous is not None
                and previous.get("relative_path") != artifact.relative_path
            ):
                raise ValueError(
                    f"artifact id is already bound to another path: "
                    f"{artifact.artifact_id}"
                )
            next_index[artifact.artifact_id] = entry

        payload = validated.model_dump_json().encode("utf-8")
        # Validate the exact bytes that are about to become visible.
        PreviewManifest.model_validate_json(payload)
        self._check_free_space(len(payload))
        self._write_index(next_index)
        try:
            self._atomic_write(
                self.manifest_path,
                payload,
                prefix="manifest.json.tmp",
            )
        except OSError:
            # The index may contain extra entries, but it cannot publish a
            # green chunk by itself. Restore the previous index when possible.
            try:
                self._write_index(self._index)
            except OSError:
                pass
            raise
        self._index = next_index

    def commit_artifact(
        self,
        *,
        plane: PreviewPlane,
        key: str,
        source: Path,
        suffix: str,
        graph_hash: str,
    ) -> PreviewArtifact:
        """Validate and atomically publish one non-empty preview artifact."""

        if plane not in _PLANES:
            raise ValueError(f"unsupported preview plane: {plane!r}")
        artifact_id = _safe_component(key, name="key")
        extension = _normalise_suffix(suffix)
        source_path = Path(source)
        try:
            source_stat = source_path.stat()
        except OSError as exc:
            raise ValueError(f"preview source is unavailable: {source_path}") from exc
        if not source_path.is_file():
            raise ValueError("preview source must be a regular file")
        if source_stat.st_size <= 0:
            raise ValueError("preview artifacts must not be empty")
        if source_stat.st_size > self.max_bytes:
            raise ValueError("preview artifact exceeds the cache byte cap")

        source_hash = _file_hash(source_path)
        relative_path = f"{plane}/{artifact_id}.{extension}"
        artifact = PreviewArtifact(
            artifact_id=artifact_id,
            relative_path=relative_path,
            mime=_mime_for(plane, extension),
            bytes=source_stat.st_size,
            sha256=source_hash,
            graph_hash=graph_hash,
            key=key,
        )
        destination = self._path_for_relative(relative_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._check_free_space(source_stat.st_size)

        previous_index = dict(self._index)
        next_index = dict(previous_index)
        next_index[artifact.artifact_id] = self._entry_from_artifact(artifact)
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=destination.parent,
                prefix=f".{destination.name}.tmp",
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                with source_path.open("rb") as source_handle:
                    shutil.copyfileobj(source_handle, handle)
                handle.flush()
                os.fsync(handle.fileno())

            # The source may have changed during the copy.  Never publish
            # bytes whose digest differs from the metadata being indexed.
            if (
                temp_path.stat().st_size != artifact.bytes
                or _file_hash(temp_path) != artifact.sha256
            ):
                raise ValueError("preview source changed during atomic copy")

            # Publish the index first.  Until the final rename, resolution
            # verifies the hash and therefore cannot expose a partial file.
            self._write_index(next_index)
            os.replace(temp_path, destination)
            temp_path = None
            self._fsync_directory(destination.parent)
        except OSError:
            try:
                self._write_index(previous_index)
            except OSError:
                pass
            raise
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass
        self._index = next_index
        return artifact

    def resolve_artifact(self, artifact_id: str) -> Path | None:
        """Resolve only an indexed, content-verified artifact ID."""

        if not isinstance(artifact_id, str):
            return None
        try:
            artifact_id = _safe_component(artifact_id, name="artifact_id")
        except ValueError:
            return None
        entry = self._index.get(artifact_id)
        if entry is None:
            self._load_index()
            entry = self._index.get(artifact_id)
        if entry is None:
            return None
        try:
            path = self._path_for_relative(str(entry["relative_path"]))
            if not path.is_file() or path.is_symlink():
                return None
            stat = path.stat()
            if stat.st_size <= 0 or stat.st_size != int(entry["bytes"]):
                return None
            if _file_hash(path) != str(entry["sha256"]):
                return None
        except (KeyError, OSError, TypeError, ValueError):
            return None
        return path

    def prune(self, manifest: PreviewManifest | None = None) -> dict[str, int]:
        """Evict expired/unreferenced artifacts while protecting live chunks."""

        live_manifest = manifest
        if live_manifest is None:
            live_manifest = self.read_manifest()
        elif not isinstance(live_manifest, PreviewManifest):
            live_manifest = PreviewManifest.model_validate(live_manifest)
        if live_manifest is not None:
            self._register_manifest_artifacts(live_manifest, persist=False)

        references = self._reference_map(live_manifest)
        current_ids = {
            artifact.artifact_id
            for state in references["current_states"]
            for artifact in self._state_artifacts(state, current=True)
        }
        fallback_ids = {
            artifact.artifact_id
            for state in references["fallback_states"]
            for artifact in self._state_artifacts(state, current=False)
        }

        result = {
            "removed_files": 0,
            "removed_bytes": 0,
            "cleared_fallbacks": 0,
            "remaining_bytes": 0,
        }
        now = time.time()
        files = list(self._artifact_files())
        sizes = {path: self._file_size(path) for path in files}
        total_bytes = sum(sizes.values())

        entry_ids_by_path: dict[str, set[str]] = {}
        for artifact_id, entry in self._index.items():
            relative_path = entry.get("relative_path")
            if isinstance(relative_path, str):
                entry_ids_by_path.setdefault(relative_path, set()).add(artifact_id)

        def remove_path(path: Path) -> None:
            nonlocal total_bytes
            size = sizes.get(path, self._file_size(path))
            try:
                path.unlink()
            except FileNotFoundError:
                return
            except OSError:
                return
            result["removed_files"] += 1
            result["removed_bytes"] += size
            total_bytes -= size
            relative = path.relative_to(self.root).as_posix()
            for artifact_id in entry_ids_by_path.get(relative, set()):
                self._index.pop(artifact_id, None)

        unreferenced: list[tuple[float, Path]] = []
        for path in files:
            relative = path.relative_to(self.root).as_posix()
            ids = entry_ids_by_path.get(relative, set())
            if ids & (current_ids | fallback_ids):
                continue
            unreferenced.append((self._access_time(path), path))

        # Expired and unreferenced files go first, followed by LRU entries
        # when the byte cap is still exceeded.
        expired = [
            item
            for item in unreferenced
            if self._is_expired(item[1], now=now)
        ]
        expired_paths = {path for _, path in expired}
        for _, path in sorted(expired, key=lambda item: (item[0], str(item[1]))):
            remove_path(path)
        for _, path in sorted(unreferenced, key=lambda item: (item[0], str(item[1]))):
            if total_bytes <= self.max_bytes:
                break
            if path not in expired_paths:
                remove_path(path)

        # Fallbacks are protected until the manifest is atomically rewritten
        # without them.  Current green artifacts are never cap victims.
        fallback_candidates: list[tuple[float, str, Path]] = []
        for artifact_id in fallback_ids - current_ids:
            entry = self._index.get(artifact_id)
            if entry is None:
                continue
            try:
                path = self._path_for_relative(str(entry["relative_path"]))
            except (TypeError, ValueError):
                continue
            if not path.is_file():
                continue
            fallback_candidates.append(
                (self._access_time(path), artifact_id, path)
            )
        fallback_candidates.sort(key=lambda item: (item[0], item[1]))

        clear_ids: set[str] = set()
        for _, artifact_id, path in fallback_candidates:
            if not self._is_expired(path, now=now) and total_bytes <= self.max_bytes:
                continue
            clear_ids.add(artifact_id)
            total_bytes -= sizes.get(path, self._file_size(path))
            if total_bytes <= self.max_bytes and not self._is_expired(
                path, now=now
            ):
                break

        if clear_ids and live_manifest is not None:
            updated_manifest, cleared_count = self._clear_fallbacks(
                live_manifest,
                clear_ids,
            )
            if cleared_count:
                self.write_manifest(updated_manifest)
                result["cleared_fallbacks"] = cleared_count
                live_manifest = updated_manifest
                for artifact_id in clear_ids:
                    entry = self._index.get(artifact_id)
                    if entry is None:
                        continue
                    try:
                        path = self._path_for_relative(str(entry["relative_path"]))
                    except (TypeError, ValueError):
                        continue
                    remove_path(path)

        # Temporary job directories are never part of a published manifest.
        for path in list(self._temporary_files()):
            remove_path(path)
        for directory in sorted(
            (path for path in (self.root / "tmp").rglob("*") if path.is_dir()),
            key=lambda item: len(item.parts),
            reverse=True,
        ):
            try:
                directory.rmdir()
            except OSError:
                pass

        result["remaining_bytes"] = sum(
            self._file_size(path) for path in self._artifact_files()
        )
        self._write_index(self._index)
        return result

    def wipe(self) -> dict[str, int]:
        """Remove preview artifacts, indexes, manifests, and temporary files."""

        result = {"removed_files": 0, "removed_bytes": 0}
        if not self.root.exists():
            self._index.clear()
            return result
        for path in sorted(
            self.root.rglob("*"),
            key=lambda item: len(item.parts),
            reverse=True,
        ):
            try:
                if path.is_symlink() or path.is_file():
                    result["removed_files"] += 1
                    try:
                        result["removed_bytes"] += path.stat().st_size
                    except OSError:
                        pass
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            except OSError:
                continue
        self._index.clear()
        return result

    def _load_index(self) -> None:
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
            artifacts = payload.get("artifacts", {})
            if not isinstance(artifacts, dict):
                return
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return
        loaded: dict[str, dict[str, Any]] = {}
        for artifact_id, entry in artifacts.items():
            if not isinstance(artifact_id, str) or not isinstance(entry, dict):
                continue
            try:
                _safe_component(artifact_id, name="artifact_id")
                relative_path = _safe_relative_path(
                    str(entry["relative_path"])
                )
                if relative_path.split("/", 1)[0] not in _PLANES:
                    continue
                loaded[artifact_id] = dict(entry)
            except (KeyError, TypeError, ValueError):
                continue
        self._index = loaded

    def _write_index(self, index: dict[str, dict[str, Any]]) -> None:
        payload = {
            "schema_version": 1,
            "artifacts": index,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self._check_free_space(len(encoded))
        self._atomic_write(
            self.index_path,
            encoded,
            prefix=".artifact_index.json.tmp",
        )

    @staticmethod
    def _atomic_write(path: Path, payload: bytes, *, prefix: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=path.parent,
                prefix=prefix,
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            temporary = None
            PreviewChunkCache._fsync_directory(path.parent)
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        try:
            descriptor = os.open(path, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(descriptor)
        except OSError:
            pass
        finally:
            os.close(descriptor)

    def _check_free_space(self, required_bytes: int) -> None:
        if self.min_free_bytes <= 0:
            return
        try:
            free_bytes = shutil.disk_usage(self.root).free
        except OSError as exc:
            raise PreviewCacheError(
                f"unable to inspect preview cache free space: {exc}"
            ) from exc
        if free_bytes < self.min_free_bytes + max(0, required_bytes):
            raise PreviewCacheError(
                errno.ENOSPC,
                "preview cache rejected: minimum free-space reserve is unavailable",
            )

    def _path_for_relative(self, relative_path: str) -> Path:
        relative_path = _safe_relative_path(relative_path)
        if relative_path.split("/", 1)[0] not in _PLANES:
            raise ValueError("artifact path must begin with a preview plane")
        root = self.root.resolve()
        candidate = (self.root / Path(*relative_path.split("/"))).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError("artifact path escapes the cache root") from exc
        return candidate

    def _entry_from_artifact(self, artifact: PreviewArtifact) -> dict[str, Any]:
        return artifact.model_dump(mode="json")

    def _validate_artifact_file(self, artifact: PreviewArtifact) -> Path:
        path = self._path_for_relative(artifact.relative_path)
        if path.is_symlink() or not path.is_file():
            raise ValueError(
                f"manifest references an unavailable artifact: "
                f"{artifact.artifact_id}"
            )
        stat = path.stat()
        if (
            stat.st_size <= 0
            or stat.st_size != artifact.bytes
            or _file_hash(path) != artifact.sha256
        ):
            raise ValueError(
                f"manifest references an invalid artifact: "
                f"{artifact.artifact_id}"
            )
        return path

    def _register_manifest_artifacts(
        self,
        manifest: PreviewManifest,
        *,
        persist: bool,
    ) -> None:
        changed = False
        for artifact in self._manifest_artifacts(manifest):
            try:
                self._validate_artifact_file(artifact)
            except (OSError, ValueError):
                continue
            previous = self._index.get(artifact.artifact_id)
            if previous is not None and (
                previous.get("relative_path") != artifact.relative_path
            ):
                continue
            entry = self._entry_from_artifact(artifact)
            if previous != entry:
                self._index[artifact.artifact_id] = entry
                changed = True
        if changed and persist:
            try:
                self._write_index(self._index)
            except OSError:
                pass

    @staticmethod
    def _manifest_artifacts(
        manifest: PreviewManifest,
    ) -> Iterator[PreviewArtifact]:
        for chunk in manifest.chunks:
            for state in (
                chunk.video,
                chunk.audio,
                chunk.playback,
            ):
                if state.current is not None:
                    yield state.current
                if state.fallback is not None:
                    yield state.fallback

    @staticmethod
    def _state_artifacts(
        state: PreviewPlaneState,
        *,
        current: bool,
    ) -> Iterator[PreviewArtifact]:
        artifact = state.current if current else state.fallback
        if artifact is not None:
            yield artifact

    @staticmethod
    def _reference_map(
        manifest: PreviewManifest | None,
    ) -> dict[str, list[PreviewPlaneState]]:
        if manifest is None:
            return {"current_states": [], "fallback_states": []}
        return {
            "current_states": [
                state
                for chunk in manifest.chunks
                for state in (chunk.video, chunk.audio, chunk.playback)
                if state.current is not None
            ],
            "fallback_states": [
                state
                for chunk in manifest.chunks
                for state in (chunk.video, chunk.audio, chunk.playback)
                if state.fallback is not None
            ],
        }

    def _artifact_files(self) -> Iterator[Path]:
        for plane in _PLANES:
            directory = self.root / plane
            if not directory.is_dir():
                continue
            try:
                paths = directory.rglob("*")
                for path in paths:
                    if path.is_file() and not path.is_symlink():
                        yield path
            except OSError:
                continue

    def _temporary_files(self) -> Iterator[Path]:
        directory = self.root / "tmp"
        if not directory.is_dir():
            return
        try:
            for path in directory.rglob("*"):
                if path.is_file() or path.is_symlink():
                    yield path
        except OSError:
            return

    @staticmethod
    def _file_size(path: Path) -> int:
        try:
            return max(0, path.stat().st_size)
        except OSError:
            return 0

    @staticmethod
    def _access_time(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    def _is_expired(self, path: Path, *, now: float) -> bool:
        if self.max_age_sec is None:
            return False
        return now - self._access_time(path) >= self.max_age_sec

    def _clear_fallbacks(
        self,
        manifest: PreviewManifest,
        artifact_ids: set[str],
    ) -> tuple[PreviewManifest, int]:
        cleared = 0
        chunks: list[PreviewChunk] = []
        for chunk in manifest.chunks:
            states: list[PreviewPlaneState] = []
            chunk_changed = False
            for state in (chunk.video, chunk.audio, chunk.playback):
                if state.fallback is None or state.fallback.artifact_id not in artifact_ids:
                    states.append(state)
                    continue
                cleared += 1
                chunk_changed = True
                states.append(
                    state.model_copy(
                        update={
                            "fallback": None,
                            "status": "green" if state.current is not None else "red",
                        }
                    )
                )
            if chunk_changed:
                updated_chunk = chunk.model_copy(
                    update={
                        "video": states[0],
                        "audio": states[1],
                        "playback": states[2],
                    }
                )
                updated_chunk = updated_chunk.model_copy(
                    update={"status": effective_status(updated_chunk)}
                )
                chunks.append(updated_chunk)
            else:
                chunks.append(chunk)
        return manifest.model_copy(update={"chunks": chunks}), cleared


__all__ = [
    "DEFAULT_PREVIEW_CACHE_MAX_AGE_SEC",
    "DEFAULT_PREVIEW_CACHE_MAX_BYTES",
    "DEFAULT_PREVIEW_CACHE_MIN_FREE_BYTES",
    "ENV_CACHE_MIN_FREE_BYTES",
    "ENV_PREVIEW_CACHE_MAX_AGE_SEC",
    "ENV_PREVIEW_CACHE_MAX_BYTES",
    "PreviewCacheError",
    "PreviewChunkCache",
    "preview_cache_max_age_sec",
    "preview_cache_max_bytes",
    "preview_cache_min_free_bytes",
]
